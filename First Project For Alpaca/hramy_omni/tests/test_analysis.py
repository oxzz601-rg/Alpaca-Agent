"""
Tests for technical indicators, market signals and regime detection.
Run:  py -m unittest discover -s tests
"""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis.indicators import (
    calculate_adx,
    calculate_atr,
    calculate_ema,
    calculate_indicators,
    calculate_macd,
    calculate_rsi,
    calculate_sma,
    latest_snapshot,
)
from analysis.regime import detect_regime
from analysis.signals import compute_signal_scores, generate_market_signals
from tests.data_builder import build_indicator_data, build_ohlcv, make_snapshot


class TestIndicators(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = build_indicator_data(n=300)

    def test_sma_known_values(self):
        series = build_ohlcv(60)["close"]
        sma5 = calculate_sma(series, 5)
        expected = series.iloc[:5].mean()
        self.assertAlmostEqual(float(sma5.iloc[4]), float(expected), places=8)

    def test_ema_converges_to_price(self):
        flat = build_ohlcv(120)["close"] * 0 + 100.0
        ema = calculate_ema(flat, 20)
        self.assertAlmostEqual(float(ema.iloc[-1]), 100.0, places=6)

    def test_rsi_bounds(self):
        rsi = calculate_rsi(self.data["close"])
        valid = rsi.dropna()
        self.assertTrue(((valid >= 0) & (valid <= 100)).all())

    def test_rsi_all_gains_is_high(self):
        rising = build_ohlcv(40)["close"].cumsum() + 100
        rsi = calculate_rsi(rising).dropna()
        self.assertGreater(float(rsi.iloc[-1]), 70)

    def test_atr_positive(self):
        atr = calculate_atr(self.data).dropna()
        self.assertTrue((atr > 0).all())

    def test_macd_identity(self):
        macd, signal, hist = calculate_macd(self.data["close"])
        for s in (macd, signal, hist):
            self.assertEqual(len(s), len(self.data))
        diff = (macd - signal - hist).abs().max()
        self.assertLess(float(diff), 1e-9)

    def test_adx_bounds(self):
        adx = calculate_adx(self.data).dropna()
        self.assertTrue(((adx >= 0) & (adx <= 100)).all())

    def test_all_indicator_columns_present(self):
        for col in ("sma20", "sma50", "ema20", "rsi", "atr", "atr_pct",
                    "macd", "macd_signal", "macd_hist", "bb_upper", "bb_lower",
                    "bb_percent_b", "adx", "momentum", "volatility",
                    "volume_ratio", "vwap20"):
            self.assertIn(col, self.data.columns)

    def test_insufficient_data_raises(self):
        with self.assertRaises(RuntimeError):
            calculate_indicators(build_ohlcv(30))

    def test_snapshot_complete_and_finite(self):
        snap = latest_snapshot(self.data)
        for key in ("price", "sma20", "sma50", "rsi", "adx", "atr_pct",
                    "bb_percent_b", "volume_ratio", "vwap20"):
            self.assertIn(key, snap)
            self.assertTrue(np.isfinite(snap[key]))


class TestSignals(unittest.TestCase):

    def test_bullish_structure(self):
        market = generate_market_signals(make_snapshot())
        self.assertEqual(market["trend"], "BULLISH")

    def test_score_bounds_random_snapshots(self):
        rng = np.random.default_rng(7)
        for _ in range(200):
            snap = make_snapshot(
                price=float(rng.uniform(50, 300)),
                sma20=float(rng.uniform(50, 300)),
                sma50=float(rng.uniform(50, 300)),
                rsi=float(rng.uniform(0, 100)),
                momentum=float(rng.uniform(-25, 25)),
                volume_ratio=float(rng.uniform(0.2, 3.5)),
                volatility=float(rng.uniform(5, 90)),
                macd=float(rng.uniform(-2, 2)),
                macd_hist=float(rng.uniform(-1, 1)),
            )
            score = compute_signal_scores(snap)
            self.assertGreaterEqual(score["composite"], -100.0)
            self.assertLessEqual(score["composite"], 100.0)
            for value in score["components"].values():
                self.assertGreaterEqual(value, -1.0)
                self.assertLessEqual(value, 1.0)

    def test_strong_uptrend_scores_positive(self):
        snap = make_snapshot(price=170, sma20=150, sma50=135,
                             rsi=58, momentum=6)
        self.assertGreater(compute_signal_scores(snap)["composite"], 30)

    def test_strong_downtrend_scores_negative(self):
        snap = make_snapshot(price=110, sma20=140, sma50=155,
                             rsi=35, momentum=-8)
        self.assertLess(compute_signal_scores(snap)["composite"], -20)

    def test_deterministic(self):
        snap = make_snapshot()
        self.assertEqual(
            compute_signal_scores(snap)["composite"],
            compute_signal_scores(snap)["composite"],
        )


class TestRegime(unittest.TestCase):

    def test_bull_trend_detected(self):
        result = detect_regime(make_snapshot(adx=30, volatility=22))
        self.assertEqual(result.regime, "BULL_TREND")
        self.assertEqual(result.trend_strength, "STRONG")

    def test_bear_trend_detected(self):
        snap = make_snapshot(price=130, sma20=140, sma50=150,
                             support20=125, resistance20=160,
                             adx=27, volatility=24)
        self.assertEqual(detect_regime(snap).regime, "BEAR_TREND")

    def test_high_volatility_detected(self):
        snap = make_snapshot(volatility=55, adx=12)
        snap["sma20"] = 151.0
        self.assertEqual(detect_regime(snap).regime, "HIGH_VOLATILITY")

    def test_low_volatility_detected(self):
        snap = make_snapshot(volatility=10, adx=10)
        snap["price"] = (snap["sma20"] + snap["sma50"]) / 2
        self.assertEqual(detect_regime(snap).regime, "LOW_VOLATILITY")

    def test_regime_is_deterministic(self):
        a = detect_regime(make_snapshot()).to_dict()
        b = detect_regime(make_snapshot()).to_dict()
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()