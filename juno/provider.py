"""The provider seam: one small surface whose job is "send this
conversation, get back a reply (or a request to use tools)".

Nothing else in Juno touches the model SDK. Swapping providers, adding
retries, or logging costs happens here and only here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


class ProviderError(Exception):
    """A friendly, user-showable failure ("the model is unreachable"),
    never a raw stack trace."""


@dataclass
class TurnResult:
    """What one model call produced."""

    content: list[Any]          # assistant content blocks, passed back verbatim next call
    text: str                   # concatenated text for display/speech
    stop_reason: str | None
    tool_calls: list[Any] = field(default_factory=list)  # tool_use blocks, if any
    usage: dict[str, int] = field(default_factory=dict)


class Provider(Protocol):
    def stream_turn(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        on_text: Callable[[str], None] | None = None,
    ) -> TurnResult: ...


class AnthropicProvider:
    """Claude via the official SDK, streaming."""

    def __init__(self, model: str, max_tokens: int = 4096):
        import anthropic

        self._anthropic = anthropic
        self.client = anthropic.Anthropic()  # key from ANTHROPIC_API_KEY
        self.model = model
        self.max_tokens = max_tokens

    def stream_turn(self, system, messages, tools, on_text=None) -> TurnResult:
        anthropic = self._anthropic
        kwargs: dict[str, Any] = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=messages,
        )
        if tools:
            kwargs["tools"] = tools
        try:
            with self.client.messages.stream(**kwargs) as stream:
                for chunk in stream.text_stream:
                    if on_text:
                        on_text(chunk)
                msg = stream.get_final_message()
        except anthropic.AuthenticationError as e:
            raise ProviderError(
                "The model rejected my API key. Check ANTHROPIC_API_KEY."
            ) from e
        except anthropic.RateLimitError as e:
            raise ProviderError(
                "The model is rate-limiting us right now. Give it a moment and try again."
            ) from e
        except anthropic.APIStatusError as e:
            raise ProviderError(
                f"The model service returned an error ({e.status_code}). Try again shortly."
            ) from e
        except anthropic.APIConnectionError as e:
            raise ProviderError(
                "I couldn't reach the model — network trouble. Try again."
            ) from e

        text = "".join(b.text for b in msg.content if b.type == "text")
        tool_calls = [b for b in msg.content if b.type == "tool_use"]
        usage = {
            "input_tokens": msg.usage.input_tokens,
            "output_tokens": msg.usage.output_tokens,
        }
        # Pass the SDK block objects back verbatim in history — this keeps
        # thinking blocks intact, which the API requires.
        return TurnResult(
            content=list(msg.content),
            text=text,
            stop_reason=msg.stop_reason,
            tool_calls=tool_calls,
            usage=usage,
        )


def make_provider(config) -> Provider:
    return AnthropicProvider(
        model=config.get("model.name", "claude-opus-4-8"),
        max_tokens=config.get("model.max_tokens", 4096),
    )
