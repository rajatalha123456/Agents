"""DATASETS routes (section 6.1).

schema-suggest is gated by tenant.llm_enabled / data_residency_region per
section 6.3 -- 409 with an explanation, never a silent skip or fallback.
"""
from __future__ import annotations

import tempfile
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select

from ..auth.dependencies import CurrentUser, get_current_user, require_role
from ..db.audit_trail_pg import PgAuditTrail
from ..db.models import Dataset, DatasetRow, Tenant
from ..db.session import tenant_session
from ..db.storage import save_file
from ..jobs.worker import enqueue_ingest_dataset
from ..llm import LLMOrchestrator
from .llm_gate import DummyLLMClient, require_llm_enabled
from .pagination import Page, pagination_params
from .rate_limit import rate_limit

router = APIRouter(prefix="/api/v1/datasets", tags=["datasets"])


class DatasetOut(BaseModel):
    id: uuid.UUID
    filename: str
    ingestion_status: str
    row_count: int | None
    column_count: int | None
    dataset_fingerprint: str | None
    ingestion_warnings: list | None
    ingestion_error: str | None


def _to_out(d: Dataset) -> DatasetOut:
    return DatasetOut(
        id=d.id, filename=d.filename, ingestion_status=d.ingestion_status, row_count=d.row_count,
        column_count=d.column_count, dataset_fingerprint=d.dataset_fingerprint,
        ingestion_warnings=d.ingestion_warnings, ingestion_error=d.ingestion_error,
    )


@router.post("", response_model=DatasetOut, status_code=202,
             dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60))])
async def upload_dataset(
    engagement_id: uuid.UUID, file: UploadFile, user: CurrentUser = Depends(get_current_user),
) -> DatasetOut:
    with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.filename}") as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    tenant_id = uuid.UUID(user.tenant_id)
    storage_key = save_file(tenant_id, tmp_path, file.filename)

    async with tenant_session(tenant_id) as session:
        dataset = Dataset(tenant_id=tenant_id, engagement_id=engagement_id, filename=file.filename,
                           storage_key=storage_key, uploaded_by=uuid.UUID(user.user_id))
        session.add(dataset)
        await session.flush()
        trail = PgAuditTrail(user.tenant_id)
        await trail.append(session, actor=user.user_id, action="dataset.upload_queued",
                            subject=str(dataset.id), payload={"filename": file.filename})
        dataset_id = dataset.id
        result = _to_out(dataset)

    await enqueue_ingest_dataset(tenant_id, dataset_id, actor=user.user_id)
    return result


@router.get("", response_model=Page[DatasetOut])
async def list_datasets(user: CurrentUser = Depends(get_current_user),
                         pagination: tuple[int, int] = Depends(pagination_params)) -> Page[DatasetOut]:
    limit, offset = pagination
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        total = (await session.execute(select(func.count()).select_from(Dataset))).scalar_one()
        result = await session.execute(select(Dataset).order_by(Dataset.uploaded_at.desc()).limit(limit).offset(offset))
        rows = list(result.scalars())
    return Page(items=[_to_out(d) for d in rows], total=total, limit=limit, offset=offset)


@router.get("/{dataset_id}", response_model=DatasetOut)
async def get_dataset(dataset_id: uuid.UUID, user: CurrentUser = Depends(get_current_user)) -> DatasetOut:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        dataset = await session.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    return _to_out(dataset)


@router.get("/{dataset_id}/profile")
async def get_dataset_profile(dataset_id: uuid.UUID, user: CurrentUser = Depends(get_current_user)) -> dict:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        dataset = await session.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    return {"schema_profile": dataset.schema_profile, "warnings": dataset.ingestion_warnings}


@router.get("/{dataset_id}/preview", dependencies=[Depends(require_role("auditor"))])
async def preview_dataset(dataset_id: uuid.UUID, n: int = 20,
                           user: CurrentUser = Depends(get_current_user)) -> dict:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        result = await session.execute(
            select(DatasetRow).where(DatasetRow.dataset_id == dataset_id).order_by(DatasetRow.item_id).limit(n)
        )
        rows = list(result.scalars())
    return {
        "rows": [
            {"item_id": r.item_id, "amount": str(r.amount), **{k: v for k, v in r.payload.items()}}
            for r in rows
        ],
    }


@router.post("/{dataset_id}/schema-suggest",
             dependencies=[Depends(rate_limit(max_requests=5, window_seconds=60))])
async def suggest_schema(dataset_id: uuid.UUID, business_context: str = "",
                          user: CurrentUser = Depends(get_current_user)) -> dict:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        tenant = await session.get(Tenant, uuid.UUID(user.tenant_id))
        require_llm_enabled(tenant)

        dataset = await session.get(Dataset, dataset_id)
        if dataset is None:
            raise HTTPException(status_code=404, detail="dataset not found")

        orchestrator = LLMOrchestrator(DummyLLMClient(), model_identifier=tenant.llm_model or "stub",
                                        prompt_version="v1")
        understanding = orchestrator.understand_schema(dataset.schema_profile or {}, business_context)

    return {
        "column_roles": understanding.column_roles,
        "preprocessing_plan": understanding.preprocessing_plan,
        "leakage_candidates": understanding.leakage_candidates,
        "note": "suggestions only -- nothing here is applied until the user accepts each field",
    }


class ColumnMapping(BaseModel):
    item_id_col: str
    amount_col: str
    timestamp_col: str | None = None
    entity_col: str | None = None


@router.put("/{dataset_id}/column-mapping", response_model=DatasetOut,
            dependencies=[Depends(require_role("auditor"))])
async def confirm_column_mapping(dataset_id: uuid.UUID, mapping: ColumnMapping,
                                  user: CurrentUser = Depends(get_current_user)) -> DatasetOut:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        dataset = await session.get(Dataset, dataset_id)
        if dataset is None:
            raise HTTPException(status_code=404, detail="dataset not found")
        dataset.item_id_col = mapping.item_id_col
        dataset.amount_col = mapping.amount_col
        dataset.timestamp_col = mapping.timestamp_col
        dataset.entity_col = mapping.entity_col
        trail = PgAuditTrail(user.tenant_id)
        await trail.append(session, actor=user.user_id, action="dataset.column_mapping_confirmed",
                            subject=str(dataset_id), payload=mapping.model_dump())
        result = _to_out(dataset)
    return result


@router.delete("/{dataset_id}", status_code=204, dependencies=[Depends(require_role("admin"))])
async def delete_dataset(dataset_id: uuid.UUID, user: CurrentUser = Depends(get_current_user)) -> None:
    from sqlalchemy import delete as sa_delete
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        dataset = await session.get(Dataset, dataset_id)
        if dataset is None:
            raise HTTPException(status_code=404, detail="dataset not found")
        # No ON DELETE CASCADE on dataset_rows.dataset_id: rows are cleared
        # explicitly first so the FK doesn't block deleting the dataset.
        await session.execute(sa_delete(DatasetRow).where(DatasetRow.dataset_id == dataset_id))
        trail = PgAuditTrail(user.tenant_id)
        await trail.append(session, actor=user.user_id, action="dataset.deleted", subject=str(dataset_id), payload={})
        await session.delete(dataset)
