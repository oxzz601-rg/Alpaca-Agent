"""Build a market dict for the AI: live Alpaca bars, or synthetic demo data."""

from __future__ import annotations

from typing import Any

from analysis.indicators import calculate_indicators, latest_snapshot
from analysis.regime import detect_regime
from analysis.signals import compute_signal_scores, generate_market_signals
from data.alpaca_data import generate_demo_data, get_historical_data
from trading.iv_rank import attach_iv_rank


def _from_frame(raw, symbol: str, current_iv: float | None = None) -> dict[str, Any]:
    data = calculate_indicators(raw)
    snap = latest_snapshot(data)
    market = generate_market_signals(snap)
    market.update(snap)
    market["score"] = compute_signal_scores(snap)
    reg = detect_regime({**snap, **market})
    market["regime"] = reg.regime
    market["trend_strength"] = reg.trend_strength
    market["symbol"] = symbol.upper()
    return attach_iv_rank(market, raw["close"], current_iv)


def build_market_context(symbol: str = "AAPL", days: int = 300, live: bool = False) -> dict[str, Any]:
    symbol = (symbol or "AAPL").upper()
    if live:
        try:
            raw = get_historical_data(symbol=symbol, days=days)
            market = _from_frame(raw, symbol)
            market["data_source"] = "alpaca"
            return market
        except Exception:
            pass
    market = _from_frame(generate_demo_data(days), symbol)
    market["data_source"] = "synthetic"
    return market
