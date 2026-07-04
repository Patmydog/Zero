"""Tier 1: the text conversation loop remembers earlier turns and
survives provider failures without corrupting state."""

import pytest

from conftest import FakeProvider, text_reply

from juno.agent import Agent
from juno.provider import ProviderError


def test_reply_streams_and_returns_text(config):
    provider = FakeProvider([text_reply("Hello there.")])
    agent = Agent(provider, config)
    chunks = []
    out = agent.run_turn("hi", on_text=chunks.append)
    assert out == "Hello there."
    assert "".join(chunks) == "Hello there."


def test_history_carries_earlier_turns(config):
    provider = FakeProvider([text_reply("Nice to meet you, Alice."), text_reply("Alice.")])
    agent = Agent(provider, config)
    agent.run_turn("My name is Alice.")
    agent.run_turn("What's my name?")
    # The second request must include the whole earlier conversation.
    second_call = provider.calls[1]["messages"]
    assert second_call[0] == {"role": "user", "content": "My name is Alice."}
    assert len(second_call) == 3  # user, assistant, then the new user turn


def test_system_prompt_has_identity(config):
    provider = FakeProvider([text_reply("ok")])
    agent = Agent(provider, config)
    agent.run_turn("hi")
    system = provider.calls[0]["system"]
    assert "Juno" in system
    assert "brief" in system


def test_provider_failure_keeps_agent_alive(config):
    class FlakyProvider:
        def __init__(self):
            self.n = 0

        def stream_turn(self, system, messages, tools, on_text=None):
            self.n += 1
            if self.n == 1:
                raise ProviderError("network down")
            return text_reply("back online")

    agent = Agent(FlakyProvider(), config)
    with pytest.raises(ProviderError):
        agent.run_turn("hello?")
    # Next turn still works; no crash, no corrupted history.
    assert agent.run_turn("try again") == "back online"
