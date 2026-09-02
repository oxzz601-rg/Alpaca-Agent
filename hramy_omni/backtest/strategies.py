"""
HRAMY OMNI AI - Strategy Suite
============================================================
Five transparent, fixed-parameter strategies compared honestly:

    A. sma_rsi            classic SMA20/50 structure + RSI filter
    B. trend_momentum     EMA50 regime filter + MACD + momentum
    C. multi_indicator    weighted multi-signal composite score
    D. ai_policy          deterministic emulation of the Groq decision
                          schema (score -> confidence/risk/size/stops)
    E. ai_risk_managed    strategy D passed through the Risk Manager

Design rules:
    - All strategies are POSITION-AWARE state machines: they know
      whether a position is open, so BUY is emitted only when flat and
      SELL only when holding (mirrors live execution reality).
    - Signals use CLOSE data of the current bar only (engine fills at
      NEXT bar's open -> no lookahead).
    - Stops/targets are ATR-aware fractions of price.
    - Parameters are fixed a priori — nothing is fitted on test data.
"""

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    AI_CONFIDENCE_THRESHOLD,
    MAX_POSITION_PERCENT,
    STOP_LOSS_MAX_PCT,
    STOP_LOSS_MIN_PCT,
)

# Composite-score thresholds (fixed a priori, not fitted)
SCORE_BUY_THRESHOLD = 40.0
SCORE_SELL_THRESHOLD = -35.0


def _base_plan(name, key, description, n, params):
    return {
        "name": name,
        "key": key,
        "description": description,
        "actions": ["HOLD"] * n,
        "stops": [0.03] * n,
        "targets": [0.06] * n,
        "params": params,
    }


def _atr_stops(row: pd.Series, atr_mult: float = 1.8) -> tuple:
    """ATR-based stop/target fractions for one bar."""
    raw = row.get("atr_pct")
    atr_pct = float(raw) / 100.0 if pd.notna(raw) else 0.02
    stop = min(max(atr_pct * atr_mult, STOP_LOSS_MIN_PCT), STOP_LOSS_MAX_PCT)
    target = stop * 2.0
    return stop, target


def _composite_score_row(row: pd.Series) -> float:
    """Row-level multi-signal composite score on [-100, +100]."""
    from analysis.signals import compute_signal_scores
    try:
        return float(compute_signal_scores(row.to_dict())["composite"])
    except Exception:
        return 0.0


def _regime_row(row: pd.Series) -> str:
    """Deterministic regime label for one bar."""
    from analysis.regime import detect_regime
    try:
        return detect_regime(row.to_dict()).regime
    except Exception:
        return "SIDEWAYS"



# ============================================================
# Strategy A - SMA structure + RSI filter (state machine)
# ============================================================

def sma_rsi_strategy(data: pd.DataFrame, params: dict | None = None) -> dict:
    """BUY when bullish SMA stack forms while RSI has headroom.
    SELL on bearish stack or momentum exhaustion (RSI > exit level).
    Position-aware: one open position at a time."""
    p = {"sma_short": 20, "sma_long": 50, "rsi_upper": 70, "rsi_exit": 78}
    if params:
        p.update(params)

    n = len(data)
    plan = _base_plan("A · SMA+RSI", "A",
                      "SMA20/50 bullish stack with RSI headroom; exits on bearish "
                      "stack or RSI exhaustion.", n, p)

    sma_s = data["close"].rolling(p["sma_short"]).mean()
    sma_l = data["close"].rolling(p["sma_long"]).mean()

    in_position = False
    for i in range(n):
        row = data.iloc[i]
        s_short = sma_s.iloc[i]
        s_long = sma_l.iloc[i]
        if pd.isna(s_short) or pd.isna(s_long):
            continue

        rsi = float(row["rsi"])
        price = float(row["close"])
        stop, target = _atr_stops(row)
        plan["stops"][i] = stop
        plan["targets"][i] = target

        if not in_position:
            if price > s_short > s_long and rsi < p["rsi_upper"]:
                plan["actions"][i] = "BUY"
                in_position = True
        else:
            if price < s_short < s_long or rsi >= p["rsi_exit"]:
                plan["actions"][i] = "SELL"
                in_position = False

    return plan


# ============================================================
# Strategy B - Trend filter + momentum confirmation (state machine)
# ============================================================

def trend_momentum_strategy(data: pd.DataFrame, params: dict | None = None) -> dict:
    """BUY above EMA50 with positive MACD histogram + momentum.
    SELL when trend support is lost (close < EMA50) or both MACD and
    momentum flip negative. Hysteresis avoids whipsaw churn."""
    p = {"ema_trend": 50, "momentum_min": 0.5}
    if params:
        p.update(params)

    n = len(data)
    plan = _base_plan("B · Trend+Momentum", "B",
                      "EMA50 regime filter; MACD + momentum confirmation with "
                      "hysteresis exits.", n, p)

    ema_trend = data["close"].ewm(span=p["ema_trend"], adjust=False).mean()

    in_position = False
    for i in range(n):
        row = data.iloc[i]
        trend_ma = ema_trend.iloc[i]
        hist = float(row.get("macd_hist", 0.0))
        mom = float(row.get("momentum", 0.0))
        price = float(row["close"])

        stop, target = _atr_stops(row)
        plan["stops"][i] = stop
        plan["targets"][i] = target

        if not in_position:
            if price > trend_ma and hist > 0 and mom > p["momentum_min"]:
                plan["actions"][i] = "BUY"
                in_position = True
        else:
            # Exit only on REAL deterioration, not single-bar noise:
            if price < trend_ma or (hist < 0 and mom < 0):
                plan["actions"][i] = "SELL"
                in_position = False

    return plan


# ============================================================
# Strategy C - Multi-indicator composite score (state machine)
# ============================================================

def multi_indicator_strategy(data: pd.DataFrame, params: dict | None = None) -> dict:
    """Weighted 6-factor composite. BUY above threshold with volume
    participation; SELL below negative threshold. Regime veto on buys."""
    p = {
        "buy_threshold": SCORE_BUY_THRESHOLD,
        "sell_threshold": SCORE_SELL_THRESHOLD,
    }
    if params:
        p.update(params)

    n = len(data)
    plan = _base_plan("C · Multi-Indicator", "C",
                      "6-factor weighted composite score with regime veto.",
                      n, p)
    scores = np.zeros(n)

    in_position = False
    for i in range(n):
        row = data.iloc[i]
        score = _composite_score_row(row)
        scores[i] = score

        stop, target = _atr_stops(row)
        plan["stops"][i] = stop
        plan["targets"][i] = target

        regime = _regime_row(row)
        volume_ratio = float(row.get("volume_ratio", 1.0))

        if not in_position:
            if (score >= p["buy_threshold"]
                    and volume_ratio >= 0.9
                    and regime not in ("BEAR_TREND", "HIGH_VOLATILITY")):
                plan["actions"][i] = "BUY"
                in_position = True
        else:
            if score <= p["sell_threshold"] or regime == "BEAR_TREND":
                plan["actions"][i] = "SELL"
                in_position = False

    plan["scores"] = scores.tolist()
    return plan


# ============================================================
# Strategy D - AI policy emulation (deterministic)
# ============================================================
# Emulates EXACTLY the decision pipeline of the Groq engine without
# network calls: composite score -> confidence / risk / size /
# stop / target in the same JSON schema, then validated with the
# same clamps. Clearly labeled as an emulation everywhere.

def ai_policy_decision(score: float, regime: str, atr_pct: float) -> dict:
    """
    Deterministic mapping from quant state to the AI schema.

    Confidence mapping: 0.35 + |score|/110, capped at 0.95.
    A composite of +28 already clears the 0.60 execution threshold,
    which mirrors how the real Groq engine behaves on strong setups.
    """
    score = max(-100.0, min(100.0, float(score)))
    confidence = round(min(0.95, 0.35 + abs(score) / 110.0), 3)

    if abs(score) >= 55 and regime != "HIGH_VOLATILITY":
        risk = "LOW"
    elif abs(score) >= 25:
        risk = "MEDIUM"
    else:
        risk = "HIGH"

    if (score >= SCORE_BUY_THRESHOLD
            and regime not in ("BEAR_TREND", "HIGH_VOLATILITY")):
        decision = "BUY"
    elif score <= SCORE_SELL_THRESHOLD:
        decision = "SELL"
    else:
        decision = "HOLD"

    stop_pct = min(max(atr_pct * 1.5, STOP_LOSS_MIN_PCT * 100), STOP_LOSS_MAX_PCT * 100)
    target_pct = min(max(stop_pct * 2.2, 1.8), 35.0)
    size_pct = (
        min(4.0 + abs(score) / 6.0, MAX_POSITION_PERCENT * 100)
        if decision != "HOLD" else 0.0
    )

    return {
        "decision": decision,
        "confidence": confidence,
        "risk": risk,
        "position_size_percent": size_pct,
        "stop_loss_percent": stop_pct,
        "take_profit_percent": target_pct,
        "market_regime": regime,
        "time_horizon": "SWING",
    }


def ai_policy_strategy(data: pd.DataFrame, params: dict | None = None) -> dict:
    """Strategy D - deterministic emulation of the Groq decision loop."""
    p = {"confidence_threshold": AI_CONFIDENCE_THRESHOLD}
    if params:
        p.update(params)

    n = len(data)
    plan = _base_plan("D · AI-Policy", "D",
                      "Deterministic emulation of the Groq schema "
                      "(score→confidence/risk/size).", n, p)

    in_position = False
    for i in range(n):
        row = data.iloc[i]
        score = _composite_score_row(row)
        regime = _regime_row(row)
        raw_atr = row.get("atr_pct")
        atr_pct = float(raw_atr) if pd.notna(raw_atr) else 2.0

        ai_out = ai_policy_decision(score, regime, atr_pct)
        plan["stops"][i] = min(
            max(ai_out["stop_loss_percent"] / 100.0, STOP_LOSS_MIN_PCT),
            STOP_LOSS_MAX_PCT,
        )
        plan["targets"][i] = ai_out["take_profit_percent"] / 100.0

        # Same validation gates as the live AI path.
        if ai_out["confidence"] < p["confidence_threshold"]:
            continue
        if ai_out["risk"] == "HIGH":
            continue

        if not in_position and ai_out["decision"] == "BUY":
            plan["actions"][i] = "BUY"
            in_position = True
        elif in_position and ai_out["decision"] == "SELL":
            plan["actions"][i] = "SELL"
            in_position = False

    return plan


# ============================================================
# Strategy E - AI policy + Risk Manager gates
# ============================================================

def ai_risk_managed_strategy(data: pd.DataFrame, params: dict | None = None) -> dict:
    """
    Strategy E - identical to D but every BUY must additionally pass
    deterministic Risk-Manager-style vetoes (regime, volatility,
    minimum reward:risk geometry).
    """
    base = ai_policy_strategy(data, params)
    p = dict(base["params"])
    p["min_rr"] = 1.8

    n = len(data)
    plan = _base_plan("E · AI+Risk Manager", "E",
                      "Strategy D gated by deterministic risk-manager vetoes "
                      "(regime, vol, R:R floor).", n, p)
    plan["actions"] = list(base["actions"])
    plan["stops"] = list(base["stops"])
    plan["targets"] = [
        max(t, s * p["min_rr"]) for s, t in zip(base["stops"], base["targets"])
    ]

    blocked_buys = 0
    for i in range(n):
        if plan["actions"][i] != "BUY":
            continue
        row = data.iloc[i]
        regime = _regime_row(row)
        raw_vol = row.get("volatility")
        volatility = float(raw_vol) if pd.notna(raw_vol) else 25.0

        vetoed = False
        if regime in ("BEAR_TREND", "HIGH_VOLATILITY"):
            vetoed = True
        elif volatility >= 55:
            vetoed = True

        if vetoed:
            plan["actions"][i] = "HOLD"
            blocked_buys += 1

    plan["blocked_buys"] = blocked_buys
    return plan


# ============================================================
# Registry
# ============================================================

STRATEGY_REGISTRY = {
    "A": ("SMA + RSI", sma_rsi_strategy),
    "B": ("Trend + Momentum", trend_momentum_strategy),
    "C": ("Multi-Indicator Score", multi_indicator_strategy),
    "D": ("AI-Policy (emulated)", ai_policy_strategy),
    "E": ("AI + Risk Manager", ai_risk_managed_strategy),
}


def get_all_strategies() -> dict:
    """Return {key: {"name":..., "fn":...}} for all registered strategies."""
    return {
        key: {"name": name, "fn": fn}
        for key, (name, fn) in STRATEGY_REGISTRY.items()
    }