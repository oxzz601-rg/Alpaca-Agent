"""
agents/_playground.py
Run with:  python3 -m agents._playground
(guide says "py -m agents._playground" - that's Windows launcher syntax;
on Linux/Mac use python3 instead of py)

Builds a full market context offline (synthetic demo data, no network,
no Alpaca key needed) and runs the deterministic options_strategist
against it. This proves the AI brain's fallback path works end to end
before Groq or Alpaca are wired in.
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.alpaca_data import generate_demo_data
from analysis.indicators import calculate_indicators, latest_snapshot
from analysis.signals import generate_market_signals, compute_signal_scores
from analysis.regime import detect_regime

from agents.options_strategist import select_strategy
from agents.context import DEFAULT_ACCOUNT


def build_market_context(symbol: str = "NVDA", days: int = 300) -> dict:
    raw = generate_demo_data(days)
    data = calculate_indicators(raw)
    snap = latest_snapshot(data)
    market = generate_market_signals(snap)
    market.update(snap)
    market["score"] = compute_signal_scores(snap)
    reg = detect_regime({**snap, **market})
    market["regime"] = reg.regime
    market["trend_strength"] = reg.trend_strength
    market["iv_rank"] = 62.0  # mock until backend provides real IV Rank
    market["symbol"] = symbol  # build_market_context doesn't set this on its own - added here
    return market


if __name__ == "__main__":
    m = build_market_context()

    print("=== Market context (key fields) ===")
    print(json.dumps({
        k: m[k] for k in ["symbol", "price", "rsi", "adx", "regime", "trend_strength", "iv_rank"]
    }, indent=2, default=str))
    print("composite score:", m["score"]["composite"])

    print("\n=== Strategist decision (deterministic matrix, no LLM) ===")
    decision = select_strategy(m, DEFAULT_ACCOUNT, m["iv_rank"])
    print(json.dumps(decision, indent=2))