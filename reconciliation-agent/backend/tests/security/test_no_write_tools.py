"""
§13.1 (FR-021) — the architecture guardrail. This is the literal test from
the spec, adapted to the actual ToolRegistry API. It must run on every
build; a developer who accidentally adds a write-capable tool cannot merge
until this test (and the fixture in §12.3) are both updated deliberately.
"""
from __future__ import annotations

from core.agent.tools import AGENT_TOOL_REGISTRY, DRAFT_TABLES

# §12.3 — tools that must never exist. This list IS the test fixture the
# spec refers to, not just documentation.
FORBIDDEN_TOOL_NAMES = {
    "post_journal",
    "approve",
    "write_off",
    "release_payment",
    "delete_record",
    "update_record",
    "modify_tolerance",
    "change_autonomy",
    "install_pack",
    "close_period",
    "certify",
}

FORBIDDEN_VERB_FRAGMENTS = {
    "post",
    "write_off",
    "writeoff",
    "approve",
    "certify",
    "release",
    "pay",
    "delete",
    "drop",
    "truncate",
    "update_record",
    "modify",
    "override",
    "grant",
}

# A handful of registered tool names legitimately contain a substring that
# also appears in FORBIDDEN_VERB_FRAGMENTS as a false positive (there are
# none today) — kept explicit so a future addition can't silently widen
# this allowlist without a reviewer noticing.
ALLOWED_FALSE_POSITIVES: set[str] = set()


def test_agent_tool_registry_has_no_write_capability():
    tools = AGENT_TOOL_REGISTRY.all()
    assert tools, "tool registry is empty — read/draft tools failed to register"

    for tool in tools:
        assert tool.write_scope in (None, "DRAFT"), (
            f"{tool.name} has write scope {tool.write_scope!r}, "
            "only None (read-only) or 'DRAFT' are permitted"
        )
        if tool.name in ALLOWED_FALSE_POSITIVES:
            continue
        lowered = tool.name.lower()
        matched = [f for f in FORBIDDEN_VERB_FRAGMENTS if f in lowered]
        assert not matched, f"{tool.name} matches forbidden verb fragment(s): {matched}"


def test_forbidden_tools_are_not_registered():
    for name in FORBIDDEN_TOOL_NAMES:
        assert name not in AGENT_TOOL_REGISTRY, f"forbidden tool {name!r} is registered"


def test_draft_tools_only_write_to_draft_safe_tables():
    """
    A tool with write_scope='DRAFT' may only declare write_tables that are
    in DRAFT_TABLES — the whitelist of tables the agent's DB role is
    allowed to INSERT into (§12.2, mirrored by the DB grant in migrations).
    """
    for tool in AGENT_TOOL_REGISTRY.all():
        if tool.write_scope != "DRAFT":
            continue
        for table in tool.write_tables:
            assert table in DRAFT_TABLES, (
                f"{tool.name} declares write access to {table!r}, "
                f"which is not in the draft-safe table set {DRAFT_TABLES}"
            )


def test_agent_db_role_is_read_plus_draft_only():
    """
    §13.1's DB-grant half of the guardrail. This needs a live database with
    the `agent_runtime` role and grants applied (created by the P0
    migrations) — it's an integration check, not a unit check, so it's
    skipped when no DB is configured rather than silently passing.
    """
    import pytest

    from core.config import get_settings

    settings = get_settings()
    try:
        from sqlalchemy import create_engine, text
    except ImportError:
        pytest.skip("sqlalchemy not installed")

    from tests.db_gate import skip_or_fail

    try:
        engine = create_engine(settings.database_url, connect_args={"connect_timeout": 2})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        skip_or_fail("no live database configured — run this in the integration environment")
        return

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT table_name, privilege_type
                FROM information_schema.role_table_grants
                WHERE grantee = :role
                """
            ),
            {"role": settings.agent_db_role},
        ).fetchall()

    for table_name, privilege in rows:
        if privilege in ("INSERT", "UPDATE"):
            assert table_name in DRAFT_TABLES, (
                f"agent role has {privilege} on {table_name!r}, "
                f"which is outside the draft-safe table set {DRAFT_TABLES}"
            )
        assert privilege != "DELETE", f"agent role must never have DELETE (found on {table_name!r})"
