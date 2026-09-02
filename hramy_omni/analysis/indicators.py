"""
HRAMY OMNI AI - Technical Indicators
============================================================
All indicators are computed from REAL market data.

Provides:
    SMA20, SMA50            - trend baselines
    EMA20, EMA50            - faster trend response
    RSI(14)                 - momentum oscillator (Wilder)
    ATR(14)                 - volatility in price units (Wilder)
    MACD(12,26,9)           - trend/momentum crossover
    Bollinger Bands(20,2)   - volatility envelope + %B + bandwidth
    ADX(14)                 - trend STRENGTH (not direction)
    Momentum(10)            - rate of change
    Volatility(20)          - annualized realized vol
    Volume SMA / ratio      - participation
    Rolling VWAP(20)        - volume-weighted fair value reference
    Support / Resistance    - rolling 20-bar extremes

Only indicators that add non-redundant information are kept.
"""

import math

import numpy as np
import pandas as pd


# ============================================================
# Individual indicator functions
# ============================================================

def calculate_sma(series: pd.Series, period: int) -> pd.Series:
    """Simple moving average."""
    return series.rolling(period).mean()


def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential moving average."""
    return series.ewm(span=period, adjust=False).mean()


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI with simple rolling mean."""
    delta = series.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)

    avg_gain = gains.rolling(period).mean()
    avg_loss = losses.rolling(period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    # When avg_loss == 0 and avg_gain > 0 the asset only went up -> RSI 100.
    rsi = rsi.where(~((avg_loss == 0) & (avg_gain > 0)), 100.0)
    rsi = rsi.replace([np.inf, -np.inf], np.nan)
    return rsi


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range (Wilder smoothing)."""
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False).mean()


def calculate_macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
):
    """MACD line, signal line and histogram."""
    macd_line = calculate_ema(series, fast) - calculate_ema(series, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calculate_bollinger(series: pd.Series, period: int = 20, num_std: float = 2.0):
    """Bollinger Bands: middle, upper, lower, %B, bandwidth."""
    middle = series.rolling(period).mean()
    std = series.rolling(period).std()
    upper = middle + num_std * std
    lower = middle - num_std * std
    width = upper - lower
    percent_b = (series - lower) / width.replace(0, np.nan)
    bandwidth = width / middle * 100
    return middle, upper, lower, percent_b, bandwidth


def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """ADX - trend strength (0-100), direction agnostic (Wilder)."""
    high, low, close = df["high"], df["low"], df["close"]
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)

    tr = pd.concat(
        [high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()],
        axis=1,
    ).max(axis=1)

    alpha = 1.0 / period
    atr = tr.ewm(alpha=alpha, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=alpha, adjust=False).mean() / atr.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=alpha, adjust=False).mean() / atr.replace(0, np.nan)

    dx_sum = (plus_di + minus_di).replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / dx_sum
    adx = dx.ewm(alpha=alpha, adjust=False).mean()
    return adx.clip(0, 100)


def calculate_vwap(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Rolling volume-weighted average price over `period` bars."""
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = typical * df["volume"]
    vol = df["volume"].replace(0, np.nan)
    return pv.rolling(period).sum() / vol.rolling(period).sum()



# ============================================================
# Aggregate indicator pipeline
# ============================================================

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add technical indicators to a DataFrame of OHLCV bars.

    Requires columns: open, high, low, close, volume.
    Returns the DataFrame with indicator columns appended.
    Raises RuntimeError if insufficient data remains after warm-up.
    """
    data = df.copy()

    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(data.columns)
    if missing:
        raise RuntimeError(f"Market data is missing columns: {sorted(missing)}")

    # ---- Moving averages ----
    data["sma20"] = calculate_sma(data["close"], 20)
    data["sma50"] = calculate_sma(data["close"], 50)
    data["ema20"] = calculate_ema(data["close"], 20)
    data["ema50"] = calculate_ema(data["close"], 50)

    # ---- RSI ----
    data["rsi"] = calculate_rsi(data["close"], 14)

    # ---- ATR ----
    data["atr"] = calculate_atr(data, 14)
    # ATR as % of price -> comparable across symbols
    data["atr_pct"] = data["atr"] / data["close"] * 100

    # ---- MACD ----
    macd, signal, hist = calculate_macd(data["close"])
    data["macd"] = macd
    data["macd_signal"] = signal
    data["macd_hist"] = hist

    # ---- Bollinger Bands ----
    bb_mid, bb_up, bb_low, pct_b, bandwidth = calculate_bollinger(data["close"])
    data["bb_mid"] = bb_mid
    data["bb_upper"] = bb_up
    data["bb_lower"] = bb_low
    data["bb_percent_b"] = pct_b
    data["bb_bandwidth"] = bandwidth

    # ---- ADX ----
    data["adx"] = calculate_adx(data, 14)

    # ---- Momentum (10-day % change) ----
    data["momentum"] = data["close"].pct_change(10) * 100

    # ---- Returns ----
    data["returns"] = data["close"].pct_change()

    # ---- Annualized volatility (20-day) ----
    data["volatility"] = data["returns"].rolling(20).std() * math.sqrt(252) * 100

    # ---- Volume analysis ----
    data["volume_sma20"] = data["volume"].rolling(20).mean()
    data["volume_ratio"] = data["volume"] / data["volume_sma20"].replace(0, np.nan)

    # ---- Rolling VWAP ----
    data["vwap20"] = calculate_vwap(data, 20)

    # ---- Support / Resistance (20-bar extremes) ----
    data["resistance20"] = data["high"].rolling(20).max()
    data["support20"] = data["low"].rolling(20).min()

    # Remove rows where core indicators are still warming up.
    # We align on the slowest required window (SMA50) plus a small
    # buffer so every strategy sees a complete feature set.
    core_columns = [
        "sma20", "sma50", "rsi", "atr", "adx", "volatility",
        "volume_ratio", "vwap20", "bb_percent_b",
    ]
    data = data.dropna(subset=[c for c in core_columns if c in data.columns])

    if data.empty:
        raise RuntimeError(
            "Not enough data to calculate indicators. "
            "Need at least ~80 complete bars."
        )

    return data


def latest_snapshot(data: pd.DataFrame) -> dict:
    """Return a dict of the latest indicator values (all floats, NaN-safe)."""
    latest = data.iloc[-1]

    def _f(column: str, default: float = 0.0) -> float:
        try:
            value = float(latest[column])
        except (KeyError, TypeError, ValueError):
            return default
        if not math.isfinite(value):
            return default
        return value

    return {
        "price": _f("close"),
        "open": _f("open"),
        "high": _f("high"),
        "low": _f("low"),
        "sma20": _f("sma20"),
        "sma50": _f("sma50"),
        "ema20": _f("ema20"),
        "ema50": _f("ema50"),
        "rsi": _f("rsi", 50.0),
        "momentum": _f("momentum"),
        "volatility": _f("volatility"),
        "volume_ratio": _f("volume_ratio", 1.0),
        "atr": _f("atr"),
        "atr_pct": _f("atr_pct"),
        "macd": _f("macd"),
        "macd_signal": _f("macd_signal"),
        "macd_hist": _f("macd_hist"),
        "bb_percent_b": _f("bb_percent_b", 0.5),
        "bb_bandwidth": _f("bb_bandwidth"),
        "bb_upper": _f("bb_upper"),
        "bb_lower": _f("bb_lower"),
        "adx": _f("adx"),
        "vwap20": _f("vwap20"),
        "resistance20": _f("resistance20"),
        "support20": _f("support20"),
    }