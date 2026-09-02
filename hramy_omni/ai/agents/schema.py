"""
HRAMY OMNI AI - agents/schema.py
============================================================
This file is THE CONTRACT (Part 3 of the guide).

The AI brain returns EXACTLY this object shape, always, no matter
what happened internally (Groq succeeded, Groq failed, local policy
ran instead). The backend only ever has to deserialize ONE shape.

Reuses the validation philosophy from ../ai/groq_engine.py:
    _num()               -> coerce to safe float
    _clamp()              -> clamp into a valid range
    _clean_string_list()  -> coerce to a clean list[str]
    _safe_fallback()      -> guaranteed-valid HOLD object on any failure

Nothing in here calls Groq. This is pure data + validation.
"""

import math

# ------------------------------------------------------------------
# Enums (Part 3 contract - do not add values without updating backend)
# ------------------------------------------------------------------

VALID_ACTIONS = {"OPEN", "CLOSE", "HOLD"}
VALID_ENGINES = {"THETA", "DIRECTIONAL", "NONE"}
VALID_STRATEGY_TYPES = {
    "CASH_SECURED_PUT",
    "COVERED_CALL",
    "BULL_CALL_SPREAD",
    "BEAR_PUT_SPREAD",
    "LONG_CALL",
    "LONG_PUT",
    "NONE",
}
VALID_RISK = {"LOW", "MEDIUM", "HIGH"}
VALID_REGIMES = {
    "BULL_TREND",
    "BEAR_TREND",
    "SIDEWAYS",
    "BREAKOUT",
    "HIGH_VOLATILITY",
    "LOW_VOLATILITY",
}
VALID_VERDICTS = {"PROCEED", "BLOCK"}
VALID_SOURCES = {"groq", "local_policy", "fallback"}

# Frontend pipeline visualizer stage names (Part 10). Match exactly.
TRACE_MARKET_ANALYST = "MARKET_ANALYST"
TRACE_OPPORTUNITY_SCANNER = "OPPORTUNITY_SCANNER"
TRACE_OPTIONS_STRATEGIST = "OPTIONS_STRATEGIST"
TRACE_RISK_MANAGER = "RISK_MANAGER"
TRACE_EXECUTION = "EXECUTION"
TRACE_PORTFOLIO_MONITOR = "PORTFOLIO_MONITOR"

AI_TRACE_STAGES = (
    TRACE_MARKET_ANALYST,
    TRACE_OPPORTUNITY_SCANNER,
    TRACE_OPTIONS_STRATEGIST,
)

# Sane numeric bounds - the AI can NEVER propose outside these,
# no matter what the LLM says. This is what "clamping" means here.
DTE_MIN, DTE_MAX = 1, 60
DELTA_MIN, DELTA_MAX = 0.05, 0.60
SPREAD_WIDTH_MIN, SPREAD_WIDTH_MAX = 1, 20
CONTRACTS_MIN, CONTRACTS_MAX = 0, 10

# Failure type codes – safe to log; never contain secrets
FAIL_NOT_CONFIGURED = "not_configured"
FAIL_SDK_MISSING = "sdk_missing"
FAIL_TIMEOUT = "timeout"
FAIL_RATE_LIMIT = "rate_limit"
FAIL_BAD_JSON = "invalid_json"
FAIL_SCHEMA = "schema_violation"
FAIL_NETWORK = "network_error"
FAIL_UNKNOWN = "unknown_error"


# ------------------------------------------------------------------
# Shared helpers (mirrors groq_engine.py exactly, on purpose)
# We copied them here so this file is self-contained and portable.
# ------------------------------------------------------------------

def _num(value, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(result):
        return default
    return result


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _clean_string_list(value, max_items=10, max_len=400) -> list:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    cleaned = []
    for item in value:
        text = str(item).strip()
        if text:
            cleaned.append(text[:max_len])
    return cleaned[:max_items]


# ------------------------------------------------------------------
# The guaranteed-safe fallback object
# ------------------------------------------------------------------

def safe_fallback(reason: str, failure_type: str = FAIL_UNKNOWN, symbol: str = "") -> dict:
    """
    Always returns a 100% contract-valid TradeDecision.
    Call this on ANY error, anywhere in the pipeline, and you are safe.
    """
    return {
        "action": "HOLD",
        "engine": "NONE",
        "symbol": symbol,
        "strategy_type": "NONE",
        "target_dte": 0,
        "target_delta": 0.0,
        "spread_width": 0,
        "contracts": 0,
        "confidence": 0.0,
        "risk": "HIGH",
        "reason": str(reason)[:500],
        "key_factors": [],
        "invalidations": [],
        "regime": "SIDEWAYS",
        "iv_rank": 0.0,
        "devils_advocate": {
            "objection": "Decision engine failed; defaulting to HOLD.",
            "verdict": "BLOCK",
        },
        "source": "fallback",
        "failure_type": failure_type,
        "agent_trace": [],
    }


# ------------------------------------------------------------------
# The validator/clamp gate - the ONLY function allowed to produce
# a "real" (non-fallback) TradeDecision
# ------------------------------------------------------------------

def validate_trade_decision(raw: dict, symbol: str = "", source: str = "local_policy") -> dict:
    """
    Take whatever dict a strategist/LLM produced and force it into a
    100% valid TradeDecision. Never raises. Never lets an LLM value
    escape un-clamped.
    """
    if not isinstance(raw, dict):
        return safe_fallback("Strategist output was not a JSON object.", FAIL_SCHEMA, symbol)

    action = str(raw.get("action", "HOLD")).upper().strip()
    if action not in VALID_ACTIONS:
        return safe_fallback(f"Invalid action '{action[:30]}'.", FAIL_SCHEMA, symbol)

    engine = str(raw.get("engine", "NONE")).upper().strip()
    if engine not in VALID_ENGINES:
        engine = "NONE"

    strategy_type = str(raw.get("strategy_type", "NONE")).upper().strip()
    if strategy_type not in VALID_STRATEGY_TYPES:
        strategy_type = "NONE"

    risk = str(raw.get("risk", "HIGH")).upper().strip()
    if risk not in VALID_RISK:
        risk = "HIGH"

    regime = str(raw.get("regime", "SIDEWAYS")).upper().strip()
    if regime not in VALID_REGIMES:
        regime = "SIDEWAYS"

    # Devil's Advocate: extract objection and verdict, defaulting to BLOCK if missing
    da_raw = raw.get("devils_advocate") or {}
    da_verdict = str(da_raw.get("verdict", "BLOCK")).upper().strip()
    if da_verdict not in VALID_VERDICTS:
        da_verdict = "BLOCK"
    devils_advocate = {
        "objection": str(da_raw.get("objection", "")).strip()[:400] or "No objection recorded.",
        "verdict": da_verdict,
    }

    source = source if source in VALID_SOURCES else "fallback"

    # --- Build the result with clamped numeric values ---
    result = {
        "action": action,
        "engine": engine,
        "symbol": str(raw.get("symbol", symbol) or symbol).upper().strip(),
        "strategy_type": strategy_type,
        "target_dte": int(_clamp(_num(raw.get("target_dte"), 21), DTE_MIN, DTE_MAX)),
        "target_delta": round(_clamp(_num(raw.get("target_delta"), 0.25), DELTA_MIN, DELTA_MAX), 2),
        "spread_width": int(_clamp(_num(raw.get("spread_width"), 0), SPREAD_WIDTH_MIN, SPREAD_WIDTH_MAX))
                        if strategy_type in {"BULL_CALL_SPREAD", "BEAR_PUT_SPREAD"} else 0,
        "contracts": int(_clamp(_num(raw.get("contracts"), 1), CONTRACTS_MIN, CONTRACTS_MAX)),
        "confidence": round(_clamp(_num(raw.get("confidence"), 0.0), 0.0, 1.0), 3),
        "risk": risk,
        "reason": (str(raw.get("reason", "")).strip() or "No reason provided.")[:800],
        "key_factors": _clean_string_list(raw.get("key_factors"), max_items=6),
        "invalidations": _clean_string_list(raw.get("invalidations"), max_items=4),
        "regime": regime,
        "iv_rank": round(_clamp(_num(raw.get("iv_rank"), 50.0), 0.0, 100.0), 1),
        "devils_advocate": devils_advocate,
        "source": source,
        "failure_type": None,
        "agent_trace": raw.get("agent_trace") if isinstance(raw.get("agent_trace"), list) else [],
    }

    # Consistency guards (same spirit as groq_engine's BUY/SELL-size guard)
    # If the final action is HOLD, we must nullify any trading parameters
    if result["action"] == "HOLD":
        result["engine"] = "NONE"
        result["strategy_type"] = "NONE"
        result["contracts"] = 0

    # Important: If Devil's Advocate says BLOCK, then we CANNOT OPEN a trade
    # According to Part 5 of the specification, BLOCK must downgrade OPEN to HOLD
    # So we override the action and clear all trading fields
    if devils_advocate["verdict"] == "BLOCK" and result["action"] == "OPEN":
        result["action"] = "HOLD"
        result["engine"] = "NONE"
        result["strategy_type"] = "NONE"
        result["contracts"] = 0

    return result