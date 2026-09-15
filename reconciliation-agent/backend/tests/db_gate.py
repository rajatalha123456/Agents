"""
Shared gate for the handful of tests that need a live, migrated Postgres
(RLS/trigger checks, the agent DB-role grant scan). By default they skip
when no database is reachable, since most contributors won't have one
running. Setting `RECON_REQUIRE_DATABASE_TESTS=1` (as `scripts/Test-Database.ps1`
does) turns that skip into a hard failure — for CI/verification runs where
a database was supposed to be there and a skip would silently hide a
regression instead of catching one.
"""
from __future__ import annotations

import os

import pytest


def skip_or_fail(reason: str) -> None:
    if os.environ.get("RECON_REQUIRE_DATABASE_TESTS"):
        pytest.fail(f"{reason} (RECON_REQUIRE_DATABASE_TESTS=1: skip is not allowed)")
    pytest.skip(reason)
