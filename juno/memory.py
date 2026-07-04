"""Long-term memory: small named facts that survive restarts.

The store is plain JSON (data/memory.json) so the user can open it,
correct a wrong fact, or delete anything by hand — memory you can't
inspect is memory you can't trust. Facts are loaded into the system
prompt as background data, never as instructions.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from .tools import ToolRegistry, obj_schema


class MemoryStore:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "memory.json"

    def all_facts(self) -> list[dict]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text() or "[]")

    def _save(self, facts: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(facts, indent=2, ensure_ascii=False) + "\n")

    def remember(self, fact: str) -> str:
        facts = self.all_facts()
        entry = {
            "id": uuid.uuid4().hex[:8],
            "fact": fact,
            "updated": datetime.now().isoformat(timespec="seconds"),
        }
        facts.append(entry)
        self._save(facts)
        return f"Remembered ({entry['id']}): {fact}"

    def update(self, fact_id: str, fact: str) -> str:
        facts = self.all_facts()
        for f in facts:
            if f["id"] == fact_id:
                f["fact"] = fact
                f["updated"] = datetime.now().isoformat(timespec="seconds")
                self._save(facts)
                return f"Updated {fact_id}."
        raise ValueError(f"No memory with id {fact_id}")

    def forget(self, fact_id: str) -> str:
        facts = self.all_facts()
        kept = [f for f in facts if f["id"] != fact_id]
        if len(kept) == len(facts):
            raise ValueError(f"No memory with id {fact_id}")
        self._save(kept)
        return f"Forgot {fact_id}."


def register_memory_tools(registry: ToolRegistry, memory: MemoryStore) -> None:
    registry.add(
        "remember_fact",
        "Use this to store one durable fact about the user or their world — "
        "a preference, an identity, a decision. One clear statement per call. "
        "Don't store passing conversation details.",
        obj_schema(
            {"fact": {"type": "string", "description": "one plain-statement fact"}},
            ["fact"],
        ),
        memory.remember,
    )
    registry.add(
        "update_fact",
        "Use this to correct a remembered fact that has gone stale. The ids "
        "are shown in your background memory section.",
        obj_schema(
            {"fact_id": {"type": "string"}, "fact": {"type": "string"}},
            ["fact_id", "fact"],
        ),
        memory.update,
    )
    registry.add(
        "forget_fact",
        "Use this to delete a remembered fact that is wrong or no longer wanted.",
        obj_schema({"fact_id": {"type": "string"}}, ["fact_id"]),
        memory.forget,
    )
