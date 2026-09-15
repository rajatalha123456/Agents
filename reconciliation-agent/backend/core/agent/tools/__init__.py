"""
Importing this package populates AGENT_TOOL_REGISTRY with exactly the read
(§12.1) and draft-only (§12.2) tools the agent is allowed to call. §12.3's
forbidden tools are never registered — see tests/security/test_no_write_tools.py.
"""
from core.agent.tools import draft_tools, read_tools  # noqa: F401
from core.agent.tools.registry import AGENT_TOOL_REGISTRY  # noqa: F401
from core.agent.tools.draft_tools import DRAFT_TABLES  # noqa: F401

__all__ = ["AGENT_TOOL_REGISTRY", "DRAFT_TABLES"]
