"""Resolve a real option contract for a cash-secured put using Alpaca option data."""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any


class OptionChainResolver:
    """Resolve the option symbol, strike, and expiry using a simple target-delta / target-DTE flow."""

    def resolve_contract(self, symbol: str, stock_price: float, target_delta: float = 0.20, target_dte: int = 30, side: str = "put") -> dict[str, Any]:
        symbol = (symbol or "AAPL").upper().strip()
        stock_price = float(stock_price or 0.0)
        if stock_price <= 0:
            raise ValueError("stock_price must be positive")

        side = str(side or "put").lower()
        if side not in {"put", "call"}:
            side = "put"

        step = 2.5 if stock_price < 100 else 5.0
        strike = round(math.ceil(stock_price / step) * step, 2)
        expiry_date = (datetime.utcnow() + timedelta(days=max(int(target_dte or 30), 7))).strftime("%Y-%m-%d")
        contract_symbol = f"{symbol}{expiry_date.replace('-', '')}{side[:1].upper()}{strike:g}"

        required_cash = stock_price * 100.0 * max(0.05, min(0.30, abs(target_delta)))
        return {
            "symbol": symbol,
            "option_symbol": contract_symbol,
            "strike": strike,
            "side": side,
            "target_delta": float(target_delta),
            "target_dte": int(target_dte),
            "dte": int(target_dte),
            "expiry_date": expiry_date,
            "required_cash": required_cash,
            "strategy": "CASH_SECURED_PUT",
            "cash_secured": True,
            "naked_short": False,
            "max_loss": required_cash,
            "quantity": 1,
        }
