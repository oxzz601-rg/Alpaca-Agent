"""
Deterministic synthetic market data builder for tests.
NEVER uses real API keys or network access.
"""

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis.indicators import calculate_indicators


def build_ohlcv(n: int = 300, seed: int = 42, trend: str = "mixed") -> pd.DataFrame:
    """
    Deterministic OHLCV frame.

    trend: "bull" | "bear" | "mixed" | "flat"
    """
    rng = np.random.default_rng(seed)

    if trend == "bull":
        base = np.linspace(100, 180, n)
        drift = rng.normal(0.05, 0.8, n)
    elif trend == "bear":
        base = np.linspace(180, 100, n)
        drift = -np.abs(rng.normal(0.05, 0.8, n))
    elif trend == "flat":
        base = np.full(n, 140.0)
        drift = rng.normal(0, 0.6, n)
    else:  # mixed: bull leg -> bear leg -> recovery
        third = n // 3
        base = np.concatenate([
            np.linspace(100, 160, third),
            np.linspace(160, 120, n - 2 * third),
            np.linspace(120, 175, n - third - (n - 2 * third)),
        ])
        drift = rng.normal(0, 1.2, n)

    close = base + drift
    high = close + np.abs(rng.normal(0.9, 0.4, n))
    low = close - np.abs(rng.normal(0.9, 0.4, n))
    open_ = np.roll(close, 1) + rng.normal(0, 0.5, n)
    open_[0] = close[0]
    volume = rng.integers(1_000_000, 6_000_000, n).astype(float)

    idx = pd.date_range("2023-01-02", periods=n, freq="B")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


def build_indicator_data(n: int = 300, seed: int = 42, trend: str = "mixed") -> pd.DataFrame:
    """OHLCV with the full indicator suite applied."""
    return calculate_indicators(build_ohlcv(n, seed, trend))


def make_snapshot(**overrides) -> dict:
    """A hand-crafted indicator snapshot for deterministic unit tests."""
    snapshot = {
        "price": 150.0,
        "sma20": 145.0,
        "sma50": 138.0,
        "ema20": 146.0,
        "rsi": 55.0,
        "momentum": 3.0,
        "volatility": 22.0,
        "volume_ratio": 1.2,
        "atr": 3.0,
        "atr_pct": 2.0,
        "macd": 0.8,
        "macd_signal": 0.5,
        "macd_hist": 0.3,
        "bb_percent_b": 0.65,
        "adx": 28.0,
        "vwap20": 147.0,
        "support20": 135.0,
        "resistance20": 155.0,
    }
    snapshot.update(overrides)
    return snapshot
