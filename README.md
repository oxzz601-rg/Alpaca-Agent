# QuantNova

QuantNova is an explainable AI options-trading research terminal built for Alpaca paper trading. It combines market data, quantitative analysis, a multi-agent decision workflow, deterministic risk controls, option-contract resolution, paper execution, and walk-forward backtesting.

It is designed to make every decision inspectable: the application shows the market inputs, selected strategy, risk-gate result, reasoning, invalidation conditions, and agent trace before any execution step.

## What It Does

- Loads daily market data from Alpaca's IEX feed.
- Calculates technical indicators and an eight-factor signal score.
- Classifies the market regime.
- Runs the agent workflow: Market Analyst, Opportunity Scanner, Options Strategist, and Devil's Advocate.
- Produces a validated `TradeDecision` contract with a safe fallback to `HOLD` when the decision is invalid or unavailable.
- Resolves option contracts from Alpaca's option chain, with a synthetic fallback for dry-run workflows.
- Applies deterministic risk checks before execution.
- Supports paper-account order submission only when explicitly requested.
- Provides a local paper portfolio simulator with fees, slippage, and round-trip accounting.
- Runs event-driven backtests, walk-forward evaluation, and strategy comparisons.
- Records structured Alpaca CLI/MCP-style events for auditability.

## Decision Pipeline

```text
Alpaca market data
        |
Indicators and signal score
        |
Market regime detection
        |
Multi-agent TradeDecision
        |
Schema validation and safe fallback
        |
Option contract resolution
        |
Deterministic risk gate
        |
Dry run or explicit Alpaca paper submission
```

The AI does not bypass the risk gate. A decision can be changed to `HOLD` or blocked when it fails confidence, exposure, collateral, strategy, or account checks.

## Requirements

- Windows, macOS, or Linux
- Python 3.10 or newer
- An Alpaca paper account with API access
- Optional: Groq API key for LLM refinement
- Optional: Alpaca CLI for CLI/MCP audit integration

## Installation on Windows

From PowerShell:

```powershell
cd "C:\Users\Admin\Desktop\Alpaca-Agent\First Project For Alpaca\hramy_omni"
py -m pip install -r requirements.txt
```

Create a local `.env` file if the project does not already have one. Keep credentials out of Git:

```ini
ALPACA_API_KEY=your_paper_api_key
ALPACA_SECRET_KEY=your_paper_secret_key
GROQ_API_KEY=your_groq_api_key
```

The Groq key is optional. Without it, the deterministic local agent policy remains available.

## Alpaca CLI Setup

The official Alpaca CLI is optional for the Python application, but it enables CLI health checks and audit events. On Windows, install Go first, then run:

```powershell
go install github.com/alpacahq/cli/cmd/alpaca@latest
$env:Path += ";$env:USERPROFILE\go\bin"
alpaca version
```

Authenticate the paper profile:

```powershell
alpaca profile login
alpaca doctor
alpaca account get
```

The expected account is a paper account. Do not use the CLI's `--live` option for this project.

## Run the Dashboard

Set the import path used by the agent packages, then launch Streamlit:

```powershell
cd "C:\Users\Admin\Desktop\Alpaca-Agent\First Project For Alpaca\hramy_omni"
$env:PYTHONPATH = ".;ai"
py -m streamlit run app.py
```

Open the local URL shown by Streamlit, normally `http://localhost:8501`.

The dashboard includes:

- Overview: market terminal, indicators, signal matrix, and paper portfolio.
- AI Decision: strategy, option contract, reasoning, agent trace, and risk gate.
- Backtest Center: train, validation, out-of-sample, benchmark, and strategy comparison views.
- Paper Execution: explicit simulated execution through the local paper portfolio.
- Assistant: natural-language questions and safe paper actions.

## Test the System

Run the complete test suite:

```powershell
cd "C:\Users\Admin\Desktop\Alpaca-Agent\First Project For Alpaca\hramy_omni"
$env:PYTHONPATH = ".;ai"
py -m unittest discover -q
```

The suite covers indicators, regimes, agent contracts, risk gates, option planning, portfolio accounting, execution behavior, and backtesting.

## CLI Workflows

Run a local synthetic dry run:

```powershell
$env:PYTHONPATH = ".;ai"
py -m trading.cli cycle AAPL
```

Run a live-data cycle without submitting an order:

```powershell
py -m trading.cli cycle AAPL --live
py -m trading.cli cycle TSLA --live
py -m trading.cli cycle NVDA --live
```

The `--live` flag uses Alpaca market data and attempts live option-chain resolution. It does not submit an order by itself.

## Paper Order Submission

The `--submit` flag sends an order to the configured Alpaca paper account when the current decision is `OPEN`, the strategy is supported, and the deterministic risk gate approves it:

```powershell
py -m trading.cli cycle SYMBOL --live --submit
```

Review the output before using `--submit`. Check the action, strategy, option symbol, quantity, required collateral, and risk result. A new cycle can produce a different decision from an earlier dry run.

After a paper submission, inspect the account with:

```powershell
alpaca order list
alpaca position list
```

Paper trading is not live trading, but it still creates real orders and positions in the paper account. Never use live credentials or live-trading flags with this project.

## Project Structure

```text
hramy_omni/
├── app.py                    # Streamlit dashboard and application flow
├── config.py                 # Environment-based configuration
├── requirements.txt          # Python dependencies
├── ai/
│   ├── chatbot.py            # Assistant commands and answers
│   └── agents/               # Agent workflow and TradeDecision schema
├── analysis/                 # Indicators, signals, and regime detection
├── data/                     # Alpaca market-data access
├── trading/
│   ├── cli.py                # Command-line workflows
│   ├── execution_loop.py    # Decision, risk, contract, and submit flow
│   ├── option_chain.py       # Option-contract resolution
│   └── mcp_cli.py            # Structured CLI/MCP event adapter
├── risk/                     # Deterministic risk management
├── portfolio/                # Local paper portfolio simulator
├── backtest/                 # Backtesting and walk-forward analysis
├── ui/                       # Dashboard panels and charts
└── tests/                    # Automated test suite
```

## Configuration

Configuration is read from environment variables. Important settings include:

- `ALPACA_API_KEY` and `ALPACA_SECRET_KEY`: Alpaca credentials.
- `GROQ_API_KEY`: optional LLM refinement.
- `HRAMY_AI_MODEL`: optional model override.
- `HRAMY_MAX_POSITION_PERCENT`: maximum position-size fraction.
- `HRAMY_RISK_PER_TRADE`: configured risk budget.
- `HRAMY_MAX_PORTFOLIO_EXPOSURE`: portfolio exposure limit.

Risk limits are enforced by code and are not controlled solely by the model.

## Security and Scope

- Credentials are read from environment variables and are not hardcoded.
- `.env` and Streamlit secrets are ignored by Git.
- The default execution mode is dry run or local simulation.
- Explicit paper submission is available through the execution loop.
- No live trading should be enabled for this project.
- This project is for research and paper-trading demonstration, not financial advice.

## Current Limitations

- Option-chain availability depends on Alpaca permissions, market state, and available contracts.
- The Streamlit dashboard currently uses its configured resolver mode; the CLI is the recommended path for validating live option-chain resolution.
- LLM refinement is optional and can be unavailable because of credentials, rate limits, or network errors.
- A `HOLD` result is an intentional safe outcome when market conditions do not provide a strong edge.
