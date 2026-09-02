"""
agents/options_strategist.py
============================================================
Agent 3 - Options Strategist. The core deliverable.

Part 6 rule: encode the matrix FIRST as plain deterministic
dict/function. LLM refines it later. This file currently has
ONLY the deterministic part - it already produces a valid
TradeDecision with zero API calls. This is the fallback that
must always work.

Allowed structures ONLY (no naked shorts, no condors, no strangles):
  THETA:       CASH_SECURED_PUT, COVERED_CALL
  DIRECTIONAL: BULL_CALL_SPREAD, BEAR_PUT_SPREAD, LONG_CALL, LONG_PUT
"""

import sys
import os

_here = os.path.dirname(os.path.abspath(__file__))
_ai = os.path.dirname(_here)
_root = os.path.dirname(_ai)
sys.path.insert(0, _root)
sys.path.insert(0, _ai)

from agents.context import has_shares as account_has_shares
from agents.schema import validate_trade_decision

IV_HIGH_THRESHOLD = 50.0
IV_LOW_THRESHOLD = 30.0


def _iv_bucket(iv_rank: float) -> str:
    if iv_rank > IV_HIGH_THRESHOLD:
        return "HIGH"
    if iv_rank < IV_LOW_THRESHOLD:
        return "LOW"
    return "MID"


def matrix_lookup(regime: str, iv_rank: float, has_shares: bool = False) -> dict:
    """
    Part 6 matrix, encoded directly. Pure function: same input -> same
    output, always. Returns a raw (not-yet-validated) decision dict.
    """
    regime = str(regime).upper().strip()
    bucket = _iv_bucket(iv_rank)

    # MID bucket (30-50 IV rank) is a grey zone the matrix doesn't cover
    # explicitly -> capital preservation, no forced trade.
    if bucket == "MID":
        return {
            "action": "HOLD",
            "engine": "NONE",
            "strategy_type": "NONE",
            "reason_hint": f"IV Rank {iv_rank:.1f} is in the grey zone (30-50) - no strong edge either way.",
        }

    table = {
        ("BULL_TREND", "LOW"): {
            "action": "OPEN", "engine": "DIRECTIONAL", "strategy_type": "BULL_CALL_SPREAD",
            "reason_hint": "Bull trend with cheap premium - defined-risk upside via debit spread.",
        },
        ("BULL_TREND", "HIGH"): {
            "action": "OPEN", "engine": "THETA", "strategy_type": "CASH_SECURED_PUT",
            "reason_hint": "Bull trend with rich premium - get paid to buy the dip.",
        },
        ("BEAR_TREND", "LOW"): {
            "action": "OPEN", "engine": "DIRECTIONAL", "strategy_type": "BEAR_PUT_SPREAD",
            "reason_hint": "Bear trend with cheap premium - defined-risk downside via debit spread.",
        },
        ("BEAR_TREND", "HIGH"): {
            "action": "OPEN", "engine": "THETA", "strategy_type": "COVERED_CALL",
            "reason_hint": "Bear trend with rich premium - harvest premium (requires existing shares).",
        },
        ("SIDEWAYS", "HIGH"): {
            "action": "OPEN", "engine": "THETA", "strategy_type": "CASH_SECURED_PUT",
            "reason_hint": "Sideways market, rich premium - collect premium without a directional bet.",
        },
        ("SIDEWAYS", "LOW"): {
            "action": "HOLD", "engine": "NONE", "strategy_type": "NONE",
            "reason_hint": "Sideways market, cheap premium - nothing attractive, do not force a trade.",
        },
        ("BREAKOUT", "LOW"): {
            "action": "OPEN", "engine": "DIRECTIONAL", "strategy_type": "LONG_CALL",
            "reason_hint": "Breakout with cheap premium - pay for convex upside.",
        },
        ("HIGH_VOLATILITY", "HIGH"): {
            "action": "OPEN", "engine": "THETA", "strategy_type": "CASH_SECURED_PUT",
            "reason_hint": "High volatility regime, rich premium - sell fear with wide/low delta.",
        },
        ("LOW_VOLATILITY", "LOW"): {
            "action": "OPEN", "engine": "DIRECTIONAL", "strategy_type": "BULL_CALL_SPREAD",
            "reason_hint": "Low volatility regime, cheap premium - volatility is cheap, buy it via debit spread.",
        },
    }

    result = table.get((regime, bucket))
    if result is None:
        return {
            "action": "HOLD",
            "engine": "NONE",
            "strategy_type": "NONE",
            "reason_hint": f"Regime '{regime}' with IV bucket '{bucket}' is not in the matrix - capital preservation.",
        }

    # COVERED_CALL needs shares. If we don't have them, fall back to HOLD.
    if result["strategy_type"] == "COVERED_CALL" and not has_shares:
        return {
            "action": "HOLD",
            "engine": "NONE",
            "strategy_type": "NONE",
            "reason_hint": "Matrix suggested COVERED_CALL but no shares are held - cannot execute, holding instead.",
        }

    return dict(result)


def default_targets(strategy_type: str) -> dict:
    """Reasonable default DTE/delta/spread_width per strategy type."""
    defaults = {
        "CASH_SECURED_PUT":  {"target_dte": 21, "target_delta": 0.25, "spread_width": 0, "contracts": 1},
        "COVERED_CALL":      {"target_dte": 21, "target_delta": 0.25, "spread_width": 0, "contracts": 1},
        "BULL_CALL_SPREAD":  {"target_dte": 30, "target_delta": 0.35, "spread_width": 5, "contracts": 1},
        "BEAR_PUT_SPREAD":   {"target_dte": 30, "target_delta": 0.35, "spread_width": 5, "contracts": 1},
        "LONG_CALL":         {"target_dte": 30, "target_delta": 0.40, "spread_width": 0, "contracts": 1},
        "LONG_PUT":          {"target_dte": 30, "target_delta": 0.40, "spread_width": 0, "contracts": 1},
        "NONE":              {"target_dte": 0, "target_delta": 0.0, "spread_width": 0, "contracts": 0},
    }
    return defaults.get(strategy_type, defaults["NONE"])


def select_strategy(market: dict, account: dict | None = None, iv_rank: float | None = None) -> dict:
    """
    Deterministic strategist. No LLM call. Always produces a valid
    TradeDecision. This is the guaranteed fallback path mentioned in
    Part 5 Agent 3: "If Groq is unavailable, the matrix alone must
    still produce a valid decision."

    market : dict produced by build_market_context() in _playground.py
             (or equivalent). Composite score lives at market["score"]["composite"].
    account: dict with at least "open_positions" (int).
    iv_rank: if not passed explicitly, falls back to market["iv_rank"].
    """
    account = account or {}
    symbol = str(market.get("symbol", "UNKNOWN"))
    regime = str(market.get("regime", "SIDEWAYS")).upper()
    iv_rank = float(iv_rank) if iv_rank is not None else float(market.get("iv_rank", 62.0))
    composite = float(market.get("score", {}).get("composite", 0.0))
    has_shares = account_has_shares(account)

    picked = matrix_lookup(regime, iv_rank, has_shares=has_shares)
    strategy_type = picked["strategy_type"]
    targets = default_targets(strategy_type)

    key_factors = [
        f"IV Rank {iv_rank:.1f} -> {_iv_bucket(iv_rank)} premium regime",
        f"Regime {regime}",
        f"Composite score {composite:+.1f}",
    ]

    reason = (
        f"{picked['reason_hint']} Symbol {symbol}, IV Rank {iv_rank:.1f}, "
        f"regime {regime}, composite score {composite:+.1f}."
    )

    raw = {
        "action": picked["action"],
        "engine": picked["engine"],
        "symbol": symbol,
        "strategy_type": strategy_type,
        "target_dte": targets["target_dte"],
        "target_delta": targets["target_delta"],
        "spread_width": targets["spread_width"],
        "contracts": targets["contracts"],
        "confidence": 0.55 if picked["action"] == "OPEN" else 0.3,
        "risk": "MEDIUM" if picked["action"] == "OPEN" else "LOW",
        "reason": reason,
        "key_factors": key_factors,
        "invalidations": [
            f"IV Rank crosses back over the {IV_LOW_THRESHOLD:.0f}/{IV_HIGH_THRESHOLD:.0f} threshold",
            f"Regime changes away from {regime}",
        ],
        "regime": regime,
        "iv_rank": iv_rank,
        "devils_advocate": {
            "objection": "Not yet reviewed by Devil's Advocate agent.",
            "verdict": "PROCEED",
        },
        "agent_trace": ["options_strategist:local_policy"],
    }

    return validate_trade_decision(raw, symbol=symbol, source="local_policy")


if __name__ == "__main__":
    # Quick manual sanity check - run this file directly to test it.
    test_market = {
        "symbol": "NVDA", "regime": "BULL_TREND", "iv_rank": 62.0,
        "score": {"composite": 45.0},
    }
    import json
    print(json.dumps(select_strategy(test_market, {}, test_market["iv_rank"]), indent=2))