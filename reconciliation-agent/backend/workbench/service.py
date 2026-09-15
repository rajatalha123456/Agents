"""Local evaluation flows using real parser, normalization and matching services.

Local actors are simulation identities, never production authentication.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from collections import defaultdict
from dataclasses import asdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from core.audit.chain import compute_event_hash
from core.agent.llm.narrative import BreakNarrativeContext, draft_narrative, get_configured_provider
from core.config import GroupMatchGuardrails, get_settings
from core.ingestion.control_totals import ControlRow, validate_control_totals
from core.ingestion.idempotency import import_identity
from core.ingestion.parsers.bai2_parser import parse_bai2
from core.ingestion.parsers.camt053_parser import parse_camt053
from core.ingestion.parsers.csv_parser import parse_csv
from core.ingestion.parsers.excel_parser import parse_excel
from core.ingestion.parsers.mt940_parser import parse_mt940
from core.breaks.classification import BreakTypeInfo, BreakTypeRegistry
from core.close.reconciliation import AccountReconciliationFacts, compute_unexplained
from core.breaks.lifecycle import IllegalTransition, TransitionRequest, transition
from core.breaks.rollforward import roll_forward
from core.matching.exact import MatchRecord, exact_pairs
from core.matching.grouping import CandidateExplosion, find_group_matches
from core.matching.tolerance import ToleranceRule, tolerance_pairs
from core.models.break_case import BreakCaseStatus as S
from core.models.canonical_record import Direction
from core.normalization.fingerprint import compute_row_fingerprint
from core.normalization.rules import normalize_currency, normalize_date, normalize_description, normalize_reference
from core.packs.loader import load_pack_file
from core.workflow.maker_checker import ApprovalRequest, MakerCheckerViolation, authorize_approval
from core.workflow.routing import RoutingRuleFacts, resolve_routing
from workbench import mock_data

_CORE_PACK_PATH = Path(__file__).resolve().parents[1] / "packs" / "core" / "manifest.yaml"

# §18.1 role code -> the simulation role label already used across the UI
# (Settings/App.tsx actor selector), so a routing decision reads naturally
# without inventing a second vocabulary for the same three roles.
_ROLE_DISPLAY_NAMES = {"CHECKER": "Reviewer", "CERTIFIER": "Controller", "MAKER": "Analyst"}


def _load_routing_rules() -> list[RoutingRuleFacts]:
    manifest = load_pack_file(_CORE_PACK_PATH)
    return [
        RoutingRuleFacts(
            break_family=rule.when.family,
            amount_band={"gte": rule.when.amount_gte} if rule.when.amount_gte is not None else None,
            dimension_filter=None,
            required_role=rule.require_role,
            escalation_role=rule.escalate_to,
            allow_auto_match=rule.allow_auto_match,
        )
        for rule in manifest.routing
    ]


_ROUTING_RULES = _load_routing_rules()


def _load_break_type_registry() -> BreakTypeRegistry:
    manifest = load_pack_file(_CORE_PACK_PATH)
    return BreakTypeRegistry([
        BreakTypeInfo(code=bt.code, family=bt.family, risk_weight=bt.risk_weight, is_sensitive=bt.is_sensitive)
        for bt in manifest.break_types
    ])


_BREAK_TYPE_REGISTRY = _load_break_type_registry()


def _risk_label(code: str) -> str:
    # §10's risk_weight is a registry field (1-8), not a per-code special
    # case to hardcode here — any future code the pack adds gets a sensible
    # bucket automatically. Thresholds mirror the "High"/AMT-02·DUP-01 vs
    # "Medium"/TIM-01 split this replaced (weight 6 vs weight 2).
    weight = _BREAK_TYPE_REGISTRY.risk_weight(code)
    if weight >= 6:
        return "High"
    if weight >= 3:
        return "Medium"
    return "Low"


def _chain(start, *targets, reason=None):
    """Apply a sequence of lifecycle transitions atomically (all-or-nothing
    from the caller's point of view — this function only returns once every
    step in the chain is legal). Several of the plan's §4.3 states collapse
    into a single human action here (e.g. a checker's one "approve" click is
    UNDER_REVIEW -> APPROVED -> ACTION_PENDING) — the intermediate states are
    still real and validated, just not separately gated by a second click.
    `reason` is forwarded to every hop; only the REOPENED transition actually
    requires it (§4.3), so it's a no-op for every other target.
    """
    current = start
    for target in targets:
        current = transition(TransitionRequest(case_status=current, target=target, reason=reason))
    return current


def _age_days(created_at: str) -> int:
    return (datetime.now(timezone.utc) - datetime.fromisoformat(created_at)).days


def _next_period(period: str) -> str:
    year, month = (int(p) for p in period.split("-"))
    month, year = (1, year + 1) if month == 12 else (month + 1, year)
    return f"{year:04d}-{month:02d}"

TENANT = str(UUID(int=1))
ACTORS = {"analyst": "MAKER", "reviewer": "CHECKER", "controller": "CERTIFIER"}

# §8.1 L2 — same account/currency/direction/reference as L1, but the value
# date may drift within a short window (typical clearing delay) with the
# amount held exact. Anything wider than this belongs to a human, not an
# auto-applied tolerance.
TIMING_TOLERANCE_RULES = [
    ToleranceRule(field="value_date", type="day_window", value=2),
    ToleranceRule(field="amount", type="absolute_or_percent", absolute=Decimal("0")),
]

# §8.3 — kept tight for a local, synchronous run: a handful of candidates
# and a short wall-clock budget per (account, currency) block, not the
# production defaults meant for a scheduled batch job.
GROUP_MATCH_GUARDRAILS = GroupMatchGuardrails(max_group_size=4, max_candidate_pool_per_group=40, time_budget_ms_per_group=200)
GROUP_MATCH_NET_TOLERANCE = Decimal("0.01")

# §6.1 — every source format this local backend can actually parse. Each
# format's parser emits its own native field names (§6: "column *meaning*
# is a mapping-studio concern"), so the default map below is a starting
# point the caller can override with `field_map`, exactly like the CSV path
# already allowed — not a claim that every bank's dialect matches it.
_PARSERS = {"CSV": parse_csv, "MT940": parse_mt940, "CAMT053": parse_camt053, "EXCEL": parse_excel, "BAI2": parse_bai2}
_CANONICAL_FIELDS = ("amount", "currency", "direction", "value_date", "reference", "description")
_DEFAULT_FIELD_MAPS = {
    "CSV": {k: k for k in _CANONICAL_FIELDS},
    "EXCEL": {k: k for k in _CANONICAL_FIELDS},
    "MT940": {"amount": "amount", "currency": "currency", "direction": "direction",
              "value_date": "value_date", "reference": "customer_reference", "description": "narrative"},
    "CAMT053": {"amount": "amount", "currency": "currency", "direction": "direction",
                "value_date": "value_date", "reference": "end_to_end_id", "description": "narrative"},
    "BAI2": {"amount": "amount", "currency": "currency", "direction": "direction",
             "value_date": "value_date", "reference": "customer_reference", "description": "narrative"},
}


def now():
    return datetime.now(timezone.utc).isoformat()


def audit(state, actor, event_type, after, before=None):
    event = dict(tenant_id=TENANT, actor=actor, event_type=event_type, before=before,
                 after=after, correlation_id=str(uuid4()), created_at=datetime.now(timezone.utc),
                 hash_prev=state["audit"][-1]["hash_self"] if state["audit"] else None)
    event["hash_self"] = compute_event_hash(**event)
    event["created_at"] = event["created_at"].isoformat()
    state["audit"].append(event)


def require_role(actor, role):
    if ACTORS.get(actor) != role:
        raise PermissionError(f"This action requires the {role.lower()} simulation role.")


def ensure_open(state, period):
    if state["periods"].get(period, {}).get("status") == "CERTIFIED":
        raise ValueError("This period is certified and locked.")


def import_csv(state, actor, *, filename, content, side, account, period, field_map=None, expected_row_count=None, file_format="CSV"):
    require_role(actor, "MAKER")
    ensure_open(state, period)
    if file_format not in _PARSERS:
        raise ValueError(f"Unsupported source format: {file_format}")
    # Excel is binary — the JSON transport carries it base64-encoded; every
    # other supported format here is text (CSV, SWIFT MT940, ISO 20022 XML).
    raw_bytes = base64.b64decode(content) if file_format == "EXCEL" else content.encode("utf-8")
    checksum, key = import_identity(tenant_id=UUID(TENANT), connector_id=uuid_for(account + side), raw_bytes=raw_bytes, period=period)
    existing = next((b for b in state["imports"] if b["key"] == key), None)
    if existing:
        return {"duplicate": True, "batch": existing}
    parsed = _PARSERS[file_format](raw_bytes)
    records, errors = [], []
    mapping = field_map or _DEFAULT_FIELD_MAPS[file_format]
    required = {"amount", "currency", "direction", "value_date", "reference"}
    if not required <= set(mapping):
        raise ValueError("Mapping must include amount, currency, direction, value_date and reference.")
    for raw in parsed.rows:
        try:
            missing = [mapping[k] for k in required if mapping[k] not in raw.fields]
            if missing:
                raise ValueError("Missing mapped columns: " + ", ".join(missing))
            values = {k: raw.fields.get(v, "") for k, v in mapping.items()}
            # Explicit decimal convention avoids guessing ambiguous source amounts.
            amount_text = values["amount"].strip()
            if not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,8})?", amount_text):
                raise ValueError("Amount must use decimal digits and an optional decimal point, with at most 8 fractional digits.")
            amount = Decimal(amount_text)
            if not amount.is_finite() or amount < 0 or amount >= Decimal("1e20") or amount.as_tuple().exponent < -8:
                raise ValueError("Amount must be nonnegative numeric(28,8); use direction for the sign.")
            direction = Direction(values["direction"].strip().upper())
            value_date = date.fromisoformat(values["value_date"].strip())
            if value_date.strftime("%Y-%m") != period:
                raise ValueError("Value date is outside the selected period.")
            currency = normalize_currency(values["currency"])
            reference = values["reference"].strip()
            if not normalize_reference(reference):
                raise ValueError("Reference is required.")
            reference_canonical = normalize_reference(reference)
            row_fingerprint = compute_row_fingerprint(
                account_ref=account, amount=amount, currency=currency, value_date=value_date,
                reference_canonical=reference_canonical, counterparty_id=None, direction=direction,
            )
            records.append(dict(id=str(uuid4()), side=side, account=account, period=period,
                                amount=format(amount, "f"), currency=currency, direction=direction.value,
                                value_date=value_date.isoformat(), reference=reference,
                                reference_canonical=reference_canonical, description=normalize_description(values.get("description", "")),
                                status="UNMATCHED", raw_payload=raw.fields, source_file=filename, row_fingerprint=row_fingerprint))
        except (ValueError, ArithmeticError) as exc:
            errors.append({"line": raw.line_no, "reason": str(exc), "raw_payload": raw.fields})
    report = validate_control_totals(
        [ControlRow(Decimal(r["amount"]), Direction(r["direction"]), r["currency"]) for r in records],
        expected_row_count=expected_row_count,
    )
    errors.extend({"line": 0, "reason": e, "raw_payload": {}} for e in report.errors)
    if not parsed.rows:
        errors.append({"line": 0, "reason": "The file contains no transaction rows.", "raw_payload": {}})
    # §6.2/§15.2 — MT940/CAMT053/BAI2 statements self-declare an opening
    # and closing balance; previously parsed and then silently discarded.
    # Where both are present, check them against the batch's own movement
    # with the real §15.2 `unexplained` arithmetic (a `None` opening/closing
    # from CSV/Excel — which declares no self-checkable total — leaves this
    # `None` rather than fabricating a check that isn't there).
    statement_check = None
    if parsed.opening_balance is not None and parsed.closing_balance is not None and not errors:
        movement = sum((Decimal(r["amount"]) if r["direction"] == "CR" else -Decimal(r["amount"]) for r in records), Decimal("0"))
        opening_signed = parsed.opening_balance.amount if parsed.opening_balance.direction == "CR" else -parsed.opening_balance.amount
        closing_signed = parsed.closing_balance.amount if parsed.closing_balance.direction == "CR" else -parsed.closing_balance.amount
        unexplained = compute_unexplained(AccountReconciliationFacts(
            opening_balance=opening_signed, movement=movement, closing_balance=closing_signed, explained=Decimal("0"),
        ))
        statement_check = {
            "opening_balance": format(parsed.opening_balance.amount, "f"), "opening_direction": parsed.opening_balance.direction,
            "closing_balance": format(parsed.closing_balance.amount, "f"), "closing_direction": parsed.closing_balance.direction,
            "movement": format(movement, "f"), "unexplained": format(unexplained, "f"),
        }
    batch = dict(id=str(uuid4()), key=key, checksum=checksum, filename=filename, side=side, account=account, period=period,
                 source_format=file_format, row_count=len(parsed.rows), valid_count=len(records), status="HELD" if errors else "COMMITTED", errors=errors,
                 control_totals={c: {"row_count": v.row_count, "debit_sum": format(v.debit_sum, "f"), "credit_sum": format(v.credit_sum, "f")} for c, v in report.currencies.items()},
                 statement_check=statement_check,
                 created_at=now(), raw_source=content, break_code="DAT-04" if report.errors else ("DAT-01" if errors else None))
    state["imports"].append(batch)
    if not errors:
        state["records"].extend(records)
    audit(state, actor, "import.held" if errors else "import.committed", {"batch_id": batch["id"], "filename": filename, "row_count": len(parsed.rows), "errors": len(errors)})
    return {"duplicate": False, "batch": batch}


def uuid_for(value):
    from uuid import NAMESPACE_URL, uuid5
    return uuid5(NAMESPACE_URL, value)


def reject_import(state, actor, batch_id, reason):
    require_role(actor, "MAKER")
    batch = next((b for b in state["imports"] if b["id"] == batch_id), None)
    if batch is None:
        raise ValueError("Import not found.")
    ensure_open(state, batch["period"])
    if batch["status"] != "HELD":
        raise ValueError("Only a held import can be rejected.")
    if not reason.strip():
        raise ValueError("A rejection reason is required.")
    batch["status"] = "REJECTED"
    batch["rejection"] = {"actor": actor, "reason": reason.strip(), "created_at": now()}
    audit(state, actor, "import.rejected", {"batch_id": batch_id, "reason": reason.strip()}, {"status": "HELD"})
    return batch


def reconcile(state, actor, period):
    require_role(actor, "MAKER")
    ensure_open(state, period)
    available = [r for r in state["records"] if r["period"] == period and r["status"] == "UNMATCHED"]
    if not available:
        raise ValueError("Import unmatched records for this period first.")
    rows = [MatchRecord(r["id"], r["side"], r["account"], r["currency"], Decimal(r["amount"]), r["direction"], date.fromisoformat(r["value_date"]), r["reference_canonical"]) for r in available]
    pairs = exact_pairs(rows)
    matched_ids = {i for pair in pairs for i in pair}
    for pair in pairs:
        state["matches"].append({"id": str(uuid4()), "record_ids": list(pair), "period": period, "rule": "L1_EXACT", "rule_version": "1.0.0", "decided_by": actor, "created_at": now()})
    remaining_rows = [r for r in rows if r.id not in matched_ids]
    tolerance_matches = tolerance_pairs(remaining_rows, TIMING_TOLERANCE_RULES)
    for a_id, b_id, matched_fields in tolerance_matches:
        state["matches"].append({"id": str(uuid4()), "record_ids": [a_id, b_id], "period": period, "rule": "L2_TOLERANCE", "rule_version": "1.0.0", "decided_by": actor, "created_at": now(), "matched_fields": matched_fields})
        matched_ids.update((a_id, b_id))
    group_matches = []
    blocks = defaultdict(lambda: {"SOURCE_A": [], "SOURCE_B": []})
    for r in rows:
        if r.id not in matched_ids:
            blocks[(r.account, r.currency)][r.side].append(r)
    for (account, currency), sides in blocks.items():
        if not sides["SOURCE_A"] or not sides["SOURCE_B"]:
            continue
        try:
            group_matches.extend(find_group_matches(sides["SOURCE_A"], sides["SOURCE_B"], GROUP_MATCH_NET_TOLERANCE, GROUP_MATCH_GUARDRAILS))
        except CandidateExplosion:
            # Production would raise a DAT-07 break here (§8.2); a local,
            # synchronous run just leaves this block for L1/L2-only coverage
            # rather than blocking the whole reconcile call on one block.
            continue
    for gm in group_matches:
        ids = list(gm.side_a_ids) + list(gm.side_b_ids)
        state["matches"].append({"id": str(uuid4()), "record_ids": ids, "period": period, "rule": "L3_GROUP", "rule_version": "1.0.0", "decided_by": actor, "created_at": now(), "net_amount": format(gm.net_amount, "f")})
        matched_ids.update(ids)
    for record in available:
        if record["id"] in matched_ids:
            record["status"] = "MATCHED"
    for case in state["breaks"]:
        if set(case["record_ids"]) <= matched_ids and case["status"] not in ("CLOSED", "RESOLVED"):
            case["status"] = "RESOLVED"
            audit(state, actor, "break.matched", {"case_id": case["id"]})
    remaining = [r for r in available if r["id"] not in matched_ids]
    covered = {i for b in state["breaks"] if b["status"] not in ("CLOSED", "RESOLVED") for i in b["record_ids"]}
    created = 0
    for r in remaining:
        if r["id"] in covered:
            continue
        related = [x for x in remaining if x["id"] not in covered and x["side"] != r["side"] and x["account"] == r["account"] and x["currency"] == r["currency"] and x["reference_canonical"] == r["reference_canonical"]]
        # §7.2/DUP-01: a duplicate is a same-side fingerprint match (account,
        # amount, currency, value date, reference, direction all equal) —
        # stricter than "same reference," since a reused reference with a
        # different amount or date is a different transaction, not a
        # duplicate. `.get(...)` degrades gracefully for any record
        # persisted before this field existed, rather than crashing on it.
        duplicate = any(x["id"] != r["id"] and x["side"] == r["side"] and x.get("row_fingerprint") and x.get("row_fingerprint") == r.get("row_fingerprint") for x in remaining)
        selected = [r] + (related if len(related) == 1 and not duplicate else [])
        code = "DUP-01" if duplicate else ("AMT-02" if related and Decimal(related[0]["amount"]) != Decimal(r["amount"]) else "TIM-01")
        title = {"DUP-01": "Possible duplicate reference", "AMT-02": "Amount difference", "TIM-01": "Timing or missing counterpart"}[code]
        case = dict(id=f"BRK-{len(state['breaks']) + 1:04}", title=title, code=code, period=period, account=r["account"], currency=r["currency"],
                    amount=r["amount"], reference=r["reference"], description=r["description"], record_ids=[x["id"] for x in selected],
                    status="OPEN", risk=_risk_label(code), created_at=now(), value_date=r["value_date"],
                    owner="Unassigned", proposal=None, decision=None, external_ref=None,
                    carry_forward_count=0, original_period=None)
        state["breaks"].append(case)
        covered.update(case["record_ids"])
        created += 1
    result = dict(id=str(uuid4()), kind="MATCHING", period=period, created_at=now(), status="COMPLETED", matched=len(pairs) + len(tolerance_matches) + len(group_matches), cases=created, rule_version="1.0.0")
    state["runs"].append(result)
    audit(state, actor, "reconciliation.completed", result)
    return result


def create_manual_match(state, actor, record_ids, reason):
    """§21.3 screen 6 (Match canvas) / §22 `POST /v1/matches:manual` — a
    human explicitly groups records the deterministic layers didn't. Still
    bound by the same net-zero-within-tolerance and isolation rules as an
    automatic group match (§4.4): this is a human *confirming* a match, not
    a way to force two unrelated records together.
    """
    require_role(actor, "MAKER")
    if not reason.strip():
        raise ValueError("A reason is required to record a manual match.")
    record_ids = list(dict.fromkeys(record_ids))  # de-dupe, preserve order
    if len(record_ids) < 2:
        raise ValueError("Select at least two records to match.")
    records = []
    for rid in record_ids:
        record = next((r for r in state["records"] if r["id"] == rid), None)
        if record is None:
            raise ValueError(f"Record {rid} not found.")
        records.append(record)
    ensure_open(state, records[0]["period"])
    if any(r["period"] != records[0]["period"] for r in records):
        raise ValueError("All selected records must be in the same period.")
    if any(r["status"] != "UNMATCHED" for r in records):
        raise ValueError("Only unmatched records can be selected.")
    if any(r["currency"] != records[0]["currency"] for r in records):
        raise ValueError("All selected records must share the same currency.")
    if not any(r["side"] == "SOURCE_A" for r in records) or not any(r["side"] == "SOURCE_B" for r in records):
        raise ValueError("A match needs at least one record from each source.")
    net = sum((Decimal(r["amount"]) if r["direction"] == "CR" else -Decimal(r["amount"]) for r in records), Decimal("0"))
    if abs(net) > GROUP_MATCH_NET_TOLERANCE:
        raise ValueError(f"Selected records do not net to zero (net {net}); adjust the selection.")

    match = {"id": str(uuid4()), "record_ids": record_ids, "period": records[0]["period"], "rule": "MANUAL",
             "rule_version": "1.0.0", "decided_by": actor, "created_at": now(), "net_amount": format(net, "f"), "reason": reason.strip()}
    state["matches"].append(match)
    matched_ids = set(record_ids)
    for r in records:
        r["status"] = "MATCHED"
    for case in state["breaks"]:
        if set(case["record_ids"]) <= matched_ids and case["status"] not in ("CLOSED", "RESOLVED"):
            case["status"] = "RESOLVED"
            audit(state, actor, "break.matched", {"case_id": case["id"]})
    audit(state, actor, "match.manual_created", {"match_id": match["id"], "record_ids": record_ids, "reason": reason.strip()})
    return match


def unmatch(state, actor, match_id, reason):
    """§22 `POST /v1/matches/{id}:unmatch` — reason mandatory. Reverses a
    match back to UNMATCHED records; it never deletes the match record
    itself (kept, marked reversed, for the audit trail — §4.4's spirit of
    never silently discarding history).
    """
    require_role(actor, "MAKER")
    if not reason.strip():
        raise ValueError("A reason is required to unmatch a match.")
    match = next((m for m in state["matches"] if m["id"] == match_id), None)
    if match is None:
        raise ValueError("Match not found.")
    if match.get("reversed"):
        raise ValueError("This match has already been reversed.")
    ensure_open(state, match["period"])
    for rid in match["record_ids"]:
        record = next((r for r in state["records"] if r["id"] == rid), None)
        if record is not None and record["status"] == "MATCHED":
            record["status"] = "UNMATCHED"
    match["reversed"] = True
    match["reversal"] = {"actor": actor, "reason": reason.strip(), "created_at": now()}
    audit(state, actor, "match.unmatched", {"match_id": match_id, "reason": reason.strip()})
    return match


def triage(state, actor, period, budget=100):
    require_role(actor, "MAKER")
    ensure_open(state, period)
    queue = [b for b in state["breaks"] if b["period"] == period and b["status"] in ("OPEN", "RETURNED", "REJECTED", "TRIAGED", "CARRIED_FORWARD")]
    queue.sort(key=lambda b: (b["risk"] == "High", Decimal(b["amount"])), reverse=True)
    settings = get_settings()
    provider = get_configured_provider(settings)
    llm_touched = 0
    llm_input_tokens = 0
    llm_output_tokens = 0
    for case in queue[:budget]:
        instructions = {
            "AMT-02": "Compare both source amounts and obtain supporting documentation. Confirm whether a fee or source correction explains the difference.",
            "DUP-01": "Verify the source transaction identifiers and supporting statement. A repeated reference is evidence for investigation, not permission to delete a record.",
            "TIM-01": "Check the counterpart source and settlement date. Request the missing transaction or document the timing difference before closing.",
        }
        evidence_records = [r for r in state["records"] if r["id"] in case["record_ids"]]
        # §13.2 — everything below is attacker-controllable (a counterparty
        # types the reference/description), so it only ever reaches the LLM
        # inside draft_narrative's untrusted-data envelope, never as an
        # instruction.
        evidence_summary = "\n".join(
            f"{r['side']}: {r['amount']} {r['currency']} {r['direction']} on {r['value_date']}, "
            f"reference {r['reference']!r}, description {r['description']!r}"
            for r in evidence_records
        )
        text, used_llm = draft_narrative(
            provider,
            BreakNarrativeContext(
                break_code=case["code"], family=case["code"].split("-")[0], account=case["account"],
                amount=case["amount"], currency=case["currency"], reference=case["reference"],
                evidence_summary=evidence_summary,
            ),
            fallback_text=instructions[case["code"]],
        )
        if used_llm:
            llm_touched += 1
            # §21.5/§24 "cost per case" — real token counts from the
            # provider's own usage metadata when it exposes them, not an
            # estimate. `getattr` degrades gracefully for a fake test
            # provider that has no such attribute.
            usage = getattr(provider, "last_usage", None)
            if usage is not None:
                llm_input_tokens += usage.input_tokens
                llm_output_tokens += usage.output_tokens
        elif provider is not None:
            # A provider IS configured but this call failed — a real
            # fallback event (§23), distinct from "no provider configured"
            # which is just the normal deterministic-only state.
            audit(state, "AGENT", "agent.fallback.engaged", {"case_id": case["id"], "reason": "LLM call failed, used deterministic template"})
        case["proposal"] = {
            "id": str(uuid4()), "maker": actor, "text": text, "evidence_ids": case["record_ids"],
            "method": f"{provider.name.capitalize()} · {provider.model}" if used_llm else "Deterministic template",
            "version": provider.model if used_llm else "1.0.0", "created_at": now(),
        }
        try:
            current = S(case["status"])
            # A reopened case is already sitting in TRIAGED (§4.3: REOPENED
            # -> TRIAGED is the reopen action's own last step) — only OPEN /
            # REJECTED / RETURNED still need the TRIAGED hop first.
            chain_targets = [S.PROPOSED] if current == S.TRIAGED else [S.TRIAGED, S.PROPOSED]
            case["status"] = _chain(current, *chain_targets).value
        except IllegalTransition as exc:
            raise ValueError(str(exc)) from exc
        # EP-04 — resolve the pack's routing rules against this case's
        # family/amount instead of a hardcoded "Reviewer" owner (§18.2's
        # approval-limit routing starts here, even though core ships only
        # one operational role today).
        try:
            decision = resolve_routing(
                break_family=case["code"].split("-")[0], amount=Decimal(case["amount"]),
                dimensions=case.get("dimensions", {}), rules=_ROUTING_RULES,
            )
            case["owner"] = _ROLE_DISPLAY_NAMES.get(decision.required_role, decision.required_role)
        except ValueError:
            case["owner"] = "Reviewer"  # no routing rule matched this family — falls back, never crashes triage
        audit(state, "AGENT", "agent.proposal.created", {"case_id": case["id"], "proposal_id": case["proposal"]["id"]})
    cases_this_run = min(len(queue), budget)
    # §24's own target: "LLM-touched break share <= 12%... breach = rule
    # engine is weak, not a model problem." Computed from this run's real
    # counts against the real configured threshold — never hardcoded here.
    llm_touched_share = (llm_touched / cases_this_run) if cases_this_run else 0.0
    llm_share_breach = llm_touched_share > settings.agent_budgets.llm_touched_breaks_max_share
    if llm_share_breach:
        audit(state, "AGENT", "agent.llm_touched_share.exceeded", {
            "period": period, "llm_touched_share": round(llm_touched_share, 4),
            "threshold": settings.agent_budgets.llm_touched_breaks_max_share,
        })
    result = dict(id=str(uuid4()), kind="AGENT", period=period, created_at=now(), status="COMPLETED",
                  cases=cases_this_run, skipped=max(0, len(queue)-budget), budget=budget,
                  model=provider.model if llm_touched else "No LLM", llm_touched=llm_touched,
                  llm_input_tokens=llm_input_tokens, llm_output_tokens=llm_output_tokens,
                  llm_touched_share=round(llm_touched_share, 4), llm_share_breach=llm_share_breach,
                  rule_version="1.0.0")
    state["runs"].append(result)
    audit(state, "AGENT", "agent.run.completed", result)
    return result


def check_records(state, actor, period):
    """One user action: validate source readiness, match, then prepare reviews.

    Retries leave prepared recommendations and existing matches alone. The
    caller supplies the transaction, so an unsuccessful check cannot commit
    a partially updated workspace.
    """
    require_role(actor, "MAKER")
    ensure_open(state, period)
    records = [r for r in state["records"] if r["period"] == period]
    if not records:
        raise ValueError("Upload your bank and accounting files for this month first.")
    if any(b["period"] == period and b["status"] == "HELD" for b in state["imports"]):
        raise ValueError("Some uploaded files need attention. Fix or reject them on Upload files, then try again.")
    accounts = {}
    for record in records:
        accounts.setdefault(record["account"], set()).add(record["side"])
    missing = [account for account, sides in accounts.items() if sides != {"SOURCE_A", "SOURCE_B"}]
    if missing:
        raise ValueError("Upload both bank and accounting records for: " + ", ".join(sorted(missing)))
    covered = {rid for b in state["breaks"] if b["period"] == period and b["status"] not in ("CLOSED", "RESOLVED") for rid in b["record_ids"]}
    new_records = any(r["status"] == "UNMATCHED" and r["id"] not in covered for r in records)
    matching = reconcile(state, actor, period) if new_records else None
    pending = any(b["period"] == period and b["status"] in ("OPEN", "RETURNED", "REJECTED", "TRIAGED", "CARRIED_FORWARD") for b in state["breaks"])
    agent = triage(state, actor, period, budget=get_settings().agent_budgets.cases_per_run) if pending else None
    open_cases = [b for b in state["breaks"] if b["period"] == period and b["status"] not in ("CLOSED", "RESOLVED")]
    return {
        "status": "COMPLETED", "new_matches": matching["matched"] if matching else 0,
        "recommendations_prepared": agent["cases"] if agent else 0,
        "differences": len(open_cases), "ready_for_review": sum(b["status"] == "PROPOSED" for b in open_cases),
        "skipped": agent["skipped"] if agent else 0,
    }


def decide(state, actor, case_id, action, reason, external_ref=None):
    case = next((b for b in state["breaks"] if b["id"] == case_id), None)
    if case is None:
        raise ValueError("Break not found.")
    ensure_open(state, case["period"])
    if not reason.strip():
        raise ValueError("A decision reason is required.")
    before = {"status": case["status"]}
    if action in ("APPROVE", "REJECT", "RETURN"):
        require_role(actor, "CHECKER")
        if case["status"] != "PROPOSED" or not case["proposal"]:
            raise ValueError("Only a proposed case can be reviewed.")
        try:
            authorize_approval(ApprovalRequest(made_by=case["proposal"]["maker"], checked_by=actor, checker_has_required_role=True))
        except MakerCheckerViolation as exc:
            raise PermissionError(str(exc)) from exc
        # §4.3: PROPOSED -> UNDER_REVIEW -> {APPROVED, REJECTED, RETURNED}; an
        # approval continues straight on to ACTION_PENDING (§14.1's maker ->
        # checker -> post pipeline treats "approved" and "action now due" as
        # the same moment, not two separately gated human steps).
        target_after_review = {"APPROVE": S.APPROVED, "REJECT": S.REJECTED, "RETURN": S.RETURNED}[action]
        chain = [S.UNDER_REVIEW, target_after_review] + ([S.ACTION_PENDING] if action == "APPROVE" else [])
        try:
            case["status"] = _chain(S.PROPOSED, *chain).value
        except IllegalTransition as exc:
            raise ValueError(str(exc)) from exc
    elif action == "CLOSE":
        require_role(actor, "CHECKER")
        if case["status"] != "ACTION_PENDING":
            raise ValueError("Approve the proposal before recording a resolution.")
        if not external_ref or not external_ref.strip():
            raise ValueError("An external action or evidence reference is required.")
        try:
            case["status"] = _chain(S.ACTION_PENDING, S.RESOLVED, S.CLOSED).value
        except IllegalTransition as exc:
            raise ValueError(str(exc)) from exc
        case["external_ref"] = external_ref.strip()
        for r in state["records"]:
            if r["id"] in case["record_ids"]:
                r["status"] = "EXPLAINED"
    elif action == "REOPEN":
        # §18.2: reopening a closed case needs a permission distinct from
        # the checker's approve/reject/return, plus the mandatory reason
        # already required above — CERTIFIER is the highest-trust local
        # role, so it stands in for that separate permission here.
        require_role(actor, "CERTIFIER")
        if case["status"] != "CLOSED":
            raise ValueError("Only a closed case can be reopened.")
        try:
            case["status"] = _chain(S.CLOSED, S.REOPENED, S.TRIAGED, reason=reason.strip()).value
        except IllegalTransition as exc:
            raise ValueError(str(exc)) from exc
        case["owner"] = "Unassigned"
        case["proposal"] = None
        case["external_ref"] = None
        for r in state["records"]:
            if r["id"] in case["record_ids"] and r["status"] == "EXPLAINED":
                r["status"] = "UNMATCHED"
    else:
        raise ValueError("Unsupported decision.")
    case["decision"] = {"actor": actor, "reason": reason.strip(), "action": action, "created_at": now()}
    audit(state, actor, "break." + action.lower(), {"case_id": case_id, "status": case["status"], "reason": reason.strip(), "external_ref": external_ref}, before)
    return case


def create_journal_draft(state, actor, case_id, lines, reason):
    """§14.1 internal path — the maker drafts a correcting entry. §11.2/
    §12.2's guardrail is structural, not a permission check here: there is
    no `post_journal` tool anywhere in this codebase (§12.3) for a human or
    agent to call — posting only ever happens as the automatic system
    action inside `decide_journal_draft`'s APPROVE branch, never on its own.
    """
    require_role(actor, "MAKER")
    case = next((b for b in state["breaks"] if b["id"] == case_id), None)
    if case is None:
        raise ValueError("Break not found.")
    ensure_open(state, case["period"])
    if case["status"] != "ACTION_PENDING":
        raise ValueError("Approve the proposal before drafting a journal entry.")
    if any(d["case_id"] == case_id and d["status"] == "SUBMITTED" for d in state["journal_drafts"]):
        raise ValueError("A journal draft is already awaiting review for this case.")
    if not reason.strip():
        raise ValueError("A journal draft reason is required.")
    if not lines or len(lines) < 2:
        raise ValueError("A journal draft needs at least two lines.")
    parsed_lines = []
    for line in lines:
        side = line.get("side")
        if side not in ("DR", "CR"):
            raise ValueError("Each journal line must be DR or CR.")
        account_role = (line.get("account_role") or "").strip()
        if not account_role:
            raise ValueError("Each journal line needs an account role.")
        try:
            amount = Decimal(str(line.get("amount", "")))
        except (ArithmeticError, ValueError, TypeError):
            raise ValueError("Each journal line needs a valid amount.")
        if not amount.is_finite() or amount <= 0:
            raise ValueError("Journal line amounts must be positive.")
        parsed_lines.append({"side": side, "account_role": account_role, "amount": format(amount, "f")})
    if not any(l["side"] == "DR" for l in parsed_lines) or not any(l["side"] == "CR" for l in parsed_lines):
        raise ValueError("A journal draft needs at least one debit and one credit line.")
    debit_total = sum(Decimal(l["amount"]) for l in parsed_lines if l["side"] == "DR")
    credit_total = sum(Decimal(l["amount"]) for l in parsed_lines if l["side"] == "CR")
    if debit_total != credit_total:
        raise ValueError(f"Journal draft does not balance: debits {debit_total} vs credits {credit_total}.")

    draft = dict(id=str(uuid4()), case_id=case_id, period=case["period"], lines=parsed_lines,
                 reason=reason.strip(), maker=actor, status="SUBMITTED", created_at=now(), decision=None)
    state["journal_drafts"].append(draft)
    audit(state, actor, "journal_draft.submitted", {"draft_id": draft["id"], "case_id": case_id})
    return draft


def decide_journal_draft(state, actor, draft_id, action, reason):
    draft = next((d for d in state["journal_drafts"] if d["id"] == draft_id), None)
    if draft is None:
        raise ValueError("Journal draft not found.")
    case = next((b for b in state["breaks"] if b["id"] == draft["case_id"]), None)
    if case is None:
        raise ValueError("Linked break not found.")
    ensure_open(state, case["period"])
    if not reason.strip():
        raise ValueError("A decision reason is required.")
    if draft["status"] != "SUBMITTED":
        raise ValueError("Only a submitted journal draft can be reviewed.")
    require_role(actor, "CHECKER")
    try:
        authorize_approval(ApprovalRequest(made_by=draft["maker"], checked_by=actor, checker_has_required_role=True))
    except MakerCheckerViolation as exc:
        raise PermissionError(str(exc)) from exc

    if action == "APPROVE":
        draft["status"] = "POSTED"
        # §14.1: "System post karta hai" — posting is automatic on
        # approval, not a separate human click, and it's what resolves the
        # break; the draft itself is the evidence, replacing an external_ref.
        try:
            case["status"] = _chain(S.ACTION_PENDING, S.RESOLVED, S.CLOSED).value
        except IllegalTransition as exc:
            raise ValueError(str(exc)) from exc
        case["external_ref"] = f"Internal journal draft {draft['id'][:8]} posted to subledger"
        for r in state["records"]:
            if r["id"] in case["record_ids"]:
                r["status"] = "EXPLAINED"
        audit(state, actor, "journal_draft.posted", {"draft_id": draft_id, "case_id": draft["case_id"]})
    elif action == "REJECT":
        draft["status"] = "REJECTED"
        audit(state, actor, "journal_draft.rejected", {"draft_id": draft_id, "case_id": draft["case_id"]})
    else:
        raise ValueError("Unsupported decision.")
    draft["decision"] = {"actor": actor, "reason": reason.strip(), "action": action, "created_at": now()}
    return draft


def certify(state, actor, period, reason):
    require_role(actor, "CERTIFIER")
    ensure_open(state, period)
    if not reason.strip():
        raise ValueError("Certification statement is required.")
    records = [r for r in state["records"] if r["period"] == period]
    if not records or {r["side"] for r in records} != {"SOURCE_A", "SOURCE_B"}:
        raise ValueError("Both sources are required for certification.")
    settings = get_settings()
    open_breaks = [b for b in state["breaks"] if b["period"] == period and b["status"] not in ("CLOSED", "RESOLVED")]
    # §15.3: certification blocks on a high-risk open break or one aged past
    # policy, not on every open item — anything milder rolls forward
    # instead (§16), it doesn't hold up the close.
    blocking = [b for b in open_breaks if b["risk"] == "High" or _age_days(b["created_at"]) > settings.aged_break_high_risk_days]
    if blocking:
        raise ValueError(f"{len(blocking)} high-risk or aged break(s) must be resolved before certification.")
    # An UNMATCHED record only clears this gate if some (non-blocking, since
    # we already checked above) break is tracking it — i.e. reconciliation
    # actually ran and the gap is a known, carrying-forward item, not a
    # record nobody has looked at yet.
    tracked_record_ids = {rid for b in open_breaks for rid in b["record_ids"]}
    if any(r["status"] == "UNMATCHED" and r["id"] not in tracked_record_ids for r in records):
        raise ValueError("Resolve all unmatched records before certification.")
    if any(b["period"] == period and b["status"] == "HELD" for b in state["imports"]):
        raise ValueError("Held imports must be addressed before certification.")

    next_period = _next_period(period)
    for case in open_breaks:
        rolled = roll_forward(
            status=S(case["status"]), carry_forward_count=case.get("carry_forward_count", 0),
            age_days=_age_days(case["created_at"]), original_period=case.get("original_period"),
            current_period=period, escalation_threshold=settings.carried_forward_escalation_count,
            high_risk_age_days=settings.aged_break_high_risk_days,
        )
        case["status"] = rolled.status.value
        case["carry_forward_count"] = rolled.carry_forward_count
        case["original_period"] = case.get("original_period") or period
        case["period"] = next_period
        if rolled.requires_escalation:
            case["risk"] = "High"
        audit(state, actor, "break.carried_forward", {
            "case_id": case["id"], "from_period": period, "to_period": next_period,
            "carry_forward_count": rolled.carry_forward_count, "requires_escalation": rolled.requires_escalation,
        })

    result = {"status": "CERTIFIED", "actor": actor, "reason": reason.strip(), "created_at": now()}
    state["periods"][period] = result
    audit(state, actor, "period.certified", {"period": period, **result})
    return result


def admin_config_snapshot():
    """§32 — "kuch bhi hardcode nahi": every knob the plan says must be
    configuration, read straight from `core.config.get_settings()` (real
    values, not a UI-invented shape) so an admin screen has something
    genuine to show without duplicating the config surface.
    """
    from workbench import scheduler as scheduler_config  # deferred: scheduler.py imports this module, avoiding a cycle

    settings = get_settings()
    return {
        "queue_priority_weights": settings.queue_weights.model_dump(),
        "confidence_band_thresholds": settings.confidence_bands.model_dump(),
        "false_match_budget": settings.false_match_budget.model_dump(),
        "agent_budgets": settings.agent_budgets.model_dump(),
        "group_match_guardrails": settings.group_match.model_dump(),
        "ageing_and_roll_forward": {
            "aged_break_high_risk_days": settings.aged_break_high_risk_days,
            "carried_forward_escalation_count": settings.carried_forward_escalation_count,
        },
        "suppress_rule_max_expiry_days": settings.suppress_rule_max_expiry_days,
        "scheduler": {
            "interval_seconds": scheduler_config.SCHEDULE_INTERVAL_SECONDS,
            "actor": scheduler_config.SCHEDULED_ACTOR,
        },
        "llm": {"provider": settings.llm.provider, "model": settings.llm.model, "configured": bool(settings.llm.api_key)},
    }


def seed(state, actor):
    require_role(actor, "MAKER")
    if state["records"] or state["imports"]:
        raise ValueError("Sample data can only be loaded into an empty workspace.")
    period = date.today().strftime("%Y-%m")
    header = "amount,currency,direction,value_date,reference,description\n"
    names = ["Atlas Trading", "Northstar Logistics", "Crescent Technologies", "Oak & Co", "Meridian Supply", "Vertex Services", "Harbor Retail", "Summit Industries"]
    a, b = [], []
    for i in range(1, 81):
        amount = Decimal(250 + i * 173)
        day = min(i % 6 + 1, date.today().day)
        line = f"{amount},USD,CR,{period}-{day:02},TXN-{i:04},{names[i % len(names)]} settlement\n"
        a.append(line)
        if i <= 68:
            b.append(line)
        elif i <= 73:
            b.append(line.replace(str(amount) + ",", str(amount - Decimal("25")) + ",", 1))
    for side, lines in (("SOURCE_A", a), ("SOURCE_B", b)):
        import_csv(state, actor, filename=f"sample-{side.lower()}.csv", content=header + "".join(lines), side=side, account="Operating account", period=period)
    reconcile(state, actor, period)
    triage(state, actor, period)
    state["sample_loaded"] = True
    return {"period": period}
