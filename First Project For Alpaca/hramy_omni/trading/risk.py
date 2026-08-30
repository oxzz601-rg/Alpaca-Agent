"""Option-risk enforcement for the Alpaca judge path."""

from __future__ import annotations

from typing import Any


class OptionRiskGate:
    """Risk checks for option execution, especially cash-secured puts."""

    def __init__(
        self,
        min_dte: int = 7,
        max_loss_pct: float = 0.02,
        max_positions: int = 3,
        max_loss_per_trade: float = 1500.0,
    ):
        self.min_dte = int(min_dte)
        self.max_loss_pct = float(max_loss_pct)
        self.max_positions = int(max_positions)
        self.max_loss_per_trade = float(max_loss_per_trade)

    def evaluate(self, plan: dict[str, Any], account: dict[str, Any], positions: list[dict[str, Any]] | None = None) -> tuple[bool, str]:
        plan = plan or {}
        account = account or {}
        positions = positions or []

        equity = float(account.get("equity") or account.get("portfolio_value") or 0.0)
        cash = float(account.get("cash") or 0.0)

        dte = int(plan.get("dte") or 0)
        if dte < self.min_dte:
            return False, f"DTE {dte} is below the minimum DTE floor of {self.min_dte}."

        strategy = str(plan.get("strategy") or "").upper()
        if strategy not in {"CASH_SECURED_PUT", "PUT", "OPTION"}:
            return False, "Only cash-secured put execution is allowed in the live judge path."

        max_loss = float(plan.get("max_loss") or 0.0)
        allowed_loss_budget = max(self.max_loss_per_trade, equity * self.max_loss_pct)
        if max_loss > allowed_loss_budget + 1e-9:
            return False, (
                f"Max loss ${max_loss:,.2f} exceeds the allowed budget of ${allowed_loss_budget:,.2f}."
            )

        if bool(plan.get("naked_short")):
            return False, "Naked short risk is blocked; only cash-secured option positions are permitted."

        if not bool(plan.get("cash_secured")):
            return False, "Option trade must be cash secured before submission."

        current_positions = len(positions)
        target_positions = int(plan.get("quantity") or 1)
        if current_positions + target_positions > self.max_positions:
            return False, (
                f"This trade would exceed the max-position cap of {self.max_positions}. "
                f"Current positions: {current_positions}."
            )

        required_cash = float(plan.get("required_cash") or 0.0)
        if required_cash > cash + 1e-9:
            return False, (
                f"Insufficient cash to secure the put: required ${required_cash:,.2f}, available ${cash:,.2f}."
            )

        return True, "Risk gate passed."
