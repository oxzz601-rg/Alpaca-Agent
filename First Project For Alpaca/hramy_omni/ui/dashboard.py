"""
HRAMY OMNI AI - Streamlit Dashboard
============================================================
Premium dark financial-terminal GUI.

Panels:
    header / connection pills
    market terminal KPI strip
    hero AI decision card (decision, confidence, plan, R:R)
    AI reasoning panel (why / key factors / invalidations)
    signal matrix + composite score
    risk management panel
    portfolio panel
    backtest center (metrics grid, IS/OOS labels)
    strategy comparison table
    trade history
    AI decision timeline
"""

from __future__ import annotations

import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from config import APP_NAME, PAPER_MODE, TAGLINE

# ============================================================
# CUSTOM CSS — QuantNova terminal identity
# ============================================================

CUSTOM_CSS = """
<style>

*, *::before, *::after { box-sizing: border-box; }

.stApp { background: #0d1117; }

[data-testid="stHeader"] { background: transparent; z-index: 20; }
[data-testid="stAppViewContainer"] { padding-top: 1.25rem; }

[data-testid="stAppViewContainer"],
[data-testid="stMain"],
[data-testid="stMainBlockContainer"] {
    max-width: 100%;
    overflow-x: hidden;
}

.block-container {
    max-width: 1560px;
    padding-top: 1.6rem;
    padding-bottom: 3rem;
}

h1, h2, h3, h4 {
    color: #e6edf3 !important;
    font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
}

#MainMenu { visibility: hidden; }
footer { visibility: hidden; }

/* ---------------- CONTAINED SURFACES ---------------- */

.panel, .ai-hero {
    width: 100%; min-width: 0; overflow: hidden;
    background: linear-gradient(180deg, #161b22, #12171f);
    border: 1px solid #30363d; border-radius: 12px;
    padding: 16px; margin-bottom: 14px;
}
.panel-title {
    color: #e6edf3; font-size: 0.75rem; font-weight: 800;
    letter-spacing: 0.08em; text-transform: uppercase;
    padding-bottom: 10px; margin-bottom: 8px;
    border-bottom: 1px solid #21262d;
}
.note { color: #8b949e; font-size: 0.75rem; line-height: 1.45; }
.ai-hero { text-align: center; border-color: #388bfd66; }
.ai-decision-label { color: #8b949e; font-size: 0.7rem; letter-spacing: 0.08em; }
.ai-decision-value { font-size: 3rem; font-weight: 900; line-height: 1.1; margin: 8px 0; }
.ai-decision-value.buy { color: #3fb950; }
.ai-decision-value.sell { color: #f85149; }
.ai-decision-value.hold { color: #d29922; }
.ai-sub-row { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; color: #8b949e; font-size: 0.72rem; }
.ai-sub-row b { color: #e6edf3; }
.conf-bar-track { height: 6px; background: #0d1117; border-radius: 3px; margin: 14px 0; overflow: hidden; }
.conf-bar-fill { height: 100%; background: linear-gradient(90deg, #d29922, #3fb950); border-radius: inherit; }
.plan-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 6px; margin-top: 12px; }
.plan-cell { min-width: 0; padding: 7px 4px; background: #0d1117; border: 1px solid #21262d; border-radius: 7px; }
.p-label { color: #8b949e; font-size: 0.62rem; text-transform: uppercase; }
.p-value { color: #e6edf3; font-size: 0.78rem; font-weight: 700; overflow-wrap: anywhere; word-break: break-word; }
.source-tag { display: inline-block; margin-top: 12px; padding: 3px 8px; border-radius: 999px; font-size: 0.65rem; }
.source-tag.groq { color: #bc8cff; border: 1px solid rgba(188,140,255,0.45); }
.source-tag.local { color: #d29922; border: 1px solid rgba(210,153,34,0.45); }

/* ---------------- HERO HEADER ---------------- */

.hero {
    width: 100% !important; max-width: 100% !important;
    box-sizing: border-box; display: block;
    background:
        radial-gradient(1200px 300px at 85% -50%, rgba(88,166,255,0.12), transparent),
        linear-gradient(135deg, #161b22 0%, #0d1117 100%);
    border: 1px solid #21262d;
    border-radius: 14px;
    padding: 22px 28px;
    margin: 10px 0 16px;
    position: relative; z-index: 1;
}
.hero-top { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.hero-badge {
    width: 42px; height: 42px; border-radius: 11px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.35rem;
    background: linear-gradient(135deg, rgba(88,166,255,0.18), rgba(63,185,80,0.15));
    border: 1px solid #30363d;
}
.hero h1 {
    margin: 0; font-size: 2.05rem; font-weight: 800; letter-spacing: 1px;
    background: linear-gradient(90deg, #58a6ff, #3fb950);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    overflow-wrap: anywhere;
}
.hero .tagline { color: #8b949e; font-size: 0.92rem; margin-top: 3px; }
.status-row { margin-top: 10px; display: flex; flex-wrap: wrap; gap: 8px; }

.status-pill {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 12px; border-radius: 999px;
    font-size: 0.76rem; font-weight: 600;
    border: 1px solid #21262d; background: #161b22;
    color: #e6edf3; max-width: 100%;
}
.status-pill .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.status-pill.online { color: #3fb950; border-color: rgba(63,185,80,0.45); }
.status-pill.online .dot { background: #3fb950; box-shadow: 0 0 8px rgba(63,185,80,0.8); }
.status-pill.offline { color: #f85149; border-color: rgba(248,81,73,0.45); }
.status-pill.offline .dot { background: #f85149; }
.status-pill.paper { color: #d29922; border-color: rgba(210,153,34,0.45); }
.status-pill.paper .dot { background: #d29922; box-shadow: 0 0 8px rgba(210,153,34,0.8); }

/* ---------------- KPI CARDS ---------------- */

.kpi-row {
    width: 100%; max-width: 100%;
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    gap: 12px; margin-bottom: 14px;
}
.kpi-card {
    width: 100%; min-width: 0; max-width: 100%;
    box-sizing: border-box; overflow: hidden;
    background: linear-gradient(180deg, #161b22, #12171f);
    border: 1px solid #21262d; border-radius: 12px;
    padding: 13px 15px;
    transition: border-color .15s ease;
}
.kpi-card:hover { border-color: #388bfd66; }
.kpi-label {
    color: #8b949e; font-size: 0.68rem;
    text-transform: uppercase; letter-spacing: 0.07em;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.kpi-value {
    color: #e6edf3; font-size: 1.28rem; font-weight: 700;
    margin-top: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.source-tag.groq { color: #bc8cff; border: 1px solid rgba(188,140,255,0.45); }
.source-tag.local { color: #d29922; border: 1px solid rgba(210,153,34,0.45); }

/* ---------------- REASONING LIST ---------------- */

.reason-list { margin: 4px 0 0 2px; padding: 0; list-style: none; }
.reason-list li {
    color: #c9d1d9; font-size: 0.83rem; line-height: 1.45;
    padding: 5px 0 5px 20px; position: relative;
    border-bottom: 1px dashed #1c2430;
}
.reason-list li:last-child { border-bottom: none; }
.reason-list li::before {
    content: "▸"; position: absolute; left: 2px; color: #58a6ff; font-weight: 700;
}
.reason-list.inv li::before { content: "⚠"; color: #d29922; }

/* ---------------- TABLES / METRICS ---------------- */

.sig-table { width: 100%; border-collapse: collapse; table-layout: fixed; }
.sig-table td { padding: 6px 8px; border-bottom: 1px solid #21262d; font-size: 0.84rem; }
.sig-table tr:last-child td { border-bottom: none; }
.sig-name { width: 40%; color: #8b949e; }
.sig-val { width: 60%; text-align: right; font-weight: 700; color: #e6edf3; overflow-wrap: anywhere; word-break: break-word; }
.pos { color: #3fb950 !important; }
.neg { color: #f85149 !important; }
.neu { color: #d29922 !important; }

.metric-grid {
    display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 10px;
}
.metric-box {
    background: #0d1117; border: 1px solid #21262d; border-radius: 10px;
    padding: 11px 8px; text-align: center;
}
.metric-box .m-label {
    color: #8b949e; font-size: 0.64rem; text-transform: uppercase;
    letter-spacing: 0.04em; line-height: 1.25; min-height: 2em;
    display: flex; align-items: center; justify-content: center;
}
.metric-box .m-value {
    color: #e6edf3; font-size: 1.08rem; font-weight: 700; margin-top: 4px;
    white-space: nowrap;
}
.m-green { color: #3fb950 !important; } .m-red { color: #f85149 !important; }
.m-yellow { color: #d29922 !important; } .m-blue { color: #58a6ff !important; }

.oos-tag {
    display: inline-block; padding: 1px 9px; margin-left: 8px;
    border-radius: 999px; font-size: 0.62rem; font-weight: 800; letter-spacing: 0.07em;
    vertical-align: middle;
}
.oos-tag.in-sample { color: #8b949e; border: 1px solid #30363d; }
.oos-tag.validation { color: #58a6ff; border: 1px solid rgba(88,166,255,0.45); }
.oos-tag.out-of-sample { color: #3fb950; border: 1px solid rgba(63,185,80,0.55); }

/* ---------------- TIMELINE ---------------- */

.timeline { border-left: 2px solid #21262d; padding-left: 14px; margin-left: 6px; }
.timeline-item { margin-bottom: 9px; position: relative; }
.timeline-item::before {
    content: ""; position: absolute; left: -19px; top: 5px;
    width: 9px; height: 9px; border-radius: 50%; background: #58a6ff;
}
.timeline-item .t-time { color: #8b949e; font-size: 0.72rem; }
.timeline-item .t-decision { font-weight: 700; color: #e6edf3; }

/* ---------------- RESPONSIVE ---------------- */

@media (max-width: 1200px) {
    .kpi-row { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .metric-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .plan-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 700px) {
    .kpi-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .plan-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .hero { padding: 16px; }
    .hero h1 { font-size: 1.6rem; }
    .ai-decision-value { font-size: 2.3rem; }
    .plan-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

[data-testid="stPlotlyChart"] {
    width: 100% !important; max-width: 100% !important; overflow: hidden !important;
}

</style>
"""


# ============================================================
# RENDERING HELPERS
# ============================================================

def _render_html(target, html: str) -> None:
    """Render raw HTML via st.html() with markdown fallback."""
    if hasattr(target, "html"):
        target.html(html)
    else:
        target.markdown(html, unsafe_allow_html=True)


def _pill(text: str, css_class: str = "") -> str:
    dot = '<span class="dot"></span>' if css_class else ""
    cls = f"status-pill {css_class}".strip()
    return f'<span class="{cls}">{dot}{text}</span>'


def _kpi(label: str, value: str, css_class: str = "") -> str:
    cls = f"kpi-value {css_class}".strip()
    return (
        '<div class="kpi-card">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="{cls}">{value}</div>'
        "</div>"
    )


def _panel(title: str, body_html: str) -> str:
    return (
        '<div class="panel">'
        f'<div class="panel-title">{title}</div>'
        f"{body_html}"
        "</div>"
    )


def _metric_box(label: str, value: str, color: str = "") -> str:
    style = f' style="color:{color} !important;"' if color else ""
    return (
        '<div class="metric-box">'
        f'<div class="m-label">{label}</div>'
        f'<div class="m-value"{style}>{value}</div>'
        "</div>"
    )


def _sig_row(name: str, value: str, cls: str = "") -> str:
    vcls = f"sig-val {cls}".strip()
    return (
        "<tr>"
        f'<td class="sig-name">{name}</td>'
        f'<td class="{vcls}">{value}</td>'
        "</tr>"
    )


def _pct_color(value) -> str:
    try:
        return "pos" if float(value) >= 0 else "neg"
    except (TypeError, ValueError):
        return ""


# ============================================================
# HEADER
# ============================================================

def inject_css(container=None) -> None:
    _render_html(container or st, CUSTOM_CSS)


def render_header(connections: dict, container=None, extra_pills: list | None = None):
    """Hero header + connection status pills."""
    target = container or st

    alpaca_ok = connections.get("alpaca", False)
    groq_ok = connections.get("groq", False)

    pills = [
        _pill("ALPACA · CONNECTED", "online") if alpaca_ok
        else _pill("ALPACA · OFFLINE", "offline"),
        _pill("GROQ AI · READY", "online") if groq_ok
        else _pill("GROQ AI · UNAVAILABLE", "offline"),
        _pill("PAPER MODE", "paper"),
    ]
    for text, cls in (extra_pills or []):
        pills.append(_pill(text, cls))

    html = f"""
    <div class="hero">
        <div class="hero-top">
            <div class="hero-badge">AI</div>
            <div>
                <h1>{APP_NAME}</h1>
                <div class="tagline">{TAGLINE} — institutional research terminal · paper only</div>
            </div>
        </div>
        <div class="status-row">{''.join(pills)}</div>
    </div>
    """
    _render_html(target, html)


# ============================================================
# MARKET TERMINAL KPI STRIP
# ============================================================

def render_market_terminal(market: dict, regime_info=None, container=None):
    """Compact professional KPI strip for the current symbol."""
    target = container or st

    price = market.get("price", 0.0)
    prev_close = market.get("prev_close") or price
    day_change = price - prev_close if prev_close else 0.0
    day_change_pct = (day_change / prev_close * 100) if prev_close else 0.0

    trend_cls = {"BULLISH": "green", "BEARISH": "red"}.get(market.get("trend"), "yellow")
    rsi = market.get("rsi", 50.0)
    rsi_cls = "red" if rsi >= 70 else ("yellow" if rsi <= 30 else "")

    cards = [
        _kpi("Last Price", f"${price:,.2f}",
             "green" if day_change >= 0 else "red"),
        _kpi("Daily Change", f"{day_change:+.2f} ({day_change_pct:+.2f}%)",
             "green" if day_change >= 0 else "red"),
        _kpi("Trend", market.get("trend", "—"), trend_cls),
        _kpi("RSI (14)", f"{rsi:.1f}", rsi_cls),
        _kpi("ATR (14)", f"${market.get('atr', 0):,.2f} "
                         f"({market.get('atr_pct', 0):.1f}%)"),
        _kpi("Volatility √252", f"{market.get('volatility', 0):.1f}%"),
    ]

    row1 = "".join(cards)
    row2 = "".join([
        _kpi("Volume vs 20d", f"{market.get('volume_ratio', 1.0):.2f}×",
             "blue" if market.get("volume_ratio", 1) > 1.3 else ""),
        _kpi("ADX (14)", f"{market.get('adx', 0):.1f} · {market.get('adx_label', '—')}"),
        _kpi("Bollinger %B", f"{market.get('bb_percent_b', 0.5):.2f}"),
        _kpi("MACD Hist", f"{market.get('macd_hist', 0):+.4f}",
             "green" if market.get("macd_hist", 0) > 0 else "red"),
        _kpi("Support 20d", f"${market.get('support20', 0):,.2f}"),
        _kpi("Resistance 20d", f"${market.get('resistance20', 0):,.2f}"),
    ])

    regime_html = ""
    if regime_info:
        regime_html = (
            f'<div class="note" style="margin-top:10px;">REGIME: '
            f"<b>{regime_info.regime}</b> · strength {regime_info.trend_strength} "
            f"— {regime_info.description}</div>"
        )

    _render_html(
        target,
        _panel(
            f"MARKET TERMINAL",
            f'<div class="kpi-row">{row1}</div>'
            f'<div class="kpi-row">{row2}</div>'
            f"{regime_html}",
        ),
    )


# ============================================================
# HERO AI DECISION
# ============================================================

def pd_escape(text: str) -> str:
    """Minimal HTML escaping for AI text."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def render_ai_decision(ai: dict, plan=None, symbol: str = "", container=None):
    """
    Visual card compatible with both the legacy BUY/SELL/HOLD schema and the
    current TradeDecision schema used by agents.orchestrator.decide().
    """
    target = container or st

    action = str(ai.get("action") or ai.get("decision") or "HOLD").upper()
    decision = action
    confidence = float(ai.get("confidence", 0.0))
    risk = ai.get("risk", "HIGH")
    regime = ai.get("regime") or ai.get("market_regime", "—")
    horizon = ai.get("time_horizon", "SWING")
    source = ai.get("source", "groq")
    model = ai.get("model", "")
    strategy = ai.get("strategy_type") or ai.get("decision_type") or "NONE"
    iv_rank = ai.get("iv_rank")

    cls = {"OPEN": "buy", "CLOSE": "sell"}.get(action, "hold")
    conf_pct = int(round(confidence * 100))

    sub_items = [
        f"<span>Action <b>{decision}</b></span>",
        f"<span>Confidence <b>{conf_pct}%</b></span>",
        f"<span>Risk <b>{risk}</b></span>",
        f"<span>Regime <b>{regime}</b></span>",
        f"<span>Strategy <b>{strategy}</b></span>",
    ]
    if iv_rank is not None:
        sub_items.append(f"<span>IV Rank <b>{float(iv_rank):.1f}</b></span>")
    if horizon and horizon != "SWING":
        sub_items.append(f"<span>Horizon <b>{horizon}</b></span>")

    plan_cells = ""
    if plan is not None:
        p = plan.to_dict() if hasattr(plan, "to_dict") else dict(plan)
        # Support both the old risk-manager plan and the execution-loop option plan.
        entry = p.get("entry_price") or p.get("strike") or 0.0
        stop = p.get("stop_price") or 0.0
        tgt = p.get("target_price") or 0.0
        qty = p.get("quantity") or 0.0
        size = p.get("position_size_percent") or 0.0
        option_symbol = p.get("option_symbol") or "—"
        expiry = p.get("expiry_date") or "—"

        rr = ""
        if stop and tgt and entry and abs(entry - stop) > 1e-9:
            rr_val = abs(tgt - entry) / abs(entry - stop)
            rr = f"{rr_val:.1f} : 1"

        cells = [
            ("Strategy", str(strategy)),
            ("Option", str(option_symbol)),
            ("Expiry", str(expiry)),
            ("Qty", f"{qty:.2f}" if qty else "—"),
            ("Cash / Collat.", f"${p.get('required_cash', 0):,.2f}" if p.get('required_cash') else "—"),
            ("Risk / Reward", rr or "—"),
        ]
        plan_cells = "".join(
            f'<div class="plan-cell"><div class="p-label">{label}</div>'
            f'<div class="p-value">{value}</div></div>'
            for label, value in cells
        )
        plan_cells = f'<div class="plan-grid">{plan_cells}</div>'

    src_cls = "groq" if source == "groq" else "local"
    src_text = (
        f"GROQ · {model}" if source == "groq"
        else ("LOCAL POLICY · AI OFFLINE" if source == "local_policy"
              else ("FALLBACK · SAFE HOLD" if source == "fallback" else "AI · LIVE"))
    )

    html = f"""
    <div class="ai-hero decision-{decision}">
        <div class="ai-decision-label">AI DECISION · {symbol}</div>
        <div class="ai-decision-value {cls}">{decision}</div>
        <div class="ai-sub-row">{''.join(sub_items)}</div>
        <div class="conf-bar-track">
            <div class="conf-bar-fill" style="width:{conf_pct}%"></div>
        </div>
        {plan_cells}
        <span class="source-tag {src_cls}">{src_text}</span>
    </div>
    """
    _render_html(target, html)


# ============================================================
# AI REASONING PANEL
# ============================================================

def render_reasoning(ai: dict, container=None):
    """WHY / KEY FACTORS / INVALIDATIONS from the actual AI output."""
    target = container or st

    reason = ai.get("reason", "")
    factors = ai.get("key_factors") or []
    invalidations = ai.get("invalidations") or []

    factor_items = "".join(f"<li>{pd_escape(str(f))}</li>" for f in factors) or \
        '<li>No key factors returned.</li>'
    inv_items = "".join(f"<li>{pd_escape(str(i))}</li>" for i in invalidations)

    inv_block = ""
    if inv_items:
        inv_block = (
            '<div style="margin-top:10px;">'
            '<div class="kpi-label">INVALIDATION CONDITIONS</div>'
            f'<ul class="reason-list inv">{inv_items}</ul></div>'
        )

    html = _panel(
        "WHY QUANTNOVA THINKS THIS",
        '<div style="color:#c9d1d9;font-size:0.86rem;line-height:1.5;margin-bottom:8px;">'
        f'{pd_escape(reason)}</div>'
        '<div class="kpi-label">KEY FACTORS</div>'
        f'<ul class="reason-list">{factor_items}</ul>'
        f"{inv_block}",
    )
    _render_html(target, html)


# ============================================================
# SIGNAL MATRIX + SCORE BREAKDOWN
# ============================================================

def render_signal_matrix(market: dict, score_data: dict | None = None, container=None):
    target = container or st

    rows = [
        _sig_row("Trend", market.get("trend", "—"),
                 {"BULLISH": "pos", "BEARISH": "neg"}.get(market.get("trend"), "neu")),
        _sig_row("RSI", f"{market.get('rsi', 50):.1f} · {market.get('rsi_signal', '—')}",
                 "neg" if market.get("rsi_signal") == "OVERBOUGHT"
                 else ("pos" if market.get("rsi_signal") == "OVERSOLD" else "")),
        _sig_row("Momentum", market.get("momentum_signal", "—"),
                 {"POSITIVE": "pos", "NEGATIVE": "neg"}.get(
                     market.get("momentum_signal"), "neu")),
        _sig_row("MACD", market.get("macd_signal", "—"),
                 "pos" if market.get("macd_signal") == "BULLISH"
                 else ("neg" if market.get("macd_signal") == "BEARISH" else "")),
        _sig_row("Volume", market.get("volume_signal", "—")),
        _sig_row("Volatility", market.get("volatility_label", "—")),
        _sig_row("ADX Strength", market.get("adx_label", "—")),
        _sig_row("Regime", market.get("regime", "—"), "neu"),
    ]

    score_html = ""
    if score_data:
        composite = score_data.get("composite", 0.0)
        comp_cls = "pos" if composite > 15 else ("neg" if composite < -15 else "neu")
        components = score_data.get("components", {})
        comp_rows = "".join(
            _sig_row(name.title(), f"{value:+.2f}",
                     "pos" if value > 0.05 else ("neg" if value < -0.05 else ""))
            for name, value in components.items()
        )
        score_html = (
            '<div style="margin-top:10px;">'
            '<div class="kpi-label">MULTI-SIGNAL SCORE (AI INPUT)</div>'
            "<table class=\"sig-table\">"
            + _sig_row("Composite", f"{composite:+.1f} / ±100", comp_cls)
            + comp_rows
            + "</table>"
            '<div class="note" style="margin-top:6px;">The composite is an input to the '
            "AI engine — the AI may agree or disagree with it.</div>"
            "</div>"
        )

    _render_html(
        target,
        _panel(
            "SIGNAL MATRIX",
            "<table class=\"sig-table\">" + "".join(rows) + "</table>" + score_html,
        ),
    )


# ============================================================
# RISK PANEL
# ============================================================

def render_risk_panel(risk_status: dict, plan=None, account: dict | None = None,
                      config_caps: dict | None = None, container=None):
    """Risk management status + caps + proposed trade geometry."""
    target = container or st

    allowed = risk_status.get("allowed", False)
    reason = risk_status.get("reason", "")

    status_label = str(risk_status.get("status") or ("PASSED" if allowed else "BLOCKED")).upper()
    banner = (
        f'<div class="note" style="color:#3fb950;">✔ {status_label} — {pd_escape(reason)}</div>'
        if allowed
        else f'<div class="note" style="color:#f85149;">✖ {status_label} — {pd_escape(reason)}</div>'
    )

    rows = []
    if account:
        exposure = account.get("exposure_percent", 0.0)
        max_exp = (config_caps or {}).get("max_exposure", 95)
        rows.append(_sig_row(
            "Portfolio Exposure", f"{exposure:.1f}% / {max_exp:.0f}%",
            "neg" if exposure > max_exp else "pos",
        ))
        rows.append(_sig_row("Cash Available",
                             f"${account.get('cash', 0):,.2f}"))
    if config_caps:
        rows.append(_sig_row("Risk Per Trade",
                             f"{config_caps.get('risk_per_trade', 1):.1f}% of equity"))
        rows.append(_sig_row("Max Position Size",
                             f"{config_caps.get('max_position', 20):.0f}% of equity"))
    if plan is not None:
        p = plan.to_dict() if hasattr(plan, "to_dict") else dict(plan)
        rows.append(_sig_row("Planned Stop",
                             f"${p.get('stop_price', 0):,.2f} ({p.get('stop_loss_percent', 0):.1f}%)"))
        rows.append(_sig_row("Planned Target",
                             f"${p.get('target_price', 0):,.2f} ({p.get('take_profit_percent', 0):.1f}%)"))

    notes = ""
    if plan is not None:
        plan_notes = getattr(plan, "notes", None) or (plan.get("notes") if isinstance(plan, dict) else [])
        for note in plan_notes or []:
            notes += f'<div class="note">• {pd_escape(str(note))}</div>'

    _render_html(
        target,
        _panel("RISK MANAGEMENT — DETERMINISTIC GATE",
               banner + "<table class=\"sig-table\">" + "".join(rows) + "</table>" + notes),
    )


# ============================================================
# PORTFOLIO PANEL
# ============================================================

def render_portfolio_panel(portfolio: dict, container=None):
    target = container or st

    total_pnl = portfolio.get("total_pnl", 0.0)
    pnl_cls = "pos" if total_pnl >= 0 else "neg"
    unreal = portfolio.get("unrealized_pnl", 0.0)

    body = (
        "<table class=\"sig-table\">"
        + _sig_row("Starting Cash", f"${portfolio.get('starting_cash', 0):,.2f}")
        + _sig_row("Cash", f"${portfolio.get('cash', 0):,.2f}")
        + _sig_row("Shares", f"{portfolio.get('shares', 0):,.4f}")
        + _sig_row("Avg Entry", f"${portfolio.get('average_entry', 0):,.2f}")
        + _sig_row("Position Value", f"${portfolio.get('position_value', 0):,.2f}")
        + _sig_row("Unrealized P/L", f"${unreal:,.2f}", _pct_color(unreal))
        + _sig_row("Realized P/L (net)",
                   f"${portfolio.get('realized_pnl', 0):,.2f}",
                   _pct_color(portfolio.get("realized_pnl", 0)))
        + _sig_row("Fees Paid", f"${portfolio.get('total_fees_paid', 0):,.2f}")
        + _sig_row("Total Value", f"${portfolio.get('total_value', 0):,.2f}")
        + _sig_row("Total P/L", f"${total_pnl:,.2f}", pnl_cls)
        + "</table>"
        '<div class="note" style="margin-top:8px;">PAPER / SIMULATION MODE — '
        "no real funds at risk.</div>"
    )
    _render_html(target, _panel("PAPER PORTFOLIO", body))


# ============================================================
# BACKTEST METRICS GRID
# ============================================================

def render_backtest_metrics(bt: dict, label: str = "", container=None):
    """Full metrics card grid with N/A handling and IS/OOS tag."""
    target = container or st

    tag_class = {
        "IN-SAMPLE": "in-sample",
        "VALIDATION": "validation",
        "OUT-OF-SAMPLE": "out-of-sample",
    }.get(label, "")
    label_html = f'<span class="oos-tag {tag_class}">{label}</span>' if label else ""

    def fmt(value, pattern="{:.2f}", prefix="", suffix=""):
        if value is None:
            return "N/A"
        try:
            return prefix + pattern.format(float(value)) + suffix
        except (TypeError, ValueError):
            return "N/A"

    ret = bt.get("return_percent")
    pf = bt.get("profit_factor")

    boxes = [
        ("Total Return", fmt(ret, "{:+.2f}", suffix="%"),
         "m-green" if (ret or 0) >= 0 else "m-red"),
        ("Win Rate", fmt(bt.get("win_rate"), "{:.1f}", suffix="%"), "m-blue"),
        ("Profit Factor", fmt(pf, "{:.2f}"),
         "m-green" if (pf or 0) >= 1 else "m-red"),
        ("Max Drawdown", fmt(bt.get("max_drawdown_percent"), "{:.2f}", suffix="%"), "m-yellow"),
        ("Sharpe", fmt(bt.get("sharpe"), "{:.2f}")),
        ("Sortino", fmt(bt.get("sortino"), "{:.2f}")),
        ("Calmar", fmt(bt.get("calmar"), "{:.2f}")),
        ("CAGR", fmt(bt.get("cagr_percent"), "{:.2f}", suffix="%")),
        ("Trades", str(bt.get("trades", 0)), ""),
        ("Win / Loss",
         f"{bt.get('winning_trades', 0)} / {bt.get('losing_trades', 0)}", ""),
        ("Avg Win · Loss",
         f"{fmt(bt.get('avg_win'), '{:+,.0f}', '$')} · "
         f"{fmt(bt.get('avg_loss'), '{:+,.0f}', '$')}", ""),
        ("Expectancy", fmt(bt.get("expectancy"), "{:+,.2f}", "$"),
         "m-green" if (bt.get("expectancy") or 0) >= 0 else "m-red"),
        ("Largest W · L",
         f"{fmt(bt.get('largest_win'), '{:+,.0f}', '$')} · "
         f"{fmt(bt.get('largest_loss'), '{:+,.0f}', '$')}", ""),
        ("Exposure", fmt(bt.get("exposure_percent"), "{:.1f}", suffix="%"), ""),
        ("Avg Hold", fmt(bt.get("avg_holding_days"), "{:.1f}", suffix="d"), ""),
        ("Alpha vs B&H", fmt(bt.get("alpha_percent"), "{:+.2f}", suffix="%"),
         "m-green" if (bt.get("alpha_percent") or 0) >= 0 else "m-red"),
    ]

    metric_boxes = []
    for metric in boxes:
        label, value, *color = metric
        metric_boxes.append(_metric_box(label, value, color[0] if color else ""))
    grid = "".join(metric_boxes)

    unreal_note = ""
    if bt.get("open_position_at_end"):
        unreal_note = (
            '<div class="note" style="margin-top:8px;">Open position at test end was '
            f"marked to market: unrealized ${bt.get('unrealized_pnl', 0):,.2f} "
            "(included in final value; realized P/L shown separately).</div>"
        )

    _render_html(
        target,
        _panel(
            "BACKTEST CENTER — HISTORICAL SIMULATION" + label_html,
            f'<div class="metric-grid">{grid}</div>{unreal_note}'
            '<div class="note" style="margin-top:8px;">Past performance does NOT '
            "guarantee future results.</div>",
        ),
    )


# ============================================================
# STRATEGY COMPARISON TABLE
# ============================================================

def render_strategy_comparison(comparison_rows: list, container=None):
    """
    comparison_rows: list of dicts with keys
        Strategy, Period, Return %, Win Rate %, Profit Factor,
        Max DD %, Sharpe, Trades, Alpha %
    """
    target = container or st

    if not comparison_rows:
        _render_html(
            target,
            _panel("STRATEGY COMPARISON", '<div class="note">No results.</div>'),
        )
        return

    df = pd.DataFrame(comparison_rows)
    target.markdown("##### ▶ STRATEGY ARENA — same data, same costs")
    target.dataframe(df, use_container_width=True, height=260, hide_index=True)


# ============================================================
# TRADE HISTORY
# ============================================================

def render_trade_history(trades: list, container=None):
    target = container or st

    if not trades:
        _render_html(
            target,
            _panel("TRADE HISTORY",
                   '<div class="note">No closed round trips yet.</div>'),
        )
        return

    rows = []
    for t in trades:
        net = float(t.get("net_pnl") or 0.0)
        rows.append({
            "#": t.get("trade_id"),
            "Entry": t.get("entry_time"),
            "Exit": t.get("exit_time"),
            "Entry $": round(float(t.get("entry_price") or 0), 2),
            "Exit $": round(float(t.get("exit_price") or 0), 2),
            "Qty": round(float(t.get("quantity") or 0), 3),
            "Net P/L": net,
            "Return %": t.get("return_percent"),
            "Hold (d)": t.get("holding_days"),
            "Exit Reason": t.get("exit_reason"),
        })

    df = pd.DataFrame(rows).sort_values("#")
    target.markdown("##### 📊 TRADE HISTORY — CLOSED ROUND TRIPS")
    target.dataframe(df, use_container_width=True, height=min(280, 80 + 26 * len(df)))


# ============================================================
# AI DECISION TIMELINE
# ============================================================

def render_timeline(history: list, container=None):
    target = container or st

    if not history:
        _render_html(
            target,
            _panel("AI DECISION TIMELINE",
                   '<div class="note">No AI decisions yet.</div>'),
        )
        return

    items = ""
    for entry in history[-10:]:
        time_str = entry.get("time", "")
        decision = entry.get("decision", "HOLD")
        conf = entry.get("confidence", 0)
        color = {"BUY": "#3fb950", "SELL": "#f85149"}.get(decision, "#d29922")
        items += (
            '<div class="timeline-item">'
            f'<div class="t-time">{time_str}</div>'
            f'<div class="t-decision" style="color:{color};">'
            f"{decision}&nbsp;&nbsp;{conf:.0%}</div>"
            "</div>"
        )

    _render_html(
        target,
        _panel("AI DECISION TIMELINE", f'<div class="timeline">{items}</div>'),
    )

