"""The tool registry: the one thing we extend forever.

A tool is a named capability with a reader-friendly description, typed
inputs, and a flag saying whether it may run on its own (`consequential`
tools stop at the confirmation gate). Adding a capability means writing
one self-contained tool and registering it — never editing the agent loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Any]
    # True = sends/spends/deletes/changes something → confirmation gate.
    consequential: bool = False
    # Optional template for the gate prompt, e.g. "send a message saying {text}".
    action_template: str | None = None

    def run(self, **kwargs) -> Any:
        return self.handler(**kwargs)

    def describe_action(self, args: dict[str, Any]) -> str:
        if self.action_template:
            try:
                return self.action_template.format(**args)
            except (KeyError, IndexError):
                pass
        return f"run tool '{self.name}' with {args}"

    def spec(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def add(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        handler: Callable[..., Any],
        consequential: bool = False,
        action_template: str | None = None,
    ) -> Tool:
        tool = Tool(name, description, input_schema, handler, consequential, action_template)
        self.register(tool)
        return tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def specs(self) -> list[dict[str, Any]]:
        return [t.spec() for t in self._tools.values()]

    def __len__(self) -> int:
        return len(self._tools)


def obj_schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    """Shorthand for the JSON schema every tool input uses."""
    return {"type": "object", "properties": properties, "required": required}
