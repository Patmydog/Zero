"""Tier 4: durable memory survives 'restarts' (new objects over the same
files), lands in the system prompt as data, and respects hand edits."""

import json

from conftest import FakeProvider, text_reply, tool_reply

from juno.agent import Agent
from juno.memory import MemoryStore, register_memory_tools
from juno.tools import ToolRegistry


def test_facts_survive_restart(config):
    m1 = MemoryStore(config.data_dir)
    m1.remember("The user prefers morning meetings.")
    # "Restart": a brand-new store over the same file.
    m2 = MemoryStore(config.data_dir)
    facts = m2.all_facts()
    assert len(facts) == 1
    assert facts[0]["fact"] == "The user prefers morning meetings."


def test_facts_loaded_into_system_prompt(config):
    memory = MemoryStore(config.data_dir)
    memory.remember("The user's name is Alice.")
    provider = FakeProvider([text_reply("Hi Alice!")])
    agent = Agent(provider, config, memory=memory)
    agent.run_turn("hello")
    system = provider.calls[0]["system"]
    assert "The user's name is Alice." in system
    assert "not instructions" in system  # memory is data, never commands


def test_agent_can_record_a_fact_via_tool(config):
    memory = MemoryStore(config.data_dir)
    registry = ToolRegistry()
    register_memory_tools(registry, memory)
    provider = FakeProvider(
        [tool_reply("remember_fact", {"fact": "The user prefers tea."}), text_reply("Noted!")]
    )
    agent = Agent(provider, config, registry=registry, memory=memory)
    agent.run_turn("remember that I prefer tea")
    assert any(f["fact"] == "The user prefers tea." for f in memory.all_facts())


def test_update_and_forget(config):
    memory = MemoryStore(config.data_dir)
    memory.remember("wrong fact")
    fid = memory.all_facts()[0]["id"]
    memory.update(fid, "right fact")
    assert memory.all_facts()[0]["fact"] == "right fact"
    memory.forget(fid)
    assert memory.all_facts() == []


def test_hand_edit_is_respected(config):
    memory = MemoryStore(config.data_dir)
    memory.remember("The user lives in Paris.")
    # The user opens the plain JSON file and fixes it by hand.
    facts = json.loads(memory.path.read_text())
    facts[0]["fact"] = "The user lives in Lyon."
    memory.path.write_text(json.dumps(facts))
    assert memory.all_facts()[0]["fact"] == "The user lives in Lyon."
