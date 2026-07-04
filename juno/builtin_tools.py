"""Juno's first tools, drawn from the AGENT.md capabilities:
web lookups, reminders/tasks, and notes.

Each store is a small human-readable JSON file under data/ so you can
open, inspect, and fix anything by hand.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path

from .tools import ToolRegistry, obj_schema

FETCH_CHAR_LIMIT = 6000


# --------------------------------------------------------------------- store


class JsonList:
    """A tiny durable list-of-dicts store."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> list[dict]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text() or "[]")

    def save(self, items: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n")


# ----------------------------------------------------------------------- web


def web_search(query: str) -> str:
    import requests

    resp = requests.get(
        "https://api.duckduckgo.com/",
        params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    pieces = []
    if data.get("AbstractText"):
        pieces.append(f"{data['AbstractText']} (source: {data.get('AbstractURL', '?')})")
    if data.get("Answer"):
        pieces.append(str(data["Answer"]))
    for topic in data.get("RelatedTopics", [])[:5]:
        if isinstance(topic, dict) and topic.get("Text"):
            pieces.append(f"- {topic['Text']}")
    if not pieces:
        return (
            "No instant answer found. Try fetch_page on a specific URL, "
            "or tell the user you couldn't find it."
        )
    return "\n".join(pieces)


def fetch_page(url: str) -> str:
    import requests

    if not url.startswith(("http://", "https://")):
        raise ValueError("url must start with http:// or https://")
    resp = requests.get(url, timeout=15, headers={"User-Agent": "juno-assistant/0.1"})
    resp.raise_for_status()
    text = resp.text
    # Crude but dependable de-HTML: drop script/style, strip tags, squeeze space.
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > FETCH_CHAR_LIMIT:
        text = text[:FETCH_CHAR_LIMIT] + " …[truncated]"
    return text or "(the page had no readable text)"


# ------------------------------------------------------------ tasks & notes


class TaskStore:
    def __init__(self, data_dir: Path):
        self.store = JsonList(data_dir / "tasks.json")

    def add(self, text: str, due: str | None = None) -> str:
        items = self.store.load()
        if due:
            datetime.fromisoformat(due)  # validate early, fail loudly
        item = {
            "id": uuid.uuid4().hex[:8],
            "text": text,
            "due": due,
            "done": False,
            "created": datetime.now().isoformat(timespec="seconds"),
        }
        items.append(item)
        self.store.save(items)
        return f"Added task {item['id']}: {text}" + (f" (due {due})" if due else "")

    def list(self, include_done: bool = False) -> str:
        items = self.store.load()
        rows = [t for t in items if include_done or not t["done"]]
        if not rows:
            return "No open tasks."
        return "\n".join(
            f"[{t['id']}] {'x' if t['done'] else ' '} {t['text']}"
            + (f" (due {t['due']})" if t.get("due") else "")
            for t in rows
        )

    def complete(self, task_id: str) -> str:
        items = self.store.load()
        for t in items:
            if t["id"] == task_id:
                t["done"] = True
                self.store.save(items)
                return f"Marked done: {t['text']}"
        raise ValueError(f"No task with id {task_id}")

    def due_now(self) -> list[dict]:
        now = datetime.now()
        return [
            t
            for t in self.store.load()
            if not t["done"] and t.get("due") and datetime.fromisoformat(t["due"]) <= now
        ]


class NoteStore:
    def __init__(self, data_dir: Path):
        self.store = JsonList(data_dir / "notes.json")

    def save_note(self, text: str) -> str:
        items = self.store.load()
        item = {
            "id": uuid.uuid4().hex[:8],
            "text": text,
            "created": datetime.now().isoformat(timespec="seconds"),
        }
        items.append(item)
        self.store.save(items)
        return f"Saved note {item['id']}."

    def search(self, query: str) -> str:
        words = [w.lower() for w in query.split()]
        hits = [
            n
            for n in self.store.load()
            if any(w in n["text"].lower() for w in words)
        ]
        if not hits:
            return f"No notes matching '{query}'."
        return "\n".join(f"[{n['id']} {n['created']}] {n['text']}" for n in hits[:10])


# --------------------------------------------------------------- simulated send


class Outbox:
    """A stand-in for a real messaging integration. It exists so the
    confirmation gate has a consequential action to guard from day one;
    'sending' just appends to data/outbox.json."""

    def __init__(self, data_dir: Path):
        self.store = JsonList(data_dir / "outbox.json")

    def send(self, recipient: str, text: str) -> str:
        items = self.store.load()
        items.append(
            {
                "recipient": recipient,
                "text": text,
                "sent": datetime.now().isoformat(timespec="seconds"),
            }
        )
        self.store.save(items)
        return f"Message to {recipient} recorded in the outbox (simulated send)."


# ------------------------------------------------------------------ register


def register_builtin_tools(registry: ToolRegistry, data_dir: Path) -> TaskStore:
    """Wire the first capabilities into the registry. Returns the TaskStore
    so the heartbeat can watch due reminders."""
    tasks = TaskStore(data_dir)
    notes = NoteStore(data_dir)
    outbox = Outbox(data_dir)

    registry.add(
        "web_search",
        "Use this to look up current facts on the web — weather, news, quick "
        "answers. Give it a plain-language query.",
        obj_schema({"query": {"type": "string", "description": "what to search for"}}, ["query"]),
        web_search,
    )
    registry.add(
        "fetch_page",
        "Use this to read the text of a specific web page when you already "
        "know its URL.",
        obj_schema({"url": {"type": "string", "description": "full http(s) URL"}}, ["url"]),
        fetch_page,
    )
    registry.add(
        "add_reminder",
        "Use this to add a task or reminder to the user's list. Include a due "
        "time when the user gives one.",
        obj_schema(
            {
                "text": {"type": "string", "description": "what to remember to do"},
                "due": {
                    "type": "string",
                    "description": "optional due time, ISO format e.g. 2026-07-04T15:00",
                },
            },
            ["text"],
        ),
        tasks.add,
    )
    registry.add(
        "list_tasks",
        "Use this to see the user's open tasks and reminders, e.g. when asked "
        "'what's on my list?'.",
        obj_schema(
            {"include_done": {"type": "boolean", "description": "also show finished tasks"}},
            [],
        ),
        tasks.list,
    )
    registry.add(
        "complete_task",
        "Use this to mark a task done, by its id from list_tasks.",
        obj_schema({"task_id": {"type": "string"}}, ["task_id"]),
        tasks.complete,
    )
    registry.add(
        "save_note",
        "Use this to save a short note the user dictates or asks you to keep.",
        obj_schema({"text": {"type": "string"}}, ["text"]),
        notes.save_note,
    )
    registry.add(
        "search_notes",
        "Use this to find saved notes when the user asks about something they "
        "noted before.",
        obj_schema({"query": {"type": "string"}}, ["query"]),
        notes.search,
    )
    registry.add(
        "send_message",
        "Use this to send a message to someone on the user's behalf. This is "
        "a consequential action and always requires the user's confirmation.",
        obj_schema(
            {"recipient": {"type": "string"}, "text": {"type": "string"}},
            ["recipient", "text"],
        ),
        outbox.send,
        consequential=True,
        action_template='send a message to {recipient} saying: "{text}"',
    )
    return tasks
