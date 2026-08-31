"""Live execution loop: AI decide() → risk → resolve contract → submit / dry-run."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Any

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AI = os.path.join(_ROOT, "ai")
for _path in (_ROOT, _AI):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from agents.orchestrator import decide as ai_decide
from agents.schema import TRACE_EXECUTION, TRACE_RISK_MANAGER

from trading.mcp_cli import MCPLogAdapter
from trading.option_chain import OptionChainResolver
from trading.risk import LIVE_STRATEGIES, OptionRiskGate


def _account_for_ai(account: dict[str, Any]) -> dict[str, Any]:
    return {
        "equity": float(account.get("equity") or account.get("portfolio_value") or 0.0),
        "cash": float(account.get("cash") or 0.0),
        "buying_power": float(account.get("buying_power") or account.get("cash") or 0.0),
        "open_positions": int(account.get("open_positions") or 0),
        "shares": float(account.get("shares") or 0.0),
        "positions": account.get("positions") or [],
    }


class ExecutionLoop:
    """Connects the AI TradeDecision contract to Alpaca paper execution."""

    def __init__(
        self,
        broker: Any = None,
        resolver: OptionChainResolver | None = None,
        gate: OptionRiskGate | None = None,
        submit: bool = False,
        use_llm: bool = False,
        live: bool | None = None,
    ):
        self.broker = broker
        if live is None:
            live = bool(submit and broker is not None)
        self.resolver = resolver or OptionChainResolver(live=bool(live))
        self.gate = gate or OptionRiskGate()
        self.submit = bool(submit)
        self.use_llm = bool(use_llm)
        self.trace: list[dict[str, Any]] = []
        self.mcp = MCPLogAdapter()

    def decide(self, symbol: str, market: dict[str, Any], account: dict[str, Any]) -> dict[str, Any]:
        market = dict(market or {})
        market["symbol"] = str(market.get("symbol") or symbol).upper()
        iv_rank = market.get("iv_rank")
        decision = ai_decide(market, _account_for_ai(account), iv_rank, use_llm=self.use_llm)
        decision["timestamp"] = datetime.now(timezone.utc).isoformat()
        self.mcp.log_call("decide", {
            "symbol": decision.get("symbol"),
            "action": decision.get("action"),
            "strategy_type": decision.get("strategy_type"),
        })
        self.trace.append({"type": "decision", **decision})
        return decision

    def run_cycle(
        self,
        symbol: str,
        market: dict[str, Any],
        account: dict[str, Any],
        positions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        decision = self.decide(symbol, market, account)
        stages = list(decision.get("agent_trace") or [])

        if decision.get("action") != "OPEN":
            self.mcp.log_call("hold_cycle", {"symbol": symbol, "reason": decision.get("reason")})
            self.trace.append({"type": "hold", "symbol": symbol, "reason": decision.get("reason")})
            stages.append(TRACE_RISK_MANAGER)
            decision["agent_trace"] = stages
            return {"status": "hold", "decision": decision}

        strategy = str(decision.get("strategy_type") or "NONE").upper()
        side = "put" if strategy in {"CASH_SECURED_PUT", "BEAR_PUT_SPREAD", "LONG_PUT"} else "call"
        order_side = "sell" if strategy in {"CASH_SECURED_PUT", "COVERED_CALL"} else "buy"

        option_plan = self.resolver.resolve_contract(
            symbol=str(decision.get("symbol") or symbol),
            stock_price=float(market.get("price") or market.get("close") or 0.0),
            target_delta=float(decision.get("target_delta") or 0.25),
            target_dte=int(decision.get("target_dte") or 21),
            side=side,
            quantity=int(decision.get("contracts") or 1),
            strategy=strategy,
        )

        ok, reason = self.gate.evaluate(option_plan, account, positions)
        stages.append(TRACE_RISK_MANAGER)
        decision["agent_trace"] = stages
        if not ok:
            self.mcp.log_call("risk_block", {"symbol": symbol, "reason": reason, "plan": option_plan})
            self.trace.append({"type": "risk_block", "symbol": symbol, "reason": reason})
            return {"status": "blocked", "reason": reason, "plan": option_plan, "decision": decision}

        if strategy not in LIVE_STRATEGIES:
            self.mcp.log_call("unsupported_strategy", {"strategy": strategy})
            return {
                "status": "unsupported_strategy",
                "reason": f"{strategy} is not in the live submit path yet.",
                "plan": option_plan,
                "decision": decision,
            }

        if not self.submit or self.broker is None:
            stages.append(TRACE_EXECUTION)
            decision["agent_trace"] = stages
            self.mcp.log_call("dry_run", {"option_symbol": option_plan.get("option_symbol")})
            self.trace.append({"type": "dry_run", "plan": option_plan})
            return {
                "status": "dry_run",
                "symbol": option_plan.get("symbol"),
                "option_symbol": option_plan.get("option_symbol"),
                "order_side": order_side,
                "decision": decision,
                "plan": option_plan,
            }

        try:
            self.mcp.log_call("broker_submit", {
                "symbol": symbol,
                "option_symbol": option_plan.get("option_symbol"),
            })
            if self.mcp.cli_available():
                self.mcp.run_cli(["account"])
            response = self.broker.submit_option_order(
                symbol=symbol,
                side=order_side,
                qty=float(option_plan.get("quantity") or 1.0),
                option_symbol=option_plan.get("option_symbol"),
            )
            stages.append(TRACE_EXECUTION)
            decision["agent_trace"] = stages
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
            self.mcp.log_call("submit_error", {"symbol": symbol, "error": type(exc).__name__})
            self.trace.append({"type": "submit_error", "symbol": symbol, "error": type(exc).__name__})
            return {"status": "error", "error": type(exc).__name__, "decision": decision, "plan": option_plan}
