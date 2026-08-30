"""
Agent 1 — Market Analyst.

Converts the quantitative snapshot into a sentiment read.
Deterministic: same numbers → same output. No network.
"""

from agents.context import composite_score
from agents.schema import _clamp, _num


def analyze(market: dict) -> dict:
    market = market if isinstance(market, dict) else {}
    composite = composite_score(market)
    regime = str(market.get("regime", "SIDEWAYS")).upper()
    rsi = _num(market.get("rsi"), 50.0)
    adx = _num(market.get("adx"), 0.0)
    iv_rank = _num(market.get("iv_rank"), 50.0)
    price = _num(market.get("price"), 0.0)

    if regime in {"BULL_TREND", "BREAKOUT"} or composite >= 20:
        sentiment = "BULLISH"
    elif regime == "BEAR_TREND" or composite <= -20:
        sentiment = "BEARISH"
    else:
        sentiment = "NEUTRAL"

    # Confidence from |composite| with a modest ADX boost when a trend is labeled.
    confidence = _clamp(abs(composite) / 100.0, 0.15, 0.95)
    if adx >= 25:
        confidence = _clamp(confidence + 0.08, 0.15, 0.95)
    if regime == "SIDEWAYS":
        confidence = _clamp(confidence * 0.85, 0.15, 0.80)

    observations = [
        f"Regime {regime} with composite score {composite:+.1f}.",
        f"RSI {rsi:.1f}, ADX {adx:.1f}, IV Rank {iv_rank:.1f}.",
    ]
    if price:
        observations.append(f"Last price {price:.2f}.")

    return {
        "sentiment": sentiment,
        "confidence": round(float(confidence), 3),
        "observations": observations,
    }
