"""Load config.toml and expose it with dotted-path access.

All tunables (model name, intervals, quiet hours, voice id, checks) live
in the config file so changing behavior is an edit there, never a code
change.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path("config.toml")


class Config:
    def __init__(self, data: dict[str, Any], base_dir: Path):
        self._data = data
        self.base_dir = base_dir

    @classmethod
    def load(cls, path: str | Path = DEFAULT_CONFIG_PATH) -> "Config":
        path = Path(path)
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return cls(data, base_dir=path.resolve().parent)

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self._data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    @property
    def data_dir(self) -> Path:
        d = self.base_dir / self.get("paths.data_dir", "data")
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def checks(self) -> list[dict[str, Any]]:
        return self._data.get("checks", [])
