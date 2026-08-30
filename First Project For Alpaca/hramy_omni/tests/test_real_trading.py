import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading.options import build_option_trade_plan
from trading.real_execution import normalize_account_snapshot
from trading.agent_loop import AutonomousAgentLoop


class TestRealTradingRequirements(unittest.TestCase):
    def test_option_trade_plan_uses_near_the_money_contract(self):
        plan = build_option_trade_plan("AAPL", 220.0, "CALL", days_to_expiry=14)
        self.assertIn(plan["side"], {"buy", "sell"})
        self.assertEqual(plan["symbol"], "AAPL")
        self.assertGreater(plan["contract_qty"], 0)
        self.assertIn(plan["option_type"], {"call", "put"})
        self.assertGreater(plan["strike"], 0.0)

    def test_account_snapshot_normalizes_equity_and_pnl(self):
        snapshot = normalize_account_snapshot({
            "account_id": "acc_123",
            "cash": 20000.0,
            "buying_power": 120000.0,
            "equity": 100000.0,
            "portfolio_value": 100000.0,
            "status": "ACTIVE",
            "pl": 500.0,
        })
        self.assertEqual(snapshot["account_id"], "acc_123")
        self.assertEqual(snapshot["cash"], 20000.0)
        self.assertEqual(snapshot["equity"], 100000.0)
        self.assertEqual(snapshot["pnl"], 500.0)

    def test_autonomous_loop_makes_safe_hold_when_no_signal(self):
        loop = AutonomousAgentLoop()
        result = loop.run_once({
            "symbol": "AAPL",
            "price": 220.0,
            "signal": "neutral",
            "confidence": 0.25,
            "cash": 100000.0,
            "shares": 0,
            "equity": 100000.0,
        })
        self.assertEqual(result["decision"], "HOLD")
        self.assertIn("autonomous", result["reason"].lower())


if __name__ == "__main__":
    unittest.main()
