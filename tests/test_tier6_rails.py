"""Tier 6: the confirmation gate blocks consequential actions until an
explicit yes, background actions default to no-plus-a-note, and the
audit trail records what happened."""

import json

from conftest import FakeProvider, text_reply, tool_reply

from juno.agent import Agent
from juno.audit import AuditLog
from juno.builtin_tools import Outbox
from juno.gate import background_gate
from juno.notices import NoticeBoard
from juno.tools import ToolRegistry, obj_schema


def outbox_registry(config):
    registry = ToolRegistry()
    outbox = Outbox(config.data_dir)
    registry.add(
        "send_message",
        "send a message",
        obj_schema({"recipient": {"type": "string"}, "text": {"type": "string"}}, ["recipient", "text"]),
        outbox.send,
        consequential=True,
        action_template='send a message to {recipient} saying: "{text}"',
    )
    return registry, outbox


def test_gate_blocks_without_yes(config):
    registry, outbox = outbox_registry(config)
    asked = []

    def deny(action):
        asked.append(action)
        return False

    provider = FakeProvider(
        [tool_reply("send_message", {"recipient": "Sam", "text": "hi"}), text_reply("Skipped it.")]
    )
    agent = Agent(provider, config, registry=registry, confirm=deny)
    agent.run_turn("text Sam hi")
    assert asked == ['send a message to Sam saying: "hi"']  # states exactly what it would do
    assert outbox.store.load() == []  # nothing was sent
    result = provider.calls[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True and "NOT" in result["content"]


def test_gate_allows_with_yes(config):
    registry, outbox = outbox_registry(config)
    provider = FakeProvider(
        [tool_reply("send_message", {"recipient": "Sam", "text": "hi"}), text_reply("Sent.")]
    )
    agent = Agent(provider, config, registry=registry, confirm=lambda a: True)
    agent.run_turn("text Sam hi")
    assert len(outbox.store.load()) == 1


def test_no_gate_means_no_action(config):
    # If nothing can confirm (no gate wired), consequential tools never run.
    registry, outbox = outbox_registry(config)
    provider = FakeProvider(
        [tool_reply("send_message", {"recipient": "Sam", "text": "hi"}), text_reply("Skipped.")]
    )
    agent = Agent(provider, config, registry=registry, confirm=None)
    agent.run_turn("text Sam hi")
    assert outbox.store.load() == []


def test_background_gate_defaults_no_and_leaves_note(config):
    notices = NoticeBoard(config.data_dir)
    gate = background_gate(notices)
    assert gate("send a message to Sam") is False  # never blocks, never allows
    pending = notices.pending()
    assert len(pending) == 1
    assert "NOT performed" in pending[0]["body"]


def test_audit_records_tools_confirmations_and_cost(config):
    registry, _ = outbox_registry(config)
    audit = AuditLog(config.data_dir, input_per_mtok=5.0, output_per_mtok=25.0)
    provider = FakeProvider(
        [tool_reply("send_message", {"recipient": "Sam", "text": "hi"}), text_reply("Sent.")]
    )
    agent = Agent(provider, config, registry=registry, confirm=lambda a: True, audit=audit)
    agent.run_turn("text Sam hi")

    events = [json.loads(line)["event"] for line in audit.path.read_text().splitlines()]
    assert "confirmation" in events
    assert "tool_run" in events
    assert "model_usage" in events
    assert audit.session_cost > 0
    assert "$" in audit.cost_summary()


def test_config_drives_behavior_not_code(config):
    # Changing a threshold in config changes behavior with no code edit.
    assert config.get("heartbeat.tick_seconds") == 1
    assert config.checks[0]["every_minutes"] == 5
    assert config.get("assistant.name") == "Juno"
