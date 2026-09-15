"""Phase 4 acceptance (section 6.5): OpenAPI generates cleanly, errors are
RFC 7807 problem details, list endpoints paginate as {items,total,limit,
offset}, and rate limiting returns 429 with Retry-After.
"""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from sampling.api import app
from tests.test_db_phase1 import _make_tenant_and_engagement

pytestmark = pytest.mark.asyncio


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_openapi_schema_generates_cleanly():
    schema = app.openapi()
    assert schema["openapi"]
    assert len(schema["paths"]) > 40
    for path, methods in schema["paths"].items():
        for method, op in methods.items():
            if method in ("get", "post", "put", "patch", "delete"):
                assert "responses" in op, f"{method.upper()} {path} has no responses documented"


async def test_404_error_is_rfc7807_problem_details():
    tenant_id, eng_id = await _make_tenant_and_engagement("problem-details-tenant")
    async with _client() as client:
        resp = await client.get(f"/api/v1/engagements/{uuid.uuid4()}")
    assert resp.status_code == 404
    body = resp.json()
    for key in ("type", "title", "status", "detail", "instance"):
        assert key in body, f"missing RFC7807 field: {key}"
    assert body["status"] == 404


async def test_list_endpoint_paginates_as_items_total_limit_offset():
    tenant_id, eng_id = await _make_tenant_and_engagement("pagination-tenant")
    async with _client() as client:
        for i in range(3):
            resp = await client.post(
                "/api/v1/engagements",
                json={"name": f"Engagement {i}", "client_name": "Client"},
            )
            assert resp.status_code == 200, resp.text

        resp = await client.get("/api/v1/engagements?limit=2&offset=0")
    assert resp.status_code == 200
    body = resp.json()
    for key in ("items", "total", "limit", "offset"):
        assert key in body
    assert body["limit"] == 2
    assert len(body["items"]) <= 2
    assert body["total"] >= 3


async def test_rate_limit_returns_429_with_retry_after(monkeypatch):
    from sampling.api_v1 import rate_limit as rate_limit_module
    tenant_id, eng_id = await _make_tenant_and_engagement("ratelimit-tenant")

    async with _client() as client:
        statuses = []
        for _ in range(8):
            resp = await client.post(f"/api/v1/datasets/{uuid.uuid4()}/schema-suggest")
            statuses.append(resp.status_code)

    assert 429 in statuses
    idx = statuses.index(429)
    async with _client() as client:
        resp = await client.post(f"/api/v1/datasets/{uuid.uuid4()}/schema-suggest")
    if resp.status_code == 429:
        assert "Retry-After" in resp.headers
