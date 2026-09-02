"""
HRAMY OMNI AI - Streamlit Entrypoint
============================================================
Premium dark financial-terminal dashboard for paper trading.

Pipeline (the AI can NEVER bypass risk management):
    Alpaca Market Data -> Indicators -> Quant Signals + Score
        -> Market Regime -> Groq AI Decision -> RISK MANAGER
        -> Execution Plan -> Paper Simulator

Cost control:
    - Historical data cached with TTL.
    - AI analysis cached by content hash + TTL — NEVER called per rerun.
"""

import hashlib
import json
import os
import sys
from datetime import datetime

import pandas as pd
import streamlit as st

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
AI_DIR = os.path.join(ROOT_DIR, "ai")
for path in (ROOT_DIR, AI_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from config import (
    AI_CACHE_TTL,
    APP_NAME,
    DATA_CACHE_TTL,
    DEFAULT_SYMBOL,
    LOOKBACK_DAYS,
    MAX_PORTFOLIO_EXPOSURE,
    MAX_POSITION_PERCENT,
    PAPER_MODE,
    RISK_PER_TRADE,
    STARTING_CASH,
)
from ai.groq_engine import is_configured as groq_is_configured
from analysis.indicators import calculate_indicators, latest_snapshot
from analysis.signals import compute_signal_scores, generate_market_signals
from analysis.regime import detect_regime
from agents.orchestrator import decide as ai_decide
from ai.chatbot import answer_question, parse_command
from backtest.engine import backtest as default_backtest, benchmark_buy_hold
from backtest.strategies import STRATEGY_REGISTRY
from backtest.walkforward import evaluate_walk_forward
from data.alpaca_data import get_historical_data
from portfolio.simulator import PaperPortfolio
from trading.option_chain import OptionChainResolver
from trading.risk import OptionRiskGate
from ui import dashboard as dash
from ui.charts import (
    drawdown_chart,
    equity_curve_chart,
    price_chart,
    regime_timeline_chart,
    rsi_gauge,
    trade_pnl_chart,
)

# ------------------------------------------------------------
# Cached loaders (cost control)
# ------------------------------------------------------------

@st.cache_data(ttl=DATA_CACHE_TTL, show_spinner=False)
def load_historical(symbol: str, days: int) -> pd.DataFrame:
    """Cached historical bars from Alpaca IEX."""
    return get_historical_data(symbol.upper(), days=days)


@st.cache_data(ttl=AI_CACHE_TTL, show_spinner=False)
def load_ai(symbol: str, market_json: str, account_json: str) -> str:
    """Cached Groq decision keyed on the full quantitative context."""
    market = json.loads(market_json)
    account = json.loads(account_json)
    return json.dumps(
        ai_decide(
            market,
            account,
            market.get("iv_rank"),
            use_llm=bool(os.getenv("GROQ_API_KEY")),
        )
    )


# ------------------------------------------------------------
# Page config + session state
# ------------------------------------------------------------

st.set_page_config(
    page_title=APP_NAME,
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

if "portfolio" not in st.session_state:
    st.session_state.portfolio = PaperPortfolio(starting_cash=STARTING_CASH)
if "decision_history" not in st.session_state:
    st.session_state.decision_history = []
if "active_section" not in st.session_state:
    st.session_state.active_section = "Overview"
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "show_landing" not in st.session_state:
    st.session_state.show_landing = True

# ------------------------------------------------------------
# Sidebar controls
# ------------------------------------------------------------

with st.sidebar:
    st.markdown("## ⚙️ QuantNova Navigator")
    st.session_state.active_section = st.radio(
        "Workspace section",
        ["Overview", "AI Decision", "Backtest Center", "Paper Execution", "Assistant"],
        index=["Overview", "AI Decision", "Backtest Center", "Paper Execution", "Assistant"].index(
            st.session_state.active_section
        ),
        label_visibility="collapsed",
    )
    st.divider()
    symbol = st.text_input("Symbol", value=DEFAULT_SYMBOL).upper().strip() or DEFAULT_SYMBOL
    lookback = st.slider("Lookback (trading days)", 160, 500, LOOKBACK_DAYS, step=20)

    if st.button("🔄 Refresh Analysis", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.caption("**Paper trading only** — no real funds are ever used.")
    st.caption(f"AI model: `{os.getenv('HRAMY_AI_MODEL', 'openai/gpt-oss-20b')}`")
    st.caption(f"Data TTL {DATA_CACHE_TTL}s · AI TTL {AI_CACHE_TTL}s")

# ------------------------------------------------------------
# Real Alpaca data pipeline
# ------------------------------------------------------------

data = None
error_message = None

try:
    with st.spinner("Loading market data…"):
        data = load_historical(symbol, lookback)
except Exception as exc:
    error_message = f"Real Alpaca data unavailable: {type(exc).__name__}"

if data is not None and len(data) < 90:
    error_message = "Alpaca returned fewer than 90 real bars; increase the lookback or check the symbol."

if error_message:
    st.error(f"❌ {error_message}")
    st.info("QuantNova will not substitute synthetic prices in the live dashboard. Configure Alpaca credentials or try another symbol.")
    st.stop()

try:
    with st.spinner("Computing indicators from Alpaca bars…"):
        data = calculate_indicators(data)
except Exception as exc:
    error_message = str(exc)

if error_message:
    st.error(f"❌ Pipeline error: {error_message}")
    st.info("Try a different symbol, increase lookback, or click Refresh Analysis.")
    st.stop()

# ------------------------------------------------------------
# Header (connection state is now truthful)
# ------------------------------------------------------------

dash.inject_css()
dash.render_header(
    connections={
        "alpaca": True,
        "groq": groq_is_configured(),
        "paper": PAPER_MODE,
    },
    extra_pills=[("REAL DATA · ALPACA IEX", "online")],
)

if st.session_state.show_landing:
    dash.render_landing({
        "alpaca": True,
        "groq": groq_is_configured(),
    })
    _, enter_col, _ = st.columns([1, 1.2, 1])
    with enter_col:
        if st.button("Open QuantNova Terminal", type="primary", use_container_width=True):
            st.session_state.show_landing = False
            st.rerun()
    st.stop()

snapshot = latest_snapshot(data)
prev_close = float(data["close"].iloc[-2]) if len(data) > 1 else snapshot["price"]

market = generate_market_signals(snapshot)
market.update(snapshot)
market["prev_close"] = prev_close

score_data = compute_signal_scores(snapshot)
score_data["close_change"] = snapshot["price"] - prev_close
market["score"] = score_data

regime_info = detect_regime({**snapshot, **market})
market["regime"] = regime_info.regime
market["trend_strength"] = regime_info.trend_strength
market["regime_description"] = regime_info.description

# ------------------------------------------------------------
# AI decision (Groq when available; deterministic local policy otherwise)
# ------------------------------------------------------------

portfolio_summary = st.session_state.portfolio.summary(snapshot["price"])
account_state = {
    "equity": portfolio_summary["total_value"],
    "cash": portfolio_summary["cash"],
    "shares": portfolio_summary["shares"],
    "position_value": portfolio_summary["position_value"],
    "exposure_percent": portfolio_summary["exposure_percent"],
}

use_llm = bool(os.getenv("GROQ_API_KEY"))
ai = ai_decide(market, account_state, market.get("iv_rank"), use_llm=use_llm)

# ------------------------------------------------------------
# Real backend risk gate + option plan
# ------------------------------------------------------------

resolver = OptionChainResolver(live=False)
plan = resolver.resolve_contract(
    symbol=symbol,
    stock_price=float(snapshot.get("price") or 0.0),
    target_delta=float(ai.get("target_delta") or 0.25),
    target_dte=int(ai.get("target_dte") or 21),
    side="put" if str(ai.get("strategy_type") or "").upper() in {"CASH_SECURED_PUT", "BEAR_PUT_SPREAD", "LONG_PUT"} else "call",
    quantity=int(ai.get("contracts") or 1),
    strategy=str(ai.get("strategy_type") or "NONE").upper(),
)

risk_gate = OptionRiskGate()
allowed, reason = risk_gate.evaluate(plan, account_state, positions=[])
risk_status = {
    "allowed": bool(allowed),
    "status": "PASSED" if allowed else "BLOCKED",
    "reason": reason,
}

final_decision = str(ai.get("action") or "HOLD").upper() if allowed else "HOLD"
if final_decision == "HOLD":
    ai["action"] = "HOLD"
    ai["strategy_type"] = "NONE"
    ai["contracts"] = 0

st.session_state.decision_history.append({
    "time": datetime.now().strftime("%H:%M:%S"),
    "decision": final_decision,
    "confidence": ai.get("confidence", 0),
    "strategy_type": ai.get("strategy_type", "NONE"),
})
st.session_state.decision_history = st.session_state.decision_history[-20:]

# ------------------------------------------------------------
# Navigator sections
# ------------------------------------------------------------

active_section = st.session_state.active_section

if active_section == "Overview":
    dash.render_market_terminal(market, regime_info)
    overview_chart, overview_signals = st.columns([1.8, 1], gap="large")
    with overview_chart:
        st.plotly_chart(price_chart(data, symbol), use_container_width=True)
    with overview_signals:
        dash.render_signal_matrix(market, score_data)
    overview_portfolio, overview_timeline = st.columns([1.25, 1], gap="large")
    with overview_portfolio:
        dash.render_portfolio_panel(portfolio_summary)
    with overview_timeline:
        dash.render_timeline(st.session_state.decision_history)
    st.stop()

if active_section == "AI Decision":
    st.markdown("## AI Decision")
    st.caption(f"{symbol} · model decision, reasoning, and deterministic risk gate")
    decision_col, risk_col = st.columns([1.1, 1], gap="large")
    with decision_col:
        dash.render_ai_decision(ai, plan, symbol)
        if ai.get("source") == "local_policy":
            st.caption("AI status: deterministic policy active · decision source: local policy")
        elif ai.get("source") == "fallback":
            st.caption("AI status: safe fallback active · decision source: schema fallback")
        elif use_llm:
            st.caption("AI status: Groq online · decision source: orchestrator refinement")
        else:
            st.caption("AI status: deterministic agent path · decision source: local policy")
    with risk_col:
        caps = {
            "max_exposure": MAX_PORTFOLIO_EXPOSURE * 100,
            "max_position": MAX_POSITION_PERCENT * 100,
            "risk_per_trade": RISK_PER_TRADE * 100,
        }
        dash.render_risk_panel(risk_status, plan, account_state, caps)
    dash.render_reasoning(ai)
    dash.render_signal_matrix(market, score_data)
    dash.render_timeline(st.session_state.decision_history)
    st.stop()

if st.session_state.active_section == "Paper Execution":
    st.markdown("## Paper Execution")
    st.caption("All activity here is simulated. The risk manager must approve every trade.")
    execute_clicked = st.button(
        "⚡ Execute AI Decision (Simulated)",
        type="primary",
        use_container_width=True,
    )
    if execute_clicked:
        if final_decision == "HOLD":
            st.warning("AI decision is HOLD — nothing executed.")
        elif not allowed:
            st.error(f"Risk Manager blocked execution: {reason}")
        else:
            qty = plan.get("quantity", 0) if plan.get("quantity", 0) > 0 else None
            stop_price = plan.get("stop_price") if final_decision == "BUY" else None
            target_price = plan.get("target_price") if final_decision == "BUY" else None
            st.session_state.last_exec_msg = st.session_state.portfolio.execute(
                symbol,
                final_decision,
                snapshot["price"],
                confidence=ai.get("confidence", 0.5),
                quantity=qty,
                stop_price=stop_price,
                target_price=target_price,
                ai_meta={"reason": (ai.get("reason") or "")[:120]},
            )
            st.rerun()
    if st.session_state.get("last_exec_msg"):
        st.success(st.session_state["last_exec_msg"])
    dash.render_trade_history(st.session_state.portfolio.trades)
    st.stop()

if st.session_state.active_section == "Assistant":
    st.markdown("## QuantNova In-App Assistant")
    st.caption("Ask questions or request safe paper actions such as: simulate this decision, refresh analysis, or reset my paper account.")
    for message in st.session_state.chat_history[-12:]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    question = st.chat_input("Ask QuantNova or request a paper action...", key="navigator_assistant_input")
    if question:
        st.session_state.chat_history.append({"role": "user", "content": question})
        command = parse_command(question)
        if command == "REFRESH_ANALYSIS":
            st.cache_data.clear()
            st.session_state.chat_history.append({"role": "assistant", "content": "Refreshing market data and analysis now."})
            st.rerun()
        elif command == "RESET_PAPER":
            st.session_state.portfolio = PaperPortfolio(starting_cash=STARTING_CASH)
            answer = "Paper portfolio reset. No real orders were placed."
        elif command == "EXECUTE_DECISION" and final_decision == "HOLD":
            answer = "The current risk-gated decision is HOLD, so nothing was simulated."
        elif command == "EXECUTE_DECISION" and not allowed:
            answer = f"Simulation blocked by the risk manager: {reason}"
        elif command == "EXECUTE_DECISION":
            qty = plan.get("quantity", 0) if plan.get("quantity", 0) > 0 else None
            stop_price = plan.get("stop_price") if final_decision == "BUY" else None
            target_price = plan.get("target_price") if final_decision == "BUY" else None
            answer = st.session_state.portfolio.execute(
                symbol, final_decision, snapshot["price"],
                confidence=ai.get("confidence", 0.5), quantity=qty,
                stop_price=stop_price,
                target_price=target_price,
                ai_meta={"reason": (ai.get("reason") or "")[:120]},
            )
        else:
            answer = answer_question(question, {
                "symbol": symbol, "decision": final_decision,
                "ai_source": ai.get("source"), "confidence": ai.get("confidence"),
                "regime": market.get("regime"), "composite_score": score_data.get("composite"),
                "paper_mode": PAPER_MODE,
            })["answer"]
        st.session_state.chat_history.append({"role": "assistant", "content": answer})
        st.rerun()
    st.stop()

# ------------------------------------------------------------
# BACKTEST CENTER — IS / VAL / OOS clearly separated
# ------------------------------------------------------------

if st.session_state.active_section != "Backtest Center":
    st.stop()

st.markdown("---")
st.markdown("## 🔬 BACKTEST CENTER")
st.caption(
    "Chronological walk-forward split — parameters selected on TRAIN only, "
    "confirmed on VALIDATION, reported untouched on OUT-OF-SAMPLE. "
    "The out-of-sample result is the one that matters."
)

try:
    with st.spinner("Running walk-forward analysis…"):
        wf = evaluate_walk_forward(data)
except Exception as exc:
    wf = None
    st.error(
        f"Walk-forward analysis failed: {type(exc).__name__}. "
        "The live dashboard remains available; try Refresh Analysis."
    )

tab_is, tab_val, tab_oos = st.tabs([
    "🟢 OUT-OF-SAMPLE (TEST)",
    "🔵 VALIDATION",
    "⚪ IN-SAMPLE (TRAIN)",
])

if wf:
    labels = wf.get("split_labels", {})

    with tab_oos:
        st.caption(f"Period: **{labels.get('test', 'N/A')}** · "
                   f"{wf['split_sizes']['test']} bars")
        e = wf["strategies"].get("E", {}).get("test")
        if e and not e.get("insufficient_data") and not e.get("error"):
            bench_ret = wf["benchmarks"]["test"].get("return_percent")
            alpha = (
                round((e.get("return_percent") or 0) - (bench_ret or 0), 2)
                if e.get("return_percent") is not None else None
            )
            dash.render_backtest_metrics(
                {**e, "alpha_percent": alpha},
                label="OUT-OF-SAMPLE",
            )
            st.plotly_chart(equity_curve_chart(
                e.get("equity_curve"),
                wf["benchmarks"]["test"].get("equity_curve"),
                title="OOS Equity · AI+Risk Manager vs Buy & Hold",
            ), use_container_width=True)
        else:
            st.info("Not enough out-of-sample bars — increase the lookback slider.")

    with tab_val:
        st.caption(f"Period: **{labels.get('validation', 'N/A')}** · "
                   f"{wf['split_sizes']['validation']} bars")
        c_val = wf["strategies"].get("C", {}).get("validation")
        if c_val and not c_val.get("insufficient_data") and not c_val.get("error"):
            dash.render_backtest_metrics(c_val, label="VALIDATION")
            st.plotly_chart(equity_curve_chart(
                c_val.get("equity_curve"),
                wf["benchmarks"]["validation"].get("equity_curve"),
                title="Validation Equity vs Buy & Hold",
            ), use_container_width=True)

    with tab_is:
        st.caption(f"Period: **{labels.get('train', 'N/A')}** · "
                   f"{wf['split_sizes']['train']} bars")
        c_train = wf["strategies"].get("C", {}).get("train")
        if c_train and not c_train.get("insufficient_data") and not c_train.get("error"):
            dash.render_backtest_metrics(c_train, label="IN-SAMPLE")
            st.plotly_chart(equity_curve_chart(
                c_train.get("equity_curve"),
                wf["benchmarks"]["train"].get("equity_curve"),
                title="In-Sample Equity vs Buy & Hold",
            ), use_container_width=True)

    # ---- Parameter selection transparency ----
    sel = wf.get("parameter_selection", {})
    opt_test = wf.get("optimized_strategy_a_test")
    with st.expander("🧪 Walk-forward parameter selection (Strategy A) — full transparency"):
        st.write(f"Selected params on TRAIN: **{sel.get('selected_params')}**")
        st.write(f"Confirmed on VALIDATION: Sharpe={sel.get('validation_sharpe')}, "
                 f"Return={sel.get('validation_return_percent')}%")
        if sel.get("trials"):
            st.dataframe(pd.DataFrame(sel["trials"]), hide_index=True)
        if opt_test:
            st.markdown("**Untouched OUT-OF-SAMPLE result with selected params:**")
            st.write({
                "return_percent": opt_test.get("return_percent"),
                "win_rate": opt_test.get("win_rate"),
                "trades": opt_test.get("trades"),
                "sharpe": opt_test.get("sharpe"),
                "max_drawdown_percent": opt_test.get("max_drawdown_percent"),
            })

    # ------------------------------------------------------------
    # STRATEGY ARENA — all 5 strategies on the OOS segment
    # ------------------------------------------------------------
    oos_rows = []
    bench_ret = wf["benchmarks"]["test"].get("return_percent")
    for key in ("A", "B", "C", "D", "E"):
        entry = wf["strategies"].get(key, {}).get("test", {})
        if not entry or entry.get("insufficient_data") or entry.get("error"):
            continue
        ret = entry.get("return_percent")
        oos_rows.append({
            "Strategy": wf["strategies"][key]["name"],
            "Description": entry.get("strategy_description", ""),
            "Return %": ret,
            "Win Rate %": entry.get("win_rate"),
            "Profit Factor": entry.get("profit_factor"),
            "Max DD %": entry.get("max_drawdown_percent"),
            "Sharpe": entry.get("sharpe"),
            "Trades": entry.get("trades"),
            "Alpha %": (
                round(ret - bench_ret, 2)
                if ret is not None and bench_ret is not None else None
            ),
        })
    oos_rows.append({
        "Strategy": "B&H",
        "Description": "Buy & Hold benchmark (same period)",
        "Return %": bench_ret,
        "Win Rate %": None,
        "Profit Factor": None,
        "Max DD %": wf["benchmarks"]["test"].get("max_drawdown_percent"),
        "Sharpe": wf["benchmarks"]["test"].get("sharpe"),
        "Trades": 1,
        "Alpha %": 0.0,
    })
    dash.render_strategy_comparison(oos_rows)

    # Full-period reference run (flagship strategy, all data, default params)
    st.markdown("##### 📊 Full-period reference (all data · default params)")
    ref_bt = default_backtest(data)
    ref_bench = benchmark_buy_hold(data)
    ref_bt["alpha_percent"] = (
        round((ref_bt.get("return_percent") or 0)
              - (ref_bench.get("return_percent") or 0), 2)
        if ref_bt.get("return_percent") is not None else None
    )
    dash.render_backtest_metrics(ref_bt)

    col_eq, col_dd = st.columns([1.6, 1], gap="medium")
    with col_eq:
        st.plotly_chart(equity_curve_chart(
            ref_bt.get("equity_curve"), ref_bench.get("equity_curve"),
        ), use_container_width=True)
    with col_dd:
        st.plotly_chart(drawdown_chart(ref_bt.get("equity_curve")), use_container_width=True)

    col_pnl, col_regime = st.columns([1.2, 1.4], gap="medium")
    with col_pnl:
        st.plotly_chart(trade_pnl_chart(ref_bt.get("trade_list")), use_container_width=True)
    with col_regime:
        st.plotly_chart(regime_timeline_chart(data), use_container_width=True)

    if ref_bt.get("trade_list"):
        dash.render_trade_history(ref_bt["trade_list"])
else:
    st.info("Backtests require more history — raise the lookback slider.")

if st.session_state.active_section == "Backtest Center":
    st.stop()

# ------------------------------------------------------------
# Paper execution handler
# ------------------------------------------------------------

st.markdown("---")
exec_col, msg_col = st.columns([1, 3])
with exec_col:
    execute_clicked = st.button(
        "⚡ Execute AI Decision (Simulated)",
        type="primary",
        use_container_width=True,
    )
if execute_clicked:
    if final_decision == "HOLD":
        st.warning("AI decision is HOLD — nothing executed.")
    elif not allowed:
        st.error(f"Risk Manager blocked execution: {reason}")
    else:
        qty = plan.get("quantity", 0) if plan.get("quantity", 0) > 0 else None
        msg = st.session_state.portfolio.execute(
            symbol,
            final_decision,
            snapshot["price"],
            confidence=ai.get("confidence", 0.5),
            quantity=qty,
            stop_price=plan.get("stop_price") if final_decision == "BUY" else None,
            target_price=plan.get("target_price") if final_decision == "BUY" else None,
            ai_meta={
                "risk": ai.get("risk", ""),
                "regime": ai.get("market_regime", ""),
                "reason": (ai.get("reason") or "")[:120],
            },
        )
        st.session_state.last_exec_msg = msg
        st.rerun()

if st.session_state.get("last_exec_msg"):
    st.success(st.session_state["last_exec_msg"])

# ------------------------------------------------------------
# Project / hackathon assistant
# ------------------------------------------------------------

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

with st.expander(
    "💬 QuantNova In-App Assistant",
    expanded=st.session_state.active_section == "Assistant",
):
    st.caption(
        "Ask about the live decision, signals, risk, backtests, paper execution, "
        "or demo preparation. Official event details must be checked at the "
        "Alpaca hackathon page."
    )
    for message in st.session_state.chat_history[-8:]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    question = st.chat_input(
        "Ask about the project, strategy, risk, or hackathon...",
        key="project_assistant_input",
    )
    if question:
        context = {
            "symbol": symbol,
            "decision": final_decision,
            "ai_source": ai.get("source", "local_policy"),
            "confidence": ai.get("confidence", 0),
            "regime": market.get("regime"),
            "composite_score": score_data.get("composite"),
            "paper_mode": PAPER_MODE,
        }
        st.session_state.chat_history.append({"role": "user", "content": question})
        command = parse_command(question)
        if command == "REFRESH_ANALYSIS":
            st.cache_data.clear()
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": "Refreshing market data and analysis now.",
            })
            st.rerun()
        elif command == "RESET_PAPER":
            st.session_state.portfolio = PaperPortfolio(starting_cash=STARTING_CASH)
            st.session_state.last_exec_msg = "Paper portfolio reset. No real orders were placed."
            result = {"answer": st.session_state.last_exec_msg, "source": "local"}
        elif command == "EXECUTE_DECISION":
            if final_decision == "HOLD":
                result = {"answer": "The current risk-gated decision is HOLD, so nothing was simulated.", "source": "local"}
            elif not allowed:
                result = {"answer": f"Simulation blocked by the risk manager: {reason}", "source": "local"}
            else:
                qty = plan.get("quantity", 0) if plan.get("quantity", 0) > 0 else None
                result = {
                    "answer": st.session_state.portfolio.execute(
                        symbol,
                        final_decision,
                        snapshot["price"],
                        confidence=ai.get("confidence", 0.5),
                        quantity=qty,
                        stop_price=plan.get("stop_price") if final_decision == "BUY" else None,
                        target_price=plan.get("target_price") if final_decision == "BUY" else None,
                        ai_meta={"reason": (ai.get("reason") or "")[:120]},
                    ),
                    "source": "paper simulator",
                }
        else:
            result = answer_question(question, context)
        st.session_state.chat_history.append({"role": "assistant", "content": result["answer"]})
        st.rerun()

# ------------------------------------------------------------
# Footer
# ------------------------------------------------------------

st.caption(
    f"{APP_NAME} — Paper Simulation Only. No real orders are ever placed. "
    "Alpaca IEX market data · Groq AI decisions · deterministic risk manager. "
    "Backtest performance does not guarantee future results."
)