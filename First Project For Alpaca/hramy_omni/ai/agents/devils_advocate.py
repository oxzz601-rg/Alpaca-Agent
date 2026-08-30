"""
Agent 4 — Devil's Advocate.

Argues against a proposed TradeDecision and votes PROCEED or BLOCK.
BLOCK is applied later by schema.validate_trade_decision (OPEN → HOLD).
"""

from agents.context import composite_score
from agents.schema import VALID_STRATEGY_TYPES, _num


def review(decision: dict, market: dict) -> dict:
    """
    Return {objection, verdict}. Never raises.
    """
    decision = decision if isinstance(decision, dict) else {}
    market = market if isinstance(market, dict) else {}

    action = str(decision.get("action", "HOLD")).upper()
    strategy = str(decision.get("strategy_type", "NONE")).upper()
    if strategy not in VALID_STRATEGY_TYPES:
        strategy = "NONE"

    rsi = _num(market.get("rsi"), 50.0)
    iv_rank = _num(decision.get("iv_rank", market.get("iv_rank")), 50.0)
    composite = composite_score(market)
    regime = str(market.get("regime", "")).upper()

    if action != "OPEN":
        return {
            "objection": "No new risk is being taken; standing down does not need a veto.",
            "verdict": "PROCEED",
        }

    # Grey-zone IV should not produce an OPEN; if it did, block it.
    if 30.0 <= iv_rank <= 50.0:
        return {
            "objection": f"IV Rank {iv_rank:.1f} sits in the 30-50 grey zone with no clear buy-vs-sell edge.",
            "verdict": "BLOCK",
        }

    # Selling cash-secured puts into an oversold tape is crash-prone.
    if strategy == "CASH_SECURED_PUT" and rsi <= 30:
        return {
            "objection": f"RSI {rsi:.1f} is oversold; selling a cash-secured put here leans into crash risk.",
            "verdict": "BLOCK",
        }

    # Buying calls into extreme overbought.
    if strategy in {"LONG_CALL", "BULL_CALL_SPREAD"} and rsi >= 75:
        return {
            "objection": f"RSI {rsi:.1f} is overbought; paying for upside here has a poor entry.",
            "verdict": "BLOCK",
        }

    # Buying puts into extreme oversold.
    if strategy in {"LONG_PUT", "BEAR_PUT_SPREAD"} and rsi <= 25:
        return {
            "objection": f"RSI {rsi:.1f} is already oversold; chasing downside with a debit structure is late.",
            "verdict": "BLOCK",
        }

    # Directional engine with almost no composite evidence.
    engine = str(decision.get("engine", "NONE")).upper()
    if engine == "DIRECTIONAL" and abs(composite) < 8:
        return {
            "objection": f"Composite score {composite:+.1f} is too weak to justify a directional debit.",
            "verdict": "BLOCK",
        }

    # Thesis fights the regime (should be rare if the matrix is used).
    if strategy in {"LONG_CALL", "BULL_CALL_SPREAD"} and regime == "BEAR_TREND":
        return {
            "objection": "Bullish structure proposed inside a BEAR_TREND regime.",
            "verdict": "BLOCK",
        }
    if strategy in {"LONG_PUT", "BEAR_PUT_SPREAD"} and regime == "BULL_TREND":
        return {
            "objection": "Bearish structure proposed inside a BULL_TREND regime.",
            "verdict": "BLOCK",
        }

    return {
        "objection": (
            f"Could still be wrong: regime {regime}, IV Rank {iv_rank:.1f}, "
            f"RSI {rsi:.1f} — but the numbers do not currently veto {strategy}."
        ),
        "verdict": "PROCEED",
    }
