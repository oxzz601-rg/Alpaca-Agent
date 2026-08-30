"""Trading integration modules for Alpaca execution, options, and autonomous loop support."""

from .agent_loop import AutonomousAgentLoop
from .execution_loop import ExecutionLoop
from .mcp_cli import MCPLogAdapter
from .option_chain import OptionChainResolver
from .options import build_option_trade_plan
from .real_execution import AlpacaBroker, get_account_snapshot, normalize_account_snapshot
from .risk import OptionRiskGate

__all__ = [
    "AlpacaBroker",
    "AutonomousAgentLoop",
    "ExecutionLoop",
    "MCPLogAdapter",
    "OptionChainResolver",
    "OptionRiskGate",
    "build_option_trade_plan",
    "get_account_snapshot",
    "normalize_account_snapshot",
]
