"""
Unit tests for the AI agents lane.

Run from hramy_omni:
    $env:PYTHONPATH = ".;ai"
    py -m unittest agents.tests.test_agents -v
"""

import json
import os
import sys
import tempfile
import unittest

_here = os.path.dirname(os.path.abspath(__file__))
_agents = os.path.dirname(_here)
_ai = os.path.dirname(_agents)
_root = os.path.dirname(_ai)
for path in (_root, _ai):
    if path not in sys.path:
        sys.path.insert(0, path)

from agents.attribution import record_lesson, relevant_lessons
from agents.context import DEFAULT_ACCOUNT
from agents.devils_advocate import review
from agents.market_analyst import analyze
from agents.opportunity_scanner import scan
from agents.options_strategist import _iv_bucket, matrix_lookup, select_strategy
from agents.llm import refine_strategy
from agents.orchestrator import decide
from agents.schema import (
    AI_TRACE_STAGES,
    DELTA_MAX,
    DTE_MAX,
    TRACE_MARKET_ANALYST,
    TRACE_OPPORTUNITY_SCANNER,
    TRACE_OPTIONS_STRATEGIST,
    validate_trade_decision,
)

FIXTURES = os.path.join(_agents, "fixtures")


def _load_fixture(name: str) -> dict:
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as handle:
        return json.load(handle)


class IvBucketTests(unittest.TestCase):
    def test_buckets(self):
        self.assertEqual(_iv_bucket(29.9), "LOW")
        self.assertEqual(_iv_bucket(40.0), "MID")
        self.assertEqual(_iv_bucket(50.1), "HIGH")


class MatrixTests(unittest.TestCase):
    def test_regime_iv_cells(self):
        cases = [
            ("BULL_TREND", 20, False, "BULL_CALL_SPREAD", "OPEN"),
            ("BULL_TREND", 62, False, "CASH_SECURED_PUT", "OPEN"),
            ("BEAR_TREND", 20, False, "BEAR_PUT_SPREAD", "OPEN"),
            ("BEAR_TREND", 62, False, "NONE", "HOLD"),
            ("BEAR_TREND", 62, True, "COVERED_CALL", "OPEN"),
            ("SIDEWAYS", 62, False, "CASH_SECURED_PUT", "OPEN"),
            ("SIDEWAYS", 20, False, "NONE", "HOLD"),
            ("BREAKOUT", 20, False, "LONG_CALL", "OPEN"),
            ("HIGH_VOLATILITY", 62, False, "CASH_SECURED_PUT", "OPEN"),
            ("LOW_VOLATILITY", 20, False, "BULL_CALL_SPREAD", "OPEN"),
            ("BULL_TREND", 40, False, "NONE", "HOLD"),
        ]
        for regime, iv, shares, strategy, action in cases:
            got = matrix_lookup(regime, iv, has_shares=shares)
            self.assertEqual(got["strategy_type"], strategy, msg=(regime, iv, shares))
            self.assertEqual(got["action"], action, msg=(regime, iv, shares))

    def test_conflicting_context_holds(self):
        market = {
            "symbol": "MSFT",
            "regime": "SIDEWAYS",
            "iv_rank": 20.0,
            "score": {"composite": 1.0},
        }
        decision = select_strategy(market, DEFAULT_ACCOUNT, 20.0)
        self.assertEqual(decision["action"], "HOLD")
        self.assertEqual(decision["strategy_type"], "NONE")


class FixtureTests(unittest.TestCase):
    def test_bull_grey_zone_holds(self):
        market = _load_fixture("market_context_bull.json")
        decision = select_strategy(market, market.get("account"), market["iv_rank"])
        self.assertEqual(decision["action"], "HOLD")
        self.assertEqual(decision["strategy_type"], "NONE")

    def test_sideways_high_iv_opens_csp(self):
        market = _load_fixture("market_context_sideways.json")
        decision = select_strategy(market, market.get("account"), market["iv_rank"])
        self.assertEqual(decision["action"], "OPEN")
        self.assertEqual(decision["strategy_type"], "CASH_SECURED_PUT")
        self.assertTrue(decision["reason"])
        self.assertTrue(decision["key_factors"])
        self.assertTrue(decision["invalidations"])

    def test_high_vol_opens_csp(self):
        market = _load_fixture("market_context_high_vol.json")
        decision = select_strategy(market, market.get("account"), market["iv_rank"])
        self.assertEqual(decision["action"], "OPEN")
        self.assertEqual(decision["strategy_type"], "CASH_SECURED_PUT")


class SchemaTests(unittest.TestCase):
    def test_clamps_out_of_range_values(self):
        clamped = validate_trade_decision(
            {
                "action": "OPEN",
                "engine": "DIRECTIONAL",
                "symbol": "NVDA",
                "strategy_type": "BULL_CALL_SPREAD",
                "target_dte": 999,
                "target_delta": 2.5,
                "spread_width": 99,
                "contracts": 99,
                "confidence": 5,
                "risk": "MEDIUM",
                "reason": "test",
                "key_factors": ["a"],
                "invalidations": ["b"],
                "regime": "BULL_TREND",
                "iv_rank": 150,
                "devils_advocate": {"objection": "ok", "verdict": "PROCEED"},
            },
            symbol="NVDA",
            source="local_policy",
        )
        self.assertEqual(clamped["target_dte"], DTE_MAX)
        self.assertEqual(clamped["target_delta"], DELTA_MAX)
        self.assertEqual(clamped["confidence"], 1.0)
        self.assertEqual(clamped["iv_rank"], 100.0)
        self.assertEqual(clamped["contracts"], 10)

    def test_block_downgrades_open_to_hold(self):
        blocked = validate_trade_decision(
            {
                "action": "OPEN",
                "engine": "THETA",
                "symbol": "NVDA",
                "strategy_type": "CASH_SECURED_PUT",
                "target_dte": 21,
                "target_delta": 0.25,
                "contracts": 1,
                "confidence": 0.8,
                "risk": "MEDIUM",
                "reason": "would open",
                "key_factors": ["x"],
                "invalidations": ["y"],
                "regime": "SIDEWAYS",
                "iv_rank": 68,
                "devils_advocate": {"objection": "earnings", "verdict": "BLOCK"},
            },
            symbol="NVDA",
        )
        self.assertEqual(blocked["action"], "HOLD")
        self.assertEqual(blocked["strategy_type"], "NONE")
        self.assertEqual(blocked["contracts"], 0)

    def test_garbage_llm_response_holds(self):
        fallback = validate_trade_decision("not-a-dict", symbol="NVDA")
        self.assertEqual(fallback["action"], "HOLD")
        self.assertEqual(fallback["source"], "fallback")

    def test_invalid_action_holds(self):
        fallback = validate_trade_decision({"action": "YOLO"}, symbol="NVDA")
        self.assertEqual(fallback["action"], "HOLD")

    def test_refine_without_groq_keeps_matrix(self):
        market = _load_fixture("market_context_sideways.json")
        base = select_strategy(market, market.get("account"), market["iv_rank"])
        from unittest.mock import patch
        with patch("agents.llm.llm_enabled", return_value=False):
            refined = refine_strategy(base, market, market.get("account"), lessons=[])
        self.assertEqual(refined["action"], base["action"])
        self.assertEqual(refined["strategy_type"], base["strategy_type"])


class DevilsAdvocateTests(unittest.TestCase):
    def test_blocks_csp_into_oversold(self):
        decision = {
            "action": "OPEN",
            "engine": "THETA",
            "strategy_type": "CASH_SECURED_PUT",
            "iv_rank": 68,
        }
        da = review(decision, {"rsi": 22, "regime": "SIDEWAYS", "score": {"composite": 4}})
        self.assertEqual(da["verdict"], "BLOCK")

    def test_proceeds_on_clean_sideways_csp(self):
        decision = {
            "action": "OPEN",
            "engine": "THETA",
            "strategy_type": "CASH_SECURED_PUT",
            "iv_rank": 68,
        }
        da = review(decision, {"rsi": 52, "regime": "SIDEWAYS", "score": {"composite": 4}})
        self.assertEqual(da["verdict"], "PROCEED")


class OrchestratorTests(unittest.TestCase):
    def test_decide_on_sideways_fixture(self):
        market = _load_fixture("market_context_sideways.json")
        decision = decide(market, market.get("account"), market["iv_rank"])
        self.assertEqual(decision["action"], "OPEN")
        self.assertEqual(decision["strategy_type"], "CASH_SECURED_PUT")
        self.assertEqual(decision["agent_trace"], list(AI_TRACE_STAGES))
        self.assertEqual(decision["agent_trace"][0], TRACE_MARKET_ANALYST)
        self.assertEqual(decision["agent_trace"][1], TRACE_OPPORTUNITY_SCANNER)
        self.assertEqual(decision["agent_trace"][2], TRACE_OPTIONS_STRATEGIST)
        self.assertIn(decision["devils_advocate"]["verdict"], {"PROCEED", "BLOCK"})

    def test_decide_never_raises(self):
        self.assertEqual(decide(None)["action"], "HOLD")
        self.assertEqual(decide({}, None, None)["action"], "HOLD")
        self.assertEqual(decide("bad")["action"], "HOLD")

    def test_block_path_through_decide(self):
        market = dict(_load_fixture("market_context_sideways.json"))
        market["rsi"] = 18
        decision = decide(market, market.get("account"), market["iv_rank"])
        self.assertEqual(decision["action"], "HOLD")
        self.assertEqual(decision["devils_advocate"]["verdict"], "BLOCK")

    def test_analyst_and_scanner(self):
        bull = _load_fixture("market_context_bull.json")
        sideways = _load_fixture("market_context_sideways.json")
        analyst = analyze(bull)
        self.assertIn(analyst["sentiment"], {"BULLISH", "BEARISH", "NEUTRAL"})
        ranked = scan([bull, sideways], DEFAULT_ACCOUNT)
        self.assertEqual(len(ranked), 2)
        tradeable = [row for row in ranked if row["tradeable"]]
        blocked = [row for row in ranked if not row["tradeable"]]
        self.assertEqual(ranked, tradeable + blocked)
        for group in (tradeable, blocked):
            scores = [row["score"] for row in group]
            self.assertEqual(scores, sorted(scores, reverse=True))


class AttributionTests(unittest.TestCase):
    def test_record_and_retrieve_lesson(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "lessons.json")
            record_lesson(
                {
                    "symbol": "NVDA",
                    "strategy_type": "CASH_SECURED_PUT",
                    "pnl": 120.0,
                    "exit_reason": "hit 50% of max profit",
                },
                path=path,
            )
            lessons = relevant_lessons("NVDA", n=3, path=path)
            self.assertEqual(len(lessons), 1)
            self.assertIn("NVDA", lessons[0])
            self.assertIn("CASH_SECURED_PUT", lessons[0])


if __name__ == "__main__":
    unittest.main()
