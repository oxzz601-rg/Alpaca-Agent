"""
agents/context.py
============================================================
Simple shapes for data that flows into the agents.
Not strict classes. Just dicts with known keys, so every agent
knows what to expect as input.

market dict (per symbol) - comes from existing indicator engine:
{
    "symbol": "NVDA",
    "price": 172.5,
    "regime": "SIDEWAYS",
    "trend_strength": 16,          # e.g. ADX
    "composite_score": 12.0,       # -100..100
    "iv_rank": 62.0,               # MOCK until backend sends real value
    "signals": ["RSI neutral", "Above SMA20"],
    "support": 172.0,
    "resistance": 181.0,
}

account dict:
{
    "equity": 100000.0,
    "cash": 40000.0,
    "open_positions": 2,
    "buying_power": 40000.0,
}

Use MOCK_IV_RANK below anywhere backend hasn't wired real IV Rank yet.
"""

MOCK_IV_RANK = 62.0

DEFAULT_ACCOUNT = {
    "equity": 100000.0,
    "cash": 100000.0,
    "open_positions": 0,
    "buying_power": 100000.0,
}


def with_mock_iv_rank(market: dict) -> dict:
    """If market dict has no iv_rank, fill it with the mock value."""
    if "iv_rank" not in market or market["iv_rank"] is None:
        market = dict(market)
        market["iv_rank"] = MOCK_IV_RANK
    return market


def composite_score(market: dict) -> float:
    """Read composite from either score.composite or composite_score."""
    if not isinstance(market, dict):
        return 0.0
    score = market.get("score")
    if isinstance(score, dict) and "composite" in score:
        try:
            return float(score["composite"])
        except (TypeError, ValueError):
            return 0.0
    try:
        return float(market.get("composite_score", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def has_shares(account: dict | None) -> bool:
    """True if the account already holds underlying shares (needed for covered calls)."""
    account = account or {}
    try:
        if float(account.get("open_positions", 0) or 0) > 0:
            return True
    except (TypeError, ValueError):
        pass
    try:
        if float(account.get("shares", 0) or 0) > 0:
            return True
    except (TypeError, ValueError):
        pass
    positions = account.get("positions") or []
    if isinstance(positions, list):
        for pos in positions:
            if not isinstance(pos, dict):
                continue
            qty = pos.get("qty", pos.get("quantity", 0))
            try:
                if float(qty or 0) > 0:
                    return True
            except (TypeError, ValueError):
                continue
    return False