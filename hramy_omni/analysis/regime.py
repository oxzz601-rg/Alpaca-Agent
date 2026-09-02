"""
HRAMY OMNI AI - Market Regime Detection
============================================================
Deterministic (rule-based) classifier that labels the current
market condition. The regime is given to the Groq AI as context
and used by the quantitative strategies.

Regimes:
    BULL_TREND        strong, rising, directional market
    BEAR_TREND        strong, falling, directional market
    SIDEWAYS          low directionality, range-bound
    HIGH_VOLATILITY   elevated volatility regime
    LOW_VOLATILITY    compressed volatility regime
    BREAKOUT          price escaping a recent range on high volume

The classifier is fully deterministic: same input -> same output.
"""

from dataclasses import dataclass, asdict


@dataclass
class RegimeResult:
    """Result of the regime classification."""
    regime: str            # primary label
    trend_strength: str    # STRONG / MODERATE / WEAK  (ADX based)
    description: str       # human-readable explanation

    def to_dict(self) -> dict:
        return asdict(self)


# Volatility percentile thresholds (annualized %)
HIGH_VOL_THRESHOLD = 40.0
LOW_VOL_THRESHOLD = 15.0

# ADX thresholds for trend strength
ADX_STRONG = 25.0
ADX_MODERATE = 18.0


def detect_regime(snapshot: dict) -> RegimeResult:
    """
    Classify the market regime from an indicator snapshot.

    Parameters
    ----------
    snapshot : dict from indicators.latest_snapshot() merged with signals.
        Required keys: price, sma20, sma50, adx, atr_pct, volatility,
        volume_ratio, resistance20, support20.

    Returns
    -------
    RegimeResult
    """
    price = float(snapshot.get("price", 0.0))
    sma20 = float(snapshot.get("sma20", price))
    sma50 = float(snapshot.get("sma50", price))
    adx = float(snapshot.get("adx", 0.0))
    volatility = float(snapshot.get("volatility", 0.0))
    volume_ratio = float(snapshot.get("volume_ratio", 1.0))
    resistance = float(snapshot.get("resistance20", price))
    support = float(snapshot.get("support20", price))

    # ---- Directional bias from moving-average structure ----
    if sma50 != 0:
        ma_spread_pct = (sma20 - sma50) / sma50 * 100
        price_vs_sma20 = (price - sma20) / sma20 * 100
    else:
        ma_spread_pct = 0.0
        price_vs_sma20 = 0.0

    bullish_structure = price > sma20 > sma50
    bearish_structure = price < sma20 < sma50

    # ---- Trend strength ----
    if adx >= ADX_STRONG:
        trend_strength = "STRONG"
    elif adx >= ADX_MODERATE:
        trend_strength = "MODERATE"
    else:
        trend_strength = "WEAK"

    # ---- Range position (breakout detection) ----
    range_size = max(resistance - support, 1e-9)
    near_resistance = resistance > 0 and price >= resistance * 0.995
    breakout_volume = volume_ratio >= 1.3

    # ------------------------------------------------------------
    # Classification order matters: chaos first (elevated volatility
    # without strong directionality), then breakout, then clean
    # trends, then quiet / sideways states.
    # ------------------------------------------------------------
    if volatility >= HIGH_VOL_THRESHOLD and not ((bullish_structure or bearish_structure) and trend_strength == "STRONG"):
        regime = "HIGH_VOLATILITY"
        description = (
            f"Volatility is elevated ({volatility:.0f}% annualized) without "
            f"a dominant directional structure (ADX {adx:.0f})."
        )
    elif bullish_structure and trend_strength in ("STRONG", "MODERATE"):
        regime = "BULL_TREND"
        description = (
            f"Price holds above rising MAs with {trend_strength.lower()} trend "
            f"strength (ADX {adx:.0f}); SMA20 is {ma_spread_pct:+.1f}% above SMA50."
        )
    elif bearish_structure and trend_strength in ("STRONG", "MODERATE"):
        regime = "BEAR_TREND"
        description = (
            f"Price sits below declining MAs with {trend_strength.lower()} trend "
            f"strength (ADX {adx:.0f}); SMA20 is {ma_spread_pct:+.1f}% below SMA50."
        )
    elif near_resistance and breakout_volume and price_vs_sma20 > 0:
        regime = "BREAKOUT"
        description = (
            f"Price is pressing the 20-bar high on {volume_ratio:.1f}x average "
            f"volume — potential upside breakout."
        )
    elif volatility <= LOW_VOL_THRESHOLD:
        regime = "LOW_VOLATILITY"
        description = (
            f"Volatility is compressed ({volatility:.0f}% annualized); "
            "conditions favor range tactics over trend following."
        )
    else:
        regime = "SIDEWAYS"
        description = (
            f"Mixed moving-average structure with weak directionality "
            f"(ADX {adx:.0f}) — range-bound conditions."
        )

    return RegimeResult(regime=regime, trend_strength=trend_strength, description=description)
