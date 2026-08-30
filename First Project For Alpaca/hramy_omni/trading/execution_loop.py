"""Live execution loop: market data → decide() → risk checks → submit → log."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from trading.agent_loop import AutonomousAgentLoop
from trading.mcp_cli import MCPLogAdapter
from trading.option_chain import OptionChainResolver
from trading.risk import OptionRiskGate


class ExecutionLoop:
    """Minimal execution engine for a cash-secured put flow."""

    def __init__(self, broker: Any, resolver: OptionChainResolver | None = None, gate: OptionRiskGate | None = None):
        self.broker = broker
        self.resolver = resolver or OptionChainResolver()
        self.gate = gate or OptionRiskGate()
        self.agent = AutonomousAgentLoop()
        self.trace: list[dict[str, Any]] = []
        self.mcp = MCPLogAdapter()

    def decide(self, symbol: str, market: dict[str, Any], account: dict[str, Any]) -> dict[str, Any]:
        signal = str(market.get("signal") or "neutral").lower()
        confidence = float(market.get("confidence") or 0.0)
        context = {
            "symbol": symbol,
            "signal": signal,
            "confidence": confidence,
            "cash": float(account.get("cash") or 0.0),
            "shares": float(account.get("shares") or 0.0),
            "equity": float(account.get("equity") or account.get("portfolio_value") or 0.0),
        }
        decision = self.agent.run_once(context)
        decision["timestamp"] = datetime.now(timezone.utc).isoformat()
        self.mcp.log_call("decide", {"symbol": symbol, "decision": decision})
        self.trace.append({"type": "decision", **decision})
        return decision

    def run_cycle(self, symbol: str, market: dict[str, Any], account: dict[str, Any], positions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        decision = self.decide(symbol, market, account)
        if decision.get("decision") == "HOLD":
            self.mcp.log_call("hold_cycle", {"symbol": symbol, "reason": decision.get("reason")})
            self.trace.append({"type": "hold", "symbol": symbol, "reason": decision.get("reason")})
            return {"status": "hold", "decision": decision}

        option_plan = self.resolver.resolve_contract(
            symbol=symbol,
            stock_price=float(market.get("price") or market.get("close") or 0.0),
            target_delta=float(market.get("target_delta") or 0.20),
            target_dte=int(market.get("target_dte") or 30),
            side="put",
        )

        ok, reason = self.gate.evaluate(option_plan, account, positions)
        if not ok:
            self.mcp.log_call("risk_block", {"symbol": symbol, "reason": reason, "plan": option_plan})
            self.trace.append({"type": "risk_block", "symbol": symbol, "reason": reason})
            return {"status": "blocked", "reason": reason, "plan": option_plan, "decision": decision}

        try:
            if self.broker is None:
                raise RuntimeError("Broker client is not configured.")
            self.mcp.log_call("broker_submit", {"symbol": symbol, "option_symbol": option_plan.get("option_symbol")})
            response = self.broker.submit_option_order(
                symbol=symbol,
                side="sell",
                qty=float(option_plan.get("quantity") or 1.0),
                option_symbol=option_plan.get("option_symbol"),
            )
            record = {
                "status": "submitted",
                "symbol": symbol,
                "option_symbol": option_plan.get("option_symbol"),
                "response": response,
                "decision": decision,
                "plan": option_plan,
                "logged_at": datetime.now(timezone.utc).isoformat(),
            }
            self.trace.append({"type": "submit", **record})
            return record
        except Exception as exc:
            self.mcp.log_call("submit_error", {"symbol": symbol, "error": str(exc)})
            self.trace.append({"type": "submit_error", "symbol": symbol, "error": str(exc)})
            return {"status": "error", "error": str(exc), "decision": decision, "plan": option_plan}
