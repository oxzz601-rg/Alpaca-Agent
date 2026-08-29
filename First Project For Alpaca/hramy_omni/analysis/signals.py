"""
HRAMY OMNI AI - Market Signal Detection & Multi-Signal Scoring
============================================================
Converts computed indicator values into interpretable signals AND
a normalized multi-signal composite score.

The composite score is an INPUT to the Groq AI — it never forces
the AI's final decision. The AI is free to disagree with it.

Score components (each normalized to [-1, +1]):
    trend        MA structure + price position
    momentum     10-day rate of change
    rsi          mean-reversion positioning
    macd         trend/momentum crossover state
    volume       participation confirmation
    volatility   risk regime penalty/bonus

Composite = weighted sum, reported on a [-100, +100] scale.
"""

from typing import List, Optional

# Component weights (sum = 1.0) — complete 8-factor multi-signal suite.
SCORE_WEIGHTS = {
    "trend": 0.20,
    "momentum": 0.15,
    "rsi": 0.15,
    "macd": 0.15,
    "volume": 0.10,
    "volatility": 0.10,
    "adx": 0.08,
    "regime": 0.07,
}



# ============================================================
# Signal generation
# ============================================================

def generate_market_signals(snapshot: dict) -> dict:
    """
    Build a signal summary from the latest indicator snapshot.

    Parameters
    ----------
    snapshot : dict from indicators.latest_snapshot()

    Returns
    -------
    dict with:
        signals           : list of human-readable signal strings
        trend             : BULLISH | BEARISH | NEUTRAL
        rsi_signal        : OVERBOUGHT | OVERSOLD | NEUTRAL
        momentum_signal   : POSITIVE | NEGATIVE | NEUTRAL
        volume_signal     : HIGH | LOW | NORMAL
        volatility_label  : LOW | MODERATE | HIGH
    """
    price = snapshot["price"]
    sma20 = snapshot["sma20"]
    sma50 = snapshot["sma50"]
    ema20 = snapshot.get("ema20", sma20)
    rsi = snapshot["rsi"]
    momentum = snapshot["momentum"]
    volatility = snapshot["volatility"]
    volume_ratio = snapshot.get("volume_ratio", 1.0)
    macd_hist = snapshot.get("macd_hist", 0.0)
    adx = snapshot.get("adx", 0.0)
    bb_percent_b = snapshot.get("bb_percent_b", 0.5)
    vwap = snapshot.get("vwap20", price)

    signals: List[str] = []

    # ----------------------------------------------------------
    # Trend
    # ----------------------------------------------------------
    if price > sma20 > sma50:
        trend = "BULLISH"
        signals.append("Price is above SMA20 and SMA20 is above SMA50.")
    elif price < sma20 < sma50:
        trend = "BEARISH"
        signals.append("Price is below SMA20 and SMA20 is below SMA50.")
    else:
        trend = "NEUTRAL"
        signals.append("Moving averages do not show a strong trend.")

    if vwap > 0:
        vwap_position = "above" if price > vwap else "below"
        signals.append(f"Price is {vwap_position} the 20-day VWAP.")

    # ----------------------------------------------------------
    # RSI
    # ----------------------------------------------------------
    if rsi >= 70:
        rsi_signal = "OVERBOUGHT"
        signals.append("RSI indicates potentially overbought conditions.")
    elif rsi <= 30:
        rsi_signal = "OVERSOLD"
        signals.append("RSI indicates potentially oversold conditions.")
    else:
        rsi_signal = "NEUTRAL"
        signals.append("RSI is in a neutral range.")

    # ----------------------------------------------------------
    # Momentum
    # ----------------------------------------------------------
    if momentum > 2:
        momentum_signal = "POSITIVE"
    elif momentum < -2:
        momentum_signal = "NEGATIVE"
    else:
        momentum_signal = "NEUTRAL"
    signals.append(
        f"10-day momentum is {momentum:+.1f}% ({momentum_signal.lower()})."
    )

    # ----------------------------------------------------------
    # MACD
    # ----------------------------------------------------------
    if macd_hist > 0:
        macd_label = "BULLISH"
        signals.append("MACD histogram is positive (bullish crossover state).")
    elif macd_hist < 0:
        macd_label = "BEARISH"
        signals.append("MACD histogram is negative (bearish crossover state).")
    else:
        macd_label = "NEUTRAL"
        signals.append("MACD is at equilibrium.")

    # ----------------------------------------------------------
    # Volume
    # ----------------------------------------------------------
    if volume_ratio > 1.5:
        volume_signal = "HIGH"
        signals.append("Trading volume is significantly above average.")
    elif volume_ratio < 0.7:
        volume_signal = "LOW"
        signals.append("Trading volume is below average.")
    else:
        volume_signal = "NORMAL"
        signals.append("Trading volume is near its average.")

    # ----------------------------------------------------------
    # Volatility classification
    # ----------------------------------------------------------
    if volatility > 40:
        volatility_label = "HIGH"
        signals.append("Annualized volatility is elevated.")
    elif volatility < 15:
        volatility_label = "LOW"
        signals.append("Annualized volatility is low.")
    else:
        volatility_label = "MODERATE"
        signals.append("Annualized volatility is moderate.")

    # ----------------------------------------------------------
    # ADX / Bollinger / EMA annotations
    # ----------------------------------------------------------
    adx_label = (
        "STRONG" if adx >= 25 else ("MODERATE" if adx >= 18 else "WEAK")
    )
    if bb_percent_b >= 1.0:
        signals.append("Price closed above the upper Bollinger band.")
    elif bb_percent_b <= 0.0:
        signals.append("Price closed below the lower Bollinger band.")

    if ema20 and price > ema20 and not (price > sma20):
        signals.append("Price holds above EMA20 despite mixed SMA structure.")

    return {
        "signals": signals,
        "trend": trend,
        "rsi_signal": rsi_signal,
        "momentum_signal": momentum_signal,
        "macd_signal": macd_label,
        "volume_signal": volume_signal,
        "volatility_label": volatility_label,
        "adx_label": adx_label,
    }


def build_signal_matrix(market: dict) -> list:
    """
    Build the display-oriented signal matrix rows.
    """
    return [
        {"Signal": "Trend", "Status": market["trend"]},
        {"Signal": "RSI", "Status": market["rsi_signal"]},
        {"Signal": "Momentum", "Status": market["momentum_signal"]},
        {"Signal": "MACD", "Status": market.get("macd_signal", "NEUTRAL")},
        {"Signal": "Volume", "Status": market["volume_signal"]},
        {"Signal": "Volatility", "Status": market["volatility_label"]},
        {"Signal": "ADX Strength", "Status": market.get("adx_label", "WEAK")},
        {"Signal": "Regime", "Status": market.get("regime", "N/A")},
    ]


# ============================================================
# Multi-signal composite score
# ============================================================

def _clip(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def compute_signal_scores(snapshot: dict) -> dict:
    """
    Compute normalized component scores and the weighted composite.

    Each component maps its raw indicator to [-1, +1]:

        trend       MA alignment (full/partial credit)
        momentum    momentum / 8  (saturates at +-8%)
        rsi         mean-reversion leaning, trend-adjusted
        macd        histogram relative to MACD line
        volume      direction-aware participation
        volatility  calm regimes bonus, chaos penalty

    Returns dict with components, composite (-100..+100), notes, weights.
    """
    price = snapshot["price"]
    sma20 = snapshot["sma20"]
    sma50 = snapshot["sma50"]

    # ---- Trend ----
    if price > sma20 > sma50:
        trend_score = 1.0
    elif price < sma20 < sma50:
        trend_score = -1.0
    elif sma20 > sma50:
        trend_score = 0.3
    elif sma20 < sma50:
        trend_score = -0.3
    else:
        trend_score = 0.0

    # ---- Momentum ----
    momentum_val = snapshot.get("momentum", 0.0)
    momentum_score = _clip(momentum_val / 8.0)

    # ---- RSI (mean-reversion leaning, adjusted by trend context) ----
    rsi_val = snapshot.get("rsi", 50.0)
    rsi_raw = (rsi_val - 50.0) / 25.0
    if trend_score >= 0.9:
        # In a strong uptrend an overbought RSI is only mildly negative.
        rsi_raw = rsi_raw if rsi_val < 70 else -(rsi_val - 70) / 30.0 * 0.5
    elif trend_score <= -0.9:
        rsi_raw = rsi_raw if rsi_val > 30 else (30 - rsi_val) / 30.0 * -0.5
    rsi_score = _clip(rsi_raw)

    # ---- MACD ----
    macd_line = snapshot.get("macd", 0.0)
    hist = snapshot.get("macd_hist", 0.0)
    denom = abs(macd_line) + 1e-9
    macd_score = _clip(hist / denom)

    # ---- Volume (direction aware) ----
    volume_ratio = snapshot.get("volume_ratio", 1.0)
    direction = 1.0 if momentum_val >= 0 else -1.0
    vol_component = _clip(volume_ratio - 1.0)
    volume_score = direction * max(0.0, vol_component)

    # ---- Volatility regime ----
    volatility = snapshot.get("volatility", 25.0)
    if volatility <= 20:
        volatility_score = 0.5
    elif volatility <= 35:
        volatility_score = 0.0
    elif volatility <= 55:
        volatility_score = -0.5
    else:
        volatility_score = -1.0

    # ---- ADX (trend strength confirmation) ----
    adx_val = snapshot.get("adx", 0.0)
    direction_sign = 1.0 if trend_score > 0 else (-1.0 if trend_score < 0 else 0.0)
    adx_normalized = min(1.0, max(0.0, (adx_val - 15.0) / 20.0)) if adx_val >= 15.0 else 0.0
    adx_score = direction_sign * adx_normalized

    # ---- Market Regime ----
    regime_str = str(snapshot.get("regime", "")).upper()
    if regime_str in ("BULL_TREND", "BREAKOUT"):
        regime_score = 1.0
    elif regime_str == "BEAR_TREND":
        regime_score = -1.0
    elif regime_str == "HIGH_VOLATILITY":
        regime_score = -0.5
    elif regime_str == "LOW_VOLATILITY":
        regime_score = 0.2
    else:
        regime_score = 0.0

    components = {
        "trend": round(trend_score, 3),
        "momentum": round(momentum_score, 3),
        "rsi": round(rsi_score, 3),
        "macd": round(macd_score, 3),
        "volume": round(volume_score, 3),
        "volatility": round(volatility_score, 3),
        "adx": round(adx_score, 3),
        "regime": round(regime_score, 3),
    }

    composite = sum(
        SCORE_WEIGHTS[name] * value for name, value in components.items()
    )
    # Scale [-1..1] weighted sum to the reported [-100..+100] band.
    composite_scaled = round(_clip(composite * 100.0, -100.0, 100.0), 1)

    notes = {
        "trend": _describe_trend(trend_score),
        "momentum": f"Momentum contributes {components['momentum']:+.2f} ({momentum_val:+.1f}%).",
        "rsi": f"RSI({rsi_val:.0f}) contributes {components['rsi']:+.2f}.",
        "macd": f"MACD histogram contributes {components['macd']:+.2f}.",
        "volume": f"Volume ratio ({volume_ratio:.2f}x) contributes {components['volume']:+.2f}.",
        "volatility": f"Volatility ({volatility:.0f}%) contributes {components['volatility']:+.2f}.",
        "adx": f"ADX({adx_val:.0f}) contributes {components['adx']:+.2f}.",
        "regime": f"Regime ({regime_str or 'N/A'}) contributes {components['regime']:+.2f}.",
    }

    return {
        "components": components,
        "composite": composite_scaled,
        "notes": notes,
        "weights": SCORE_WEIGHTS,
    }


def _describe_trend(score: float) -> str:
    if score >= 0.9:
        return "Perfect bullish MA alignment."
    if score >= 0.2:
        return "Partially bullish MA structure."
    if score <= -0.9:
        return "Perfect bearish MA alignment."
    if score <= -0.2:
        return "Partially bearish MA structure."
    return "Mixed moving-average structure."