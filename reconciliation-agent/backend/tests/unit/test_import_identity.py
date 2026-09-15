from uuid import UUID

import pytest

from core.ingestion.idempotency import import_identity


def identity(**overrides):
    values = dict(tenant_id=UUID(int=1), connector_id=UUID(int=2), raw_bytes=b"statement", period="2026-09")
    values.update(overrides)
    return import_identity(**values)


def test_retry_has_same_identity():
    assert identity() == identity()


@pytest.mark.parametrize("override", [dict(tenant_id=UUID(int=3)), dict(connector_id=UUID(int=3)), dict(raw_bytes=b"changed"), dict(period="2026-10")])
def test_import_scope_changes_key(override):
    assert identity()[1] != identity(**override)[1]


@pytest.mark.parametrize("period", ["", " 2026-09", "2026-09 "])
def test_noncanonical_period_rejected(period):
    with pytest.raises(ValueError):
        identity(period=period)
