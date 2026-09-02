"""Run full unit test suite and log results to smoke_out.txt."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

OUT = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "smoke_out.txt"), "w", encoding="utf-8")

def log(msg):
    OUT.write(str(msg) + "\n")
    OUT.flush()

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai"))

from tests.test_analysis import TestIndicators, TestSignals, TestRegime
from tests.test_ai_risk_portfolio import TestAIValidation, TestRiskManager, TestPaperPortfolio, TestSecurityAudit
from tests.test_backtest import TestExecutionModel, TestTradeAccounting, TestStrategiesProducePlans, TestWalkForward
from tests.test_execution_ai import ExecutionAiTests, IvRankTests, OccSymbolTests
from agents.tests.test_agents import (
    AttributionTests,
    DevilsAdvocateTests,
    FixtureTests,
    IvBucketTests,
    MatrixTests,
    OrchestratorTests,
    SchemaTests,
)

test_classes = [
    TestIndicators, TestSignals, TestRegime,
    TestAIValidation, TestRiskManager, TestPaperPortfolio, TestSecurityAudit,
    TestExecutionModel, TestTradeAccounting, TestStrategiesProducePlans, TestWalkForward,
    IvBucketTests, MatrixTests, FixtureTests, SchemaTests,
    DevilsAdvocateTests, OrchestratorTests, AttributionTests,
    OccSymbolTests, IvRankTests, ExecutionAiTests,
]

total_ran = 0
total_failed = 0
total_errors = 0

for cls in test_classes:
    log(f"\n--- Running {cls.__name__} ---")
    suite = unittest.TestLoader().loadTestsFromTestCase(cls)
    runner = unittest.TextTestRunner(stream=OUT, verbosity=2)
    res = runner.run(suite)
    total_ran += res.testsRun
    total_failed += len(res.failures)
    total_errors += len(res.errors)
    log(f"{cls.__name__}: {res.testsRun} run, {len(res.failures)} failed, {len(res.errors)} errors")

log(f"\n==========================================")
log(f"GRAND TOTAL TESTS: {total_ran}")
log(f"GRAND TOTAL FAILURES: {total_failed}")
log(f"GRAND TOTAL ERRORS: {total_errors}")
log(f"ALL TESTS PASSED: {total_failed == 0 and total_errors == 0}")
log(f"==========================================")

# Generate and log full Strategy Arena performance benchmark
from tests.data_builder import build_indicator_data
from backtest.walkforward import evaluate_walk_forward
from backtest.engine import run_backtest, benchmark_buy_hold
from backtest.strategies import STRATEGY_REGISTRY

bench_data = build_indicator_data(400, seed=101, trend="mixed")
wf_result = evaluate_walk_forward(bench_data)

log(f"\n=== STRATEGY ARENA: OUT-OF-SAMPLE PERFORMANCE (TEST SEGMENT: {wf_result['split_labels']['test']}) ===")
log(f"{'Strategy':<25} | {'Return %':<10} | {'Win Rate':<10} | {'Profit Factor':<15} | {'Sharpe':<8} | {'Max DD %':<10} | {'Trades':<8} | {'Alpha %':<10}")
log("-" * 110)

bench_ret = wf_result["benchmarks"]["test"].get("return_percent") or 0.0
for k, (name, _) in STRATEGY_REGISTRY.items():
    seg = wf_result["strategies"][k]["test"]
    ret = seg.get("return_percent")
    wr = f"{seg.get('win_rate')}%" if seg.get("win_rate") is not None else "N/A"
    pf = str(seg.get("profit_factor")) if seg.get("profit_factor") is not None else "N/A"
    sh = str(seg.get("sharpe")) if seg.get("sharpe") is not None else "N/A"
    dd = f"{seg.get('max_drawdown_percent')}%" if seg.get("max_drawdown_percent") is not None else "N/A"
    tr = str(seg.get("trades", 0))
    alp = f"{ret - bench_ret:+.2f}%" if ret is not None else "N/A"
    ret_str = f"{ret:+.2f}%" if ret is not None else "N/A"
    log(f"{name:<25} | {ret_str:<10} | {wr:<10} | {pf:<15} | {sh:<8} | {dd:<10} | {tr:<8} | {alp:<10}")

b_sh = str(wf_result["benchmarks"]["test"].get("sharpe")) if wf_result["benchmarks"]["test"].get("sharpe") is not None else "N/A"
b_dd = f"{wf_result['benchmarks']['test'].get('max_drawdown_percent')}%"
log(f"{'Buy & Hold Benchmark':<25} | {bench_ret:+.2f}%     | {'N/A':<10} | {'N/A':<15} | {b_sh:<8} | {b_dd:<10} | {'1':<8} | {'0.00%':<10}")
log("=" * 110)

OUT.close()


# Generate sanitized .env.example
env_example_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env.example")
with open(env_example_path, "w", encoding="utf-8") as env_f:
    env_f.write("""# ============================================================
# HRAMY OMNI AI - Environment Configuration Template
# ============================================================
# Copy this file to .env and configure your credentials.
# NEVER commit your .env file to version control.
# ============================================================

# 1. Market Data (Alpaca IEX Data Feed)
ALPACA_API_KEY=your_alpaca_api_key_here
ALPACA_SECRET_KEY=your_alpaca_secret_key_here
ALPACA_PAPER_API_KEY=your_paper_api_key_here
ALPACA_PAPER_SECRET_KEY=your_paper_secret_key_here
ALPACA_PAPER_ACCOUNT_ID=your_paper_account_id_here

# 2. AI Decision Engine (Groq Cloud API)
GROQ_API_KEY=your_groq_api_key_here
HRAMY_AI_MODEL=openai/gpt-oss-20b
HRAMY_AI_CONFIDENCE_THRESHOLD=0.60

# 3. Risk Management & Portfolio Constraints
HRAMY_MAX_POSITION_PERCENT=0.20
HRAMY_RISK_PER_TRADE=0.01
HRAMY_MAX_PORTFOLIO_EXPOSURE=0.95
HRAMY_MAX_DAILY_LOSS=0.05

# 4. Realistic Execution Cost Model
HRAMY_COMMISSION_RATE=0.0005
HRAMY_SLIPPAGE_PCT=0.0005
HRAMY_SPREAD_PCT=0.0002
""")