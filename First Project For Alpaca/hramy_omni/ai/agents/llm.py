"""
Optional Groq refinement for the options agents.

The deterministic matrix is always the source of truth. This module may
improve the reason / confidence / HOLD veto. Any failure returns the
matrix decision unchanged. Tests never need a Groq key.
"""

from __future__ import annotations

import json

from agents.prompts import STRATEGIST_SYSTEM, strategist_user
from agents.schema import (
    FAIL_BAD_JSON,
    FAIL_NETWORK,
    FAIL_NOT_CONFIGURED,
    FAIL_RATE_LIMIT,
    FAIL_SDK_MISSING,
    FAIL_TIMEOUT,
    FAIL_UNKNOWN,
    validate_trade_decision,
)


def llm_enabled() -> bool:
    try:
        from config import GROQ_API_KEY
        return bool(GROQ_API_KEY)
    except Exception:
        return False


def _classify(exc: Exception) -> str:
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if "timeout" in name or "timed out" in text or "timeout" in text:
        return FAIL_TIMEOUT
    if ("rate" in text and "limit" in text) or "429" in text:
        return FAIL_RATE_LIMIT
    if "connect" in name or "connection" in text or "network" in text:
        return FAIL_NETWORK
    if "auth" in text or "401" in text or "api key" in text:
        return FAIL_NOT_CONFIGURED
    if "json" in text and ("valid" in text or "failed_generation" in text):
        return FAIL_BAD_JSON
    return FAIL_UNKNOWN


def _extract_json(content: str) -> dict:
    try:
        from groq_engine import extract_json
        return extract_json(content)
    except ImportError:
        try:
            from ai.groq_engine import extract_json
            return extract_json(content)
        except ImportError:
            text = (content or "").strip()
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end > start:
                return json.loads(text[start:end + 1])
            raise json.JSONDecodeError("No JSON object found", text, 0)


def refine_strategy(
    base_decision: dict,
    market: dict,
    account: dict | None = None,
    lessons: list | None = None,
) -> dict:
    """
    Ask Groq to refine a matrix TradeDecision. Never raises.
    On any failure, return the original matrix decision.
    """
    base_decision = base_decision if isinstance(base_decision, dict) else {}
    market = market if isinstance(market, dict) else {}
    account = account or {}
    symbol = str(base_decision.get("symbol") or market.get("symbol") or "")

    if not llm_enabled():
        return base_decision

    try:
        from groq import Groq
        from config import AI_MODEL, GROQ_API_KEY, REQUEST_TIMEOUT
    except ImportError:
        fallback = dict(base_decision)
        fallback["failure_type"] = FAIL_SDK_MISSING
        return fallback

    matrix_hint = (
        f"{base_decision.get('action')} {base_decision.get('engine')} "
        f"{base_decision.get('strategy_type')} dte={base_decision.get('target_dte')} "
        f"delta={base_decision.get('target_delta')}"
    )
    user = strategist_user(market, account, matrix_hint, lessons or [])
    user += (
        "\nReturn a TradeDecision JSON with keys: action, engine, symbol, strategy_type, "
        "target_dte, target_delta, spread_width, contracts, confidence, risk, reason, "
        "key_factors, invalidations, regime, iv_rank. "
        "You may veto to HOLD. You may not invent strikes or prices."
    )

    try:
        client = Groq(api_key=GROQ_API_KEY, timeout=REQUEST_TIMEOUT)
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": STRATEGIST_SYSTEM},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=1600,
        )
        content = response.choices[0].message.content
        if not content or not str(content).strip():
            return base_decision
        parsed = _extract_json(content)
        if not isinstance(parsed, dict):
            return base_decision

        # Keep server-computed facts; LLM may refine action/reason/sizing targets.
        parsed.setdefault("symbol", symbol)
        parsed.setdefault("regime", market.get("regime", base_decision.get("regime")))
        parsed.setdefault("iv_rank", market.get("iv_rank", base_decision.get("iv_rank")))
        parsed.setdefault("devils_advocate", base_decision.get("devils_advocate"))
        parsed["agent_trace"] = list(base_decision.get("agent_trace") or [])
        refined = validate_trade_decision(parsed, symbol=symbol, source="groq")
        if refined.get("source") == "fallback":
            out = dict(base_decision)
            out["failure_type"] = FAIL_BAD_JSON
            return out
        return refined
    except json.JSONDecodeError:
        return {**base_decision, "failure_type": FAIL_BAD_JSON}
    except Exception as exc:
        return {**base_decision, "failure_type": _classify(exc)}
