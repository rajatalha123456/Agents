"""§12.1 — read-only tools. None of these ever write anything."""
from __future__ import annotations

from core.agent.tools.registry import AGENT_TOOL_REGISTRY, Tool

READ_TOOL_NAMES = [
    "get_break_case",
    "get_record",
    "find_candidates",
    "get_match_rule_result",
    "get_balance",
    "get_ageing",
    "search_knowledge",
    "get_document_chunk",
    "find_precedent",
    "get_dimension_value",
    "get_counterparty",
]

_PURPOSES = {
    "get_break_case": "Case facts",
    "get_record": "One canonical record + raw payload",
    "find_candidates": "Filtered candidate search (capped, deterministic sort)",
    "get_match_rule_result": "What a matching rule concluded and why",
    "get_balance": "Account balance at a given date",
    "get_ageing": "Break ageing profile",
    "search_knowledge": "RAG search, tenant + effective-date filtered",
    "get_document_chunk": "The exact cited chunk",
    "find_precedent": "Approved past cases, ranked similarity",
    "get_dimension_value": "Dimension registry lookup",
    "get_counterparty": "Counterparty master data",
}


def register_read_tools() -> None:
    for name in READ_TOOL_NAMES:
        if name in AGENT_TOOL_REGISTRY:
            continue
        AGENT_TOOL_REGISTRY.register(
            Tool(name=name, purpose=_PURPOSES[name], write_scope=None)
        )


register_read_tools()
