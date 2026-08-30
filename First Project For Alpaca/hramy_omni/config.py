"""
HRAMY OMNI AI - Configuration Module
============================================================
Loads configuration from environment variables ONLY.
Never hardcodes credentials.

Every tunable parameter can be overridden via environment
variables (HRAMY_ prefix) without touching source code.
"""

import os
from datetime import datetime, timedelta

# python-dotenv is optional — the app works with plain environment variables.
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    from zoneinfo import ZoneInfo
    EASTERN_TZ = ZoneInfo("America/New_York")
except Exception:
    import pytz
    EASTERN_TZ = pytz.timezone("America/New_York")


def _env_float(name: str, default: float) -> float:
    """Read a float env var, falling back to the default on any problem."""
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return float(default)


# ------------------------------------------------------------
# Credentials (environment variables ONLY)
# ------------------------------------------------------------
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_PAPER_API_KEY = os.getenv("ALPACA_PAPER_API_KEY", ALPACA_API_KEY)
ALPACA_PAPER_SECRET_KEY = os.getenv("ALPACA_PAPER_SECRET_KEY", ALPACA_SECRET_KEY)
ALPACA_PAPER_ACCOUNT_ID = os.getenv("ALPACA_PAPER_ACCOUNT_ID", "")
ALPACA_ACCOUNT_ID = ALPACA_PAPER_ACCOUNT_ID or os.getenv("ALPACA_ACCOUNT_ID", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# ------------------------------------------------------------
# Application settings
# ------------------------------------------------------------
APP_NAME = "QuantNova"
TAGLINE = "AI-Powered Explainable Market Intelligence"
PAPER_MODE = True  # Strictly paper / simulation. NEVER live.

DEFAULT_SYMBOL = "AAPL"
LOOKBACK_DAYS = 320          # Enough bars for SMA50 + ADX(14) + MACD warm-up
MIN_BARS_REQUIRED = 80       # Minimum bars needed after indicator warm-up
STARTING_CASH = 100_000.00
TRADING_DAYS_PER_YEAR = 252

# Overridable via environment so the model can be changed without code edits.
AI_MODEL = os.getenv("HRAMY_AI_MODEL", "openai/gpt-oss-20b")

AI_CONFIDENCE_THRESHOLD = _env_float("HRAMY_AI_CONFIDENCE_THRESHOLD", 0.60)

# ------------------------------------------------------------
# Risk management (deterministic layer — overrides the AI)
# ------------------------------------------------------------
MAX_POSITION_PERCENT = _env_float("HRAMY_MAX_POSITION_PERCENT", 0.20)
RISK_PER_TRADE = _env_float("HRAMY_RISK_PER_TRADE", 0.01)          # 1% equity risk per trade
MAX_PORTFOLIO_EXPOSURE = _env_float("HRAMY_MAX_PORTFOLIO_EXPOSURE", 0.95)

# Hard clamps applied to AI-proposed stop / take-profit percentages
STOP_LOSS_MIN_PCT = 0.008     # 0.8% — stops tighter than this are noise
STOP_LOSS_MAX_PCT = 0.12      # 12%  — wider than this is not risk management
TAKE_PROFIT_MIN_PCT = 0.015   # 1.5%
TAKE_PROFIT_MAX_PCT = 0.35    # 35%
MIN_RISK_REWARD_RATIO = 1.2   # target must be >= 1.2x the stop distance

# Position-size cap proposed by the AI is clamped to this band
AI_POSITION_SIZE_MIN_PCT = 0.0
AI_POSITION_SIZE_MAX_PCT = MAX_POSITION_PERCENT

# Maximum daily-loss circuit breaker (fraction of equity)
MAX_DAILY_LOSS_PERCENT = _env_float("HRAMY_MAX_DAILY_LOSS", 0.05)

# ------------------------------------------------------------
# Execution cost model (realistic fills — used by backtest AND paper trades)
# ------------------------------------------------------------
COMMISSION_RATE = _env_float("HRAMY_COMMISSION_RATE", 0.0005)   # 5 bps per side
SLIPPAGE_PCT = _env_float("HRAMY_SLIPPAGE_PCT", 0.0005)         # 5 bps adverse fill
SPREAD_PCT = _env_float("HRAMY_SPREAD_PCT", 0.0002)             # assumed half-spread cost

# SIMULATION_QTY retained for backwards compatibility of the manual
# "Execute" button when no AI sizing is available.
SIMULATION_QTY = 1

# ------------------------------------------------------------
# Walk-forward / out-of-sample configuration
# ------------------------------------------------------------
WF_TRAIN_FRACTION = 0.60     # in-sample development period
WF_VALIDATION_FRACTION = 0.20  # parameter-selection period
# remaining fraction is the untouched OUT-OF-SAMPLE test period

# ------------------------------------------------------------
# Request / caching settings (cost control)
# ------------------------------------------------------------
DATA_CACHE_TTL = 300          # seconds - cache historical data
AI_CACHE_TTL = 600            # seconds - cache AI analysis
REQUEST_TIMEOUT = 30          # seconds - HTTP timeout
MAX_RETRIES = 2               # never retry infinitely


def get_historical_start_end(days: int = LOOKBACK_DAYS):
    """Return explicit (start, end) timestamps for Alpaca bars request.

    Alpaca requires explicit start/end for reliable multi-bar retrieval.
    We pad the start by extra calendar days to account for weekends/holidays
    so we always receive >= `days` trading bars.
    """
    end = datetime.now(EASTERN_TZ)
    # Pad ~1.5 calendar days per trading day to guarantee enough bars
    padded_days = int(days * 1.5) + 15
    start = end - timedelta(days=padded_days)
    return start, end
