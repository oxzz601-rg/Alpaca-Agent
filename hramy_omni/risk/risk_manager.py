"""
HRAMY OMNI AI - Risk Manager
============================================================
Deterministic risk layer between the AI engine and the simulator.

Architecture (the AI can NEVER bypass this):
    Market Data -> Indicators -> Quant Signals -> Groq AI
        -> RISK MANAGER (this module) -> Position Sizing -> Paper Simulator

The risk manager:
    - clamps AI-proposed position size / stop / take-profit to policy bands
    - converts AI percentages into a concrete execution plan
      (fractional quantity, stop price, target price, notional)
    - OVERRIDES BUY->HOLD and SELL->HOLD when rules are violated

Checks:
    1. AI confidence >= threshold
    2. AI risk level != HIGH
    3. BUY exposure <= max position percent AND portfolio exposure cap
    4. Cash available for the simulated buy
    5. Conflicting technical signals
    6. Open position required for SELL
    7. Stop-loss / take-profit geometry is sane (risk-reward floor)

This module is purely deterministic - NO LLM involvement.
"""

import os
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    AI_CONFIDENCE_THRESHOLD,
    MAX_POSITION_PERCENT,
    MAX_PORTFOLIO_EXPOSURE,
    MIN_RISK_REWARD_RATIO,
    RISK_PER_TRADE,
    STOP_LOSS_MAX_PCT,
    STOP_LOSS_MIN_PCT,
    TAKE_PROFIT_MAX_PCT,
    TAKE_PROFIT_MIN_PCT,
)


@dataclass
class ExecutionPlan:
    """Concrete, risk-approved trade plan produced from an AI decision."""
    action: str                    # BUY | SELL | HOLD
    quantity: float = 0.0          # fractional shares
    entry_price: float = 0.0
    stop_price: float = 0.0
    target_price: float = 0.0
    notional_value: float = 0.0
    position_size_percent: float = 0.0   # of equity actually used
    stop_loss_percent: float = 0.0
    take_profit_percent: float = 0.0
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "quantity": round(self.quantity, 6),
            "entry_price": round(self.entry_price, 4),
            "stop_price": round(self.stop_price, 4),
            "target_price": round(self.target_price, 4),
            "notional_value": round(self.notional_value, 2),
            "position_size_percent": round(self.position_size_percent, 2),
            "stop_loss_percent": round(self.stop_loss_percent, 2),
            "take_profit_percent": round(self.take_profit_percent, 2),
            "notes": self.notes,
        }


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class RiskManager:
    """Deterministic, rule-based risk manager."""

    def __init__(
        self,
        confidence_threshold: float = AI_CONFIDENCE_THRESHOLD,
        max_position_percent: float = MAX_POSITION_PERCENT,
        max_exposure_percent: float = MAX_PORTFOLIO_EXPOSURE,
        risk_per_trade: float = RISK_PER_TRADE,
        stop_min: float = STOP_LOSS_MIN_PCT,
        stop_max: float = STOP_LOSS_MAX_PCT,
        target_min: float = TAKE_PROFIT_MIN_PCT,
        target_max: float = TAKE_PROFIT_MAX_PCT,
        min_rr: float = MIN_RISK_REWARD_RATIO,
    ):
        self.confidence_threshold = confidence_threshold
        self.max_position_percent = max_position_percent
        self.max_exposure_percent = max_exposure_percent
        self.risk_per_trade = risk_per_trade
        self.stop_min = stop_min
        self.stop_max = stop_max
        self.target_min = target_min
        self.target_max = target_max
        self.min_rr = min_rr

    # ----------------------------------------------------------
    # Core gate evaluation (BUY / SELL / HOLD allowed or blocked)
    # ----------------------------------------------------------
    def evaluate(
        self,
        decision: str,
        ai: dict,
        price: float,
        account: dict,
        market: dict,
    ) -> tuple:
        """
        Evaluate an AI decision against risk rules.

        Returns (allowed: bool, status: str, reason: str).
        """
        confidence = ai.get("confidence", 0.0)
        ai_risk = ai.get("risk", "HIGH")

        if decision == "HOLD":
            return True, "PASSED", "AI decided HOLD — no execution needed."

        # 1. Confidence threshold -------------------------------------
        if confidence < self.confidence_threshold:
            return False, "BLOCKED", (
                f"AI confidence ({confidence:.0%}) is below the required "
                f"threshold ({self.confidence_threshold:.0%})."
            )

        # 2. High-risk rejection --------------------------------------
        if ai_risk == "HIGH":
            return False, "BLOCKED", "AI assessed this trade as HIGH risk."

        shares = float(account.get("shares", 0) or 0)
        cash = float(account.get("cash", 0) or 0)
        equity = float(account.get("equity", cash) or 0)

        # 3. Exposure caps for BUY ------------------------------------
        if decision == "BUY":
            requested_pct = _clamp(
                ai.get("position_size_percent", 5.0) / 100.0,
                0.0, self.max_position_percent,
            )
            current_exposure = (shares * price) / equity if equity > 0 else 1.0
            if current_exposure + requested_pct > self.max_exposure_percent + 1e-9:
                return False, "BLOCKED", (
                    f"Adding {requested_pct:.0%} would push exposure above the "
                    f"{self.max_exposure_percent:.0%} cap "
                    f"(currently {current_exposure:.0%})."
                )
            required_cash = equity * requested_pct
            if cash < required_cash:
                return False, "BLOCKED", (
                    f"Insufficient simulated cash (${cash:,.2f}) for the "
                    f"proposed ${required_cash:,.2f} position."
                )

        # 4. Conflicting technical signals -----------------------------
        if decision == "BUY":
            if market.get("momentum_signal") == "NEGATIVE" and market.get("trend") == "BEARISH":
                return False, "BLOCKED", (
                    "Conflicting signals: BUY requested while trend is bearish "
                    "and momentum is negative."
                )
            if market.get("regime") == "BEAR_TREND":
                return False, "BLOCKED", "BUY blocked: detected regime is BEAR_TREND."

        if decision == "SELL":
            if shares <= 0:
                return False, "BLOCKED", "No open position to sell."
            if market.get("trend") == "BULLISH" and market.get("momentum_signal") == "POSITIVE":
                return False, "BLOCKED", (
                    "Conflicting signals: SELL requested while trend is bullish "
                    "and momentum is positive."
                )

        return True, "PASSED", "All risk checks passed."


    # ----------------------------------------------------------
    # Execution plan builder (sizing + stops, all deterministic)
    # ----------------------------------------------------------
    def build_execution_plan(
        self,
        decision: str,
        ai: dict,
        price: float,
        account: dict,
        market: dict | None = None,
    ) -> ExecutionPlan:
        """
        Convert an AI decision into a risk-approved execution plan.

        Position sizing combines:
            - AI-proposed size (clamped to max position percent)
            - volatility-aware risk sizing via stop distance
        The SMALLER of the two governs (conservative by design).
        """
        plan = ExecutionPlan(action="HOLD", entry_price=price)

        allowed, status, reason = self.evaluate(decision, ai, price, account, market or {})
        if not allowed or decision == "HOLD":
            plan.notes.append(reason)
            return plan

        shares_held = float(account.get("shares", 0) or 0)
        cash = float(account.get("cash", 0) or 0)
        equity = float(account.get("equity", cash) or 0)

        # ---- Stop / take-profit distances (AI proposal, clamped) ----
        atr_pct = (market or {}).get("atr_pct")
        atr_floor = (float(atr_pct) / 100.0 * 1.2) if atr_pct else self.stop_min
        atr_floor = _clamp(atr_floor, self.stop_min, self.stop_max)

        stop_pct = _clamp(
            ai.get("stop_loss_percent", 2.5) / 100.0,
            max(self.stop_min, atr_floor),
            self.stop_max,
        )
        target_pct = _clamp(
            ai.get("take_profit_percent", stop_pct * 2) / 100.0,
            self.target_min,
            self.target_max,
        )

        # Enforce minimum risk-reward geometry.
        if target_pct < stop_pct * self.min_rr:
            target_pct = _clamp(stop_pct * self.min_rr, self.target_min, self.target_max)
            plan.notes.append(
                f"Take-profit widened to {target_pct:.1%} to keep R:R >= {self.min_rr}."
            )

        if decision == "SELL":
            qty = shares_held  # exit the full position
            plan.action = "SELL"
            plan.quantity = qty
            plan.notional_value = qty * price
            plan.position_size_percent = (qty * price / equity * 100) if equity else 0.0
            plan.stop_price = price * (1 + stop_pct)
            plan.target_price = price * (1 - target_pct)
            plan.stop_loss_percent = stop_pct * 100
            plan.take_profit_percent = target_pct * 100
            plan.notes.append("SELL exits the entire open position.")
            return plan

        # ---- BUY sizing ----
        ai_size_pct = _clamp(
            ai.get("position_size_percent", 5.0) / 100.0,
            0.0, self.max_position_percent,
        )

        # Volatility-aware alternative: risk a fixed fraction of equity
        # across the stop distance.
        risk_based_qty = (
            (equity * self.risk_per_trade) / (price * stop_pct)
            if price > 0 and stop_pct > 0 else 0.0
        )
        risk_based_notional = risk_based_qty * price
        risk_based_pct = risk_based_notional / equity if equity > 0 else 0.0

        chosen_pct = min(ai_size_pct, risk_based_pct)
        if chosen_pct <= 0:
            chosen_pct = min(ai_size_pct, self.max_position_percent)

        # Cash constraint (leave a small buffer for fees/slippage)
        affordable_pct = max((cash / equity * 0.99), 0.0) if equity > 0 else 0.0
        final_pct = min(chosen_pct, affordable_pct, self.max_position_percent)

        qty = (equity * final_pct) / price if price > 0 else 0.0

        plan.action = "BUY"
        plan.quantity = qty
        plan.entry_price = price
        plan.notional_value = qty * price
        plan.position_size_percent = final_pct * 100
        plan.stop_price = price * (1 - stop_pct)
        plan.target_price = price * (1 + target_pct)
        plan.stop_loss_percent = stop_pct * 100
        plan.take_profit_percent = target_pct * 100
        plan.notes.append(
            f"Sized at {final_pct:.1%} of equity "
            f"(AI {ai_size_pct:.1%}, risk-model {risk_based_pct:.1%})."
        )
        return plan


def risk_check(
    decision: str,
    ai: dict,
    price: float,
    account: dict,
    market: dict,
) -> tuple:
    """Convenience wrapper around RiskManager.evaluate()."""
    manager = RiskManager()
    return manager.evaluate(decision, ai, price, account, market)


# Module-level default manager reused by the app.
default_manager = RiskManager()