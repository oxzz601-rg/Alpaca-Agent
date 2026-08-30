"""Autonomous agent loop for the Alpaca hackathon flow."""

from __future__ import annotations


class AutonomousAgentLoop:
    """Minimal autonomous loop that makes decisions from a signal snapshot."""

    def __init__(self, min_confidence: float = 0.55):
        self.min_confidence = float(min_confidence)

    def run_once(self, context: dict) -> dict:
        symbol = str(context.get("symbol") or "AAPL").upper()
        signal = str(context.get("signal") or "neutral").lower()
        confidence = float(context.get("confidence", 0.0) or 0.0)
        cash = float(context.get("cash", 0.0) or 0.0)
        shares = float(context.get("shares", 0.0) or 0.0)
        equity = float(context.get("equity", cash) or 0.0)

        if confidence < self.min_confidence:
            return {
                "symbol": symbol,
                "decision": "HOLD",
                "confidence": confidence,
                "reason": "Autonomous agent loop blocked: signal confidence is below the minimum threshold.",
                "cash": cash,
                "shares": shares,
                "equity": equity,
            }

        if signal in {"bullish", "buy", "positive"}:
            return {
                "symbol": symbol,
                "decision": "BUY",
                "confidence": confidence,
                "reason": "Autonomous agent loop approved a bullish trade under the risk and confidence gate.",
                "cash": cash,
                "shares": shares,
                "equity": equity,
            }

        if signal in {"bearish", "sell", "negative"}:
            return {
                "symbol": symbol,
                "decision": "SELL",
                "confidence": confidence,
                "reason": "Autonomous agent loop approved a bearish exit under the risk and confidence gate.",
                "cash": cash,
                "shares": shares,
                "equity": equity,
            }

        return {
            "symbol": symbol,
            "decision": "HOLD",
            "confidence": confidence,
            "reason": "Autonomous agent loop held the position because the signal was neutral and not actionable.",
            "cash": cash,
            "shares": shares,
            "equity": equity,
        }
