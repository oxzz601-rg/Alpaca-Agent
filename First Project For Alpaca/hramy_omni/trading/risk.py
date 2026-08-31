"""Option-risk enforcement. AI cannot bypass this gate."""

from __future__ import annotations

from typing import Any

LIVE_STRATEGIES = {"CASH_SECURED_PUT"}


class OptionRiskGate:
    """Risk checks for option execution.

    Cash-secured puts are collateralized (strike * 100). That collateral is
    checked against cash, not against the 1%-of-equity debit-spread budget.
    """

    def __init__(
        self,
        min_dte: int = 7,
        max_loss_pct: float = 0.02,
        max_positions: int = 6,
        max_loss_per_trade: float = 1500.0,
        max_collateral_pct: float = 0.35,
    ):
        self.min_dte = int(min_dte)
        self.max_loss_pct = float(max_loss_pct)
        self.max_positions = int(max_positions)
        self.max_loss_per_trade = float(max_loss_per_trade)
        self.max_collateral_pct = float(max_collateral_pct)

    def evaluate(
        self,
        plan: dict[str, Any],
        account: dict[str, Any],
        positions: list[dict[str, Any]] | None = None,
    ) -> tuple[bool, str]:
        plan = plan or {}
        account = account or {}
        positions = positions or []

        equity = float(account.get("equity") or account.get("portfolio_value") or 0.0)
        cash = float(account.get("cash") or 0.0)

        dte = int(plan.get("dte") or 0)
        if dte < self.min_dte:
            return False, f"DTE {dte} is below the minimum DTE floor of {self.min_dte}."

        strategy = str(plan.get("strategy") or "").upper()
        if strategy not in LIVE_STRATEGIES:
            return False, (
                f"Live execution currently allows {sorted(LIVE_STRATEGIES)}; "
                f"got {strategy or 'NONE'}."
            )

        if bool(plan.get("naked_short")):
            return False, "Naked short risk is blocked; only cash-secured option positions are permitted."

        if strategy == "CASH_SECURED_PUT" and not bool(plan.get("cash_secured")):
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
                f"Insufficient cash to secure the put: required ${required_cash:,.2f}, "
                f"available ${cash:,.2f}."
            )

        if equity > 0 and required_cash > equity * self.max_collateral_pct + 1e-9:
            return False, (
                f"CSP collateral ${required_cash:,.2f} exceeds "
                f"{self.max_collateral_pct:.0%} of equity ${equity:,.2f}."
            )

        if strategy != "CASH_SECURED_PUT":
            max_loss = float(plan.get("max_loss") or 0.0)
            allowed_loss_budget = max(self.max_loss_per_trade, equity * self.max_loss_pct)
            if max_loss > allowed_loss_budget + 1e-9:
                return False, (
                    f"Max loss ${max_loss:,.2f} exceeds the allowed budget of "
                    f"${allowed_loss_budget:,.2f}."
                )

        return True, "Risk gate passed."
