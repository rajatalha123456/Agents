"""Phase 1 integration tests against a real PostgreSQL 16 instance
(docker compose up -d postgres). These are the acceptance tests required
by section 3.6: RLS isolation (including a raw query with no WHERE
clause), fingerprint mismatch detection, concurrent audit append, and
append-only enforcement at the database level.
"""
import asyncio
import os
import uuid

import pandas as pd
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from sampling.db.audit_trail_pg import PgAuditTrail
from sampling.db.models import Dataset, DatasetRow, Engagement, Tenant
from sampling.db.repositories import DatasetFingerprintMismatch, load_population
from sampling.db.session import SessionFactory, tenant_session
from sampling.determinism import dataset_fingerprint

ADMIN_URL = os.environ.get(
    "MIGRATIONS_DATABASE_URL_ASYNC",
    "postgresql+asyncpg://audit_admin:audit_admin_dev_password@localhost:55433/audit_sampling",
)

pytestmark = pytest.mark.asyncio

admin_engine = create_async_engine(ADMIN_URL)
AdminSessionFactory = async_sessionmaker(admin_engine, expire_on_commit=False)


async def _make_tenant_and_engagement(name: str) -> tuple[uuid.UUID, uuid.UUID]:
    async with AdminSessionFactory() as session:
        tenant = Tenant(name=name, slug=f"{name}-{uuid.uuid4().hex[:8]}")
        session.add(tenant)
        await session.flush()
        engagement = Engagement(tenant_id=tenant.id, name="E1", client_name="Client")
        session.add(engagement)
        await session.commit()
        return tenant.id, engagement.id


async def _make_dataset_with_rows(tenant_id: uuid.UUID, engagement_id: uuid.UUID, frame: pd.DataFrame) -> uuid.UUID:
    fp = dataset_fingerprint(frame, "item_id", "amount")
    # Unique per call (not a fixed "x"*64): every request now resolves to
    # the single fixed default tenant post auth-removal, so multiple
    # datasets created within one test run would otherwise collide on the
    # (tenant_id, file_sha256) uniqueness constraint.
    sha256 = uuid.uuid4().hex + uuid.uuid4().hex
    async with AdminSessionFactory() as session:
        dataset = Dataset(
            tenant_id=tenant_id, engagement_id=engagement_id, filename="test.csv",
            file_sha256=sha256, dataset_fingerprint=fp,
            row_count=len(frame), column_count=len(frame.columns),
        )
        session.add(dataset)
        await session.flush()
        for _, row in frame.iterrows():
            session.add(DatasetRow(
                tenant_id=tenant_id, dataset_id=dataset.id,
                item_id=row["item_id"], amount=float(row["amount"]), payload={},
            ))
        await session.commit()
        return dataset.id


@pytest.fixture(scope="module", autouse=True)
def _require_postgres():
    pass  # tests will fail loudly with a connection error if postgres is down


async def test_rls_isolation_across_tenants_via_orm():
    frame_a = pd.DataFrame({"item_id": ["a1", "a2"], "amount": [100.0, 200.0]})
    frame_b = pd.DataFrame({"item_id": ["b1", "b2"], "amount": [300.0, 400.0]})

    tenant_a, eng_a = await _make_tenant_and_engagement("tenant-a")
    tenant_b, eng_b = await _make_tenant_and_engagement("tenant-b")
    await _make_dataset_with_rows(tenant_a, eng_a, frame_a)
    await _make_dataset_with_rows(tenant_b, eng_b, frame_b)

    async with tenant_session(tenant_a) as session:
        result = await session.execute(text("SELECT item_id FROM dataset_rows"))
        item_ids = {r[0] for r in result}

    assert item_ids == {"a1", "a2"}
    assert "b1" not in item_ids and "b2" not in item_ids


async def test_rls_isolation_raw_select_star_no_where_clause():
    """Proves RLS -- not an application-level filter -- is doing the work:
    a raw SELECT * with no WHERE clause at all still only returns the
    connected tenant's rows.
    """
    frame_a = pd.DataFrame({"item_id": [f"raw-a-{i}" for i in range(3)], "amount": [1.0, 2.0, 3.0]})
    frame_b = pd.DataFrame({"item_id": [f"raw-b-{i}" for i in range(3)], "amount": [4.0, 5.0, 6.0]})

    tenant_a, eng_a = await _make_tenant_and_engagement("raw-tenant-a")
    tenant_b, eng_b = await _make_tenant_and_engagement("raw-tenant-b")
    await _make_dataset_with_rows(tenant_a, eng_a, frame_a)
    await _make_dataset_with_rows(tenant_b, eng_b, frame_b)

    async with tenant_session(tenant_a) as session:
        result = await session.execute(text("SELECT * FROM dataset_rows"))
        rows = result.fetchall()

    ids_seen = {r._mapping["item_id"] for r in rows}
    assert any(i.startswith("raw-a-") for i in ids_seen)
    assert not any(i.startswith("raw-b-") for i in ids_seen)


async def test_fingerprint_mismatch_detected_on_load():
    tenant_id, eng_id = await _make_tenant_and_engagement("fp-mismatch-tenant")
    frame = pd.DataFrame({"item_id": ["x1", "x2"], "amount": [10.0, 20.0]})
    dataset_id = await _make_dataset_with_rows(tenant_id, eng_id, frame)

    # Tamper with a stored row's amount directly, bypassing the app layer,
    # simulating data changing underneath a recorded fingerprint.
    async with AdminSessionFactory() as session:
        await session.execute(
            text("UPDATE dataset_rows SET amount = 999.99 WHERE tenant_id = :tid AND item_id = 'x1'"),
            {"tid": str(tenant_id)},
        )
        await session.commit()

    async with tenant_session(tenant_id) as session:
        with pytest.raises(DatasetFingerprintMismatch):
            await load_population(session, dataset_id)


async def test_concurrent_audit_appends_produce_gapless_verifiable_chain():
    tenant_id, _ = await _make_tenant_and_engagement("audit-concurrency-tenant")
    trail = PgAuditTrail(tenant_id)

    async def append_one(i: int):
        async with tenant_session(tenant_id) as session:
            await trail.append(session, actor="auditor", action="test.action", subject=f"s{i}", payload={"i": i})

    await asyncio.gather(*(append_one(i) for i in range(50)))

    async with tenant_session(tenant_id) as session:
        report = await trail.verify(session)
        events = await trail.events(session)

    assert report.valid is True
    assert report.events_checked == 50
    assert sorted(e.sequence for e in events) == list(range(50))


async def test_audit_events_update_rejected_by_permissions():
    tenant_id, _ = await _make_tenant_and_engagement("audit-permissions-tenant")
    trail = PgAuditTrail(tenant_id)

    async with tenant_session(tenant_id) as session:
        await trail.append(session, actor="auditor", action="test.action", subject="s0", payload={})

    with pytest.raises(DBAPIError):
        async with tenant_session(tenant_id) as session:
            await session.execute(
                text("UPDATE audit_events SET payload = '{}' WHERE tenant_id = :tid"),
                {"tid": str(tenant_id)},
            )


async def test_tampered_row_caught_by_verify_with_correct_sequence():
    tenant_id, _ = await _make_tenant_and_engagement("audit-tamper-tenant")
    trail = PgAuditTrail(tenant_id)

    for i in range(5):
        async with tenant_session(tenant_id) as session:
            await trail.append(session, actor="auditor", action="test.action", subject=f"s{i}", payload={"i": i})

    # Tamper as the superuser admin role, since app_role cannot UPDATE
    # audit_events -- this simulates an attacker with elevated DB access,
    # the threat model verify() exists to catch.
    async with AdminSessionFactory() as session:
        await session.execute(
            text("UPDATE audit_events SET payload = '{\"i\": 999}' WHERE tenant_id = :tid AND sequence = 2"),
            {"tid": str(tenant_id)},
        )
        await session.commit()

    async with tenant_session(tenant_id) as session:
        report = await trail.verify(session)

    assert report.valid is False
    assert report.first_invalid_sequence == 2
    assert report.reason == "content altered"
