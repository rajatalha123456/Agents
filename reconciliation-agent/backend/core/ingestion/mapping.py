"""
§17.1 — mapping studio mechanism: turn one parser-format row into
canonical-field-named raw values, using a `mapping_template.field_map`
(canonical field -> source column name). This module only renames columns;
it does not parse dates/amounts/currencies — that's core/normalization's
job, applied afterwards by core/ingestion/quarantine.py. AI-assisted
mapping *suggestion* (§17.1 step 3) is a separate, LLM-backed concern that
produces a `field_map` for a human to confirm — this module is what runs
once that field_map exists, on every subsequent import.
"""
from __future__ import annotations

from core.ingestion.parsers.base import RawRow

# The canonical fields a mapping_template.field_map may target — mirrors
# the subset of canonical_record columns (§4.1) that come directly from a
# source row, rather than being derived (dimensions, fingerprint, ...) or
# assigned by the pipeline (tenant_id, run_id, connector_id, status).
CANONICAL_FIELDS = frozenset(
    {
        "external_ref",
        "posted_date",
        "value_date",
        "amount",
        "direction",
        "currency",
        "account_ref",
        "counterparty_raw",
        "reference_raw",
        "description_raw",
    }
)


def apply_mapping(raw_row: RawRow, field_map: dict[str, str]) -> dict[str, str]:
    """
    `field_map` is `{canonical_field: source_column_name}`. A canonical
    field the template doesn't map, or a source column missing from this
    particular row, both come back as `""` — normalization/quarantine
    (DAT-01, required field missing) is what turns that into a decision,
    not this function.
    """
    return {
        canonical_field: raw_row.fields.get(source_column, "")
        for canonical_field, source_column in field_map.items()
        if canonical_field in CANONICAL_FIELDS
    }
