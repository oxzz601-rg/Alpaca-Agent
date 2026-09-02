"""
Agent 6 — Attribution / Memory.

Stores one-line lessons after closed trades and feeds the last N
relevant lessons back into later strategist context.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

DEFAULT_LESSONS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures",
    "lessons.json",
)


def _read(path: str) -> list:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, list) else []
    except FileNotFoundError:
        return []
    except (OSError, json.JSONDecodeError):
        return []


def _write(path: str, lessons: list) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(lessons, handle, indent=2)


def load_lessons(path: str | None = None) -> list:
    return _read(path or DEFAULT_LESSONS_PATH)


def relevant_lessons(symbol: str = "", n: int = 5, path: str | None = None) -> list:
    """Return the last N lesson strings, preferring the same symbol."""
    lessons = load_lessons(path)
    symbol = str(symbol or "").upper()
    texts = []
    for item in reversed(lessons):
        if isinstance(item, str):
            texts.append(item)
            continue
        if not isinstance(item, dict):
            continue
        item_symbol = str(item.get("symbol", "")).upper()
        lesson = str(item.get("lesson", "")).strip()
        if not lesson:
            continue
        if symbol and item_symbol and item_symbol != symbol:
            continue
        texts.append(lesson)
        if len(texts) >= n:
            break
    if len(texts) < n:
        for item in reversed(lessons):
            if not isinstance(item, dict):
                continue
            lesson = str(item.get("lesson", "")).strip()
            if lesson and lesson not in texts:
                texts.append(lesson)
            if len(texts) >= n:
                break
    return texts[:n]


def record_lesson(
    closed_trade: dict,
    path: str | None = None,
) -> dict:
    """
    Append a one-line lesson for a closed trade.
    closed_trade keys: symbol, strategy_type, pnl, reason, exit_reason
    """
    path = path or DEFAULT_LESSONS_PATH
    closed_trade = closed_trade if isinstance(closed_trade, dict) else {}
    symbol = str(closed_trade.get("symbol", "UNKNOWN")).upper()
    strategy = str(closed_trade.get("strategy_type", "NONE")).upper()
    pnl = closed_trade.get("pnl", closed_trade.get("pnl_percent", 0))
    try:
        pnl_num = float(pnl)
    except (TypeError, ValueError):
        pnl_num = 0.0
    outcome = "won" if pnl_num > 0 else "lost" if pnl_num < 0 else "flat"
    exit_reason = str(closed_trade.get("exit_reason", closed_trade.get("reason", "unspecified")))
    lesson = (
        f"{symbol} {strategy} {outcome} ({pnl_num:+.2f}): {exit_reason[:180]}"
    )
    entry = {
        "symbol": symbol,
        "strategy_type": strategy,
        "pnl": pnl_num,
        "lesson": lesson,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    lessons = load_lessons(path)
    lessons.append(entry)
    _write(path, lessons)
    return entry
