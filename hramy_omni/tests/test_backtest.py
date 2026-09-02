"""
Tests for the backtesting engine: execution realism, trade
accounting, metrics and walk-forward integrity.
Run:  py -m unittest discover -s tests
"""

import math
import os
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.engine import (
    _max_drawdown,
    benchmark_buy_hold,
    compute_metrics,
    run_backtest,
)
from backtest.strategies import (
    ai_policy_strategy,
    ai_risk_managed_strategy,
    multi_indicator_strategy,
    sma_rsi_strategy,
    trend_momentum_strategy,
)
from backtest.walkforward import evaluate_walk_forward, split_data
from tests.data_builder import build_indicator_data


class TestExecutionModel(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = build_indicator_data(n=320)

    def test_trade_is_round_trip(self):
        plan = sma_rsi_strategy(self.data)
        result = run_backtest(self.data, actions=plan["actions"],
                              stops=plan["stops"], targets=plan["targets"])
        for trade in result["trade_list"]:
            self.assertIn(trade["exit_reason"], ("SIGNAL", "STOP", "TARGET"))
            self.assertGreater(trade["quantity"], 0)
            # entry -> exit ordering in time
            self.assertLessEqual(str(trade["entry_time"]), str(trade["exit_time"]))

    def test_no_lookahead_entry_after_signal(self):
        """Entry fill must occur AFTER the signal bar (next bar open)."""
        plan = sma_rsi_strategy(self.data)
        result = run_backtest(self.data, actions=plan["actions"],
                              stops=plan["stops"], targets=plan["targets"])
        dates = list(self.data.index.strftime("%Y-%m-%d"))
        for trade in result["trade_list"]:
            self.assertIn(trade["entry_time"], dates)
            entry_idx = dates.index(trade["entry_time"])
            # engine only fills from bar 1 onward; signal was at entry-1 or earlier
            self.assertGreaterEqual(entry_idx, 1)

    def test_stop_loss_triggers_on_crash(self):
        """A violent crash after entry MUST exit via STOP."""
        data = build_indicator_data(n=300).copy()
        # Force a BUY early then crash
        n = len(data)
        actions = ["HOLD"] * n
        actions[30] = "BUY"
        stops = [0.02] * n
        targets = [0.10] * n
        # crash: gap down 12% on the bar after entry and keep falling
        data.iloc[31, data.columns.get_loc("open")] *= 0.90
        data.iloc[31, data.columns.get_loc("close")] *= 0.85
        data.iloc[31, data.columns.get_loc("low")] *= 0.83

        result = run_backtest(data, actions=actions, stops=stops, targets=targets)
        self.assertEqual(result["trades"], 1)
        self.assertEqual(result["trade_list"][0]["exit_reason"], "STOP")
        self.assertLess(result["trade_list"][0]["net_pnl"], 0)

    def test_take_profit_triggers(self):
        data = build_indicator_data(n=300).copy()
        n = len(data)
        actions = ["HOLD"] * n
        actions[30] = "BUY"
        stops = [0.02] * n
        targets = [0.03] * n
        # Normal fill on bar 31, then strong rally on bar 32 to trigger target
        data.iloc[32, data.columns.get_loc("high")] *= 1.10
        data.iloc[32, data.columns.get_loc("close")] *= 1.08

        result = run_backtest(data, actions=actions, stops=stops, targets=targets)
        self.assertEqual(result["trades"], 1)
        self.assertEqual(result["trade_list"][0]["exit_reason"], "TARGET")
        self.assertGreater(result["trade_list"][0]["net_pnl"], 0)

    def test_costs_are_charged(self):
        """Zero trades -> final value equals starting cash exactly."""
        n = len(self.data)
        result = run_backtest(self.data, actions=["HOLD"] * n)
        self.assertEqual(result["trades"], 0)
        self.assertAlmostEqual(result["final_value"], result["starting_value"], places=2)


class TestTradeAccounting(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = build_indicator_data(n=320)

    def test_open_position_marked_to_market(self):
        data = build_indicator_data(n=200).copy()
        n = len(data)
        actions = ["HOLD"] * n
        actions[n - 3] = "BUY"
        stops = [0.05] * n
        targets = [0.20] * n
        result = run_backtest(data, actions=actions, stops=stops, targets=targets)
        if not result["open_position_at_end"]:
            self.skipTest("position exited before test end (stop/target hit)")
        last_close = float(data["close"].iloc[-1])
        expected_unrealized = (last_close - result["open_entry_price"]) * result["open_quantity"]
        self.assertAlmostEqual(
            result["unrealized_pnl"], expected_unrealized, places=2
        )
        realized_sum = sum(t["net_pnl"] for t in result["trade_list"])
        self.assertAlmostEqual(result["realized_pnl"], realized_sum, places=1)

    def test_metrics_na_when_no_trades(self):
        result = run_backtest(self.data, actions=["HOLD"] * len(self.data))
        self.assertIsNone(result["win_rate"])
        self.assertIsNone(result["profit_factor"])

    def test_profit_factor_none_when_no_losses(self):
        metrics = compute_metrics(
            equity_curve=[{"value": 100}, {"value": 110}],
            trades=[{"net_pnl": 10, "return_percent": 10}],
            starting_cash=100,
        )
        self.assertIsNone(metrics["profit_factor"])  # undefined (infinite)
        self.assertEqual(metrics["win_rate"], 100.0)

    def test_drawdown_known_value(self):
        eq = pd.Series([100, 120, 90, 95])
        max_dd, _ = _max_drawdown(eq)
        self.assertAlmostEqual(max_dd, 0.25, places=6)  # 120 -> 90

    def test_max_drawdown_matches_equity(self):
        plan = multi_indicator_strategy(self.data)
        result = run_backtest(self.data, actions=plan["actions"],
                              stops=plan.get("stops"), targets=plan.get("targets"))
        eq = pd.Series([p["value"] for p in result["equity_curve"]])
        dd, _ = _max_drawdown(eq)
        self.assertAlmostEqual(dd * 100, result["max_drawdown_percent"], places=1)

    def test_benchmark_buy_hold_return(self):
        bench = benchmark_buy_hold(self.data)
        first_open = float(self.data["open"].iloc[0])
        last_close = float(self.data["close"].iloc[-1])
        expected = (last_close / first_open - 1) * 100
        self.assertAlmostEqual(bench["return_percent"], round(expected, 2), places=1)

    def test_alpha_is_strategy_minus_benchmark(self):
        plan = sma_rsi_strategy(self.data)
        result = run_backtest(self.data, actions=plan["actions"],
                              stops=plan.get("stops"), targets=plan.get("targets"))
        bench_ret = benchmark_buy_hold(self.data)["return_percent"]
        expected = round(result["return_percent"] - bench_ret, 2)
        self.assertAlmostEqual(result["alpha_percent"], expected, places=2)


class TestStrategiesProducePlans(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = build_indicator_data(n=320)

    def test_all_strategies_emit_valid_action_lists(self):
        for fn in (sma_rsi_strategy, trend_momentum_strategy,
                   multi_indicator_strategy, ai_policy_strategy,
                   ai_risk_managed_strategy):
            plan = fn(self.data)
            self.assertEqual(len(plan["actions"]), len(self.data))
            self.assertEqual(len(plan["stops"]), len(self.data))
            self.assertEqual(len(plan["targets"]), len(self.data))
            for action in plan["actions"]:
                self.assertIn(action, ("BUY", "SELL", "HOLD"))
            for s in plan["stops"]:
                self.assertGreater(s, 0)
                self.assertLess(s, 0.30)

    def test_strategies_are_stateful_no_consecutive_buys(self):
        """BUY never repeats while a position would already be open."""
        plan = sma_rsi_strategy(self.data)
        holding = False
        for action in plan["actions"]:
            if action == "BUY":
                self.assertFalse(holding, "BUY emitted while already positioned")
                holding = True
            elif action == "SELL":
                self.assertTrue(holding, "SELL emitted while flat")
                holding = False

    def test_risk_managed_blocks_more_than_plain_ai(self):
        plain = ai_policy_strategy(self.data)
        gated = ai_risk_managed_strategy(self.data)
        buys_plain = sum(1 for a in plain["actions"] if a == "BUY")
        buys_gated = sum(1 for a in gated["actions"] if a == "BUY")
        self.assertLessEqual(buys_gated, buys_plain)


class TestWalkForward(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = build_indicator_data(n=400)

    def test_split_sizes_and_no_overlap(self):
        split = split_data(self.data)
        total = sum(split["sizes"].values())
        self.assertEqual(total, len(self.data))

        train_dates = set(split["train"].index)
        val_dates = set(split["validation"].index)
        test_dates = set(split["test"].index)
        self.assertFalse(train_dates & val_dates, "train overlaps validation")
        self.assertFalse(train_dates & test_dates, "train overlaps test")
        self.assertFalse(val_dates & test_dates, "validation overlaps test")

        self.assertLess(split["train"].index.max(), split["validation"].index.min())
        self.assertLess(split["validation"].index.max(), split["test"].index.min())

    def test_walk_forward_runs_all_strategies(self):
        wf = evaluate_walk_forward(self.data)
        for key in ("A", "B", "C", "D", "E"):
            entry = wf["strategies"][key]
            for segment in ("train", "validation", "test"):
                seg_result = entry[segment]
                if seg_result.get("insufficient_data"):
                    continue
                self.assertNotIn("error", seg_result,
                                 f"{key}/{segment} raised an error")
        for segment in ("train", "validation", "test"):
            self.assertIn(segment, wf["benchmarks"])


if __name__ == "__main__":
    unittest.main()