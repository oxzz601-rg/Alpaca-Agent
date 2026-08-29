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