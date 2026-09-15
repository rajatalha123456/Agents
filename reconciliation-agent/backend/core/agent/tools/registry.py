"""
§12 — the tool registry. This is the entire set of capabilities the agent
runtime can invoke. §12.3's forbidden list is enforced as a test fixture
(tests/security/test_no_write_tools.py), not just documentation — adding a
write-capable tool here without updating that test is what the guardrail
suite exists to catch.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

WriteScope = Literal[None, "DRAFT"]


@dataclass(frozen=True)
class Tool:
    name: str
    purpose: str
    write_scope: WriteScope  # None = read-only. "DRAFT" = writes only to a *_draft-safe table.
    write_tables: tuple[str, ...] = ()  # which tables this tool may INSERT into, if any
    handler: Callable | None = None


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool {tool.name!r} already registered")
        self._tools[tool.name] = tool

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._tools


AGENT_TOOL_REGISTRY = ToolRegistry()
