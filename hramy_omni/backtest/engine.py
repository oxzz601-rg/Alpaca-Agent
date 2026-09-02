"""
HRAMY OMNI AI - Backtesting Engine
============================================================
Event-driven historical simulation with realistic execution.

Design (no lookahead, no fabrication):
    - Strategy signals are computed from bar i CLOSE values only.
    - Orders execute at bar i+1 OPEN with slippage + half-spread.
    - Stop-loss / take-profit are checked INTRABAR against each bar's
      high/low (stop checked before target = conservative).
    - Position sizing is volatility/risk based with hard caps:
        risk-per-trade, max-position-percent, max-exposure, cash.
    - Fractional shares supported.
    - Commission charged per side.

Trade accounting:
    - A trade is an ENTRY -> EXIT round trip.
    - Positions still open at the last bar are NOT silently dropped:
      they remain marked-to-market and reported as unrealized P/L,
      separate from realized P/L of closed trades.

Metrics (N/A when insufficient data):
    total return, CAGR, win rate, trades W/L, average win/loss,
    largest win/loss, profit factor, expectancy, max drawdown,
    avg holding period, exposure, Sharpe, Sortino, Calmar,
    buy-&-hold benchmark comparison + alpha.
"""

import math
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    COMMISSION_RATE,
    MAX_PORTFOLIO_EXPOSURE,
    MAX_POSITION_PERCENT,
    RISK_PER_TRADE,
    SLIPPAGE_PCT,
    SPREAD_PCT,
    STARTING_CASH,
    STOP_LOSS_MIN_PCT,
    TRADING_DAYS_PER_YEAR,
)


# ============================================================
# Helpers
# ============================================================

def _finite(value: float):
    """Return a JSON-safe float (None instead of NaN/inf)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _max_drawdown(equity: pd.Series):
    """Return (max_drawdown_fraction, drawdown duration in bars)."""
    if len(equity) == 0:
        return 0.0, 0
    rolling_peak = equity.cummax()
    dd = equity / rolling_peak - 1.0
    max_dd = float(dd.min()) if len(dd) else 0.0
    duration = 0
    current = 0
    for value in dd.values:
        if value < 0:
            current += 1
            duration = max(duration, current)
        else:
            current = 0
    return abs(max_dd), duration


# ============================================================
# Performance metrics
# ============================================================

def compute_metrics(
    equity_curve: list,
    trades: list,
    starting_cash: float,
    unrealized_pnl: float = 0.0,
    total_bars: int = 0,
    bars_in_market: int = 0,
) -> dict:
    """
    Compute the full performance-metric suite.

    Any metric that cannot be computed honestly is returned as None
    (rendered as 'N/A' by the UI).
    """
    result = {
        "starting_value": starting_cash,
        "final_value": None,
        "return_percent": None,
        "cagr_percent": None,
        "annualized_return_percent": None,
        "trades": len(trades),
        "winning_trades": 0,
        "losing_trades": 0,
        "win_rate": None,
        "avg_win": None,
        "avg_loss": None,
        "largest_win": None,
        "largest_loss": None,
        "profit_factor": None,
        "expectancy": None,
        "expectancy_percent": None,
        "max_drawdown_percent": None,
        "drawdown_duration_bars": None,
        "avg_holding_days": None,
        "exposure_percent": None,
        "sharpe": None,
        "sortino": None,
        "calmar": None,
        "realized_pnl": None,
        "unrealized_pnl": None,
    }

    # ---- Equity-based metrics ----
    if equity_curve:
        eq = pd.Series([point["value"] for point in equity_curve], dtype=float)
        final_value = float(eq.iloc[-1])
        result["final_value"] = round(final_value, 2)
        total_return = (final_value - starting_cash) / starting_cash
        result["return_percent"] = round(total_return * 100, 2)

        n = len(eq)
        years = n / TRADING_DAYS_PER_YEAR if n else 0.0
        if years > 0 and final_value > 0 and starting_cash > 0:
            cagr = (final_value / starting_cash) ** (1.0 / years) - 1.0
            cagr_val = _finite(cagr * 100)
            if cagr_val is not None:
                result["cagr_percent"] = round(cagr_val, 2)
                result["annualized_return_percent"] = result["cagr_percent"]

        # Daily returns -> Sharpe / Sortino
        rets = eq.pct_change().dropna()
        if len(rets) > 2:
            std = float(rets.std(ddof=0))
            if std > 0:
                sharpe = float(rets.mean()) / std * math.sqrt(TRADING_DAYS_PER_YEAR)
                result["sharpe"] = round(_finite(sharpe), 2)
            downside = rets[rets < 0]
            if len(downside) >= 2 and std > 0:
                down_std = float(downside.std(ddof=0))
                if down_std > 0:
                    sortino = float(rets.mean()) / down_std * math.sqrt(TRADING_DAYS_PER_YEAR)
                    result["sortino"] = round(_finite(sortino), 2)

        max_dd, duration = _max_drawdown(eq)
        result["max_drawdown_percent"] = round(max_dd * 100, 2)
        result["drawdown_duration_bars"] = duration

        if max_dd > 0 and result["cagr_percent"] is not None:
            calmar = result["cagr_percent"] / (max_dd * 100)
            result["calmar"] = round(_finite(calmar), 2)

        if total_bars > 0:
            result["exposure_percent"] = round(bars_in_market / total_bars * 100, 1)

    # ---- Trade-based metrics ----
    pnls = [float(t["net_pnl"]) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    result["winning_trades"] = len(wins)
    result["losing_trades"] = len(losses)

    if pnls:
        result["win_rate"] = round(len(wins) / len(pnls) * 100, 1)
        result["expectancy"] = round(sum(pnls) / len(pnls), 2)

    if wins:
        result["avg_win"] = round(sum(wins) / len(wins), 2)
        result["largest_win"] = round(max(wins), 2)
    if losses:
        result["avg_loss"] = round(sum(losses) / len(losses), 2)
        result["largest_loss"] = round(min(losses), 2)

    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    if pnls and gross_loss > 0:
        result["profit_factor"] = round(gross_win / gross_loss, 2)
    # gross_loss == 0 -> profit factor undefined -> stays None (N/A)

    returns_pct = [float(t.get("return_percent", 0.0)) for t in trades]
    if returns_pct:
        result["expectancy_percent"] = round(sum(returns_pct) / len(returns_pct), 3)

    hold_days = [t.get("holding_days") for t in trades if t.get("holding_days") is not None]
    if hold_days:
        result["avg_holding_days"] = round(sum(hold_days) / len(hold_days), 1)

    result["realized_pnl"] = round(sum(pnls), 2)
    result["unrealized_pnl"] = round(_finite(unrealized_pnl) or 0.0, 2)

    return result


# ============================================================
# Core event-driven simulation
# ============================================================

def run_backtest(
    data: pd.DataFrame,
    actions=None,
    stops=None,
    targets=None,
    starting_cash: float = STARTING_CASH,
    commission_rate: float = COMMISSION_RATE,
    slippage_pct: float = SLIPPAGE_PCT,
    spread_pct: float = SPREAD_PCT,
    risk_per_trade: float = RISK_PER_TRADE,
    max_position_percent: float = MAX_POSITION_PERCENT,
    max_exposure_percent: float = MAX_PORTFOLIO_EXPOSURE,
) -> dict:
    """
    Execute an event-driven backtest.

    Signals in `actions` are decided on bar i's close and filled at
    bar i+1 open (no lookahead). BUY is ignored when a position is
    open; SELL when flat. stops/targets are fractional distances.
    """
    n = len(data)
    if n < 10:
        empty_metrics = compute_metrics([], [], starting_cash)
        empty_metrics["warning"] = "Not enough data for backtest."
        return {
            **empty_metrics,
            "alpha_percent": None,
            "trade_list": [],
            "equity_curve": [],
        }

    def _safe_list(lst, default):
        if lst is None:
            return [default] * n
        out = list(lst)[:n]
        while len(out) < n:
            out.append(default)
        return out

    if actions is None:
        actions = ["HOLD"] * n
    stops = _safe_list(stops, max(0.02, STOP_LOSS_MIN_PCT))
    targets = _safe_list(targets, 0.05)

    cost_per_side = slippage_pct + spread_pct

    cash = float(starting_cash)
    shares = 0.0
    position = None
    trades = []
    equity_curve = []
    bars_in_market = 0

    pending_action = None
    pending_stop = None
    pending_target = None
    pending_meta = {}

    def _close_position(fill_price, exit_time, exit_reason):
        nonlocal cash, shares, position
        gross = (fill_price - position["entry_price"]) * position["quantity"]
        fee = abs(fill_price * position["quantity"]) * commission_rate
        net = gross - fee - position["fees_entry"]
        cash += fill_price * position["quantity"] - fee
        holding_days = max(
            (exit_time - position["entry_time"]).total_seconds() / 86400.0, 0.0
        )
        trades.append({
            "trade_id": len(trades) + 1,
            "entry_time": str(position["entry_time"].date()),
            "exit_time": str(exit_time.date()),
            "entry_price": round(position["entry_price"], 4),
            "exit_price": round(fill_price, 4),
            "quantity": round(position["quantity"], 6),
            "gross_pnl": round(gross, 2),
            "fees": round(fee + position["fees_entry"], 4),
            "net_pnl": round(net, 2),
            "return_percent": round(
                (fill_price / position["entry_price"] - 1) * 100, 3
            ) if position["entry_price"] > 0 else 0.0,
            "holding_days": round(holding_days, 2),
            "exit_reason": exit_reason,
            "strategy_signal": position.get("signal", ""),
            "ai_confidence": position.get("confidence"),
            "risk_score": position.get("risk", ""),
        })
        shares = 0.0
        position = None

    for j in range(1, n):
        bar = data.iloc[j]
        ts = data.index[j]
        o = float(bar["open"])
        h = float(bar["high"])
        l = float(bar["low"])
        c = float(bar["close"])

        # ---- 1. Fill pending order at this bar's OPEN ----------------
        if pending_action == "BUY" and position is None and shares == 0:
            fill = o * (1 + cost_per_side)
            equity_now = cash + shares * o
            stop_frac = max(min(float(pending_stop), 0.25), STOP_LOSS_MIN_PCT)

            # Risk-based sizing across the stop distance + hard caps
            qty_risk = (
                (equity_now * risk_per_trade) / (fill * stop_frac)
                if fill > 0 and stop_frac > 0 else 0.0
            )
            qty_position_cap = (
                equity_now * max_position_percent / fill if fill > 0 else 0.0
            )
            free_exposure = max(equity_now * max_exposure_percent, 0.0)
            qty_exposure_cap = free_exposure / fill if fill > 0 else 0.0
            qty_cash_cap = (
                max(cash * 0.985, 0.0) / (fill * (1 + commission_rate))
                if fill > 0 else 0.0
            )

            qty = min(qty_risk, qty_position_cap, qty_exposure_cap, qty_cash_cap)
            if qty > 0:
                notional = qty * fill
                entry_fee = notional * commission_rate
                if notional + entry_fee <= cash:
                    cash -= (notional + entry_fee)
                    shares = qty
                    position = {
                        "symbol": "",
                        "entry_time": ts,
                        "entry_price": fill,
                        "quantity": qty,
                        "fees_entry": entry_fee,
                        "stop_price": pending_stop,
                        "target_price": pending_target,
                        "signal": pending_meta.get("signal", ""),
                        "confidence": pending_meta.get("confidence"),
                        "risk": pending_meta.get("risk", ""),
                    }
        elif pending_action == "SELL" and position is not None:
            fill = o * (1 - cost_per_side)
            _close_position(fill, ts, "SIGNAL")

        pending_action = None
        pending_meta = {}

        # ---- 2. Intrabar stop / target management --------------------
        if position is not None:
            bars_in_market += 1
            stop_px = position.get("stop_price")
            target_px = position.get("target_price")
            hit_stop = stop_px is not None and l <= stop_px
            hit_target = target_px is not None and h >= target_px
            if hit_stop:
                # Gap-aware conservative fill: gap through stop -> open.
                if o < stop_px:
                    fill = o * (1 - cost_per_side)
                else:
                    fill = stop_px * (1 - cost_per_side)
                _close_position(max(fill, 0.01), ts, "STOP")
            elif hit_target:
                if o > target_px:
                    fill = o * (1 - cost_per_side)
                else:
                    fill = target_px * (1 - cost_per_side)
                _close_position(fill, ts, "TARGET")

        # ---- 3. Mark-to-market at the close --------------------------
        equity = cash + shares * c
        equity_curve.append({"date": str(ts.date()), "value": round(equity, 2)})

        # ---- 4. Decide next action from THIS close (no lookahead) ----
        action = str(actions[j] if j < len(actions) else "HOLD").upper()
        if action == "BUY" and position is None:
            pending_action = "BUY"
            # stops[j]/targets[j] are FRACTIONS -> convert to price levels
            pending_stop = c * (1 - float(stops[j]))
            pending_target = c * (1 + float(targets[j]))
            pending_meta = {"signal": "BUY"}
        elif action == "SELL" and position is not None:
            pending_action = "SELL"

    # ---- End of test: mark open position to market -------------------
    unrealized = 0.0
    open_at_end = False
    if position is not None:
        open_at_end = True
        last_close = float(data.iloc[-1]["close"])
        unrealized = (last_close - position["entry_price"]) * position["quantity"]

    metrics = compute_metrics(
        equity_curve=equity_curve,
        trades=trades,
        starting_cash=starting_cash,
        unrealized_pnl=unrealized,
        total_bars=n - 1,
        bars_in_market=bars_in_market,
    )
    metrics["open_position_at_end"] = open_at_end
    metrics["open_shares"] = round(shares, 6)
    metrics["final_value_includes_unrealized"] = open_at_end
    if open_at_end:
        metrics["open_entry_price"] = round(position["entry_price"], 4)
        metrics["open_quantity"] = round(position["quantity"], 6)

    # ---- Benchmark + alpha over the exact same period ---------------
    bench = benchmark_buy_hold(data, starting_cash)
    alpha = None
    if metrics["return_percent"] is not None and bench["return_percent"] is not None:
        alpha = round(metrics["return_percent"] - bench["return_percent"], 2)

    return {
        **metrics,
        "alpha_percent": alpha,
        "benchmark": bench,
        "trade_list": trades,
        "equity_curve": equity_curve,
    }


# ============================================================
# Buy & Hold benchmark
# ============================================================

def benchmark_buy_hold(data: pd.DataFrame, starting_cash: float = STARTING_CASH) -> dict:
    """
    Buy & hold the symbol for the exact same period.
    Entry at first bar's open, marked to market at last close.
    """
    if data is None or len(data) == 0:
        return {
            "return_percent": None,
            "final_value": starting_cash,
            "equity_curve": [],
            "max_drawdown_percent": None,
            "sharpe": None,
        }

    entry_price = float(data.iloc[0]["open"])
    shares = starting_cash / entry_price if entry_price > 0 else 0.0

    equity_curve = []
    closes = data["close"].astype(float)
    dates = [str(ts.date()) for ts in data.index]
    for date_str, close in zip(dates, closes.values):
        equity_curve.append({
            "date": date_str,
            "value": round(shares * float(close), 2),
        })

    final_value = shares * float(closes.iloc[-1])
    total_return = (final_value - starting_cash) / starting_cash

    eq = pd.Series([p["value"] for p in equity_curve], dtype=float)
    max_dd, _ = _max_drawdown(eq)

    rets = eq.pct_change().dropna()
    sharpe = None
    if len(rets) > 2 and float(rets.std(ddof=0)) > 0:
        sharpe = round(_finite(
            float(rets.mean()) / float(rets.std(ddof=0)) * math.sqrt(TRADING_DAYS_PER_YEAR)
        ), 2)

    return {
        "return_percent": round(total_return * 100, 2),
        "final_value": round(final_value, 2),
        "equity_curve": equity_curve,
        "max_drawdown_percent": round(max_dd * 100, 2),
        "sharpe": sharpe,
    }



def backtest(data: pd.DataFrame, starting_cash: float = STARTING_CASH) -> dict:
    """Backwards-compatible convenience wrapper.

    Runs the default multi-indicator strategy from strategies.py so
    legacy callers (and tests) keep working.
    """
    try:
        from backtest.strategies import multi_indicator_strategy
        plan = multi_indicator_strategy(data)
    except Exception:
        plan = {"actions": ["HOLD"] * len(data)}
    return run_backtest(
        data,
        actions=plan.get("actions"),
        stops=plan.get("stops"),
        targets=plan.get("targets"),
        starting_cash=starting_cash,
    )