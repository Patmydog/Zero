import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from juno.config import Config
from juno.provider import TurnResult


class FakeBlock:
    """Mimics an SDK content block (text or tool_use)."""

    def __init__(self, type, **kw):
        self.type = type
        for k, v in kw.items():
            setattr(self, k, v)


def text_reply(text):
    return TurnResult(
        content=[{"type": "text", "text": text}],
        text=text,
        stop_reason="end_turn",
        usage={"input_tokens": 10, "output_tokens": 5},
    )


def tool_reply(name, args, call_id="call_1"):
    block = FakeBlock("tool_use", name=name, input=args, id=call_id)
    return TurnResult(
        content=[block],
        text="",
        stop_reason="tool_use",
        tool_calls=[block],
        usage={"input_tokens": 10, "output_tokens": 5},
    )


class FakeProvider:
    """Plays back a script of TurnResults and records every request."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def stream_turn(self, system, messages, tools, on_text=None):
        self.calls.append({"system": system, "messages": [dict(m) for m in messages], "tools": tools})
        result = self.script.pop(0)
        if callable(result):
            result = result(messages)
        if on_text and result.text:
            on_text(result.text)
        return result


@pytest.fixture
def config(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        f"""
[assistant]
name = "Juno"
purpose = "test assistant"
persona = "brief"

[model]
name = "claude-opus-4-8"
max_tokens = 512

[paths]
data_dir = "data"

[heartbeat]
enabled = true
tick_seconds = 1
quiet_start = "22:00"
quiet_end = "08:00"

[[checks]]
name = "demo_check"
every_minutes = 5
prompt = "look at the thing"
"""
    )
    return Config.load(cfg)
