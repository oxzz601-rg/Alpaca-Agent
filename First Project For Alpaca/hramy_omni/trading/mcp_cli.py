"""A minimal MCP/CLI logging adapter for the live Alpaca judge loop."""

from __future__ import annotations

import json
from datetime import datetime, timezone


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

    def export(self) -> str:
        return json.dumps({"events": self.events}, indent=2)
