"""Pagination convention (section 6.2): every list endpoint takes
?limit=&offset= and responds {items, total, limit, offset}.
"""
from __future__ import annotations

from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


def pagination_params(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)) -> tuple[int, int]:
    return limit, offset
