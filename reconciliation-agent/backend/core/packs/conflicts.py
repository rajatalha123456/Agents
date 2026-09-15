"""
§5.3 — pack conflict rules. These run at install/dry-run time, across the
already-installed pack set plus the candidate pack, before anything is
persisted.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.packs.manifest_schema import PackManifest


class PackConflictError(Exception):
    """Raised when installing `manifest` would violate a §5.3 conflict rule."""


@dataclass
class InstalledPackState:
    """A minimal view of what's already installed, enough to check conflicts against."""

    break_codes: set[str] = field(default_factory=set)
    dimension_keys: set[str] = field(default_factory=set)
    pack_ids: set[str] = field(default_factory=set)


CORE_PACK_ID = "core"


def check_conflicts(manifest: PackManifest, installed: InstalledPackState) -> None:
    """
    Raises PackConflictError on the first violation found. Checks, in order:

    1. Break code collision — two packs cannot define the same code.
    2. Dimension key collision — install fails outright (§5.3).
    3. The core pack can never be the *target* of this check (uninstall is
       handled separately — see `assert_not_uninstalling_core`).
    """
    new_codes = {bt.code for bt in manifest.break_types}
    clash = new_codes & installed.break_codes
    if clash:
        raise PackConflictError(
            f"pack {manifest.pack.id!r} defines break code(s) {sorted(clash)} "
            "already owned by another installed pack"
        )

    new_dims = {d.key for d in manifest.dimensions}
    dim_clash = new_dims & installed.dimension_keys
    if dim_clash:
        raise PackConflictError(
            f"pack {manifest.pack.id!r} defines dimension key(s) {sorted(dim_clash)} "
            "already registered by another installed pack"
        )


def assert_not_uninstalling_core(pack_id: str) -> None:
    """§5.3 — `core@1.x` is always installed and can never be uninstalled."""
    if pack_id == CORE_PACK_ID:
        raise PackConflictError("the core pack cannot be uninstalled")


def resolve_allow_auto_match(routing_flags: list[bool]) -> bool:
    """
    §5.3 — `allow_auto_match: false` always wins, no matter how many other
    routing rules say true. This is restriction-over-permission, applied
    across every rule that matches a given break/case, from every pack.
    """
    return all(routing_flags) if routing_flags else True
