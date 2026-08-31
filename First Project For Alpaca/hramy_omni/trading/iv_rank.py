"""IV Rank for the AI lane.

True 252-day implied-vol percentile needs a long IV history. Until that
feed is available we rank the latest realized volatility against its own
history (same 0–100 scale the strategist matrix expects).
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd


def realized_vol_rank(closes: pd.Series, window: int = 20) -> float:
    """Percentile (0-100) of the latest annualized realized vol vs its history."""
    series = pd.to_numeric(closes, errors="coerce").dropna()
    if len(series) < window + 5:
        return 62.0
    rets = series.pct_change().dropna()
    rv = rets.rolling(window).std() * math.sqrt(252.0) * 100.0
    rv = rv.dropna()
    if rv.empty:
        return 62.0
    current = float(rv.iloc[-1])
    if not math.isfinite(current):
        return 62.0
    rank = float((rv <= current).mean() * 100.0)
    return round(max(0.0, min(100.0, rank)), 1)


def iv_rank_from_chain(current_iv: float | None, closes: pd.Series | None = None) -> float:
    """
    If the live chain gives an ATM IV, convert it to a 0-100 rank against
    realized-vol history. Otherwise fall back to realized-vol rank alone.
    """
    if closes is not None and len(closes) >= 25:
        base = realized_vol_rank(closes)
    else:
        base = 62.0
    if current_iv is None:
        return base
    try:
        iv = float(current_iv)
    except (TypeError, ValueError):
        return base
    if not math.isfinite(iv) or iv <= 0:
        return base
    # IV is often a decimal (0.32) or a percent (32). Normalize to percent.
    if iv <= 3.0:
        iv *= 100.0
    # Blend: if live IV is rich vs typical 20-day RV rank, pull rank up, else down.
    blended = 0.5 * base + 0.5 * max(0.0, min(100.0, iv))
    return round(blended, 1)


def attach_iv_rank(market: dict[str, Any], closes: pd.Series | None = None, current_iv: float | None = None) -> dict[str, Any]:
    market = dict(market or {})
    market["iv_rank"] = iv_rank_from_chain(current_iv, closes)
    if current_iv is not None:
        market["implied_vol"] = current_iv
    return market
