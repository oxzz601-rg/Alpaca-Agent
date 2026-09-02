"""
Single public AI entrypoint.

    from agents.orchestrator import decide
    decision = decide(market_context, account_state, iv_rank)

ANALYZE → DECIDE. Never raises. Always returns a schema-valid TradeDecision.
Does not call the broker, fetch option chains, or submit orders.
"""

from agents.attribution import relevant_lessons
from agents.context import DEFAULT_ACCOUNT, with_mock_iv_rank
from agents.devils_advocate import review as review_decision
from agents.llm import refine_strategy
from agents.market_analyst import analyze
from agents.opportunity_scanner import scan
from agents.options_strategist import select_strategy
from agents.schema import AI_TRACE_STAGES, FAIL_UNKNOWN, safe_fallback, validate_trade_decision


def _as_universe(market_context) -> list:
    if market_context is None:
        return []
    if isinstance(market_context, list):
        return [item for item in market_context if isinstance(item, dict)]
    if isinstance(market_context, dict):
        nested = market_context.get("universe")
        if isinstance(nested, list):
            return [item for item in nested if isinstance(item, dict)]
        if not market_context.get("symbol") and not market_context.get("regime"):
            return []
        return [market_context]
    return []


def _pick_market(ranked: list, fallback: dict) -> dict:
    for row in ranked:
        if row.get("tradeable") and isinstance(row.get("market"), dict):
            return row["market"]
    if ranked and isinstance(ranked[0].get("market"), dict):
        return ranked[0]["market"]
    return fallback


def decide(market_context, account_state=None, iv_rank=None, use_llm: bool = False) -> dict:
    """
    Run Market Analyst → Opportunity Scanner → Options Strategist → Devil's Advocate.

    market_context: one market dict, or a list of market dicts (universe).
    account_state: equity/cash/positions dict.
    iv_rank: optional override applied to the selected symbol.
    """
    try:
        account = dict(account_state or DEFAULT_ACCOUNT)
        universe = _as_universe(market_context)
        if not universe:
            return safe_fallback(
                "No market context was provided.",
                FAIL_UNKNOWN,
                symbol="",
            )

        primary = with_mock_iv_rank(dict(universe[0]))
        if iv_rank is not None:
            try:
                primary["iv_rank"] = float(iv_rank)
            except (TypeError, ValueError):
                pass

        analyst = analyze(primary)
        ranked = scan(universe, account)
        selected = with_mock_iv_rank(dict(_pick_market(ranked, primary)))
        if iv_rank is not None:
            try:
                selected["iv_rank"] = float(iv_rank)
            except (TypeError, ValueError):
                pass

        lessons = relevant_lessons(str(selected.get("symbol", "")), n=5)
        decision = select_strategy(selected, account, selected.get("iv_rank"))
        if use_llm:
            decision = refine_strategy(decision, selected, account, lessons)
        da = review_decision(decision, selected)

        extra_factors = list(decision.get("key_factors") or [])
        extra_factors.insert(0, f"Analyst {analyst['sentiment']} ({analyst['confidence']:.2f})")
        if ranked:
            top = ranked[0]
            extra_factors.append(
                f"Scanner top {top['symbol']} score {top['score']} tradeable={top['tradeable']}"
            )
        if lessons:
            extra_factors.append(f"Lesson: {lessons[0]}")

        decision["devils_advocate"] = da
        decision["key_factors"] = extra_factors[:6]
        decision["agent_trace"] = list(AI_TRACE_STAGES)

        validated = validate_trade_decision(
            decision,
            symbol=str(selected.get("symbol", "")),
            source=decision.get("source") or "local_policy",
        )
        validated["agent_trace"] = list(AI_TRACE_STAGES)
        return validated
    except Exception as exc:
        symbol = ""
        if isinstance(market_context, dict):
            symbol = str(market_context.get("symbol", ""))
        return safe_fallback(
            f"Orchestrator failed closed: {type(exc).__name__}.",
            FAIL_UNKNOWN,
            symbol=symbol,
        )
