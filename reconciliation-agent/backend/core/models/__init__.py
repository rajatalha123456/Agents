"""
Import every model module so `Base.metadata` is fully populated for Alembic
autogenerate and for anything that needs the whole schema (e.g. the RLS
migration, which iterates all tenant-scoped tables).
"""
from core.models.base import Base  # noqa: F401
from core.models import (  # noqa: F401
    agent_run,
    audit,
    break_case,
    break_type,
    canonical_record,
    close,
    connector,
    dimension_registry,
    external_action,
    journal,
    knowledge,
    match,
    proposal,
    routing,
    tenant,
    tolerance,
    universe,
)

__all__ = ["Base"]
