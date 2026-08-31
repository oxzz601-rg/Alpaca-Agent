"""Alpaca brokerage integration helpers for the real-trading hackathon path."""

from __future__ import annotations

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
        "account_id": str(raw.get("account_id") or raw.get("id") or ALPACA_PAPER_ACCOUNT_ID or ""),
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
        "account_id": getattr(account, "id", getattr(account, "account_id", ALPACA_PAPER_ACCOUNT_ID)),
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
        account = self.client.get_account()
        return normalize_account_snapshot({
            "account_id": getattr(account, "id", getattr(account, "account_id", self.account_id)),
            "cash": float(getattr(account, "cash", 0.0)),
            "buying_power": float(getattr(account, "buying_power", 0.0)),
            "equity": float(getattr(account, "equity", 0.0)),
            "portfolio_value": float(getattr(account, "portfolio_value", 0.0)),
            "status": getattr(account, "status", "ACTIVE"),
            "pl": float(getattr(account, "pl", 0.0)),
        })

    def options_eligible(self) -> bool:
        if self.client is None:
            raise RuntimeError("Alpaca paper-trading client is not configured.")
        account = self.client.get_account()
        for attr in ("options_trading_level", "options_approved_level", "option_level"):
            raw = getattr(account, attr, None)
            if raw is None:
                continue
            try:
                return int(raw) >= 3
            except (TypeError, ValueError):
                continue
        return False

    def options_level(self) -> int:
        if self.client is None:
            return 0
        account = self.client.get_account()
        for attr in ("options_trading_level", "options_approved_level", "option_level"):
            raw = getattr(account, attr, None)
            try:
                if raw is not None:
                    return int(raw)
            except (TypeError, ValueError):
                continue
        return 0

    def get_clock(self) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("Alpaca paper-trading client is not configured.")
        clock = self.client.get_clock()
        return {
            "timestamp": str(getattr(clock, "timestamp", None)),
            "is_open": bool(getattr(clock, "is_open", False)),
            "next_open": str(getattr(clock, "next_open", None)),
            "next_close": str(getattr(clock, "next_close", None)),
        }

    def get_positions(self) -> list[dict[str, Any]]:
        if self.client is None:
            raise RuntimeError("Alpaca paper-trading client is not configured.")
        return [
            {
                "symbol": getattr(p, "symbol", ""),
                "qty": getattr(p, "qty", 0),
                "market_value": getattr(p, "market_value", 0.0),
                "unrealized_pl": getattr(p, "unrealized_pl", 0.0),
            }
            for p in self.client.get_all_positions()
        ]

    def get_option_chain(self, symbol: str, expiration_date: str | None = None, strike: float | None = None):
        if self.client is None:
            raise RuntimeError("Alpaca paper-trading client is not configured.")
        if hasattr(self.client, "get_option_chain"):
            return self.client.get_option_chain(symbol=symbol, expiration_date=expiration_date, strike=strike)
        return {"symbol": symbol, "expiration_date": expiration_date, "strike": strike, "contracts": []}

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
        )
        return self._serialize_order(self.client.submit_order(order_data=request))

    def submit_option_order(self, symbol: str, side: str, qty: float = 1.0, option_symbol: str | None = None) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("Real Alpaca execution is not available because credentials are missing.")
        if not self.options_eligible():
            raise RuntimeError("This Alpaca paper account does not have options trading enabled (need level 3).")

        target_symbol = option_symbol or symbol
        if MarketOrderRequest is None or OrderSide is None or TimeInForce is None:
            raise RuntimeError("Alpaca trading SDK is unavailable in this environment.")

        order_side = OrderSide.SELL if str(side).upper() in {"SELL", "SHORT", "WRITE"} else OrderSide.BUY
        payload: dict[str, Any] = {
            "symbol": target_symbol,
            "qty": qty,
            "side": order_side,
            "time_in_force": TimeInForce.DAY,
        }
        try:
            from alpaca.trading.enums import PositionIntent
            payload["position_intent"] = (
                PositionIntent.SELL_TO_OPEN if order_side == OrderSide.SELL else PositionIntent.BUY_TO_OPEN
            )
        except Exception:
            pass
        request = MarketOrderRequest(**payload)
        return self._serialize_order(self.client.submit_order(order_data=request))

    @staticmethod
    def _serialize_order(order: Any) -> dict[str, Any]:
        if isinstance(order, dict):
            return order
        return {
            "id": str(getattr(order, "id", "")),
            "client_order_id": str(getattr(order, "client_order_id", "")),
            "symbol": getattr(order, "symbol", ""),
            "status": str(getattr(order, "status", "")),
            "side": str(getattr(order, "side", "")),
            "qty": str(getattr(order, "qty", "")),
            "filled_qty": str(getattr(order, "filled_qty", "")),
            "order_type": str(getattr(order, "order_type", getattr(order, "type", ""))),
            "submitted_at": str(getattr(order, "submitted_at", "")),
        }
