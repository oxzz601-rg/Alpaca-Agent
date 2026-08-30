"""Alpaca brokerage integration helpers for the real-trading hackathon path."""

from __future__ import annotations

import os
from typing import Any

try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest, OrderRequest
    from alpaca.trading.enums import OrderSide, OrderClass, TimeInForce
except Exception:  # pragma: no cover - optional dependency can be absent during tests
    TradingClient = None
    MarketOrderRequest = None
    OrderRequest = None
    OrderSide = None
    OrderClass = None
    TimeInForce = None

from config import ALPACA_PAPER_API_KEY, ALPACA_PAPER_SECRET_KEY, ALPACA_PAPER_ACCOUNT_ID


def normalize_account_snapshot(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize Alpaca account data into a consistent, project-friendly dict."""
    raw = raw or {}
    cash = float(raw.get("cash", raw.get("available_cash", 0.0)) or 0.0)
    equity = float(raw.get("equity", raw.get("portfolio_value", cash)) or 0.0)
    portfolio_value = float(raw.get("portfolio_value", equity) or 0.0)
    buying_power = float(raw.get("buying_power", portfolio_value * 4.0) or 0.0)
    pnl = float(raw.get("pl", raw.get("pnl", 0.0)) or 0.0)
    return {
        "account_id": str(raw.get("account_id") or ALPACA_PAPER_ACCOUNT_ID or ""),
        "cash": cash,
        "buying_power": buying_power,
        "equity": equity,
        "portfolio_value": portfolio_value,
        "status": str(raw.get("status") or "ACTIVE").upper(),
        "pnl": pnl,
        "realized_pl": float(raw.get("realized_pl", 0.0) or 0.0),
        "unrealized_pl": float(raw.get("unrealized_pl", 0.0) or 0.0),
    }


def get_account_snapshot() -> dict[str, Any]:
    """Return the current paper-account snapshot or raise if credentials are missing."""
    if not ALPACA_PAPER_API_KEY or not ALPACA_PAPER_SECRET_KEY:
        raise RuntimeError("ALPACA_PAPER_API_KEY and ALPACA_PAPER_SECRET_KEY must be configured.")
    if TradingClient is None:
        raise RuntimeError("alpaca-py is not installed.")

    client = TradingClient(api_key=ALPACA_PAPER_API_KEY, secret_key=ALPACA_PAPER_SECRET_KEY, paper=True)
    account = client.get_account()
    return normalize_account_snapshot({
        "account_id": getattr(account, "account_id", ALPACA_PAPER_ACCOUNT_ID),
        "cash": getattr(account, "cash", 0.0),
        "buying_power": getattr(account, "buying_power", 0.0),
        "equity": getattr(account, "equity", 0.0),
        "portfolio_value": getattr(account, "portfolio_value", 0.0),
        "status": getattr(account, "status", "ACTIVE"),
        "pl": getattr(account, "pl", 0.0),
        "realized_pl": getattr(account, "realized_pl", 0.0),
        "unrealized_pl": getattr(account, "unrealized_pl", 0.0),
    })


class AlpacaBroker:
    """Simple wrapper around the Alpaca paper-trading API."""

    def __init__(self, paper: bool = True, api_key: str | None = None, secret_key: str | None = None):
        self.paper = paper
        self.api_key = api_key or ALPACA_PAPER_API_KEY
        self.secret_key = secret_key or ALPACA_PAPER_SECRET_KEY
        self.account_id = ALPACA_PAPER_ACCOUNT_ID
        self.client = None

        if self.api_key and self.secret_key and TradingClient is not None:
            self.client = TradingClient(api_key=self.api_key, secret_key=self.secret_key, paper=self.paper)

    def account_snapshot(self) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("Alpaca paper-trading client is not configured.")
        return normalize_account_snapshot({
            "account_id": self.account_id,
            "cash": float(self.client.get_account().cash),
            "buying_power": float(self.client.get_account().buying_power),
            "equity": float(self.client.get_account().equity),
            "portfolio_value": float(self.client.get_account().portfolio_value),
            "status": getattr(self.client.get_account(), "status", "ACTIVE"),
            "pl": float(getattr(self.client.get_account(), "pl", 0.0)),
        })

    def submit_market_order(self, symbol: str, side: str, qty: float = 1.0, order_type: str = "stock") -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("Real Alpaca execution is not available because credentials are missing.")
        if MarketOrderRequest is None or OrderSide is None or TimeInForce is None:
            raise RuntimeError("Alpaca trading SDK is unavailable in this environment.")

        order_side = OrderSide.BUY if str(side).upper() == "BUY" else OrderSide.SELL
        request = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=order_side,
            time_in_force=TimeInForce.DAY,
            order_class=OrderClass.MARKET,
        )
        return self.client.submit_order(order_data=request)

    def submit_option_order(self, symbol: str, side: str, qty: float = 1.0, option_symbol: str | None = None) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("Real Alpaca execution is not available because credentials are missing.")
        target_symbol = option_symbol or symbol
        return self.submit_market_order(target_symbol, side, qty=qty, order_type="option")
