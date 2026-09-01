"""
HRAMY OMNI AI - Paper Portfolio Simulator
============================================================
A fully simulated portfolio. NO live trading - paper mode only.

Tracks:
    starting cash, current cash, fractional shares, average entry price,
    position value, unrealized P/L, realized P/L (net of fees),
    total portfolio value, and ROUND-TRIP trade history.

A "trade" is a completed ENTRY -> EXIT round trip. Every record includes
entry/exit prices, quantity, gross P/L, fees, net P/L, return percent,
holding period, exit reason, and AI context.

Execution realism:
    - configurable commission + slippage on every fill
    - fractional shares supported
    - never allows negative cash or overselling

IMPORTANT: This module NEVER places real orders.
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import COMMISSION_RATE, SLIPPAGE_PCT, STARTING_CASH


class PaperPortfolio:
    """In-memory simulated portfolio with realistic fill modeling."""

    def __init__(
        self,
        starting_cash: float = STARTING_CASH,
        commission_rate: float = COMMISSION_RATE,
        slippage_pct: float = SLIPPAGE_PCT,
        symbol: str = "AAPL",
    ):
        self.starting_cash = float(starting_cash)
        self.cash = self.starting_cash
        self.shares = 0.0                 # fractional shares allowed
        self.average_entry = 0.0
        self.realized_pnl_gross = 0.0
        self.total_fees_paid = 0.0
        self.commission_rate = commission_rate
        self.slippage_pct = slippage_pct
        self.symbol = symbol
        self.trades = []                  # closed round trips
        self.open_trade = None            # dict while a position is open

    # ----------------------------------------------------------
    # Valuation helpers
    # ----------------------------------------------------------

    def position_value(self, price: float) -> float:
        return self.shares * price

    def total_value(self, price: float) -> float:
        return self.cash + self.position_value(price)

    def unrealized_pnl(self, price: float) -> float:
        if self.shares <= 0:
            return 0.0
        return (price - self.average_entry) * self.shares

    def total_pnl(self, price: float) -> float:
        return self.total_value(price) - self.starting_cash

    def exposure_percent(self, price: float) -> float:
        total = self.total_value(price)
        if total <= 0:
            return 0.0
        return self.position_value(price) / total * 100

    # ----------------------------------------------------------
    # Fill modeling
    # ----------------------------------------------------------

    def _buy_fill_price(self, price: float) -> float:
        """Adverse fill for a buy: pay slippage."""
        return price * (1 + self.slippage_pct)

    def _sell_fill_price(self, price: float) -> float:
        """Adverse fill for a sell: receive less."""
        return price * (1 - self.slippage_pct)

    def _commission(self, notional: float) -> float:
        return abs(notional) * self.commission_rate

    # ----------------------------------------------------------
    # Trade execution (simulated only)
    # ----------------------------------------------------------

    def execute(
        self,
        symbol: str,
        decision: str,
        price: float,
        confidence: float = 1.0,
        quantity: float | None = None,
        stop_price: float | None = None,
        target_price: float | None = None,
        ai_meta: dict | None = None,
    ) -> str:
        """
        Execute a simulated trade.

        Parameters
        ----------
        decision   : BUY | SELL | HOLD
        price      : current market price (fills get slippage applied)
        quantity   : fractional shares; None => sensible default
                     (BUY: 10% of cash / SELL: entire position)
        stop/target: attached to the open-trade record for tracking

        Returns a human-readable status string.
        """
        decision = str(decision).upper().strip()
        if price <= 0:
            return "NO TRADE: invalid price."

        # ---------------- BUY ----------------
        if decision == "BUY":
            qty = (self.cash * 0.10) / price if quantity is None else float(quantity)
            if qty <= 0:
                return "NO TRADE: computed quantity is zero."

            fill = self._buy_fill_price(price)
            notional = qty * fill
            fee = self._commission(notional)

            if notional + fee > self.cash:
                # Scale down to what cash allows (fee-aware).
                qty = max((self.cash - fee) / fill, 0.0) if fill > 0 else 0.0
                if qty <= 0:
                    return "NO TRADE: insufficient simulated cash."
                notional = qty * fill
                fee = self._commission(notional)

            old_shares = self.shares
            old_avg = self.average_entry
            self.cash -= (notional + fee)
            self.shares += qty
            self.total_fees_paid += fee

            if old_shares == 0:
                self.average_entry = fill
            else:
                self.average_entry = ((old_avg * old_shares) + notional) / self.shares

            if self.open_trade is None:
                self.open_trade = {
                    "symbol": symbol,
                    "entry_time": datetime.now().isoformat(timespec="seconds"),
                    "entry_price": fill,
                    "quantity": qty,
                    "fees_entry": fee,
                    "stop_price": stop_price,
                    "target_price": target_price,
                    "ai_confidence": confidence,
                    **(ai_meta or {}),
                }
            else:
                self.open_trade["quantity"] += qty
                self.open_trade["fees_entry"] += fee

            return (
                f"SIMULATED BUY: {qty:.4f} {symbol} @ ${fill:.2f} (fee ${fee:.2f})"
            )

        # ---------------- SELL ----------------
        if decision == "SELL":
            if self.shares <= 0:
                return "NO TRADE: no simulated shares available to sell."

            sell_qty = self.shares if quantity is None else min(float(quantity), self.shares)
            if sell_qty <= 0:
                return "NO TRADE: invalid sell quantity."

            fill = self._sell_fill_price(price)
            notional = sell_qty * fill
            fee = self._commission(notional)
            gross_pnl = (fill - self.average_entry) * sell_qty
            net_pnl = gross_pnl - fee

            self.cash += (notional - fee)
            self.shares -= sell_qty
            self.realized_pnl_gross += gross_pnl
            self.total_fees_paid += fee

            entry_time = (
                self.open_trade.get("entry_time")
                if self.open_trade else datetime.now().isoformat(timespec="seconds")
            )
            holding_days = 0.0
            try:
                t0 = datetime.fromisoformat(entry_time)
                holding_days = max((datetime.now() - t0).total_seconds() / 86400.0, 0.0)
            except (ValueError, TypeError):
                pass

            self.trades.append({
                "trade_id": len(self.trades) + 1,
                "time": datetime.now().isoformat(timespec="seconds"),
                "symbol": symbol,
                "action": "CLOSE",
                "entry_time": entry_time,
                "exit_time": datetime.now().isoformat(timespec="seconds"),
                "entry_price": round(self.average_entry, 4),
                "exit_price": round(fill, 4),
                "quantity": round(sell_qty, 6),
                "gross_pnl": round(gross_pnl, 2),
                "fees": round(fee, 2),
                "net_pnl": round(net_pnl, 2),
                "return_percent": round(
                    (fill / self.average_entry - 1) * 100 if self.average_entry else 0.0, 3
                ),
                "holding_days": round(holding_days, 4),
                "exit_reason": "MANUAL",
                "ai_confidence": confidence,
                "risk": (ai_meta or {}).get("risk", ""),
            })

            if self.shares <= 1e-9:
                self.shares = 0.0
                self.average_entry = 0.0
                self.open_trade = None

            return (
                f"SIMULATED SELL: {sell_qty:.4f} {symbol} @ ${fill:.2f} | "
                f"net P/L: ${net_pnl:+.2f}"
            )

        return "NO TRADE: AI decided HOLD."

    # ----------------------------------------------------------
    # Summary / serialization
    # ----------------------------------------------------------

    def summary(self, price: float) -> dict:
        """Return a snapshot of the portfolio state at `price`."""
        return {
            "starting_cash": self.starting_cash,
            "cash": self.cash,
            "shares": self.shares,
            "average_entry": self.average_entry,
            "position_value": self.position_value(price),
            "unrealized_pnl": self.unrealized_pnl(price),
            "realized_pnl": sum(t.get("net_pnl", 0.0) for t in self.trades),
            "realized_pnl_gross": self.realized_pnl_gross,
            "total_fees_paid": self.total_fees_paid,
            "total_value": self.total_value(price),
            "total_pnl": self.total_pnl(price),
            "exposure_percent": self.exposure_percent(price),
            "open_position": bool(self.shares > 0),
            "trades": list(self.trades),
            "closed_trades": len(self.trades),
        }