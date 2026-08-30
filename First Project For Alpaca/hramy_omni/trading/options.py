"""Option-trading helpers for the Alpaca hackathon project."""

from __future__ import annotations

from datetime import datetime, timedelta


def build_option_trade_plan(
    symbol: str,
    current_price: float,
    option_type: str,
    days_to_expiry: int = 14,
    side: str = "buy",
    contract_qty: int = 1,
) -> dict:
    """Build a simple near-the-money option plan for a stock symbol.

    The project supports the mandatory options-trading requirement without
    depending on a broker response to generate a valid plan. This is intended
    to align with the hackathon requirement while keeping execution logic safe
    and explicit.
    """
    symbol = (symbol or "AAPL").upper().strip()
    option_type = (option_type or "call").lower().strip()
    side = (side or "buy").lower().strip()
    if option_type not in {"call", "put"}:
        option_type = "call"
    if side not in {"buy", "sell"}:
        side = "buy"
    price = float(current_price or 0.0)
    if price <= 0:
        raise ValueError("current_price must be positive")

    strike_step = 2.5 if price < 100 else 5.0
    nearest_strike = round(price / strike_step) * strike_step
    expiry = (datetime.utcnow() + timedelta(days=max(days_to_expiry, 1))).strftime("%Y-%m-%d")

    return {
        "symbol": symbol,
        "option_type": option_type,
        "strike": round(nearest_strike, 2),
        "side": side,
        "contract_qty": max(int(contract_qty or 1), 1),
        "expiry": expiry,
        "days_to_expiry": max(int(days_to_expiry or 1), 1),
        "contract_symbol": f"{symbol}{expiry.replace('-', '')}{option_type[:1].upper()}{nearest_strike:g}",
    }
