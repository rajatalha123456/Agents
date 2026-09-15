from __future__ import annotations

import enum

from sqlalchemy import Boolean, Enum, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TenantScoped, UUIDPk


class DimensionDataType(str, enum.Enum):
    STRING = "string"
    NUMBER = "number"
    DATE = "date"
    UUID = "uuid"


class DimensionRegistry(Base, UUIDPk, TenantScoped):
    """
    EP-01 — the mechanism side of dimensions. A pack (or the core pack)
    registers a key here; core never hardcodes what the key *means*.

    `is_isolating = True` is the load-bearing flag (§4.1): a match group can
    never span two records whose isolating-dimension values differ. Enforced
    as a DB constraint at match_group creation time, not just in application
    code — see migrations for the constraint/trigger.
    """

    __tablename__ = "dimension_registry"
    __table_args__ = (UniqueConstraint("tenant_id", "pack_id", "key"),)

    pack_id: Mapped[str] = mapped_column(String, nullable=False)
    key: Mapped[str] = mapped_column(String, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    data_type: Mapped[DimensionDataType] = mapped_column(
        Enum(DimensionDataType, name="dimension_data_type"), nullable=False
    )
    is_indexed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_filterable: Mapped[bool] = mapped_column(Boolean, default=False)
    is_isolating: Mapped[bool] = mapped_column(Boolean, default=False)
