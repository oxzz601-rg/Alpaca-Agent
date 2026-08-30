"""
Agent 2 — Opportunity Scanner.

Ranks a universe of symbol market-dicts. Scoring is deterministic:
  |composite| × IV-fit × a small ADX/liquidity tilt.
"""

from agents.context import composite_score, with_mock_iv_rank
from agents.options_strategist import _iv_bucket
from agents.schema import _num


def _iv_fit(iv_rank: float) -> float:
    bucket = _iv_bucket(iv_rank)
    if bucket in {"HIGH", "LOW"}:
        return 1.0
    return 0.35


def _candidate_score(market: dict) -> float:
    composite = abs(composite_score(market))
    iv_rank = _num(market.get("iv_rank"), 50.0)
    adx = _num(market.get("adx"), 0.0)
    volume_ratio = _num(market.get("volume_ratio"), 1.0)
    iv_fit = _iv_fit(iv_rank)
    liquidity = _clamp_liq(volume_ratio)
    adx_tilt = 1.0 + min(adx, 40.0) / 200.0
    return round(composite * iv_fit * liquidity * adx_tilt, 2)


def _clamp_liq(volume_ratio: float) -> float:
    if volume_ratio <= 0:
        return 0.7
    return max(0.6, min(1.3, volume_ratio))


def _tradeable(market: dict, score: float) -> bool:
    bucket = _iv_bucket(_num(market.get("iv_rank"), 50.0))
    regime = str(market.get("regime", "")).upper()
    if bucket == "MID":
        return False
    if bucket == "HIGH" and regime in {"SIDEWAYS", "HIGH_VOLATILITY", "BULL_TREND"}:
        return True
    return score >= 12.0


def scan(universe: list, account: dict | None = None) -> list:
    """
    Rank candidates. Each item:
      {symbol, score, tradeable, why, market}
    """
    account = account or {}
    ranked = []
    for item in universe or []:
        if not isinstance(item, dict):
            continue
        market = with_mock_iv_rank(dict(item))
        symbol = str(market.get("symbol", "UNKNOWN")).upper()
        score = _candidate_score(market)
        tradeable = _tradeable(market, score)
        bucket = _iv_bucket(_num(market.get("iv_rank"), 50.0))
        why = (
            f"{symbol} score {score:.1f} from |composite| {abs(composite_score(market)):.1f} "
            f"and IV bucket {bucket}."
        )
        if not tradeable:
            why += " Not tradeable now (grey-zone IV or weak setup)."
        ranked.append({
            "symbol": symbol,
            "score": score,
            "tradeable": tradeable,
            "why": why,
            "market": market,
        })

    ranked.sort(key=lambda row: (row["tradeable"], row["score"]), reverse=True)
    return ranked
