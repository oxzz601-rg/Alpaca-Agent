"""
HRAMY OMNI AI - Logging Configuration
============================================================
Secure logging setup.
- Credentials are NEVER logged.
- Default level is INFO; set HRAMY_LOG_LEVEL to override.
"""

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import APP_NAME

# Blocklist of variable names whose values must never be logged.
SENSITIVE_NAMES = {
    "api_key",
    "apikey",
    "secret",
    "token",
    "password",
    "authorization",
    "alpaca_api_key",
    "alpaca_secret_key",
    "groq_api_key",
}


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure and return the application logger."""
    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler()
    handler.setFormatter(fmt)

    logger = logging.getLogger(APP_NAME)
    logger.setLevel(os.getenv("HRAMY_LOG_LEVEL", level).upper())
    logger.addHandler(handler)

    return logger


def safe_log(logger: logging.Logger, level: int, message: str, **kwargs) -> None:
    """
    Log a message while filtering any sensitive kwargs.
    Values for keys in SENSITIVE_NAMES are replaced with '***'.
    """
    safe_kwargs = {}
    for key, value in kwargs.items():
        if key.lower() in SENSITIVE_NAMES:
            safe_kwargs[key] = "***"
        else:
            safe_kwargs[key] = value
    logger.log(level, message, **safe_kwargs)


# Singleton logger
logger = setup_logging()