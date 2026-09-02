"""Resolve a cash-secured put from AI target_delta / target_dte.

Tries the live Alpaca option chain first. If credentials, the SDK, or the
chain are unavailable, falls back to a synthetic OCC symbol so offline
tests and dry-runs still work.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from config import ALPACA_PAPER_API_KEY, ALPACA_PAPER_SECRET_KEY

OCC_RE = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8})$")


def occ_option_symbol(underlying: str, expiry_date: str, side: str, strike: float) -> str:
    """OCC symbol: AAPL250117P00225000 (YYMMDD + C/P + strike*1000, 8 digits)."""
    root = (underlying or "").upper().strip()
    yymmdd = expiry_date.replace("-", "")[2:]
    cp = "P" if str(side).lower().startswith("p") else "C"
    strike_int = int(round(float(strike) * 1000))
    return f"{root}{yymmdd}{cp}{strike_int:08d}"


def parse_occ_symbol(option_symbol: str) -> dict[str, Any]:
    text = str(option_symbol or "").upper().strip()
    match = OCC_RE.match(text)
    if not match:
        return {"root": "", "expiry_date": "", "side": "", "strike": 0.0}
    root, yymmdd, cp, strike_raw = match.groups()
    expiry_date = f"20{yymmdd[:2]}-{yymmdd[2:4]}-{yymmdd[4:6]}"
    return {
        "root": root,
        "expiry_date": expiry_date,
        "side": "put" if cp == "P" else "call",
        "strike": int(strike_raw) / 1000.0,
    }


def _plan(
    symbol: str,
    option_symbol: str,
    strike: float,
    side: str,
    delta: float,
    dte: int,
    expiry_date: str,
    quantity: int,
    strategy: str,
    source: str,
    implied_vol: float | None = None,
    bid: float | None = None,
    ask: float | None = None,
) -> dict[str, Any]:
    qty = max(int(quantity or 1), 1)
    required_cash = float(strike) * 100.0 * qty
    strategy = str(strategy or "CASH_SECURED_PUT").upper()
    return {
        "symbol": symbol,
        "option_symbol": option_symbol,
        "strike": float(strike),
        "side": side,
        "target_delta": float(delta),
        "target_dte": int(dte),
        "dte": int(dte),
        "expiry_date": expiry_date,
        "required_cash": required_cash,
        "strategy": strategy,
        "cash_secured": strategy == "CASH_SECURED_PUT",
        "naked_short": False,
        "max_loss": required_cash,
        "quantity": qty,
        "source": source,
        "implied_vol": implied_vol,
        "bid": bid,
        "ask": ask,
    }


class OptionChainResolver:
    """Resolve strike, expiry, OCC symbol, and CSP collateral from AI targets."""

    def __init__(self, live: bool = False, api_key: str | None = None, secret_key: str | None = None):
        self.live = bool(live)
        self.api_key = api_key or ALPACA_PAPER_API_KEY
        self.secret_key = secret_key or ALPACA_PAPER_SECRET_KEY

    def resolve_contract(
        self,
        symbol: str,
        stock_price: float,
        target_delta: float = 0.25,
        target_dte: int = 21,
        side: str = "put",
        quantity: int = 1,
        strategy: str = "CASH_SECURED_PUT",
    ) -> dict[str, Any]:
        if self.live:
            try:
                return self._resolve_live(
                    symbol, stock_price, target_delta, target_dte, side, quantity, strategy
                )
            except Exception:
                fallback = self._resolve_synthetic(
                    symbol, stock_price, target_delta, target_dte, side, quantity, strategy
                )
                fallback["source"] = "synthetic_fallback"
                return fallback
        return self._resolve_synthetic(
            symbol, stock_price, target_delta, target_dte, side, quantity, strategy
        )

    def _resolve_synthetic(
        self,
        symbol: str,
        stock_price: float,
        target_delta: float,
        target_dte: int,
        side: str,
        quantity: int,
        strategy: str,
    ) -> dict[str, Any]:
        symbol = (symbol or "AAPL").upper().strip()
        stock_price = float(stock_price or 0.0)
        if stock_price <= 0:
            raise ValueError("stock_price must be positive")

        side = str(side or "put").lower()
        if side not in {"put", "call"}:
            side = "put"

        dte = max(int(target_dte or 21), 7)
        delta = abs(float(target_delta or 0.25))
        step = 1.0 if stock_price < 50 else 2.5 if stock_price < 100 else 5.0
        otm_gap = step * max(1, round((0.50 - min(delta, 0.49)) / 0.10))
        raw_strike = stock_price - otm_gap if side == "put" else stock_price + otm_gap
        strike = round(math.floor(raw_strike / step) * step, 2)
        if strike <= 0:
            strike = step
        expiry_date = (datetime.now(timezone.utc) + timedelta(days=dte)).strftime("%Y-%m-%d")
        option_symbol = occ_option_symbol(symbol, expiry_date, side, strike)
        return _plan(
            symbol, option_symbol, strike, side, delta, dte, expiry_date,
            quantity, strategy, source="synthetic",
        )

    def _resolve_live(
        self,
        symbol: str,
        stock_price: float,
        target_delta: float,
        target_dte: int,
        side: str,
        quantity: int,
        strategy: str,
    ) -> dict[str, Any]:
        symbol = (symbol or "AAPL").upper().strip()
        if not self.api_key or not self.secret_key:
            raise RuntimeError("Alpaca keys are not configured for live chain lookup.")

        from alpaca.data.enums import OptionsFeed
        from alpaca.data.historical.option import OptionHistoricalDataClient
        from alpaca.data.requests import OptionChainRequest
        from alpaca.trading.enums import ContractType

        side = str(side or "put").lower()
        contract_type = ContractType.PUT if side == "put" else ContractType.CALL
        dte = max(int(target_dte or 21), 7)
        delta_target = abs(float(target_delta or 0.25))
        today = datetime.now(timezone.utc).date()
        start = today + timedelta(days=max(dte - 10, 7))
        end = today + timedelta(days=dte + 14)

        client = OptionHistoricalDataClient(self.api_key, self.secret_key)
        request = OptionChainRequest(
            underlying_symbol=symbol,
            feed=OptionsFeed.INDICATIVE,
            type=contract_type,
            expiration_date_gte=start.isoformat(),
            expiration_date_lte=end.isoformat(),
        )
        chain = client.get_option_chain(request)
        if not chain:
            raise RuntimeError(f"Empty option chain for {symbol}.")

        best = None
        best_score = None
        for occ_symbol, snap in chain.items():
            parsed = parse_occ_symbol(occ_symbol)
            if not parsed["expiry_date"]:
                continue
            expiry = datetime.strptime(parsed["expiry_date"], "%Y-%m-%d").date()
            contract_dte = (expiry - today).days
            if contract_dte < 7:
                continue
            greeks = getattr(snap, "greeks", None)
            delta = abs(float(getattr(greeks, "delta", 0.0) or 0.0)) if greeks else 0.0
            if delta <= 0:
                # No greek: approximate with OTM distance vs spot.
                if stock_price > 0:
                    delta = max(0.05, min(0.60, 0.50 - abs(parsed["strike"] - stock_price) / stock_price))
            score = abs(delta - delta_target) + 0.015 * abs(contract_dte - dte)
            quote = getattr(snap, "latest_quote", None)
            bid = float(getattr(quote, "bid_price", 0) or 0) if quote else 0.0
            ask = float(getattr(quote, "ask_price", 0) or 0) if quote else 0.0
            if best_score is None or score < best_score:
                best_score = score
                best = {
                    "option_symbol": occ_symbol,
                    "strike": parsed["strike"],
                    "expiry_date": parsed["expiry_date"],
                    "dte": contract_dte,
                    "delta": delta,
                    "implied_vol": getattr(snap, "implied_volatility", None),
                    "bid": bid or None,
                    "ask": ask or None,
                }

        if best is None:
            raise RuntimeError(f"No suitable {side} contract found for {symbol}.")

        return _plan(
            symbol,
            best["option_symbol"],
            best["strike"],
            side,
            best["delta"],
            best["dte"],
            best["expiry_date"],
            quantity,
            strategy,
            source="alpaca_chain",
            implied_vol=best["implied_vol"],
            bid=best["bid"],
            ask=best["ask"],
        )
