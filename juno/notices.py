"""The notice inbox: where proactive findings land.

Quiet by default — a notice is *held* here until the user sees and
dismisses it. Nothing is ever fire-and-forget: if the interface was
closed when a check found something, the notice waits (catch-up-on-
return, never deliver-once-and-lose-it).
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path


class NoticeBoard:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "notices.json"
        self._lock = threading.Lock()
        # Optional live hook: the CLI/voice loop can set this to be told
        # immediately when an urgent notice arrives.
        self.on_urgent = None

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text() or "[]")

    def _save(self, items: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n")

    def post(self, title: str, body: str, urgent: bool = False) -> str:
        with self._lock:
            items = self._load()
            notice = {
                "id": uuid.uuid4().hex[:8],
                "title": title,
                "body": body,
                "urgent": bool(urgent),
                "created": datetime.now().isoformat(timespec="seconds"),
                "dismissed": False,
            }
            items.append(notice)
            self._save(items)
        if notice["urgent"] and self.on_urgent:
            try:
                self.on_urgent(notice)
            except Exception:
                pass  # surfacing must never crash the loop
        return f"Notice posted ({notice['id']})."

    def pending(self) -> list[dict]:
        return [n for n in self._load() if not n["dismissed"]]

    def dismiss(self, notice_id: str) -> bool:
        with self._lock:
            items = self._load()
            for n in items:
                if n["id"] == notice_id and not n["dismissed"]:
                    n["dismissed"] = True
                    self._save(items)
                    return True
        return False

    def dismiss_all(self) -> int:
        with self._lock:
            items = self._load()
            count = 0
            for n in items:
                if not n["dismissed"]:
                    n["dismissed"] = True
                    count += 1
            self._save(items)
        return count
