"""Tier 2: the model can call tools, chain them, and recover from
tool failures without crashing the loop."""

from conftest import FakeProvider, text_reply, tool_reply

from juno.agent import Agent
from juno.builtin_tools import TaskStore, register_builtin_tools
from juno.tools import ToolRegistry, obj_schema


def make_agent(config, script, registry):
    provider = FakeProvider(script)
    return Agent(provider, config, registry=registry), provider


def test_tool_call_result_flows_back(config):
    registry = ToolRegistry()
    registry.add("get_time", "current time", obj_schema({}, []), lambda: "12:00")
    agent, provider = make_agent(
        config,
        [tool_reply("get_time", {}), text_reply("It's noon.")],
        registry,
    )
    assert agent.run_turn("what time is it?") == "It's noon."
    # The tool result was fed back to the model on the second call.
    followup = provider.calls[1]["messages"][-1]
    assert followup["role"] == "user"
    assert followup["content"][0]["type"] == "tool_result"
    assert followup["content"][0]["content"] == "12:00"


def test_multiple_tool_rounds(config):
    registry = ToolRegistry()
    registry.add("a", "step a", obj_schema({}, []), lambda: "A-done")
    registry.add("b", "step b", obj_schema({}, []), lambda: "B-done")
    agent, _ = make_agent(
        config,
        [tool_reply("a", {}, "c1"), tool_reply("b", {}, "c2"), text_reply("both done")],
        registry,
    )
    assert agent.run_turn("do a then b") == "both done"


def test_tool_failure_returns_error_to_model(config):
    def boom():
        raise RuntimeError("the file is missing")

    registry = ToolRegistry()
    registry.add("boom", "fails", obj_schema({}, []), boom)
    agent, provider = make_agent(
        config,
        [tool_reply("boom", {}), text_reply("Sorry, that failed.")],
        registry,
    )
    # No crash: the error goes back to the model as data.
    assert agent.run_turn("try it") == "Sorry, that failed."
    result = provider.calls[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True
    assert "the file is missing" in result["content"]


def test_unknown_tool_is_reported_not_fatal(config):
    registry = ToolRegistry()
    agent, _ = make_agent(
        config,
        [tool_reply("nope", {}), text_reply("recovered")],
        registry,
    )
    assert agent.run_turn("hi") == "recovered"


def test_task_store_roundtrip(config):
    tasks = TaskStore(config.data_dir)
    tasks.add("buy milk")
    msg = tasks.add("call mom", due="2020-01-01T09:00")
    assert "call mom" in msg
    listing = tasks.list()
    assert "buy milk" in listing and "call mom" in listing
    assert len(tasks.due_now()) == 1  # 2020 is long past due
    task_id = tasks.due_now()[0]["id"]
    tasks.complete(task_id)
    assert "call mom" not in tasks.list()


def test_builtin_registration(config):
    registry = ToolRegistry()
    register_builtin_tools(registry, config.data_dir)
    names = {s["name"] for s in registry.specs()}
    assert {"web_search", "fetch_page", "add_reminder", "list_tasks", "send_message"} <= names
    # send_message is on the never-without-asking list.
    assert registry.get("send_message").consequential is True
    assert registry.get("list_tasks").consequential is False
