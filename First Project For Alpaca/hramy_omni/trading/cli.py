"""Command-line interface for the Alpaca trading hackathon flow."""

from __future__ import annotations

import argparse
import json

from config import ALPACA_PAPER_ACCOUNT_ID, STARTING_CASH
from data.alpaca_data import get_historical_data
from trading.agent_loop import AutonomousAgentLoop
from trading.options import build_option_trade_plan
from trading.real_execution import get_account_snapshot, normalize_account_snapshot


def _status() -> dict:
    try:
        snapshot = get_account_snapshot()
        return {"status": "ok", "account": snapshot}
    except Exception as exc:
        return {
            "status": "not_configured",
            "account_id": ALPACA_PAPER_ACCOUNT_ID,
            "starting_cash": STARTING_CASH,
            "error": str(exc),
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

    args = parser.parse_args()

    if args.command == "status":
        print(json.dumps(_status(), indent=2))
    elif args.command == "market":
        print(json.dumps(_market(args.symbol, args.days), indent=2))
    elif args.command == "option":
        print(json.dumps(_option(args.symbol, args.side, args.option_type, args.price, args.days), indent=2))
    elif args.command == "autonomous":
        print(json.dumps(_autonomous(args.symbol, args.signal, args.confidence, args.cash, args.shares, args.equity), indent=2))


if __name__ == "__main__":
    main()
