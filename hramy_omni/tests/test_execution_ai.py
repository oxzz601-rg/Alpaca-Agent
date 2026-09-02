"""AI + backend execution-loop tests (no live Alpaca orders)."""

import json
import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AI = os.path.join(_ROOT, "ai")
for path in (_ROOT, _AI):
    if path not in sys.path:
        sys.path.insert(0, path)

from trading.execution_loop import ExecutionLoop
from trading.iv_rank import realized_vol_rank
from trading.option_chain import occ_option_symbol, parse_occ_symbol
from trading.risk import OptionRiskGate

FIXTURE = os.path.join(_AI, "agents", "fixtures", "market_context_sideways.json")


class FakeBroker:
    def __init__(self):
        self.calls = []

    def submit_option_order(self, **kwargs):
        self.calls.append(kwargs)
        return {"id": "paper-mock", "status": "accepted"}


def _load_sideways():
    with open(FIXTURE, encoding="utf-8") as handle:
        return json.load(handle)


class OccSymbolTests(unittest.TestCase):
    def test_occ_format(self):
        symbol = occ_option_symbol("AAPL", "2026-01-16", "put", 225.0)
        self.assertEqual(symbol, "AAPL260116P00225000")

    def test_parse_occ(self):
        parsed = parse_occ_symbol("AAPL260116P00225000")
        self.assertEqual(parsed["root"], "AAPL")
        self.assertEqual(parsed["expiry_date"], "2026-01-16")
        self.assertEqual(parsed["side"], "put")
        self.assertEqual(parsed["strike"], 225.0)


class IvRankTests(unittest.TestCase):
    def test_rank_is_clamped(self):
        import pandas as pd
        closes = pd.Series([100.0, 101.0, 99.0, 102.0] * 40)
        rank = realized_vol_rank(closes)
        self.assertGreaterEqual(rank, 0.0)
        self.assertLessEqual(rank, 100.0)


class ExecutionAiTests(unittest.TestCase):
    def test_sideways_fixture_dry_runs_csp(self):
        market = _load_sideways()
        account = market["account"]
        loop = ExecutionLoop(broker=None, submit=False, use_llm=False)
        result = loop.run_cycle("AAPL", market, account, positions=[])
        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(result["decision"]["action"], "OPEN")
        self.assertEqual(result["decision"]["strategy_type"], "CASH_SECURED_PUT")
        self.assertTrue(result["plan"]["cash_secured"])
        self.assertIn("P", result["option_symbol"])
        self.assertIn("RISK_MANAGER", result["decision"]["agent_trace"])
        self.assertIn("EXECUTION", result["decision"]["agent_trace"])
        self.assertIn("OPTIONS_STRATEGIST", result["decision"]["agent_trace"])

    def test_devils_advocate_block_holds(self):
        market = _load_sideways()
        market["rsi"] = 18
        loop = ExecutionLoop(submit=False, use_llm=False)
        result = loop.run_cycle("AAPL", market, market["account"], positions=[])
        self.assertEqual(result["status"], "hold")
        self.assertEqual(result["decision"]["action"], "HOLD")
        self.assertEqual(result["decision"]["devils_advocate"]["verdict"], "BLOCK")

    def test_submit_uses_ai_targets_on_mock_broker(self):
        market = _load_sideways()
        broker = FakeBroker()
        loop = ExecutionLoop(broker=broker, submit=True, use_llm=False)
        result = loop.run_cycle("AAPL", market, market["account"], positions=[])
        self.assertEqual(result["status"], "submitted")
        self.assertEqual(len(broker.calls), 1)
        self.assertEqual(broker.calls[0]["side"], "sell")
        self.assertEqual(broker.calls[0]["option_symbol"], result["option_symbol"])

    def test_risk_blocks_when_cash_too_low(self):
        market = _load_sideways()
        account = dict(market["account"])
        account["cash"] = 10.0
        loop = ExecutionLoop(submit=False)
        result = loop.run_cycle("AAPL", market, account, positions=[])
        self.assertEqual(result["status"], "blocked")

    def test_gate_rejects_naked_short(self):
        gate = OptionRiskGate()
        ok, reason = gate.evaluate(
            {
                "dte": 21,
                "strategy": "CASH_SECURED_PUT",
                "cash_secured": True,
                "naked_short": True,
                "required_cash": 1000,
                "quantity": 1,
            },
            {"equity": 100000, "cash": 100000},
            [],
        )
        self.assertFalse(ok)
        self.assertIn("Naked", reason)


if __name__ == "__main__":
    unittest.main()
