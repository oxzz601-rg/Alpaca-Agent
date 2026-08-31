"""
HRAMY OMNI AI - Alpaca Market Data
============================================================
Market-data layer for the HRAMY OMNI application.

Uses Alpaca's IEX feed so the application works with accounts
that do not have access to recent SIP data.

This module is responsible ONLY for market data.
It does not place trades.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import (
    StockBarsRequest,
    StockLatestBarRequest,
)
from alpaca.data.timeframe import TimeFrame

from config import ALPACA_API_KEY, ALPACA_SECRET_KEY

DEFAULT_LOOKBACK_DAYS = 100


def get_market_data_cli(symbol: str = "AAPL", days: int = DEFAULT_LOOKBACK_DAYS) -> dict:
    """CLI-friendly snapshot of market data for local or MCP-style usage."""
    df = get_historical_data(symbol=symbol, days=days)
    return {
        "symbol": symbol.upper(),
        "rows": int(len(df)),
        "latest_close": float(df["close"].iloc[-1]),
        "start": df.index[0].isoformat() if len(df) else None,
        "end": df.index[-1].isoformat() if len(df) else None,
    }


# ============================================================
# Configuration
# ============================================================

# IEX is available for accounts that don't have recent SIP access.
DATA_FEED = DataFeed.IEX

# Cache the client so we only build it once.
_client = None


# ============================================================
# Client (lazy)
# ============================================================

def _create_client() -> StockHistoricalDataClient:
    """Create the Alpaca historical-data client.

    Credentials come from config.py, which loads them from .env.
    """
    if not ALPACA_API_KEY:
        raise RuntimeError("ALPACA_API_KEY is not configured.")
    if not ALPACA_SECRET_KEY:
        raise RuntimeError("ALPACA_SECRET_KEY is not configured.")

    return StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)


def get_client() -> StockHistoricalDataClient:
    """Return a lazily-created, cached Alpaca data client."""
    global _client
    if _client is None:
        _client = _create_client()
    return _client


# ============================================================
# Historical Data
# ============================================================

def get_historical_data(
    symbol: str,
    days: int = DEFAULT_LOOKBACK_DAYS,
) -> pd.DataFrame:
    """
    Download daily historical stock bars from Alpaca.

    Parameters
    ----------
    symbol:
        Stock ticker, e.g. "AAPL".
    days:
        Number of *trading* days to request. The function requests
        additional calendar days to account for weekends/holidays so
        that at least ``days`` trading bars are returned when possible.

    Returns
    -------
    pandas.DataFrame
        Columns: open, high, low, close, volume
        Index: timestamp (datetime, sorted ascending)
    """
    symbol = symbol.upper().strip()

    if not symbol:
        raise ValueError("Symbol cannot be empty.")
    if days <= 0:
        raise ValueError("days must be greater than zero.")

    # --------------------------------------------------------
    # Request more calendar days than trading days requested so
    # we reliably get enough bars (weekends + holidays).
    # --------------------------------------------------------
    end = datetime.now(timezone.utc)
    padded_days = int(days * 1.6) + 20
    start = end - timedelta(days=padded_days)

    request = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
        feed=DATA_FEED,
    )

    try:
        result = get_client().get_stock_bars(request)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to download Alpaca market data for {symbol}: {exc}"
        ) from exc

    df = result.df.copy()

    if df.empty:
        raise RuntimeError(f"Alpaca returned no historical data for {symbol}.")

    # --------------------------------------------------------
    # Normalize MultiIndex (symbol / timestamp) -> timestamp
    # --------------------------------------------------------
    if isinstance(df.index, pd.MultiIndex):
        df = df.reset_index()
        if "symbol" in df.columns:
            df = df[df["symbol"].astype(str).str.upper() == symbol]
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            df = df.set_index("timestamp")
    else:
        df.index = pd.to_datetime(df.index, utc=True)

    # Keep only expected columns.
    required_columns = ["open", "high", "low", "close", "volume"]
    missing = [c for c in required_columns if c not in df.columns]
    if missing:
        raise RuntimeError(
            "Alpaca response is missing required columns: " + ", ".join(missing)
        )

    df = df[required_columns].copy()

    # Ensure numeric values.
    for column in required_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    # Remove malformed rows.
    df = df.dropna(subset=required_columns)

    # Sort oldest -> newest and drop duplicate timestamps.
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]

    if df.empty:
        raise RuntimeError(
            f"No valid historical bars remain for {symbol} after cleaning."
        )

    return df


# ============================================================
# Latest Price
# ============================================================

def get_latest_price(symbol: str) -> float:
    """Get the latest available IEX bar for a symbol."""
    symbol = symbol.upper().strip()
    if not symbol:
        raise ValueError("Symbol cannot be empty.")

    request = StockLatestBarRequest(
        symbol_or_symbols=symbol,
        feed=DATA_FEED,
    )

    try:
        result = get_client().get_stock_latest_bar(request)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to retrieve latest price for {symbol}: {exc}"
        ) from exc

    if symbol not in result:
        raise RuntimeError(f"No latest IEX bar returned for {symbol}.")

    bar = result[symbol]
    if bar is None or bar.close is None:
        raise RuntimeError(f"Latest bar for {symbol} has no closing price.")

    return float(bar.close)


# ============================================================
# Connection Test
# ============================================================

# ============================================================
# Demo data fallback (clearly labeled synthetic)
# ============================================================

def generate_demo_data(days: int = 300) -> pd.DataFrame:
    """
    Deterministic synthetic OHLCV series used ONLY when Alpaca is
    unreachable, so the terminal keeps working for demos.

    The UI labels this state prominently as SYNTHETIC DEMO DATA.
    It is never mixed with real market data.
    """
    import numpy as np

    rng = np.random.default_rng(42)
    n = max(int(days), 120)

    trend = np.concatenate([
        np.linspace(150, 190, n // 3),
        np.linspace(190, 170, n // 4),
        np.linspace(170, 210, n - n // 3 - n // 4),
    ])
    noise = rng.normal(0, 2.0, n)
    close = trend + noise
    high = close + np.abs(rng.normal(1.0, 0.5, n))
    low = close - np.abs(rng.normal(1.0, 0.5, n))
    open_ = np.roll(close, 1) + rng.normal(0, 0.6, n)
    open_[0] = close[0]
    volume = rng.integers(2_000_000, 9_000_000, n).astype(float)

    idx = pd.date_range(end=pd.Timestamp.today().normalize(), periods=n, freq="B")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


def test_connection(symbol: str = "AAPL") -> dict:
    """Test the Alpaca market-data connection."""
    symbol = symbol.upper().strip()
    try:
        price = get_latest_price(symbol)
        return {
            "connected": True,
            "feed": "IEX",
            "symbol": symbol,
            "latest_price": price,
            "error": None,
        }
    except Exception:
        return {
            "connected": False,
            "feed": "IEX",
            "symbol": symbol,
            "latest_price": None,
            "error": "unavailable",
        }