"""
HRAMY OMNI AI - Walk-Forward / Out-of-Sample Analysis
============================================================
Splits the historical data chronologically:

    |-------- TRAIN (in-sample) --------|-- VALIDATION --|-- TEST (OOS) --|
                 60%                          20%              20%

Rules enforced:
    - Segments never overlap; the test segment is NEVER used for
      parameter selection.
    - The only optimization performed is a SMALL fixed grid for
      Strategy A (6 combinations), selected on TRAIN by Sharpe
      (min-trade filter) and confirmed on VALIDATION.
    - All other strategies run with fixed a-priori parameters on every
      segment, so their OOS results are fully honest.
    - Every reported result is labeled IN-SAMPLE / VALIDATION /
      OUT-OF-SAMPLE in the UI.
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.engine import benchmark_buy_hold, run_backtest
from backtest.strategies import (
    STRATEGY_REGISTRY,
    sma_rsi_strategy,
)
from config import WF_TRAIN_FRACTION, WF_VALIDATION_FRACTION

# Small, transparent grid for Strategy A parameter selection
SMA_RSI_GRID = [
    {"sma_short": 15, "sma_long": 50},
    {"sma_short": 20, "sma_long": 50},
    {"sma_short": 20, "sma_long": 60},
    {"rsi_upper": 65},
    {"rsi_upper": 70},
    {"rsi_upper": 75, "rsi_exit": 82},
]


def split_data(data: pd.DataFrame):
    """
    Chronologically split into train / validation / test segments.
    """
    n = len(data)
    train_end = int(n * WF_TRAIN_FRACTION)
    val_end = int(n * (WF_TRAIN_FRACTION + WF_VALIDATION_FRACTION))

    train = data.iloc[:train_end].copy()
    validation = data.iloc[train_end:val_end].copy()
    test = data.iloc[val_end:].copy()

    def _label(df):
        if len(df) == 0:
            return "N/A"
        return f"{df.index[0].date()} → {df.index[-1].date()}"

    return {
        "train": train,
        "validation": validation,
        "test": test,
        "labels": {
            "train": _label(train),
            "validation": _label(validation),
            "test": _label(test),
        },
        "sizes": {
            "train": len(train),
            "validation": len(validation),
            "test": len(test),
        },
    }


def _sharpe_of(result: dict) -> float:
    """Sharpe used for parameter selection (-inf when unavailable)."""
    sharpe = result.get("sharpe")
    if sharpe is None:
        return float("-inf")
    return float(sharpe)


def select_sma_rsi_params(train: pd.DataFrame, validation: pd.DataFrame) -> dict:
    """
    Select Strategy A parameters on TRAIN, confirm on VALIDATION.
    The OUT-OF-SAMPLE segment is intentionally NOT touched here.
    """
    best = None
    trials = []

    for override in SMA_RSI_GRID:
        params = {}
        params.update(override)

        try:
            plan = sma_rsi_strategy(train, params=params)
            result = run_backtest(
                train,
                actions=plan["actions"],
                stops=plan.get("stops"),
                targets=plan.get("targets"),
            )
        except Exception:
            continue

        trades = int(result.get("trades") or 0)
        score = _sharpe_of(result)
        if trades < 2:
            score -= 10.0  # discourage single-trade flukes

        trials.append({
            "params": params,
            "train_sharpe": None if score == float("-inf") else round(score, 2),
            "train_return": result.get("return_percent"),
            "train_trades": trades,
        })

        if best is None or score > best["score"]:
            best = {"params": params, "score": score}

    chosen = best["params"] if best else {}

    # Confirmation pass on validation with the selected parameters.
    val_sharpe = None
    val_return = None
    if chosen and len(validation) > 30:
        plan = sma_rsi_strategy(validation, params=chosen)
        result = run_backtest(
            validation,
            actions=plan["actions"],
            stops=plan.get("stops"),
            targets=plan.get("targets"),
        )
        val_sharpe = result.get("sharpe")
        val_return = result.get("return_percent")

    return {
        "selected_params": chosen,
        "validation_sharpe": val_sharpe,
        "validation_return_percent": val_return,
        "trials": trials,
    }


def evaluate_walk_forward(data: pd.DataFrame, starting_cash: float = 100_000.0) -> dict:
    """
    Run all strategies over train/validation/test and assemble a
    labeled comparison, including the buy-&-hold benchmark per segment.
    """
    split = split_data(data)

    results = {}
    for key, (name, fn) in STRATEGY_REGISTRY.items():
        entry = {"name": name}
        for segment in ("train", "validation", "test"):
            df_seg = split[segment]
            label = {
                "train": "IN-SAMPLE",
                "validation": "VALIDATION",
                "test": "OUT-OF-SAMPLE",
            }[segment]

            if len(df_seg) < 40:
                entry[segment] = {"label": label, "insufficient_data": True}
                continue

            try:
                plan = fn(df_seg)
                result = run_backtest(
                    df_seg,
                    actions=plan["actions"],
                    stops=plan.get("stops"),
                    targets=plan.get("targets"),
                    starting_cash=starting_cash,
                )
                result["label"] = label
                result["strategy_description"] = plan.get("description", "")
                entry[segment] = result
            except Exception as exc:
                entry[segment] = {"label": label, "error": type(exc).__name__}

        results[key] = entry

    benchmarks = {}
    for segment in ("train", "validation", "test"):
        df_seg = split[segment]
        if len(df_seg) > 5:
            benchmarks[segment] = benchmark_buy_hold(df_seg, starting_cash)
        else:
            benchmarks[segment] = {"return_percent": None}

    # Parameter selection happens ONLY on train+validation.
    selection = select_sma_rsi_params(split["train"], split["validation"])

    # Re-run strategy A on TEST with the SELECTED parameters (untouched until now).
    optimized_test = None
    if len(split["test"]) >= 40 and selection["selected_params"]:
        plan = sma_rsi_strategy(split["test"], params=selection["selected_params"])
        optimized_test = run_backtest(
            split["test"],
            actions=plan["actions"],
            stops=plan.get("stops"),
            targets=plan.get("targets"),
            starting_cash=starting_cash,
        )
        optimized_test["label"] = "OUT-OF-SAMPLE"

    return {
        "split_labels": split["labels"],
        "split_sizes": split["sizes"],
        "strategies": results,
        "benchmarks": benchmarks,
        "parameter_selection": selection,
        "optimized_strategy_a_test": optimized_test,
    }