"""Command-line interface for the Alpaca trading hackathon flow."""

from __future__ import annotations

import argparse
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AI = os.path.join(_ROOT, "ai")
for _path in (_ROOT, _AI):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from agents.context import DEFAULT_ACCOUNT
from config import ALPACA_PAPER_ACCOUNT_ID, STARTING_CASH
from data.alpaca_data import get_historical_data
from trading.agent_loop import AutonomousAgentLoop
from trading.execution_loop import ExecutionLoop
from trading.market_context import build_market_context
from trading.option_chain import OptionChainResolver
from trading.options import build_option_trade_plan
from trading.real_execution import AlpacaBroker, get_account_snapshot


def _status() -> dict:
    try:
        broker = AlpacaBroker()
        snapshot = broker.account_snapshot()
        snapshot["options_level"] = broker.options_level()
        snapshot["options_eligible"] = broker.options_eligible()
        clock = broker.get_clock()
        return {"status": "ok", "account": snapshot, "clock": clock}
    except Exception as exc:
        return {
            "status": "not_configured",
            "account_id": ALPACA_PAPER_ACCOUNT_ID,
            "starting_cash": STARTING_CASH,
            "error": type(exc).__name__,
        }


def _market(symbol: str, days: int) -> dict:
    df = get_historical_data(symbol=symbol, days=days)
    return {
        "symbol": symbol.upper(),
        "rows": int(len(df)),
        "latest_close": float(df["close"].iloc[-1]),
        "start": df.index[0].isoformat() if len(df) else None,
        "end": df.index[-1].isoformat() if len(df) else None,
    }


def _option(symbol: str, side: str, option_type: str, price: float, days: int) -> dict:
    return build_option_trade_plan(symbol, price, option_type, days_to_expiry=days, side=side)


def _autonomous(symbol: str, signal: str, confidence: float, cash: float, shares: float, equity: float) -> dict:
    loop = AutonomousAgentLoop()
    return loop.run_once({
        "symbol": symbol,
        "signal": signal,
        "confidence": confidence,
        "cash": cash,
        "shares": shares,
        "equity": equity,
    })


def _cycle(symbol: str, submit: bool, use_llm: bool, live: bool) -> dict:
    market = build_market_context(symbol, live=live)
    broker = AlpacaBroker() if (submit or live) else None
    account = dict(DEFAULT_ACCOUNT)
    positions: list = []
    if live and broker is not None and broker.client is not None:
        try:
            account = broker.account_snapshot()
            positions = broker.get_positions()
        except Exception:
            pass
    loop = ExecutionLoop(broker=broker, submit=submit, use_llm=use_llm, live=live)
    if live:
        loop.mcp.run_cli(["--help"])
    result = loop.run_cycle(symbol, market, account, positions=positions)
    result["data_source"] = market.get("data_source")
    result["iv_rank"] = market.get("iv_rank")
    result["mcp_log"] = loop.mcp.export()
    return result


def _chain(symbol: str, price: float, dte: int, delta: float, live: bool) -> dict:
    resolver = OptionChainResolver(live=live)
    return resolver.resolve_contract(symbol, price, target_delta=delta, target_dte=dte, side="put")


def main() -> None:
    parser = argparse.ArgumentParser(description="Alpaca trading CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="fetch the paper account snapshot")

    market = sub.add_parser("market", help="fetch market data for a symbol")
    market.add_argument("symbol", nargs="?", default="AAPL")
    market.add_argument("--days", type=int, default=90)

    option = sub.add_parser("option", help="build an option trade plan")
    option.add_argument("symbol", nargs="?", default="AAPL")
    option.add_argument("--price", type=float, default=220.0)
    option.add_argument("--type", dest="option_type", default="call")
    option.add_argument("--side", default="buy")
    option.add_argument("--days", type=int, default=14)

    auto = sub.add_parser("autonomous", help="run one autonomous loop cycle")
    auto.add_argument("symbol", nargs="?", default="AAPL")
    auto.add_argument("--signal", default="neutral")
    auto.add_argument("--confidence", type=float, default=0.65)
    auto.add_argument("--cash", type=float, default=STARTING_CASH)
    auto.add_argument("--shares", type=float, default=0.0)
    auto.add_argument("--equity", type=float, default=STARTING_CASH)

    cycle = sub.add_parser("cycle", help="AI decide() → risk → option plan (dry-run by default)")
    cycle.add_argument("symbol", nargs="?", default="AAPL")
    cycle.add_argument("--submit", action="store_true", help="actually send a paper order (off by default)")
    cycle.add_argument("--llm", action="store_true", help="optional Groq refine")
    cycle.add_argument("--live", action="store_true", help="use Alpaca bars + live option chain")

    chain = sub.add_parser("chain", help="resolve a CSP contract (synthetic unless --live)")
    chain.add_argument("symbol", nargs="?", default="AAPL")
    chain.add_argument("--price", type=float, default=220.0)
    chain.add_argument("--dte", type=int, default=21)
    chain.add_argument("--delta", type=float, default=0.25)
    chain.add_argument("--live", action="store_true")

    args = parser.parse_args()

    if args.command == "status":
        print(json.dumps(_status(), indent=2, default=str))
    elif args.command == "market":
        print(json.dumps(_market(args.symbol, args.days), indent=2))
    elif args.command == "option":
        print(json.dumps(_option(args.symbol, args.side, args.option_type, args.price, args.days), indent=2))
    elif args.command == "autonomous":
        print(json.dumps(_autonomous(args.symbol, args.signal, args.confidence, args.cash, args.shares, args.equity), indent=2))
    elif args.command == "cycle":
        print(json.dumps(_cycle(args.symbol, args.submit, args.llm, args.live), indent=2, default=str))
    elif args.command == "chain":
        print(json.dumps(_chain(args.symbol, args.price, args.dte, args.delta, args.live), indent=2, default=str))


if __name__ == "__main__":
    main()
