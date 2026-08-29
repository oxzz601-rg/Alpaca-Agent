# 🤖 HRAMY OMNI AI

**AI-Powered Explainable Market Intelligence for Paper Trading & Quantitative Research**

An institutional-grade AI market research, simulation, and decision-support terminal:

```
Alpaca Market Data (IEX Feed) → 14 Technical Indicators → Market Regime Detection
    → 8-Factor Multi-Signal Score → Groq AI Decision Engine → Anti-Fabrication Validation
    → Deterministic Risk Manager → Position Sizing → Paper Portfolio Simulator
    → Event-Driven Backtester (Walk-Forward OOS) → Bloomberg-Style Terminal GUI
```

> ⚠️ **PAPER / SIMULATION MODE ONLY** — this application **never** places real orders.

---

## 🧠 Core System Capabilities

1. **Market Data Layer** (`data/alpaca_data.py`):
   - Daily OHLCV bars via Alpaca Market Data IEX feed.
   - Padded date windows guaranteeing sufficient bars for warm-up.
   - Robust offline synthetic fallback for demonstration continuity.

2. **Quantitative Engine** (`analysis/indicators.py` & `analysis/signals.py`):
   - 14 quantitative indicators: SMA20/50, EMA20/50, RSI(14), ATR(14), MACD(12,26,9), Bollinger Bands(20,2), ADX(14), Momentum(10), Realized Volatility(20), Volume Ratio, Rolling VWAP(20), Support/Resistance(20).
   - 8-Factor normalized multi-signal scoring system on `[-100, +100]`.

3. **Deterministic Market Regime Classifier** (`analysis/regime.py`):
   - Classifies market state: `BULL_TREND`, `BEAR_TREND`, `SIDEWAYS`, `HIGH_VOLATILITY`, `LOW_VOLATILITY`, `BREAKOUT`.

4. **Groq AI Decision Engine** (`ai/groq_engine.py`):
   - Receives complete quantitative context (indicators, regime, scores, account equity/exposure, risk constraints).
   - Returns structured JSON decision with confidence, risk, sizing, stop loss %, take profit %, horizon, reason, key factors, and invalidation conditions.
   - Strict anti-fabrication validator drops hallucinations and clamps outputs. Degrades gracefully to `SAFE HOLD`.

5. **Deterministic Risk Manager** (`risk/risk_manager.py`):
   - Sits strictly between AI and execution.
   - Vetoes invalid trades (confidence floor, HIGH risk veto, regime conflict veto, cash/exposure caps).
   - Enforces minimum Risk:Reward ratio (>= 1.2x) and ATR-based stop clamps.

6. **Paper Portfolio Simulator** (`portfolio/simulator.py`):
   - Realistic execution modeling: commission, slippage, and spread.
   - Fractional shares supported.
   - Full completed round-trip trade accounting and separation of realized vs. unrealized P/L.

7. **Event-Driven Backtest & Walk-Forward Suite** (`backtest/`):
   - Next-bar open execution (zero lookahead).
   - Intrabar stop-loss and take-profit checking (conservative stop precedence).
   - Walk-forward chronological splits: Train (60%), Validation (20%), Out-of-Sample (20%).
   - Strategy Arena comparing 5 strategies + Buy & Hold benchmark with Alpha calculation.

---

## 📁 Project Structure

```
hramy_omni/
├── app.py                     # Streamlit entrypoint / orchestrator
├── config.py                  # Env-var config (no hardcoded secrets)
├── requirements.txt           # Python dependencies
├── README.md                  # Project documentation
├── PROJECT_SOURCE.txt         # Architecture / source specification
├── .env.example               # Sanitized environment template
├── .gitignore                 # Protects .env from commits
├── .streamlit/
│   └── config.toml            # Dark terminal theme
├── data/
│   └── alpaca_data.py         # Alpaca data layer (IEX feed, lazy client)
├── analysis/
│   ├── indicators.py          # 14 technical indicators
│   ├── regime.py              # Market regime detection
│   └── signals.py             # 8-factor multi-signal scoring
├── ai/
│   └── groq_engine.py         # Groq LLM → validated structured JSON
├── risk/
│   └── risk_manager.py        # Deterministic risk layer & position sizing
├── portfolio/
│   └── simulator.py           # Paper portfolio (round-trip accounting)
├── backtest/
│   ├── engine.py              # Event-driven backtesting engine & metrics
│   ├── strategies.py          # 5-strategy comparison suite
│   └── walkforward.py         # Walk-forward out-of-sample framework
├── ui/
│   ├── dashboard.py           # Institutional dark terminal GUI panels
│   └── charts.py              # Plotly candles, equity curve, drawdown, regime strip
├── utils/
│   └── logging_config.py      # Secure logging (never logs secrets)
└── tests/
    ├── data_builder.py        # Deterministic synthetic test data generator
    ├── test_analysis.py       # Indicator, signal, and regime test suite
    ├── test_ai_risk_portfolio.py # AI validator, risk gate, portfolio test suite
    └── test_backtest.py       # Backtest execution, accounting, walk-forward tests
```

---

## 🚀 How to Run

> ⚠️ Always use `py` (or `py -m ...`) on Windows.

### 1. Install Dependencies

```powershell
cd "C:\Users\Mohammed Ramy\Desktop\First Project For Alpaca\hramy_omni"
py -m pip install -r requirements.txt
```

### 2. Configure Environment Variables

```powershell
copy .env.example .env
```

Configure your credentials in `.env`:
```ini
ALPACA_API_KEY=your_alpaca_api_key
ALPACA_SECRET_KEY=your_alpaca_secret_key
GROQ_API_KEY=your_groq_api_key
```

### 3. Run the Test Suite

```powershell
py _smoke_test.py
```
Expected: **66/66 unit tests pass (0 failures, 0 errors)**.

### 4. Launch the Institutional Terminal

```powershell
py -m streamlit run app.py
```

Navigate to `http://localhost:8501`.

---

## 🛡️ Security & Compliance

- **Zero credential logging**: Keys are never printed, displayed in the GUI, or written to disk.
- **Strictly paper**: No real funds or real exchange order routing code exists.
- **Fail-safe degradation**: If AI or market data APIs are unreachable, the application falls back safely without leaking details or crashing.