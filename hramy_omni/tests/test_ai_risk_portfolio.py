"""
Tests for the AI validation gate (anti-fabrication), risk manager
and paper portfolio accounting.
Run:  py -m unittest discover -s tests
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.chatbot import SYSTEM_PROMPT, _offline_answer, parse_command
from ai.groq_engine import _validate_result, extract_json, local_policy_decision
from portfolio.simulator import PaperPortfolio
from risk.risk_manager import RiskManager


def make_ai(**overrides) -> dict:
    base = {
        "decision": "BUY",
        "confidence": 0.85,
        "risk": "MEDIUM",
        "position_size_percent": 12.0,
        "stop_loss_percent": 2.5,
        "take_profit_percent": 5.5,
        "time_horizon": "SWING",
        "market_regime": "BULL_TREND",
        "reason": "Momentum confirms trend.",
        "key_factors": ["RSI 55", "ADX 30"],
        "invalidations": ["Close below SMA20"],
    }
    base.update(overrides)
    return base


class TestAIValidation(unittest.TestCase):
    """The AI can never fabricate data or bypass clamps."""

    def test_valid_decision_passes(self):
        result = _validate_result(make_ai())
        self.assertEqual(result["decision"], "BUY")
        self.assertEqual(result["source"], "groq")
        self.assertIsNone(result["failure_type"])

    def test_invalid_decision_becomes_safe_hold(self):
        result = _validate_result(make_ai(decision="YOLO"))
        self.assertEqual(result["decision"], "HOLD")
        self.assertEqual(result["failure_type"], "schema_violation")

    def test_invalid_risk_becomes_safe_hold(self):
        result = _validate_result(make_ai(risk="EXTREME"))
        self.assertEqual(result["decision"], "HOLD")

    def test_local_policy_acts_on_strong_bullish_setup(self):
        market = {
            "score": {"composite": 25.0},
            "regime": "BULL_TREND",
            "trend": "BULLISH",
            "momentum_signal": "POSITIVE",
            "volatility_label": "MODERATE",
            "atr_pct": 2.2,
        }
        result = local_policy_decision(market, {"shares": 0})
        self.assertEqual(result["decision"], "BUY")
        self.assertGreater(result["confidence"], 0.5)

    def test_in_app_commands_are_explicit(self):
        self.assertEqual(parse_command("simulate this decision"), "EXECUTE_DECISION")
        self.assertEqual(parse_command("reset my paper account"), "RESET_PAPER")
        self.assertEqual(parse_command("refresh market analysis"), "REFRESH_ANALYSIS")
        self.assertIsNone(parse_command("change the code for me"))

    def test_assistant_is_in_app_only(self):
        self.assertNotIn("hackathon", SYSTEM_PROMPT.lower())
        self.assertNotIn("hackathon", _offline_answer("hello").lower())

    def test_confidence_clamped_to_unit_interval(self):
        self.assertLessEqual(_validate_result(make_ai(confidence=7.5))["confidence"], 1.0)
        self.assertGreaterEqual(_validate_result(make_ai(confidence=-3))["confidence"], 0.0)

    def test_position_size_clamped_to_cap(self):
        result = _validate_result(make_ai(position_size_percent=90.0))
        self.assertLessEqual(result["position_size_percent"], 20.0 + 1e-9)

    def test_stop_and_target_clamped(self):
        low = _validate_result(make_ai(stop_loss_percent=0.01, take_profit_percent=0.001))
        self.assertGreaterEqual(low["stop_loss_percent"], 0.8)
        self.assertGreaterEqual(low["take_profit_percent"], 1.5)
        high = _validate_result(make_ai(stop_loss_percent=99, take_profit_percent=500))
        self.assertLessEqual(high["stop_loss_percent"], 12.0)
        self.assertLessEqual(high["take_profit_percent"], 35.0)

    def test_hold_forces_zero_size(self):
        result = _validate_result(make_ai(decision="HOLD", position_size_percent=15))
        self.assertEqual(result["position_size_percent"], 0.0)

    def test_buy_with_zero_size_gets_floor(self):
        result = _validate_result(make_ai(position_size_percent=0))
        self.assertGreater(result["position_size_percent"], 0.0)

    def test_ai_supplied_prices_are_dropped(self):
        result = _validate_result(
            make_ai(confidence="very high", price=999_999, fabricated_price=42)
        )
        self.assertNotIn("price", result)
        self.assertNotIn("fabricated_price", result)

    def test_extract_json_plain(self):
        self.assertEqual(extract_json('{"decision": "HOLD"}')["decision"], "HOLD")

    def test_extract_json_markdown_fence(self):
        text = '```json\n{"decision": "BUY", "confidence": 0.9}\n```'
        self.assertEqual(extract_json(text)["decision"], "BUY")

    def test_extract_json_embedded_in_prose(self):
        text = 'Sure! {"decision": "SELL"} hope that helps'
        self.assertEqual(extract_json(text)["decision"], "SELL")

    def test_extract_json_garbage_raises(self):
        with self.assertRaises(Exception):
            extract_json("no json here at all")


class TestRiskManager(unittest.TestCase):

    def setUp(self):
        self.rm = RiskManager()
        self.account = {"equity": 100_000.0, "cash": 100_000.0, "shares": 0}
        self.market = {"trend": "BULLISH", "momentum_signal": "POSITIVE",
                       "regime": "BULL_TREND", "atr_pct": 2.0}

    def test_low_confidence_blocked(self):
        allowed, _, reason = self.rm.evaluate(
            "BUY", make_ai(confidence=0.3), 100.0, self.account, self.market
        )
        self.assertFalse(allowed)
        self.assertIn("confidence", reason.lower())

    def test_high_risk_blocked(self):
        allowed, _, _ = self.rm.evaluate(
            "BUY", make_ai(risk="HIGH"), 100.0, self.account, self.market
        )
        self.assertFalse(allowed)

    def test_bear_regime_blocks_buy(self):
        market = dict(self.market, regime="BEAR_TREND")
        allowed, _, reason = self.rm.evaluate(
            "BUY", make_ai(), 100.0, self.account, market
        )
        self.assertFalse(allowed)
        self.assertIn("BEAR_TREND", reason)

    def test_sell_without_position_blocked(self):
        allowed, _, reason = self.rm.evaluate(
            "SELL", make_ai(), 100.0, self.account, self.market
        )
        self.assertFalse(allowed)
        self.assertIn("position", reason.lower())

    def test_exposure_cap_blocks_buy(self):
        account = {"equity": 100_000.0, "cash": 10_000.0, "shares": 900}
        ai = make_ai(position_size_percent=20.0)
        allowed, _, reason = self.rm.evaluate("BUY", ai, 100.0, account, self.market)
        self.assertFalse(allowed)
        self.assertIn("exposure", reason.lower())

    def test_hold_always_allowed(self):
        allowed, status, _ = self.rm.evaluate(
            "HOLD", make_ai(confidence=0.1), 100.0, self.account, {}
        )
        self.assertTrue(allowed)
        self.assertEqual(status, "PASSED")

    def test_plan_sizing_respects_max_position_cap(self):
        ai = make_ai(position_size_percent=50.0)
        plan = self.rm.build_execution_plan("BUY", ai, 100.0, self.account, self.market)
        self.assertEqual(plan.action, "BUY")
        self.assertLessEqual(plan.notional_value,
                             self.account["equity"] * 0.20 + 1e-6)

    def test_blocked_decision_yields_hold_plan(self):
        plan = self.rm.build_execution_plan(
            "BUY", make_ai(risk="HIGH"), 100.0, self.account, self.market
        )
        self.assertEqual(plan.action, "HOLD")

    def test_sell_plan_exits_full_position(self):
        account = {"equity": 100_000.0, "cash": 50_000.0, "shares": 37.5}
        bear = {"trend": "BEARISH", "momentum_signal": "NEGATIVE",
                "regime": "BEAR_TREND", "atr_pct": 2.0}
        plan = self.rm.build_execution_plan("SELL", make_ai(), 100.0, account, bear)
        self.assertEqual(plan.action, "SELL")
        self.assertAlmostEqual(plan.quantity, 37.5)


class TestPaperPortfolio(unittest.TestCase):

    def setUp(self):
        self.pf = PaperPortfolio(starting_cash=10_000.0,
                                 commission_rate=0.001, slippage_pct=0.001)

    def test_buy_reduces_cash_and_charges_fee(self):
        msg = self.pf.execute("TEST", "BUY", 100.0, quantity=2.0)
        self.assertIn("SIMULATED BUY", msg)
        self.assertAlmostEqual(self.pf.shares, 2.0)
        fill = 100.0 * 1.001                      # slippage on the fill (100.10)
        notional = 2.0 * fill                     # 200.20
        fee = notional * 0.001                    # 0.2002
        expected_cash = 10_000.0 - (notional + fee)
        self.assertAlmostEqual(self.pf.cash, expected_cash, places=4)

    def test_sell_creates_round_trip_record(self):
        self.pf.execute("TEST", "BUY", 100.0, quantity=2.0)
        msg = self.pf.execute("TEST", "SELL", 110.0)
        self.assertIn("SIMULATED SELL", msg)
        self.assertEqual(len(self.pf.trades), 1)
        trade = self.pf.trades[0]
        for field in ("trade_id", "entry_time", "exit_time", "entry_price",
                      "exit_price", "quantity", "gross_pnl", "fees",
                      "net_pnl", "return_percent", "holding_days",
                      "exit_reason"):
            self.assertIn(field, trade)
        self.assertGreater(trade["net_pnl"], 0)

    def test_cannot_oversell_or_go_negative_cash(self):
        self.pf.execute("TEST", "BUY", 100.0, quantity=1.0)
        self.pf.execute("TEST", "SELL", 105.0, quantity=50.0)
        self.assertEqual(self.pf.shares, 0.0)
        self.assertIn("NO TRADE", self.pf.execute("TEST", "SELL", 105.0))

    def test_fractional_shares_supported(self):
        self.pf.execute("TEST", "BUY", 100.0, quantity=0.5)
        self.assertAlmostEqual(self.pf.shares, 0.5)

    def test_buy_scales_down_when_cash_short(self):
        pf = PaperPortfolio(starting_cash=100.0,
                            commission_rate=0.001, slippage_pct=0.001)
        msg = pf.execute("TEST", "BUY", 100.0, quantity=5.0)
        self.assertIn("SIMULATED BUY", msg)
        self.assertLess(pf.cash, 100.0)
        self.assertGreaterEqual(pf.cash, 0.0)

    def test_hold_does_nothing(self):
        msg = self.pf.execute("TEST", "HOLD", 100.0)
        self.assertIn("HOLD", msg)
        self.assertEqual(self.pf.cash, 10_000.0)

    def test_summary_separates_realized_and_unrealized(self):
        self.pf.execute("TEST", "BUY", 100.0, quantity=2.0)
        open_summary = self.pf.summary(120.0)
        self.assertTrue(open_summary["open_position"])
        self.assertGreater(open_summary["unrealized_pnl"], 0)
        self.assertAlmostEqual(open_summary["realized_pnl"], 0.0)

        self.pf.execute("TEST", "SELL", 120.0)
        closed = self.pf.summary(120.0)
        self.assertFalse(closed["open_position"])
        self.assertGreater(closed["realized_pnl"], 0)
        self.assertAlmostEqual(closed["unrealized_pnl"], 0.0)


class TestSecurityAudit(unittest.TestCase):
    """Ensure absolute API key security across the entire project."""

    def test_gitignore_protects_env_and_secrets(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        gitignore_path = os.path.join(root, ".gitignore")
        self.assertTrue(os.path.exists(gitignore_path), ".gitignore must exist")
        content = open(gitignore_path, "r", encoding="utf-8").read()
        self.assertIn(".env", content, ".gitignore must ignore .env")

    def test_no_hardcoded_credentials_in_python_files(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for dirpath, _, filenames in os.walk(root):
            if any(part in dirpath for part in (".git", "__pycache__", "venv", ".venv", "env", "tests")):
                continue
            for fname in filenames:
                if fname.endswith(".py"):
                    fpath = os.path.join(dirpath, fname)
                    text = open(fpath, "r", encoding="utf-8", errors="ignore").read()
                    for line in text.splitlines():
                        line_clean = line.strip()
                        if line_clean.startswith("#"):
                            continue
                        if any(var in line_clean for var in ("ALPACA_API_KEY =", "ALPACA_SECRET_KEY =", "GROQ_API_KEY =")):
                            self.assertIn("os.getenv", line_clean,
                                         f"Credential must use os.getenv in {fname}: {line_clean}")


if __name__ == "__main__":
    unittest.main()