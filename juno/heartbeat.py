"""The heartbeat: a background loop that lets Juno act without being
spoken to — and stay quiet unless something is genuinely worth saying.

Design rules baked in (see AGENT.md):
- checks and intervals live in config, not code
- next-due times persist to disk, so restarts don't refire everything
- a check still running when it comes due again is skipped, not stacked
- quiet hours: non-urgent notices are held silently for later
- background confirmations never block: they time out to "no" + a note
- one kill switch pauses everything without tearing anything down

Each check runs through the same agent core in a fresh, short-lived
conversation; the model decides whether the result is worth a notice via
the surface_notice tool.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, time as dtime, timedelta
from pathlib import Path
from typing import Callable

from .provider import ProviderError
from .tools import ToolRegistry, obj_schema

HEARTBEAT_NOTE = (
    "This is a scheduled background check, not the user speaking. "
    "The user is not available to answer questions. Be quiet by default: "
    "only call surface_notice if the finding genuinely warrants attention; "
    "otherwise do nothing and reply with the single word OK."
)


def parse_hhmm(s: str) -> dtime:
    h, m = s.split(":")
    return dtime(int(h), int(m))


def in_quiet_hours(now: dtime, start: dtime, end: dtime) -> bool:
    if start == end:
        return False
    if start < end:
        return start <= now < end
    return now >= start or now < end  # window crosses midnight


class Schedule:
    """Durable next-due bookkeeping (data/state/schedule.json)."""

    def __init__(self, data_dir: Path):
        self.path = data_dir / "state" / "schedule.json"
        self._due: dict[str, str] = {}
        if self.path.exists():
            self._due = json.loads(self.path.read_text() or "{}")

    def next_due(self, name: str) -> datetime | None:
        iso = self._due.get(name)
        return datetime.fromisoformat(iso) if iso else None

    def set_next_due(self, name: str, when: datetime) -> None:
        self._due[name] = when.isoformat(timespec="seconds")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._due, indent=2) + "\n")


class Heartbeat:
    def __init__(
        self,
        config,
        agent_factory: Callable[[ToolRegistry], object],
        notices,
        audit=None,
    ):
        """agent_factory builds a fresh Agent wired to a given registry —
        the same brain, a new short conversation per check."""
        self.config = config
        self.agent_factory = agent_factory
        self.notices = notices
        self.audit = audit
        self.schedule = Schedule(config.data_dir)
        self.pause_flag = config.data_dir / "state" / "paused"
        self._running: set[str] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------- controls

    @property
    def paused(self) -> bool:
        return self.pause_flag.exists()

    def pause(self) -> None:
        self.pause_flag.parent.mkdir(parents=True, exist_ok=True)
        self.pause_flag.write_text(datetime.now().isoformat())

    def resume(self) -> None:
        if self.pause_flag.exists():
            self.pause_flag.unlink()

    def start(self) -> None:
        if not self.config.get("heartbeat.enabled", True):
            return
        self._thread = threading.Thread(target=self._loop, daemon=True, name="heartbeat")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    # ----------------------------------------------------------------- loop

    def _loop(self) -> None:
        tick = self.config.get("heartbeat.tick_seconds", 30)
        while not self._stop.wait(timeout=tick):
            try:
                self.tick()
            except Exception as e:  # the heartbeat must never die quietly...
                self._audit("heartbeat_error", error=str(e))

    def tick(self, now: datetime | None = None) -> list[str]:
        """Run whatever is due. Returns names of checks that ran (for tests)."""
        if self.paused:
            return []
        now = now or datetime.now()
        ran = []
        for check in self.config.checks:
            name = check["name"]
            due = self.schedule.next_due(name)
            if due is None:
                # First sighting: schedule ahead instead of firing everything
                # at once on boot.
                self.schedule.set_next_due(
                    name, now + timedelta(minutes=check.get("every_minutes", 60))
                )
                continue
            if due > now:
                continue
            with self._lock:
                if name in self._running:
                    continue  # still working — skip, don't stack
                self._running.add(name)
            # Advance the schedule first so a crash can't cause a refire storm.
            self.schedule.set_next_due(
                name, now + timedelta(minutes=check.get("every_minutes", 60))
            )
            try:
                self.run_check(check, now)
                ran.append(name)
            finally:
                with self._lock:
                    self._running.discard(name)
        return ran

    def run_check(self, check: dict, now: datetime) -> None:
        registry = ToolRegistry()
        quiet = self._is_quiet(now.time())

        def surface_notice(title: str, body: str, urgent: bool = False) -> str:
            if quiet and not urgent:
                # Held silently; it's in the inbox for catch-up either way.
                result = self.notices.post(title, body, urgent=False)
                return result + " (quiet hours: held for later, not surfaced now)"
            return self.notices.post(title, body, urgent=urgent)

        registry.add(
            "surface_notice",
            "Use this only when a check finds something genuinely worth the "
            "user's attention. urgent=true reserves a real interruption for "
            "things that can't wait.",
            obj_schema(
                {
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "urgent": {"type": "boolean"},
                },
                ["title", "body"],
            ),
            surface_notice,
        )

        agent = self.agent_factory(registry)
        prompt = f"{HEARTBEAT_NOTE}\n\nCheck '{check['name']}': {check['prompt']}"
        try:
            agent.run_turn(prompt)
            self._audit("check_ran", check=check["name"])
        except ProviderError as e:
            self._audit("check_failed", check=check["name"], error=str(e))

    def _is_quiet(self, now: dtime) -> bool:
        start = self.config.get("heartbeat.quiet_start")
        end = self.config.get("heartbeat.quiet_end")
        if not start or not end:
            return False
        return in_quiet_hours(now, parse_hhmm(start), parse_hhmm(end))

    def _audit(self, event: str, **fields) -> None:
        if self.audit:
            self.audit.write(event, **fields)
