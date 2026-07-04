"""A visible audit trail: what Juno did and why, plus a running model
cost tally so a runaway loop is visible immediately.

Plain JSONL at data/audit.jsonl — grep it, tail it, trust it.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path


class AuditLog:
    def __init__(self, data_dir: Path, input_per_mtok: float = 0.0, output_per_mtok: float = 0.0):
        self.path = data_dir / "audit.jsonl"
        self.input_per_mtok = input_per_mtok
        self.output_per_mtok = output_per_mtok
        self._lock = threading.Lock()
        self.session_cost = 0.0
        self.session_tokens = {"input": 0, "output": 0}

    def write(self, event: str, **fields) -> None:
        entry = {"ts": datetime.now().isoformat(timespec="seconds"), "event": event, **fields}
        line = json.dumps(entry, ensure_ascii=False, default=str)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a") as f:
                f.write(line + "\n")

    def record_usage(self, usage: dict) -> None:
        cost = (
            usage.get("input_tokens", 0) * self.input_per_mtok
            + usage.get("output_tokens", 0) * self.output_per_mtok
        ) / 1_000_000
        with self._lock:
            self.session_cost += cost
            self.session_tokens["input"] += usage.get("input_tokens", 0)
            self.session_tokens["output"] += usage.get("output_tokens", 0)
        self.write("model_usage", **usage, cost_usd=round(cost, 6))

    def cost_summary(self) -> str:
        return (
            f"This session: {self.session_tokens['input']} in / "
            f"{self.session_tokens['output']} out tokens, "
            f"≈ ${self.session_cost:.4f}"
        )
