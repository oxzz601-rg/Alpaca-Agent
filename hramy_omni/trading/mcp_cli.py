"""Alpaca CLI / MCP-style call logger.

Every cycle records structured events. If the `alpaca` CLI is installed,
account/status commands are also executed so the project uses Alpaca CLI
as required by the hackathon (MCP server can be used in addition).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Any


class MCPLogAdapter:
    """Records CLI/MCP style calls for each cycle."""

    def __init__(self):
        self.events: list[dict] = []

    def log_call(self, call_name: str, payload: dict | None = None) -> dict:
        event = {
            "call_name": call_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload or {},
        }
        self.events.append(event)
        return event

    def cli_available(self) -> bool:
        return shutil.which("alpaca") is not None

    def run_cli(self, args: list[str], timeout: int = 30) -> dict[str, Any]:
        """Run `alpaca <args>`. Never logs secrets — only argv after the binary."""
        exe = shutil.which("alpaca")
        if not exe:
            result = {"ok": False, "reason": "alpaca_cli_not_installed", "args": args}
            self.log_call("alpaca_cli_missing", result)
            return result
        try:
            completed = subprocess.run(
                [exe, *args],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            result = {
                "ok": completed.returncode == 0,
                "args": args,
                "returncode": completed.returncode,
                "stdout": (completed.stdout or "")[-2000:],
                "stderr": (completed.stderr or "")[-500:],
            }
            self.log_call("alpaca_cli", {"args": args, "returncode": completed.returncode, "ok": result["ok"]})
            return result
        except Exception as exc:
            result = {"ok": False, "reason": type(exc).__name__, "args": args}
            self.log_call("alpaca_cli_error", result)
            return result

    def export(self) -> str:
        return json.dumps({"events": self.events}, indent=2)
