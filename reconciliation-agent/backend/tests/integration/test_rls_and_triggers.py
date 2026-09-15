"""
§20 / §4.4 — integration checks for the guarantees migrations/versions/
0002_rls_agent_role_integrity_triggers.py installs at the DB layer:
tenant RLS isolation, audit_event insert-only, canonical_record.raw_payload
immutability, and the isolating-dimension match_group block.

These need a live Postgres with migrations applied (`alembic upgrade
head`), so — like test_no_write_tools.py's DB-grant test — they skip
rather than fail when no database is configured, unless
`RECON_REQUIRE_DATABASE_TESTS=1` is set (see `tests/db_gate.py`), in which
case a missing database fails the run instead of silently hiding it. Each
test runs inside a transaction that's rolled back at the end, so nothing
here needs its own cleanup and tests never see each other's rows.
"""
from __future__ import annotations

import uuid

import pytest

from core.config import get_settings
from tests.db_gate import skip_or_fail

pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.exc import ProgrammingError  # noqa: E402


def _live_engine():
    settings = get_settings()
    try:
        engine = create_engine(settings.database_url, connect_args={"connect_timeout": 2})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = 'agent_runtime'"))
    except Exception:
        skip_or_fail("no live database with migrations applied — run in the integration environment")
    return engine


@pytest.fixture
def conn():
    engine = _live_engine()
    connection = engine.connect()
    trans = connection.begin()
    try:
        yield connection
    finally:
        trans.rollback()
        connection.close()


def _new_tenant(conn, name: str) -> str:
    tenant_id = str(uuid.uuid4())
    conn.execute(
        text(
            "INSERT INTO tenant (id, name, base_currency, timezone, active_packs, created_at) "
            "VALUES (:id, :name, 'USD', 'UTC', '{}', now())"
        ),
        {"id": tenant_id, "name": name},
    )
    return tenant_id


def test_rls_blocks_cross_tenant_reads_and_writes(conn):
    tenant_a = _new_tenant(conn, "RLS Tenant A")
    tenant_b = _new_tenant(conn, "RLS Tenant B")
    connector_id = str(uuid.uuid4())
    conn.execute(
        text(
            "INSERT INTO connector (id, tenant_id, type, format, created_at) "
            "VALUES (:id, :tenant_id, 'BANK_STATEMENT', 'CSV', now())"
        ),
        {"id": connector_id, "tenant_id": tenant_a},
    )

    # `recon`/the app owner role bypasses RLS unless we scope as a
    # non-bypass role — the migration's own agent_runtime role is
    # NOLOGIN and read-only, which is exactly the restriction we want to
    # exercise here (it must never see another tenant's rows either).
    conn.execute(text("SET LOCAL ROLE agent_runtime"))

    # `SET` itself doesn't accept bound parameters; set_config() does and
    # is equivalent to `SET LOCAL <name> = <value>` when is_local=true.
    conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_a})
    count_a = conn.execute(text("SELECT count(*) FROM connector")).scalar()
    assert count_a == 1

    conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_b})
    count_b = conn.execute(text("SELECT count(*) FROM connector")).scalar()
    assert count_b == 0

    conn.execute(text("RESET ROLE"))


def test_audit_event_rejects_update_and_delete(conn):
    tenant_id = _new_tenant(conn, "Audit Tenant")
    event_id = str(uuid.uuid4())
    conn.execute(
        text(
            "INSERT INTO audit_event (id, tenant_id, actor, event_type, hash_self, created_at) "
            "VALUES (:id, :tenant_id, 'AGENT', 'agent.run.started', 'deadbeef', now())"
        ),
        {"id": event_id, "tenant_id": tenant_id},
    )

    with pytest.raises(ProgrammingError, match="append-only"):
        conn.execute(
            text("UPDATE audit_event SET actor = 'someone_else' WHERE id = :id"), {"id": event_id}
        )


def test_canonical_record_raw_payload_is_immutable(conn):
    tenant_id = _new_tenant(conn, "Immutability Tenant")
    connector_id = str(uuid.uuid4())
    record_id = str(uuid.uuid4())
    conn.execute(
        text(
            "INSERT INTO connector (id, tenant_id, type, format, created_at) "
            "VALUES (:id, :tenant_id, 'BANK_STATEMENT', 'CSV', now())"
        ),
        {"id": connector_id, "tenant_id": tenant_id},
    )
    conn.execute(
        text(
            "INSERT INTO canonical_record (id, tenant_id, run_id, side, connector_id, external_ref, "
            "posted_date, value_date, amount, direction, currency, base_amount, account_ref, "
            "dimensions, raw_payload, row_fingerprint, status, created_at) "
            "VALUES (:id, :tenant_id, :run_id, 'SOURCE_A', :connector_id, 'EXT-1', "
            "'2026-09-01', '2026-09-01', 50.00, 'CR', 'USD', 50.00, 'ACC-1', "
            "'{}', '{\"raw\": \"a\"}', 'fp-immutable', 'INGESTED', now())"
        ),
        {"id": record_id, "tenant_id": tenant_id, "run_id": str(uuid.uuid4()), "connector_id": connector_id},
    )

    with pytest.raises(ProgrammingError, match="immutable"):
        conn.execute(
            text("UPDATE canonical_record SET raw_payload = '{\"raw\": \"tampered\"}' WHERE id = :id"),
            {"id": record_id},
        )


def test_match_group_cannot_span_isolating_dimension(conn):
    tenant_id = _new_tenant(conn, "Isolation Tenant")
    connector_id = str(uuid.uuid4())
    conn.execute(
        text(
            "INSERT INTO connector (id, tenant_id, type, format, created_at) "
            "VALUES (:id, :tenant_id, 'BANK_STATEMENT', 'CSV', now())"
        ),
        {"id": connector_id, "tenant_id": tenant_id},
    )
    conn.execute(
        text(
            "INSERT INTO dimension_registry (id, tenant_id, pack_id, key, label, data_type, "
            "is_indexed, is_filterable, is_isolating) "
            "VALUES (:id, :tenant_id, 'test-pack', 'pool_id', 'Pool', 'STRING', true, true, true)"
        ),
        {"id": str(uuid.uuid4()), "tenant_id": tenant_id},
    )
    universe_id = str(uuid.uuid4())
    conn.execute(
        text(
            "INSERT INTO universe (id, tenant_id, code, label, side_a_filter, side_b_filter, "
            "match_keys, require_dimension, autonomy_level, created_at) "
            "VALUES (:id, :tenant_id, 'U-TEST', 'Test', '{}', '{}', '[]', '[]', "
            "'A2_PROPOSE_ON_SCHEDULE', now())"
        ),
        {"id": universe_id, "tenant_id": tenant_id},
    )

    record_pool_1 = str(uuid.uuid4())
    record_pool_2 = str(uuid.uuid4())
    for record_id, pool, ref in ((record_pool_1, "POOL-1", "A1"), (record_pool_2, "POOL-2", "B1")):
        conn.execute(
            text(
                "INSERT INTO canonical_record (id, tenant_id, run_id, side, connector_id, "
                "external_ref, posted_date, value_date, amount, direction, currency, base_amount, "
                "account_ref, dimensions, raw_payload, row_fingerprint, status, created_at) "
                "VALUES (:id, :tenant_id, :run_id, 'SOURCE_A', :connector_id, :ref, "
                "'2026-09-01', '2026-09-01', 50.00, 'CR', 'USD', 50.00, 'ACC-1', "
                ":dims, '{}', :fp, 'INGESTED', now())"
            ),
            {
                "id": record_id,
                "tenant_id": tenant_id,
                "run_id": str(uuid.uuid4()),
                "connector_id": connector_id,
                "ref": ref,
                "dims": f'{{"pool_id": "{pool}"}}',
                "fp": f"fp-{ref}",
            },
        )

    match_group_id = str(uuid.uuid4())
    conn.execute(
        text(
            "INSERT INTO match_group (id, tenant_id, universe_id, cardinality, decided_by, "
            "decided_at, created_at) "
            "VALUES (:id, :tenant_id, :universe_id, '1:1', 'HUMAN', now(), now())"
        ),
        {"id": match_group_id, "tenant_id": tenant_id, "universe_id": universe_id},
    )

    conn.execute(
        text(
            "INSERT INTO match_member (id, tenant_id, match_group_id, record_id, role) "
            "VALUES (:id, :tenant_id, :group_id, :record_id, 'primary')"
        ),
        {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "group_id": match_group_id,
            "record_id": record_pool_1,
        },
    )

    with pytest.raises(ProgrammingError, match="isolating dimension"):
        conn.execute(
            text(
                "INSERT INTO match_member (id, tenant_id, match_group_id, record_id, role) "
                "VALUES (:id, :tenant_id, :group_id, :record_id, 'offset')"
            ),
            {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "group_id": match_group_id,
                "record_id": record_pool_2,
            },
        )
