"""
HRAMY OMNI AI - Groq AI Decision Engine
============================================================
The AI receives the COMPLETE quantitative feature set (indicators,
multi-signal score breakdown, regime classification, portfolio state,
risk constraints) and independently produces a structured decision.

Design guarantees:
    - The AI can NEVER fabricate market data: only server-computed
      values are placed in the prompt, and every numeric field of the
      response is validated + clamped. Prices/indicators from the AI
      are never accepted.
    - Any failure (network, rate limit, malformed JSON, out-of-range
      values) degrades to a SAFE HOLD with a failure type logged.
    - Credentials are read from the environment and never exposed.

Output schema (strictly validated):
{
  "decision": "BUY" | "SELL" | "HOLD",
  "confidence": 0.0..1.0,
  "risk": "LOW" | "MEDIUM" | "HIGH",
  "position_size_percent": 0..max_position_percent*100,
  "stop_loss_percent": 0.8..12,
  "take_profit_percent": 1.5..35,
  "time_horizon": "INTRADAY"|"SWING"|"POSITION",
  "market_regime": "<regime echo or AI assessment>",
  "reason": "...",
  "key_factors": ["..."],
  "invalidations": ["..."]
}
"""

import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    AI_MODEL,
    GROQ_API_KEY,
    REQUEST_TIMEOUT,
    MAX_POSITION_PERCENT,
    STOP_LOSS_MIN_PCT,
    STOP_LOSS_MAX_PCT,
    TAKE_PROFIT_MIN_PCT,
    TAKE_PROFIT_MAX_PCT,
)

VALID_DECISIONS = {"BUY", "SELL", "HOLD"}
VALID_RISK = {"LOW", "MEDIUM", "HIGH"}
VALID_HORIZONS = {"INTRADAY", "SWING", "POSITION"}

# Failure types (safe to log; never contain credentials)
FAIL_NOT_CONFIGURED = "not_configured"
FAIL_SDK_MISSING = "sdk_missing"
FAIL_TIMEOUT = "timeout"
FAIL_RATE_LIMIT = "rate_limit"
FAIL_BAD_JSON = "invalid_json"
FAIL_SCHEMA = "schema_violation"
FAIL_NETWORK = "network_error"
FAIL_UNKNOWN = "unknown_error"

_last_failure: dict = {"type": None, "detail": ""}


def get_last_failure() -> dict:
    """Return the last engine failure (type + safe detail string)."""
    return dict(_last_failure)


class GroqEngineError(Exception):
    """Raised for missing credentials or engine-level setup errors."""


def is_configured() -> bool:
    """Whether a Groq API key is present in the environment (existence only)."""
    return bool(GROQ_API_KEY)


# ============================================================
# Safe failure fallback
# ============================================================

def _safe_fallback(reason: str, failure_type: str = FAIL_UNKNOWN) -> dict:
    _last_failure["type"] = failure_type
    _last_failure["detail"] = str(reason)[:300]
    return {
        "decision": "HOLD",
        "confidence": 0.0,
        "risk": "HIGH",
        "position_size_percent": 0.0,
        "stop_loss_percent": 0.0,
        "take_profit_percent": 0.0,
        "time_horizon": "SWING",
        "market_regime": "UNKNOWN",
        "reason": reason,
        "key_factors": [],
        "invalidations": [],
        "source": "fallback",
        "failure_type": failure_type,
        "model": AI_MODEL if is_configured() else "unavailable",
    }


def _num(value, default: float = 0.0) -> float:
    """Coerce to finite float or default."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(result):
        return default
    return result


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


# ============================================================
# JSON validation — the anti-fabrication gate
# ============================================================

def _validate_result(result: dict, market: dict | None = None) -> dict:
    """
    Validate/normalise the parsed AI JSON against the strict schema.

    Guarantees:
        - decision in {BUY, SELL, HOLD}
        - confidence clamped to [0, 1]
        - risk in {LOW, MEDIUM, HIGH}
        - position_size_percent clamped to [0, MAX_POSITION_PERCENT*100]
        - stop/take-profit percentages clamped to sane bands
        - horizon in {INTRADAY, SWING, POSITION}
        - lists of clean strings for key_factors / invalidations
    The AI NEVER supplies prices, indicators or portfolio values.
    """
    decision = str(result.get("decision", "HOLD")).upper().strip()
    if decision not in VALID_DECISIONS:
        return _safe_fallback(
            f"AI returned invalid decision '{decision[:40]}' — safe hold.",
            FAIL_SCHEMA,
        )

    confidence = _clamp(_num(result.get("confidence"), 0.0), 0.0, 1.0)

    risk = str(result.get("risk", "HIGH")).upper().strip()
    if risk not in VALID_RISK:
        return _safe_fallback(
            "AI returned invalid risk level — safe hold.",
            FAIL_SCHEMA,
        )

    max_size = MAX_POSITION_PERCENT * 100.0
    position_size = _clamp(_num(result.get("position_size_percent"), 0.0), 0.0, max_size)

    stop_loss = _clamp(_num(result.get("stop_loss_percent"), STOP_LOSS_MIN_PCT * 100),
                       STOP_LOSS_MIN_PCT * 100, STOP_LOSS_MAX_PCT * 100)
    take_profit = _clamp(_num(result.get("take_profit_percent"), TAKE_PROFIT_MIN_PCT * 100),
                         TAKE_PROFIT_MIN_PCT * 100, TAKE_PROFIT_MAX_PCT * 100)

    horizon = str(result.get("time_horizon", "SWING")).upper().strip()
    if horizon not in VALID_HORIZONS:
        horizon = "SWING"

    regime = str(result.get("market_regime", "")).upper().strip() or "UNKNOWN"

    reason = str(result.get("reason", "")).strip()
    if not reason:
        reason = "AI did not provide a reason."

    key_factors = _clean_string_list(result.get("key_factors"))
    invalidations = _clean_string_list(result.get("invalidations"))

    validated = {
        "decision": decision,
        "confidence": round(confidence, 3),
        "risk": risk,
        "position_size_percent": round(position_size, 2),
        "stop_loss_percent": round(stop_loss, 2),
        "take_profit_percent": round(take_profit, 2),
        "time_horizon": horizon,
        "market_regime": regime,
        "reason": reason,
        "key_factors": key_factors,
        "invalidations": invalidations,
        "source": "groq",
        "failure_type": None,
        "model": AI_MODEL,
    }

    # Consistency guard: BUY/SELL with ~zero size is meaningless -> force size floor.
    if decision in ("BUY", "SELL") and validated["position_size_percent"] <= 0.0:
        validated["position_size_percent"] = round(min(5.0, max_size), 2)

    # HOLD must not carry sizing intent.
    if decision == "HOLD":
        validated["position_size_percent"] = 0.0

    return validated


def _clean_string_list(value) -> list:
    """Coerce an arbitrary value into a list of non-empty strings."""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    cleaned = []
    for item in value:
        text = str(item).strip()
        if text:
            cleaned.append(text[:400])
    return cleaned[:10]


def extract_json(content: str) -> dict:
    """
    Extract a JSON object from raw model output.

    Handles models that wrap JSON in markdown fences despite instructions.
    Raises json.JSONDecodeError when no object can be recovered.
    """
    text = content.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # strip ```json ... ``` fences
    if "```" in text:
        for chunk in text.split("```"):
            candidate = chunk.strip()
            if candidate.startswith("json"):
                candidate = candidate[4:].strip()
            if candidate.startswith("{") and candidate.endswith("}"):
                return json.loads(candidate)

    # first { ... last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start:end + 1])

    raise json.JSONDecodeError("No JSON object found", text, 0)


# ============================================================
# Prompt builder — full quantitative context, zero credentials
# ============================================================

def build_prompt(symbol: str, market: dict, account: dict) -> str:
    """Construct the analysis prompt.

    ONLY server-computed values enter the prompt. The AI is explicitly
    instructed that it may not invent data and must reason from what
    it is given. No credentials are ever included.
    """
    score = market.get("score", {})
    components = score.get("components", {})
    notes = score.get("notes", {})
    signals_text = "\n".join(f"- {s}" for s in market.get("signals", []))

    def fmt(value, pattern="{:.2f}", fallback="N/A"):
        try:
            v = float(value)
            return "N/A" if not math.isfinite(v) else pattern.format(v)
        except (TypeError, ValueError):
            return fallback

    return f"""
You are the independent AI decision engine of QuantNova, an explainable,
risk-aware market-analysis system. You provide decision support only.
A deterministic quantitative engine has already computed every number below.
You MUST reason ONLY from these numbers — you may not invent prices,
indicators, or portfolio values. You MAY disagree with the composite
quantitative score if your reasoning justifies it.

=== MARKET DATA (computed server-side) ===
SYMBOL: {symbol}
LAST PRICE: ${fmt(market['price'])}

MOVING AVERAGES:
  SMA20: ${fmt(market['sma20'])}   SMA50: ${fmt(market['sma50'])}
  EMA20: ${fmt(market.get('ema20'))}   EMA50: ${fmt(market.get('ema50'))}
  VWAP(20d): ${fmt(market.get('vwap20'))}

OSCILLATORS / STRENGTH:
  RSI(14): {fmt(market['rsi'], '{:.1f}')}
  ADX(14): {fmt(market.get('adx'), '{:.1f}')}
  MACD hist: {fmt(market.get('macd_hist'), '{:.4f}')}  (MACD line {fmt(market.get('macd'), '{:.4f}')})

VOLATILITY & RANGE:
  Annualized volatility: {fmt(market['volatility'], '{:.1f}')}%
  ATR(14): ${fmt(market.get('atr'))} ({fmt(market.get('atr_pct'), '{:.2f}')}% of price)
  Bollinger %B: {fmt(market.get('bb_percent_b'), '{:.2f}')}

VOLUME & LEVELS:
  Relative volume: {fmt(market.get('volume_ratio'), '{:.2f}')}x of 20-day average
  20-bar support: ${fmt(market.get('support20'))} / resistance: ${fmt(market.get('resistance20'))}

MOMENTUM & REGIME:
  10-day momentum: {fmt(market['momentum'], '{:+.2f}')}%
  Detected regime: {market.get('regime', 'UNKNOWN')} (trend strength: {market.get('trend_strength', 'N/A')})
  Regime note: {market.get('regime_description', '')}

QUANTITATIVE MULTI-SIGNAL SCORE (composite {fmt(score.get('composite'), '{:+.1f}')} on -100..+100):
  trend={fmt(components.get('trend'), '{:+.2f}')}, momentum={fmt(components.get('momentum'), '{:+.2f}')}, rsi={fmt(components.get('rsi'), '{:+.2f}')}, macd={fmt(components.get('macd'), '{:+.2f}')}, volume={fmt(components.get('volume'), '{:+.2f}')}, volatility={fmt(components.get('volatility'), '{:+.2f}')}
  {notes.get('trend', '')}
  {notes.get('rsi', '')}

SIGNAL CLASSIFICATIONS:
{signals_text}

=== PORTFOLIO STATE (paper simulation) ===
EQUITY: ${fmt(account.get('equity'))}
CASH AVAILABLE: ${fmt(account.get('cash'))}
CURRENT POSITION: {account.get('shares', 0)} shares (${fmt(account.get('position_value'))})
CURRENT EXPOSURE: {fmt(account.get('exposure_percent', 0), '{:.1f}')}%

=== HARD RISK CONSTRAINTS (non-negotiable) ===
  Max position size: {MAX_POSITION_PERCENT * 100:.0f}% of equity
  Stop-loss must be between {STOP_LOSS_MIN_PCT * 100:.1f}% and {STOP_LOSS_MAX_PCT * 100:.0f}%
  Take-profit must be between {TAKE_PROFIT_MIN_PCT * 100:.1f}% and {TAKE_PROFIT_MAX_PCT * 100:.0f}%
  Take-profit should exceed the stop distance (positive expectancy)

=== YOUR TASK ===
Evaluate whether a trade is justified RIGHT NOW given this exact state.
Consider regime fit, risk/reward vs ATR, volume confirmation, and portfolio
context. If evidence conflicts or is weak, choose HOLD — capital preservation
is acceptable output.

Return ONLY a JSON object in EXACTLY this format:
{{
  "decision": "HOLD",
  "confidence": 0.75,
  "risk": "MEDIUM",
  "position_size_percent": 10.0,
  "stop_loss_percent": 2.5,
  "take_profit_percent": 5.0,
  "time_horizon": "SWING",
  "market_regime": "{market.get('regime', 'UNKNOWN')}",
  "reason": "One concise paragraph citing the actual numbers above.",
  "key_factors": ["Factor 1 with number", "Factor 2 with number"],
  "invalidations": ["Condition that would reverse this view"]
}}

Rules:
- decision: exactly one of BUY, SELL, HOLD
- confidence: 0..1 (your honest conviction; do not inflate)
- risk: LOW, MEDIUM, or HIGH (your assessment of THIS trade)
- position_size_percent: percent of equity you propose (<= {MAX_POSITION_PERCENT * 100:.0f}); use 0 for HOLD
- stop_loss_percent/take_profit_percent: distances from current price in %
- time_horizon: INTRADAY, SWING, or POSITION
- market_regime: the regime you assess from the data
- key_factors: 2-5 bullet facts FROM THE DATA ABOVE
- invalidations: 1-3 concrete conditions that would invalidate the thesis
- No Markdown, no commentary outside the JSON object.
""".strip()


SYSTEM_PROMPT = (
    "You are QuantNova's institutional-grade market decision engine. "
    "You analyze strictly quantitative inputs and respond with valid JSON only. "
    "You never invent data, never give financial advice disclaimers inside JSON, "
    "and always preserve capital when evidence is ambiguous."
)


# ============================================================
# Main AI call
# ============================================================

def _classify_exception(exc: Exception) -> str:
    """Map an SDK exception to a safe failure type (no details leaked)."""
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if "timeout" in name or "timed out" in text or "timeout" in text:
        return FAIL_TIMEOUT
    if "rate" in text and "limit" in text or "429" in text:
        return FAIL_RATE_LIMIT
    if "connect" in name or "connection" in text or "network" in text:
        return FAIL_NETWORK
    if "auth" in text or "401" in text or "api key" in text:
        # Authentication problem — never echo the key itself.
        return FAIL_NOT_CONFIGURED
    return FAIL_UNKNOWN


def get_ai_decision(symbol: str, market: dict, account: dict) -> dict:
    """
    Ask Groq for a structured decision over the full quantitative context.

    Returns a validated dict matching the documented schema.
    Always returns a SAFE HOLD result on any failure — never raises,
    never leaks credentials, never accepts fabricated data.
    """
    if not is_configured():
        return _safe_fallback(
            "GROQ_API_KEY is not configured — running in quantitative-only mode.",
            FAIL_NOT_CONFIGURED,
        )

    try:
        from groq import Groq
    except ImportError:
        return _safe_fallback(
            "AI engine unavailable: groq SDK not installed.",
            FAIL_SDK_MISSING,
        )

    try:
        client = Groq(api_key=GROQ_API_KEY, timeout=REQUEST_TIMEOUT)

        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_prompt(symbol, market, account)},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=900,
        )

        content = response.choices[0].message.content
        if not content or not content.strip():
            return _safe_fallback(
                "AI returned an empty response — safe hold.",
                FAIL_BAD_JSON,
            )

        result = extract_json(content)
        if not isinstance(result, dict):
            return _safe_fallback(
                "AI JSON was not an object — safe hold.",
                FAIL_SCHEMA,
            )
        return _validate_result(result, market)

    except json.JSONDecodeError:
        return _safe_fallback(
            "AI returned invalid JSON — holding position.",
            FAIL_BAD_JSON,
        )
    except Exception as exc:
        failure_type = _classify_exception(exc)
        friendly = {
            FAIL_TIMEOUT: "AI request timed out — holding position.",
            FAIL_RATE_LIMIT: "AI rate limit reached — holding position.",
            FAIL_NETWORK: "AI network error — holding position.",
            FAIL_NOT_CONFIGURED: "AI authentication failed — check GROQ_API_KEY validity.",
            FAIL_UNKNOWN: "AI analysis unavailable — holding position.",
        }.get(failure_type, "AI analysis unavailable — holding position.")
        return _safe_fallback(friendly, failure_type)


# ============================================================
# Deterministic offline policy (used when Groq is unavailable)
# ============================================================

def local_policy_decision(market: dict, account: dict | None = None) -> dict:
    """
    A transparent, deterministic fallback policy that mirrors the AI schema.

    This actively trades when the evidence is strong enough, instead of
    defaulting to HOLD on every moderately favorable setup. It is used only
    when the Groq engine is unavailable, but it still produces a meaningful
    decision signal for the UI and the execution pipeline.
    """
    composite = float(market.get("score", {}).get("composite", 0.0))
    regime = str(market.get("regime", "UNKNOWN")).upper()
    trend = str(market.get("trend", "NEUTRAL")).upper()
    momentum_signal = str(market.get("momentum_signal", "NEUTRAL")).upper()
    volatility_label = str(market.get("volatility_label", "MODERATE")).upper()
    atr_pct = float(market.get("atr_pct") or 2.0)
    shares = float((account or {}).get("shares", 0) or 0)

    # Strong, risk-aware decision rules: act on high-conviction setups.
    bullish_context = (
        regime in {"BULL_TREND", "BREAKOUT"} or trend == "BULLISH"
    )
    bearish_context = (
        regime in {"BEAR_TREND"} or trend == "BEARISH"
    )
    stable_vol = volatility_label not in {"HIGH"}

    if composite >= 25 and bullish_context and stable_vol and momentum_signal != "NEGATIVE":
        decision = "BUY"
    elif composite <= -25 and bearish_context and stable_vol and momentum_signal != "POSITIVE":
        decision = "SELL"
    else:
        decision = "HOLD"

    confidence = min(0.95, max(0.25, 0.52 + abs(composite) / 140.0))
    if decision == "HOLD":
        confidence = min(0.7, confidence)

    risk_level = (
        "LOW" if abs(composite) >= 55 and stable_vol else
        "MEDIUM" if abs(composite) >= 25 else "HIGH"
    )

    stop_pct = _clamp(max(atr_pct * 1.5, STOP_LOSS_MIN_PCT * 100),
                      STOP_LOSS_MIN_PCT * 100, STOP_LOSS_MAX_PCT * 100)
    target_pct = _clamp(stop_pct * 2.2, TAKE_PROFIT_MIN_PCT * 100, TAKE_PROFIT_MAX_PCT * 100)

    size_pct = round(_clamp(abs(composite) / 6.0, 0.0, MAX_POSITION_PERCENT * 100), 1)
    if decision == "HOLD":
        size_pct = 0.0

    reason = (
        f"Deterministic fallback policy: composite score {composite:+.1f}, regime {regime}, "
        f"trend {trend}, momentum {momentum_signal.lower()} and volatility {volatility_label.lower()}."
    )
    key_factors = [
        f"Composite score {composite:+.1f}/100",
        f"Regime {regime} ({trend})",
        f"Momentum signal {momentum_signal}",
        f"ATR {atr_pct:.1f}% sets stop distance",
    ]

    invalidations = [
        "Composite score weakens or flips sign",
        "Regime moves into HIGH_VOLATILITY or BEAR_TREND",
        "Momentum signal contradicts the directional thesis",
    ]

    if decision == "SELL":
        invalidations = [
            "Bullish reversal or positive momentum confirmation",
            "Regime improves to BULL_TREND",
            "Position is already flat or the signal is weak",
        ]

    return {
        "decision": decision,
        "confidence": round(confidence, 3),
        "risk": risk_level,
        "position_size_percent": size_pct if decision != "HOLD" else 0.0,
        "stop_loss_percent": round(stop_pct, 2),
        "take_profit_percent": round(target_pct, 2),
        "time_horizon": "SWING",
        "market_regime": regime,
        "reason": reason,
        "key_factors": key_factors,
        "invalidations": invalidations,
        "source": "local_policy",
        "failure_type": None,
        "model": "deterministic-policy",
    }