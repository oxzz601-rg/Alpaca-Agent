"""
HRAMY OMNI AI - Plotly Charts
============================================================
Institutional-grade dark-terminal charts:

    price_chart            candles + SMAs/EMA + Bollinger + trade markers
    equity_curve_chart     strategy equity vs Buy & Hold benchmark
    drawdown_chart         underwater (drawdown) area chart
    trade_pnl_chart        net P/L per trade distribution
    regime_timeline_chart  deterministic regime classification strip
    rsi_gauge              RSI dial

All charts share the HRAMY OMNI dark identity.
"""
import os
import sys

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DARK_BG = "#0d1117"
PANEL_BG = "#161b22"
GRID = "#21262d"
TEXT = "#e6edf3"
MUTED = "#8b949e"
GREEN = "#3fb950"
RED = "#f85149"
BLUE = "#58a6ff"
YELLOW = "#d29922"
PURPLE = "#bc8cff"


def _style(fig, height=460, title=None):
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=DARK_BG,
        plot_bgcolor=PANEL_BG,
        font=dict(color=TEXT, family="Inter, Segoe UI, sans-serif"),
        margin=dict(l=10, r=10, t=48 if title else 14, b=10),
        height=height,
        hovermode="x unified",
        legend=dict(
            orientation="h", yanchor="top", y=0.99, xanchor="left", x=0,
            entrywidth=0, entrywidthmode="pixels",
            font=dict(size=10),
            bgcolor="rgba(0,0,0,0)",
        ),
    )
    if title:
        fig.update_layout(title=dict(text=title, font=dict(size=15, color=TEXT)))
    fig.update_xaxes(gridcolor=GRID, showgrid=True, zeroline=False)
    fig.update_yaxes(gridcolor=GRID, showgrid=True, zeroline=False)
    return fig


def price_chart(data, symbol, trades=None):
    """
    Main terminal chart: candlesticks + SMA20/SMA50/EMA20 + Bollinger
    shading + volume bars + optional round-trip trade markers.
    """
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.78, 0.22], vertical_spacing=0.03,
    )

    fig.add_trace(go.Candlestick(
        x=data.index, open=data["open"], high=data["high"],
        low=data["low"], close=data["close"], name="Price",
        increasing_line_color=GREEN, decreasing_line_color=RED,
        increasing_fillcolor=GREEN, decreasing_fillcolor=RED,
    ), row=1, col=1)

    if {"bb_upper", "bb_lower"} <= set(data.columns):
        fig.add_trace(go.Scatter(
            x=data.index, y=data["bb_upper"], name="BB Upper",
            line=dict(width=1, color="rgba(88,166,255,0.35)"),
            hoverinfo="skip",
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=data.index, y=data["bb_lower"], name="BB Lower",
            line=dict(width=1, color="rgba(88,166,255,0.35)"),
            fill="tonexty", fillcolor="rgba(88,166,255,0.05)",
            hoverinfo="skip",
        ), row=1, col=1)

    for col, color, name, dash in [
        ("sma20", BLUE, "SMA20", "solid"),
        ("sma50", YELLOW, "SMA50", "solid"),
        ("ema20", PURPLE, "EMA20", "dot"),
    ]:
        if col in data.columns:
            fig.add_trace(go.Scatter(
                x=data.index, y=data[col], name=name,
                line=dict(color=color, width=1.5, dash=dash),
            ), row=1, col=1)

    if trades:
        fig.add_trace(go.Scatter(
            x=pd.to_datetime([t.get("entry_time") for t in trades], errors="coerce"),
            y=[t.get("entry_price") for t in trades],
            mode="markers", name="Entries",
            marker=dict(symbol="triangle-up", size=13, color=GREEN,
                        line=dict(width=1, color=DARK_BG)),
            text=[f"#{t.get('trade_id')} entry" for t in trades],
            hovertemplate="%{text}<br>%{x}<br>$%{y:.2f}<extra></extra>",
        ), row=1, col=1)
        colors = [GREEN if float(t.get("net_pnl") or 0) >= 0 else RED for t in trades]
        fig.add_trace(go.Scatter(
            x=pd.to_datetime([t.get("exit_time") for t in trades], errors="coerce"),
            y=[t.get("exit_price") for t in trades],
            mode="markers", name="Exits",
            marker=dict(symbol="triangle-down", size=13, color=colors,
                        line=dict(width=1, color=DARK_BG)),
            text=[
                f"#{t.get('trade_id')} exit · {t.get('exit_reason')} · "
                f"${float(t.get('net_pnl') or 0):+.2f}"
                for t in trades
            ],
            hovertemplate="%{text}<br>%{x}<br>$%{y:.2f}<extra></extra>",
        ), row=1, col=1)

    vol_colors = [
        GREEN if c >= o else RED
        for o, c in zip(data["open"], data["close"])
    ]
    fig.add_trace(go.Bar(
        x=data.index, y=data["volume"], name="Volume",
        marker_color=vol_colors, opacity=0.55, showlegend=False,
    ), row=2, col=1)

    fig.update_xaxes(rangeslider_visible=False)
    return _style(fig, height=520, title=f"{symbol} · Daily Candles + Signals")


def rsi_gauge(rsi):
    color = GREEN if 30 <= rsi <= 70 else (RED if rsi > 70 else YELLOW)
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=rsi,
        number=dict(font=dict(size=28, color=color)),
        title=dict(text="RSI (14)", font=dict(size=13, color=MUTED)),
        gauge=dict(
            axis=dict(range=[0, 100], tickcolor=MUTED, tickwidth=1),
            bar=dict(color=color, thickness=0.35),
            bgcolor=PANEL_BG, borderwidth=1, bordercolor=GRID,
            steps=[
                {"range": [0, 30], "color": "rgba(210,153,34,0.25)"},
                {"range": [30, 70], "color": "rgba(63,185,80,0.15)"},
                {"range": [70, 100], "color": "rgba(248,81,73,0.25)"},
            ],
            threshold={"line": {"color": TEXT, "width": 2}, "thickness": 0.75, "value": 70},
        ),
    ))
    fig.update_layout(
        template="plotly_dark", paper_bgcolor=DARK_BG,
        height=200, margin=dict(l=20, r=20, t=30, b=10),
    )
    return fig


def equity_curve_chart(strategy_curve, benchmark_curve=None,
                       title="Equity Curve · Strategy vs Buy & Hold"):
    """Strategy equity vs Buy & Hold benchmark."""
    fig = go.Figure()
    if strategy_curve:
        sdf = pd.DataFrame(strategy_curve)
        fig.add_trace(go.Scatter(
            x=sdf["date"], y=sdf["value"], name="Strategy",
            line=dict(color=BLUE, width=2.2), fill="tozeroy",
            fillcolor="rgba(88,166,255,0.07)",
        ))
    if benchmark_curve:
        bdf = pd.DataFrame(benchmark_curve)
        fig.add_trace(go.Scatter(
            x=bdf["date"], y=bdf["value"], name="Buy & Hold",
            line=dict(color=MUTED, width=1.6, dash="dash"),
        ))
    return _style(fig, height=340, title=title)


def drawdown_chart(equity_curve, title="Drawdown (Underwater)"):
    """Drawdown percentage from running peak."""
    if not equity_curve:
        return go.Figure()
    eq = pd.DataFrame(equity_curve)["value"].astype(float)
    peak = eq.cummax()
    dd = (eq / peak - 1.0) * 100
    dates = pd.DataFrame(equity_curve)["date"]

    fig = go.Figure(go.Scatter(
        x=dates, y=dd, name="Drawdown %",
        line=dict(color=RED, width=1.5),
        fill="tozeroy", fillcolor="rgba(248,81,73,0.18)",
    ))
    fig.update_yaxes(ticksuffix="%")
    return _style(fig, height=220, title=title)


def trade_pnl_chart(trades, title="Net P/L per Trade"):
    """Bar chart of net P/L per closed trade."""
    if not trades:
        return go.Figure()
    ids = [f"#{t.get('trade_id')}" for t in trades]
    pnls = [float(t.get("net_pnl") or 0.0) for t in trades]
    colors = [GREEN if p >= 0 else RED for p in pnls]

    fig = go.Figure(go.Bar(
        x=ids, y=pnls, marker_color=colors, name="Net P/L",
        hovertemplate="%{x}: $%{y:+.2f}<extra></extra>",
    ))
    fig.update_yaxes(tickprefix="$")
    return _style(fig, height=260, title=title)


def regime_timeline_chart(data):
    """Deterministic regime classification rendered as a colored strip."""
    try:
        from analysis.regime import detect_regime
    except ImportError:
        return go.Figure()

    regimes, dates = [], []
    for ts, row in data.iterrows():
        snap = {
            "price": float(row["close"]),
            "sma20": float(row["sma20"]),
            "sma50": float(row["sma50"]),
            "adx": float(row.get("adx", 0) or 0),
            "volatility": float(row.get("volatility", 25) or 25),
            "volume_ratio": float(row.get("volume_ratio", 1)) if pd.notna(row.get("volume_ratio")) else 1.0,
            "resistance20": float(row.get("resistance20", row["close"])),
            "support20": float(row.get("support20", row["close"])),
        }
        regimes.append(detect_regime(snap).regime)
        dates.append(ts)

    color_map = {
        "BULL_TREND": GREEN,
        "BEAR_TREND": RED,
        "SIDEWAYS": MUTED,
        "HIGH_VOLATILITY": YELLOW,
        "LOW_VOLATILITY": BLUE,
        "BREAKOUT": PURPLE,
    }

    fig = go.Figure()
    for regime_key, color in color_map.items():
        xs = [d for d, r in zip(dates, regimes) if r == regime_key]
        if xs:
            fig.add_trace(go.Scatter(
                x=xs, y=[1] * len(xs),
                mode="markers", name=regime_key,
                marker=dict(symbol="square", size=7, color=color),
                hovertemplate=f"{regime_key}<br>%{{x}}<extra></extra>",
            ))
    fig.update_yaxes(visible=False, range=[0, 2])
    return _style(fig, height=170, title="Market Regime Timeline (deterministic)")
