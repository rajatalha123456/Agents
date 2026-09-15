"""
§12.2 — draft-only tools. Each writes to exactly one table, and that table
is always a DRAFT-status/append-only surface — never anything the agent
could use to affect a live financial record. `emit_event` publishes to an
outbound bus (EP-09); the bus itself is read-only from downstream's
perspective, the agent cannot use it to invoke anything back.
"""
from __future__ import annotations

from core.agent.tools.registry import AGENT_TOOL_REGISTRY, Tool

DRAFT_TABLES = {
    "proposal",
    "journal_draft",
    "evidence_item",
}

_DRAFT_TOOLS = [
    Tool(
        name="create_proposal",
        purpose="Create a DRAFT-status proposal row",
        write_scope="DRAFT",
        write_tables=("proposal",),
    ),
    Tool(
        name="create_journal_draft",
        purpose="Create a DRAFT-status internal journal draft",
        write_scope="DRAFT",
        write_tables=("journal_draft",),
    ),
    Tool(
        name="attach_evidence",
        purpose="Attach an evidence item to a proposal",
        write_scope="DRAFT",
        write_tables=("evidence_item",),
    ),
    Tool(
        name="emit_event",
        purpose="Publish to the outbound event bus (EP-09); downstream-read-only",
        write_scope="DRAFT",
        write_tables=(),
    ),
]


def register_draft_tools() -> None:
    for tool in _DRAFT_TOOLS:
        if tool.name in AGENT_TOOL_REGISTRY:
            continue
        AGENT_TOOL_REGISTRY.register(tool)


register_draft_tools()
