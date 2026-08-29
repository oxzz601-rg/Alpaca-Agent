"""Bounded in-app assistant for the QuantNova terminal."""

from __future__ import annotations

import os
import re

from config import AI_MODEL, GROQ_API_KEY, REQUEST_TIMEOUT

SYSTEM_PROMPT = """You are the QuantNova in-app assistant.
You help with the paper-trading app, quantitative signals, backtesting,
 risk controls, and paper execution. You may suggest changes, but you cannot
 edit files, change credentials, place orders, or change risk limits.
Keep answers concise and practical. This app is paper/simulation only.
"""


def parse_command(question: str) -> str | None:
    """Map natural-language requests to explicit, non-destructive app commands."""
    text = str(question or "").lower().strip()
    if re.search(r"\b(reset|restart|clear)\b.*\b(paper|portfolio|account|simulation)", text):
        return "RESET_PAPER"
    if re.search(r"\b(refresh|reload|update)\b.*\b(analysis|data|market)", text):
        return "REFRESH_ANALYSIS"
    if re.search(r"\b(simulate|execute|place)\b.*\b(decision|trade|signal|it|this)", text):
        return "EXECUTE_DECISION"
    return None


def _offline_answer(question: str) -> str:
    """Return useful guidance when the optional chat model is unavailable."""
    lower = question.lower()
    if any(word in lower for word in ("backtest", "win rate", "performance", "strategy")):
        return (
            "Use the OUT-OF-SAMPLE tab as the honest performance check. Compare "
            "return, profit factor, drawdown, Sharpe, trade count, and benchmark "
            "alpha; win rate alone is not enough."
        )
    if any(word in lower for word in ("change", "edit", "modify", "fix")):
        return (
            "I can suggest or implement a specific code change through the main "
            "coding assistant, but this chat panel cannot edit files, credentials, "
            "risk limits, or place trades by itself."
        )
    return (
        "Chat is available for project architecture, signals, risk, backtests, "
        "and paper execution. Configure GROQ_API_KEY for natural-language answers."
    )


def answer_question(question: str, context: dict | None = None) -> dict:
    """Answer a bounded project question using Groq when configured."""
    question = str(question or "").strip()
    if not question:
        return {"answer": "Ask me about the project, strategy, risk, backtests, or the hackathon.", "source": "local"}

    if not GROQ_API_KEY:
        return {"answer": _offline_answer(question), "source": "local"}

    try:
        from groq import Groq

        client = Groq(api_key=GROQ_API_KEY, timeout=REQUEST_TIMEOUT)
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"PROJECT CONTEXT:\n{context or {}}\n\nQUESTION:\n{question}",
                },
            ],
            temperature=0.2,
            max_tokens=500,
        )
        answer = (response.choices[0].message.content or "").strip()
        if answer:
            return {"answer": answer, "source": "groq"}
    except Exception:
        pass

    return {"answer": _offline_answer(question), "source": "local"}
