"""RLS, agent_runtime role/grants, and §4.4 integrity triggers

§20 — shared schema + Postgres RLS is the multi-tenancy decision, enforced
here at the DB layer (not just application WHERE clauses) so a forgotten
tenant filter can never leak across tenants. §13.1 — agent_runtime is the
DB role the agent connects as: SELECT everywhere, INSERT only on the
draft-safe tables (core.agent.tools.draft_tools.DRAFT_TABLES), never
UPDATE/DELETE anywhere — this migration is the other half of the guardrail
that tests/security/test_no_write_tools.py::test_agent_db_role_is_read_plus_draft_only
checks against a live database. §4.4 — three integrity rules the model
docstrings already promise are "DB constraint/trigger, not application
code": audit_event is insert-only, canonical_record.raw_payload never
mutates, and a match_group can never span two different values of an
is_isolating dimension.

Revision ID: 0002_rls_agent_role
Revises: b09900336144
Create Date: 2026-09-07
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0002_rls_agent_role"
down_revision: Union[str, None] = "b09900336144"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Every table that carries tenant_id (i.e. every core table except
# `tenant` itself). Kept as an explicit, reviewed list rather than derived
# from reflection so a newly added table can't silently ship without RLS —
# a future migration must add it here deliberately.
TENANT_SCOPED_TABLES = [
    "connector",
    "mapping_template",
    "import_batch",
    "dimension_registry",
    "tolerance_profile",
    "universe",
    "recon_run",
    "canonical_record",
    "match_group",
    "match_member",
    "break_type",
    "break_case",
    "proposal",
    "evidence_item",
    "decision",
    "journal_draft",
    "external_action_ref",
    "routing_rule",
    "knowledge_document",
    "document_chunk",
    "retrieval_trace",
    "agent_run",
    "audit_event",
    "close_period",
    "account_reconciliation",
]

# §12.2 — the only tables the agent's DB role may INSERT into. Mirrors
# core.agent.tools.draft_tools.DRAFT_TABLES exactly; that constant is the
# application-side source of truth and this list is its DB-grant mirror,
# not a second source of truth to drift from it.
DRAFT_TABLES = ["proposal", "journal_draft", "evidence_item"]

AGENT_DB_ROLE = "agent_runtime"


def upgrade() -> None:
    # --- §20: RLS on every tenant-scoped table -----------------------
    # `current_setting('app.tenant_id', true)` returns NULL (not an error)
    # when the session hasn't set it, and tenant_id = NULL is never true —
    # so an application connection that forgets to set the tenant context
    # sees zero rows rather than every tenant's rows (fail closed).
    for table in TENANT_SCOPED_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY tenant_isolation_policy ON "{table}" '
            f"USING (tenant_id = current_setting('app.tenant_id', true)::uuid) "
            f"WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid)"
        )

    # --- §13.1: the agent_runtime role --------------------------------
    # NOLOGIN here deliberately — login capability and the actual password
    # are assigned operationally via the secrets vault (§6.3's rule
    # applies to the app's own DB credentials too), never embedded in a
    # migration.
    op.execute(
        f"DO $$ BEGIN "
        f"IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{AGENT_DB_ROLE}') THEN "
        f"CREATE ROLE {AGENT_DB_ROLE} NOLOGIN; "
        f"END IF; "
        f"END $$"
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {AGENT_DB_ROLE}")

    # SELECT everywhere, including `tenant` itself (read tools need it,
    # §12.1) plus every tenant-scoped table.
    for table in ["tenant", *TENANT_SCOPED_TABLES]:
        op.execute(f'GRANT SELECT ON "{table}" TO {AGENT_DB_ROLE}')

    # INSERT only on the draft-safe surface (§12.2). No UPDATE, no DELETE,
    # anywhere, ever — that omission is the guardrail, not a grant to add.
    for table in DRAFT_TABLES:
        op.execute(f'GRANT INSERT ON "{table}" TO {AGENT_DB_ROLE}')

    # --- §4.4 / §23: audit_event is insert-only -----------------------
    op.execute(
        """
        CREATE FUNCTION audit_event_prevent_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_event is append-only: % is not permitted (§4.4)', TG_OP;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER audit_event_no_update "
        "BEFORE UPDATE ON audit_event "
        "FOR EACH ROW EXECUTE FUNCTION audit_event_prevent_mutation()"
    )
    op.execute(
        "CREATE TRIGGER audit_event_no_delete "
        "BEFORE DELETE ON audit_event "
        "FOR EACH ROW EXECUTE FUNCTION audit_event_prevent_mutation()"
    )

    # --- §4.4: canonical_record.raw_payload never mutates -------------
    op.execute(
        """
        CREATE FUNCTION canonical_record_prevent_raw_payload_mutation() RETURNS trigger AS $$
        BEGIN
            IF NEW.raw_payload IS DISTINCT FROM OLD.raw_payload THEN
                RAISE EXCEPTION 'canonical_record.raw_payload is immutable once written (§4.4)';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER canonical_record_raw_payload_immutable "
        "BEFORE UPDATE ON canonical_record "
        "FOR EACH ROW EXECUTE FUNCTION canonical_record_prevent_raw_payload_mutation()"
    )

    # --- §4.1 / §4.4 / §8.3: isolating dimensions can't cross ----------
    # A match_group may never end up with members whose canonical_record
    # disagrees on the value of a dimension the tenant has registered as
    # is_isolating (EP-01/EP-03's Mizan example: two different pool_ids
    # can never land in the same match_group). Checked as an AFTER INSERT
    # trigger on match_member so it fires within the same transaction as
    # the insert and rolls the whole thing back — this is the "DB
    # constraint, application check nahi" the model docstrings promise.
    op.execute(
        """
        CREATE FUNCTION enforce_isolating_dimensions() RETURNS trigger AS $$
        DECLARE
            dim RECORD;
            distinct_count integer;
        BEGIN
            FOR dim IN
                SELECT key FROM dimension_registry
                WHERE tenant_id = NEW.tenant_id AND is_isolating = true
            LOOP
                SELECT count(DISTINCT cr.dimensions ->> dim.key) INTO distinct_count
                FROM match_member mm
                JOIN canonical_record cr ON cr.id = mm.record_id
                WHERE mm.match_group_id = NEW.match_group_id
                  AND cr.dimensions ->> dim.key IS NOT NULL;

                IF distinct_count > 1 THEN
                    RAISE EXCEPTION
                        'match_group % spans isolating dimension "%" across multiple values (§4.1/§4.4)',
                        NEW.match_group_id, dim.key;
                END IF;
            END LOOP;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER match_member_isolating_dimension_check "
        "AFTER INSERT ON match_member "
        "FOR EACH ROW EXECUTE FUNCTION enforce_isolating_dimensions()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS match_member_isolating_dimension_check ON match_member")
    op.execute("DROP FUNCTION IF EXISTS enforce_isolating_dimensions()")

    op.execute(
        "DROP TRIGGER IF EXISTS canonical_record_raw_payload_immutable ON canonical_record"
    )
    op.execute("DROP FUNCTION IF EXISTS canonical_record_prevent_raw_payload_mutation()")

    op.execute("DROP TRIGGER IF EXISTS audit_event_no_delete ON audit_event")
    op.execute("DROP TRIGGER IF EXISTS audit_event_no_update ON audit_event")
    op.execute("DROP FUNCTION IF EXISTS audit_event_prevent_mutation()")

    for table in DRAFT_TABLES:
        op.execute(f'REVOKE INSERT ON "{table}" FROM {AGENT_DB_ROLE}')
    for table in ["tenant", *TENANT_SCOPED_TABLES]:
        op.execute(f'REVOKE SELECT ON "{table}" FROM {AGENT_DB_ROLE}')
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {AGENT_DB_ROLE}")
    op.execute(f"DROP ROLE IF EXISTS {AGENT_DB_ROLE}")

    for table in TENANT_SCOPED_TABLES:
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation_policy ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
