"""
§5.2 — pack lifecycle: Upload -> Dry-run -> Approve -> Activate -> Rollback.

This module implements Upload (parse + schema-validate + conflict-check).
Dry-run/Approve/Activate/Rollback are workflow states on top of a validated
manifest (persisted via the `packs` API router, §22) and are not re-derived
here — but every one of them starts by calling `load_pack_file` /
`load_pack_manifest`, so an invalid manifest can never enter the pipeline.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from core.packs.conflicts import InstalledPackState, PackConflictError, check_conflicts
from core.packs.manifest_schema import PackManifest
from core.packs.version import satisfies

ENGINE_VERSION = "1.0.0"


class PackLoadError(Exception):
    """Raised when a manifest fails to parse, validate, or is compat-incompatible."""


def load_pack_manifest(raw_yaml: str) -> PackManifest:
    try:
        data = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as exc:
        raise PackLoadError(f"invalid YAML: {exc}") from exc

    try:
        manifest = PackManifest.model_validate(data)
    except ValidationError as exc:
        raise PackLoadError(f"manifest schema validation failed:\n{exc}") from exc

    if not satisfies(ENGINE_VERSION, manifest.pack.engine_compat):
        raise PackLoadError(
            f"pack {manifest.pack.id!r} requires engine_compat "
            f"{manifest.pack.engine_compat!r}, running engine is {ENGINE_VERSION!r}"
        )

    return manifest


def load_pack_file(path: str | Path) -> PackManifest:
    return load_pack_manifest(Path(path).read_text(encoding="utf-8"))


def load_and_check(raw_yaml: str, installed: InstalledPackState) -> PackManifest:
    """Convenience: load + validate + conflict-check in one call, as `POST /v1/packs` would."""
    manifest = load_pack_manifest(raw_yaml)
    try:
        check_conflicts(manifest, installed)
    except PackConflictError:
        raise
    return manifest
