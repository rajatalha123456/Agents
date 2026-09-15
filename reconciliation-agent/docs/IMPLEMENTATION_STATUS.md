# Implementation status — 7 September 2026

This is a capability inventory, not a percentage or a claim that any full roadmap phase is production complete.

| Area | Present | Still required for the full v3 plan |
| --- | --- | --- |
| P0 foundation | ORM schema, migrations (upgrade **and** downgrade verified reversible), audit hashing, pack loader, tool guard tests; local workbench API. RLS/triggers/agent-role grants verified against a live migrated Postgres 16 instance. **Standard local-dev infra added**: `docker-compose.yml` gives zero-config Postgres+Redis matching `core/config.py`'s own defaults. **Real authentication now wired**: `workbench/auth.py` — PBKDF2 password hashing, JWT-signed sessions (`POST /api/auth/login`), every mutating route verifying the token's signature via `require_actor()` instead of trusting a client-supplied header; frontend has a real login screen replacing the old role dropdown | Production identity provider and gateway scopes (the three demo accounts are a fixed local seed, not an IdP-backed roster), service/repository integration (workbench still uses SQLite, not the Postgres schema — a deliberate, documented local-eval boundary, not an oversight), complete security CI running the DB check automatically |
| P1 ingestion | All v1/v2-must formats from §6.1 now parse and import live: CSV, MT940, CAMT.053, Excel (.xlsx, multi-sheet + merged-header handling), and BAI2 (US banks) — one shared import path, format-aware default field maps, matching frontend format selector | Production import storage and repositories, pain.002, durable quarantine model, encrypted raw storage, revalidation workflow, REST/DB read-only connectors |
| P2 matching | Tested exact 1:1 matcher (L1), tolerance matcher (L2), and group matcher (L3) all wired into the local reconcile run; duplicate detection now uses the real §7.2 fingerprint (account+amount+currency+date+reference+direction), replacing a looser reference-only heuristic that could misclassify a reused reference with a different amount as a duplicate; three-class break generation; core 48-code registry; break-type registry lookup and isolating-dimension enforcement; **§22's manual match/unmatch API now exists** (`POST /v1/matches:manual` / `:unmatch` equivalents) with a real Match canvas UI — a human can group unmatched records the deterministic layers didn't (bound by the same net-zero-within-tolerance rule as L3), and reverse any match with a mandatory reason | L4 candidate scoring/blocking at scale, L5 learned re-ranker, replay/back-test datasets, production persistence, group-match confidence discount (§8.3) |
| P3 workflow | Connected break queue, filters, evidence drawer, maker/checker decisions tied to real signed-in accounts, not a client-trusted header (maker-checker same-actor check delegates to `core.workflow.maker_checker`); every status transition in the workbench (triage, approve/reject/return, close, reopen) now runs through the real `core.breaks.lifecycle` state machine, including the previously-unbuilt reopen action (Controller-only, mandatory reason, returns a closed case to triage) with a matching UI control; EP-04 routing engine now wired into live triage — case ownership is resolved from the core pack's real routing rules (family → role, with an amount-based escalation to Controller for large AMT breaks), not a hardcoded string | Dimension-filtered routing (only family/amount used so far), assignment/SLA/escalation, independent verification of external evidence |
| P4 close | Local readiness checks, evidence export (now with a dedicated Certification pack preview screen); `unexplained` balance computation and certification-blocker evaluation exist as tested standalone modules; §16 roll-forward wired into the live `certify()` path (blocks only on a high-risk/aged-past-policy open break, everything else carries forward as the same case); **§14.1's internal journal draft path is now built end-to-end** — a maker drafts a balanced (debits=credits) correcting entry against an ACTION_PENDING case, a distinct checker approves it, and only *that approval* triggers the automatic system post that resolves and closes the case (no `post_journal` tool exists anywhere for a human or agent to call directly, matching §12.3's guardrail) | `unexplained`/per-account certification-blocker modules still not wired to a live per-account view (workbench has no account-level opening/closing balances yet), certification pack contract as a formal export format, close calendars |
| P5 deterministic agent | Budget/runtime contracts; manual triage with 100-case cap, risk/value ordering, templates and linked evidence. **A real Celery scheduler now exists** (`workbench/scheduler.py`) — verified end-to-end against a live Redis broker and worker (not just unit-tested logic): it discovered real open periods in the actual workbench store and ran genuine reconcile+triage cycles against them | Persistent job lifecycle/monitoring, full runtime integration with the ORM/Postgres path (the scheduler runs against the SQLite workbench, same boundary as P0's above), configured priority formula, tenant budgets and kill switches |
| P6 LLM | A real, working provider adapter (`core/agent/llm/`): provider-neutral `LLMProvider` interface + a Gemini implementation (`gemini-3.6-flash` via direct REST call), wired into live `triage()` with §13.2's untrusted-data envelope and §13.5 deterministic fallback. **Real token/cost metering now wired too**: `GeminiProvider` captures the actual `usageMetadata` from every response (input/output/thinking tokens — not estimated), `triage()` accumulates it per run and computes §24's real "LLM-touched breaks share" against the actual configured 12% threshold, firing a genuine `agent.llm_touched_share.exceeded` audit event and a UI warning when exceeded — verified against the real API (a real call used 285 input / 93 output tokens, correctly flagged at 100% > 12%) | RAG ingestion/retrieval, citation traces (no knowledge corpus exists to retrieve from), converting real token counts into a real dollar cost against `AgentBudgets.llm_cost_ceiling_per_case_usd` (needs a configured price-per-token, not just a token count), acceptance evaluation |
| P7 scoring | Confidence-band helper; isotonic calibration, ECE, reliability-diagram and the false-match circuit breaker are now **exercised end-to-end** via a clearly-labeled synthetic dataset (`workbench/mock_data.py`, `synthetic: true` throughout) on the new Model governance screen — real code, fabricated-but-honest inputs, since no real historical match dispositions exist yet | L4 candidate scoring, L5 learned re-ranker, wiring calibration/circuit-breaker into live matching runs against *real* dispositions once they exist |
| P8 frontend | React/TypeScript/Vite app; **all 18 of §21.3's screens are now connected**: Overview, Universe board (2), Break queue (4), Match canvas (6), Approval queue (8), Journal drafts (9), Ageing (10), Period close (11), Certification pack (12), Imports (13), Rule packs (14), Model governance (16), Agent activity + Run detail (3, 15), Audit trail (17), Admin (18), Pilot, Settings — every one backed by real workspace data or clearly-labeled synthetic data, none a placeholder. Two real bugs found and fixed while building the last of these: a sidebar overflow bug (14+ nav items pushed controls off-screen) and a missing pack-data fetch on Admin | Real auth, account balances, accessibility/localization audit, UAT, and turning every screen's local-workbench data source into the ORM/Postgres one |
| P9 pilot | Synthetic sample workflow; new Pilot screen with a clearly-labeled dummy tenant (`is_dummy: true`, status `NOT_ONBOARDED`) — activity numbers shown are real (drawn from this workspace's own imports/breaks/runs), not fabricated pilot KPIs | A real customer, real permitted source data, deployment infrastructure, operational controls and measured pilot results — none of which a dummy tenant record can substitute for |
| P10 packs | Existing generic pack loading and registry | Full extension-point integration, Mizan implementation, signed historical dry run and external handoff |

## Added in this continuation (7 September 2026, second pass)

- L2 tolerance matching (`core/matching/tolerance.py`) and L3 group matching
  with subset-sum guardrails and candidate-explosion detection
  (`core/matching/grouping.py`) — P2's remaining matching layers.
- `core/breaks/` (previously empty): lifecycle state machine enforcing the
  §4.3 diagram including reopen-with-reason and period-close carry-forward
  (`lifecycle.py`); §16 roll-forward math (`rollforward.py`); break-type
  registry lookup plus the isolating-dimension check that stops a match
  from crossing an `is_isolating` dimension (`classification.py`).
- `core/workflow/` (previously empty): the routing engine resolving EP-04
  rules against a case's facts, with `allow_auto_match: false` always
  winning per §5.3 (`routing.py`); maker-checker enforcement including the
  same-actor block and mandatory-reason reopen rule (`maker_checker.py`).
- `core/close/` (previously empty): the `unexplained` balance computation
  (`reconciliation.py`) and certification-blocker evaluation for §15.3's
  three block conditions (`certification.py`).
- Confidence calibration (`core/matching/calibration.py`): per-universe
  isotonic fit/predict, expected calibration error, and reliability-diagram
  bins for the §21.5 transparency screen — the pieces §9.1 requires on top
  of the existing raw-score-to-band helper.
- False-match circuit breaker (`core/matching/circuit_breaker.py`): §9.3's
  automatic trip / human-with-mandatory-reason-only reset, tested against
  all three budget metrics.
- Installed the `matching` optional dependency group (scikit-learn,
  lightgbm, polars) into the project venv so this code actually runs, not
  just imports in isolation.
- Fixed a stale Windows temp-directory permission issue that was failing
  all integration tests; pytest now uses an in-repo basetemp.
- 64 new unit tests (92 → 156 passing) covering all of the above.

## Added in this continuation (7 September 2026, third pass)

- Wired `core.matching.tolerance` into `workbench/service.py::reconcile` as
  a real L2 pass after L1 exact (2-day value-date window, exact amount) —
  the local backend now actually runs two matching layers, not one.
- Wired `core.workflow.maker_checker.authorize_approval` into
  `workbench/service.py::decide`, replacing the inline same-actor check
  with the tested, centralized rule (still translated to the same 403
  response the frontend already expects).
- Added integration tests for the new tolerance-matching path (matches
  across a date drift, does not bridge an amount difference) and confirmed
  all prior workbench integration tests are unaffected (92 → 158 passing).
- Did *not* force the full `core.breaks.lifecycle` state machine into the
  workbench's review flow: the workbench collapses UNDER_REVIEW into the
  APPROVE action and RESOLVED into CLOSE, and the connected frontend reads
  those exact status strings — switching to the full state machine needs a
  matching frontend change (an extra review step) to avoid silently
  breaking the UI. Left as a scoped follow-up.
- Wired `core.matching.grouping.find_group_matches` into the same
  `reconcile` call as a third pass (L3) over whatever L1/L2 left unmatched,
  blocked by (account, currency) with a tight local-run guardrail
  (`GROUP_MATCH_GUARDRAILS`, max size 4 / 40 candidates / 200ms) so a
  synchronous HTTP request never hangs on the NP-hard search. A
  `CandidateExplosion` on one block is skipped rather than failing the
  whole reconcile call (production would raise DAT-07 instead; the
  workbench doesn't have a break-creation path for it yet).
- Added a group-matching integration test (one credit against three
  debits) and confirmed the fixed sample-data counts in the existing
  `test_sample_data_is_explicit_and_auditable` test are unaffected, since
  the seeded sample data is single-direction and never nets to zero in a
  group (92 → 159 passing).
- Confirmed the frontend only reads run-summary counts (`matched`, `cases`,
  `rule_version`), not the raw `matches` row shape, so the new `L2_TOLERANCE`
  / `L3_GROUP` rows and extra fields are backward compatible with no UI change needed.

## Added in this continuation (7 September 2026, fourth pass)

- Replaced every inline status assignment in `workbench/service.py`
  (`triage`, `decide`) with real calls through `core.breaks.lifecycle.transition`,
  via a small `_chain()` helper that applies a sequence of transitions
  atomically. The plan's §4.3 intermediate states (UNDER_REVIEW, APPROVED,
  RESOLVED) are now genuinely passed through and validated on every review
  action — they just resolve within one HTTP call each, so the connected
  frontend needed zero changes to its status strings or click flow.
- Implemented the previously-missing **reopen** action end to end: backend
  (`CLOSED -> REOPENED -> TRIAGED`, Controller-only, mandatory reason,
  clears the proposal/external ref, reverts explained records to
  unmatched) and a matching frontend control on closed cases, gated to the
  Controller role.
- `triage()` now also re-picks up reopened (TRIAGED-status) cases, not just
  OPEN/REJECTED/RETURNED ones.
- Added 5 new integration tests: reject/return-then-retriage cycle,
  rejecting a review on a non-PROPOSED case, reopen role/reason
  enforcement, reopen-then-retriage, and reopening a non-CLOSED case
  (92 → 163 backend tests passing).
- Verified via `tsc --noEmit`, `npm run build`, and the full Playwright
  e2e suite (both specs) that the frontend still compiles and the real
  browser flow (sample data, review, imports, audit, mobile nav, CSV
  upload) is unaffected.

## Added in this continuation (7 September 2026, fifth pass)

- New Excel (.xlsx) parser (`core/ingestion/parsers/excel_parser.py`):
  auto header-row detection (skips blank leading rows), merged-header
  forward-fill with duplicate disambiguation, trailing-blank-row
  skipping, and a `list_sheet_names` helper for a future sheet picker —
  produces the exact same `ParsedFile`/`RawRow` shape as every other
  parser. Installed the `bankformats` optional dependency group
  (openpyxl, mt-940, lxml) into the project venv.
- Added a `direction` field to the MT940 parser's output (canonical
  CR/DR derived from the raw `:61:` C/D mark), matching what CAMT.053
  already did — the raw `status` field is kept alongside it, unchanged,
  for backward compatibility.
- **Wired all four parsers into one live import path** in
  `workbench/service.py::import_csv` (CSV, MT940, CAMT053, EXCEL — Excel
  content travels base64-encoded over the same JSON transport), each with
  its own sensible default field map the caller can still override,
  exactly like the CSV path already allowed.
- Added a matching **frontend format selector** to the import dialog
  (source format dropdown, format-aware file-picker `accept` filter and
  hint text, per-format default column mapping, base64 encoding for
  Excel) — previously only CSV was reachable from the UI even though
  MT940/CAMT.053 parsers already existed unused.
- 12 new backend tests (8 Excel parser unit tests, 4 multi-format
  integration tests) — 163 → 175 backend tests passing. Verified via
  `tsc --noEmit`, `npm run build`, and the full Playwright e2e suite that
  the existing CSV flow is unaffected by the new format-selector UI.

## Added in this continuation (7 September 2026, sixth pass)

- New BAI2 parser (`core/ingestion/parsers/bai2_parser.py`) — the last
  §6.1 format still missing. Tracks group ('02') and account ('03') header
  context while walking the file so each transaction detail ('16') row
  carries its account/currency/as-of-date; handles '88' continuation
  records (appends to the previous row's narrative); converts BAI2's
  integer-cents amount encoding to a decimal string; derives a canonical
  CR/DR `direction` from the BAI2 type-code catalog (1xx-3xx credit,
  4xx-6xx debit). Row-level oddities pass through as raw strings rather
  than being rejected, matching every other parser's structure-only
  contract.
- Wired BAI2 into the same live import path as the other four formats
  (`workbench/service.py`, `workbench/app.py`) and added it to the
  frontend's format selector (default field map, file-picker `accept`
  filter, hint text).
- Fixed a test that had been using "BAI2" as its example of an
  *unsupported* format — now that BAI2 is supported, switched it to a
  still-fictional format name.
- 7 new tests (6 BAI2 parser unit tests, 1 BAI2 import integration test)
  — 175 → 182 backend tests passing. Verified via `tsc --noEmit`,
  `npm run build`, and the full Playwright e2e suite.
- **P1 ingestion's format list from §6.1 is now fully implemented** for
  everything markable "Must (v1)" or "Should (v2)" except the read-only
  REST/DB connectors and pain.002, which need a live external endpoint to
  connect to rather than being pure parsing work.

## Added in this continuation (7 September 2026, seventh pass)

- **New "Ageing" screen** (§21.3 screen 10, "Suspense & ageing" — previously
  entirely missing): a new nav item computing real ageing buckets
  (0–30/31–60/61–90/90+ days) by count and by value-per-currency, from
  actual break `created_at` timestamps — no placeholder or fabricated
  numbers. Documented in-page that this is calendar age within the current
  period, since §16 carry-forward/roll-forward isn't wired into this local
  backend yet (the standalone `core.breaks.rollforward` module exists and
  is tested, just not connected here — see the P4 row above).
- Fixed a real accuracy bug while in there: the Settings screen's
  "Matching" row still said "L1 exact · unambiguous 1:1 pairs", which
  became false the moment L2/L3 were wired into the live reconcile run —
  updated it to describe all three layers.
- Added a real Playwright e2e assertion for the new screen (not just a
  manual check): navigates to Ageing, confirms the heading, confirms the
  0–30-day bucket's count matches the open-breaks count-chip (catching any
  double-counting bug), and screenshots it. Visually reviewed the
  screenshot in a real browser render — bars, empty-bucket "—" placeholders,
  and currency-grouped totals all render correctly against real sample data
  (12 open breaks, $157,662.00 total, all in the 0–30-day bucket since
  they were just created).
- Verified via `tsc --noEmit`, `npm run build`, and the full Playwright
  e2e suite (both specs still pass) that nothing else regressed.

## Added in this continuation (7 September 2026, eighth pass)

- **New "Rule packs" screen** (§21.3 screen 14 — previously only a 2-number
  summary buried in Settings): a full page rendering the real installed
  pack manifest from the existing `GET /api/packs` endpoint — pack
  metadata (name, version, engine compatibility, description), a roles
  table (who can approve which break families, per the actual
  `RoleSpec.can_approve`/`cannot` data), and the full 48-code break type
  registry with a working family filter, risk weight, and a visible
  "never auto-match" flag for `is_sensitive` codes. Added a proper `Pack`
  TypeScript type mirroring `core/packs/manifest_schema.py::PackManifest`
  instead of the ad hoc partial shape that was there before.
- Added real Playwright e2e assertions: navigates to Rule packs, confirms
  all 48 rows render, filters to the TIM family and confirms exactly 8 rows
  (the real count from the manifest), screenshots it. Visually reviewed
  the render in a real browser — roles table, break registry, and family
  filter all display correctly against the real backend response.
- Verified via `tsc --noEmit`, `npm run build`, the full Playwright e2e
  suite, and a full backend re-run (182 passing, unchanged — no backend
  code touched this pass) that nothing regressed.

## Added in this continuation (8 September 2026, ninth pass)

- **Actually verified P0's RLS/trigger/agent-role guarantees against a live
  database for the first time.** A Postgres 16 Docker container matching
  `.data/postgres-test.env` was already present but had never had
  migrations applied (0 tables). Ran `alembic upgrade head` against it —
  both migrations applied cleanly, all 26 tables + 25 tenant-isolation
  RLS policies + the `agent_runtime` role landed correctly — then ran the
  full suite against it via the existing (but apparently never-executed)
  `scripts/Test-Database.ps1`: **187 passed, 0 skipped**, versus the usual
  182 passed / 5 skipped. The 5 newly-executed tests confirm, against a
  real database: cross-tenant RLS isolation, `audit_event` insert-only,
  `canonical_record.raw_payload` immutability, the isolating-dimension
  `match_group` block (§4.1/§4.4), and the `agent_runtime` DB role's
  read-plus-draft-only grants (§13.1).
- Found and fixed a real gap while verifying this: `Test-Database.ps1` set
  `RECON_REQUIRE_DATABASE_TESTS=1` intending to turn a skip into a hard
  failure if the database wasn't actually reachable, but nothing in the
  test suite ever read that variable — it was dead code, so the script
  could report "all passed" even if the DB connection silently failed and
  every DB test quietly skipped. Added `tests/db_gate.py` (a shared
  `skip_or_fail` helper) and wired it into both
  `tests/integration/test_rls_and_triggers.py` and
  `tests/security/test_no_write_tools.py`. Verified all three states by
  hand: skips normally with no DB and the flag unset; **fails** with the
  flag set and no DB reachable; passes with the flag set and a real DB.
- Corrected the README's own claim, which said skips are "not evidence
  RLS was verified" — true before this pass, and now updated to record
  that it *has* been verified, with the reproducible steps to redo it.
- This closes the specific "verified live RLS" gap called out in P0 for
  several passes running. It does not mean P0 is production-ready — the
  workbench that the frontend actually talks to still runs on SQLite with
  simulated roles, not this verified Postgres schema; wiring the two
  together is real repository/service-layer work, not yet done.

## Added in this continuation (8 September 2026, tenth pass)

- **Wired the EP-04 routing engine into the live triage path.** Populated
  the core pack manifest's previously-empty `routing: []` with real rules
  (every family → the generic CHECKER role core defines, plus an
  amount-escalation rule mirroring §5.1's own example: an AMT break
  ≥ 1,000,000 routes to CERTIFIER instead). `workbench/service.py::triage`
  now loads the pack once, converts its routing specs to
  `RoutingRuleFacts`, and calls `core.workflow.routing.resolve_routing`
  per case to set `owner` — replacing the hardcoded `"Reviewer"` string
  that was there regardless of the break's family or amount.
- Added 2 integration tests: a 2,000,000-amount AMT break routes to
  "Controller", a small one still routes to "Reviewer" (184 passing).
  Reran the full Playwright e2e suite (both specs pass) to confirm the
  sample workspace's break ownership — which stays "Reviewer" since its
  synthetic amounts are all small — is unaffected.
- This is still a small mechanism relative to §5.1's full routing surface
  (dimension filters, multiple packs' conflicting rules, `allow_auto_match`
  actually gating anything) — but ownership assignment in the live path is
  now genuinely rule-driven instead of a placeholder string.

## Added in this continuation (8 September 2026, eleventh pass)

- **Wired §16 roll-forward into the live `certify()` path** — another
  built-but-never-used module. `workbench/service.py::certify` previously
  blocked on *any* open break, which is stricter than §15.3 (only a
  high-risk or aged-past-policy break should block; everything else
  carries forward, §16) and made the roll-forward module structurally
  unreachable — a break could never both be "open" and "eligible to
  certify" at the same time. Fixed the actual blocking rule to match the
  spec, then call `core.breaks.rollforward.roll_forward` on every
  remaining open break: it moves into `CARRIED_FORWARD`, its `period`
  field advances to the next month (so it surfaces in that period's break
  queue, ageing view, etc. via the existing period filters — no separate
  code path needed), `original_period` and `carry_forward_count` are
  tracked, and `created_at` is preserved so age keeps accumulating instead
  of resetting.
- Found and fixed a second, related bug while wiring this: certify() also
  unconditionally blocked on *any* `UNMATCHED` record, which made the
  roll-forward path unreachable a second way (a carrying-forward break's
  own evidence records are, by definition, unmatched). Relaxed it to only
  block on an unmatched record that isn't tracked by any open break —
  i.e. one nobody has investigated yet — which is the actual failure mode
  that rule exists to catch.
- `triage()` now also picks up `CARRIED_FORWARD` cases in the period they
  rolled into, so a rolled-forward break gets re-proposed like any other
  open item rather than sitting inert.
- Updated the frontend to match: the Period-close checklist and the
  Certify button now key off "high-risk or aged breaks open" instead of
  "any breaks open," with the checklist detail line distinguishing
  blockers from carry-forward-eligible items. Visually verified in a real
  browser — the sample workspace correctly shows "5 high-risk or aged
  break(s) block certification" (its DUP-01/AMT-02 breaks are High risk).
- Added 2 integration tests: a Medium-risk open break allows
  certification and rolls forward correctly (verified id/age/count/period
  all update as expected, and it re-triages in the new period); a
  High-risk open break still blocks certification. 184 → 186 backend
  tests passing. Verified via `tsc --noEmit`, `npm run build`, and the
  full Playwright e2e suite that nothing else regressed.

## Added in this continuation (8 September 2026, twelfth pass)

- **Found and fixed a real migration bug** while verifying downgrade
  reversibility (prompted by a look at `migrations/script.py.mako`):
  `b09900336144_initial_schema.py`'s autogenerated `downgrade()` drops
  every table but never drops the 12 Postgres ENUM types SQLAlchemy
  created for their `sa.Enum(...)` columns — a known autogenerate gap.
  Confirmed by hand against the live database: `alembic downgrade base`
  succeeded and looked clean (`\dt` showed zero tables), but the *next*
  `alembic upgrade head` failed with `type "close_period_status" already
  exists`, because 12 orphaned enum types were left behind. Fixed by
  explicitly dropping all 12 by name at the end of `downgrade()`, then
  verified a full downgrade → upgrade → downgrade → upgrade cycle against
  the live database with zero errors and zero orphaned types at each step.
- Added a **permanent regression test**
  (`tests/integration/test_migration_reversibility.py`) that runs the
  actual `alembic downgrade base` → `upgrade head` cycle against a live
  database via Alembic's own command API, gated the same way as the other
  DB-only tests (skip without a database, hard-fail under
  `RECON_REQUIRE_DATABASE_TESTS=1`) and always restoring `head` in a
  `finally` block regardless of outcome, since every other DB test assumes
  a fully migrated schema.
- Fixed a `path_separator` deprecation warning in `alembic.ini` noticed
  along the way (Alembic will require it in a future version; harmless
  today but free to fix now).
- 186 → 187 backend tests (192 with the DB gate enabled) passing.

## Added in this continuation (8 September 2026, thirteenth pass)

- **Wired `core.normalization.fingerprint.compute_row_fingerprint` (§7.2)
  into live ingestion** — every imported record now carries a real
  `row_fingerprint`; found and fixed a real classification bug in
  `reconcile()`'s duplicate check while doing it: the old heuristic
  flagged two same-side records as a duplicate (DUP-01) whenever they
  shared account/currency/reference, ignoring amount and date entirely —
  so two legitimate partial payments against the same invoice reference
  would have been wrongly called a duplicate. Replaced it with a real
  fingerprint comparison (adds amount/value-date/direction to the match),
  degrading gracefully via `.get()` for any record persisted before this
  field existed. 2 new tests covering both the fixed case and the
  still-correctly-detected true-duplicate case.
- **Added a real "Run detail" view** (§21.3 screen 3): the Run history
  table's rows now expand to show a MATCHING run's actual L1/L2/L3
  rule-hit counts, computed from `state.matches` (which has carried a real
  `rule` field since the L2/L3 wiring pass, but nothing in the UI had ever
  read it) — not a placeholder. An AGENT run's row expands to its
  budget/proposed/skipped/model detail. Added an e2e assertion and
  visually confirmed against the sample workspace (68 real L1-exact
  matches shown correctly).
- 186 → 188 backend tests passing; full Playwright e2e suite green;
  `tsc --noEmit` / `npm run build` clean.
- **Wired `core.breaks.classification.BreakTypeRegistry` in too**: break
  `risk` was a hardcoded `"High" if code in ("DUP-01","AMT-02") else
  "Medium"` special case. Replaced with real risk-weight bucketing
  (weight ≥6 High, ≥3 Medium, else Low) from the same pack manifest
  already loaded for routing — any future break code the pack adds gets a
  sensible risk bucket automatically instead of silently defaulting to
  "Medium". This changed TIM-01 (registry risk_weight 2) from "Medium" to
  the more accurate "Low"; updated the one test that asserted the old
  value and confirmed the certification-blocking behavior (which only
  keys off "High") is unaffected. 188 passing, e2e suite green.
- **Wired `core.close.reconciliation.compute_unexplained` (§15.2) and
  fixed a real data-loss bug in the process**: MT940/CAMT053/BAI2 parsers
  extract a statement's self-declared opening/closing balance
  (`ParsedFile.opening_balance`/`closing_balance`) but the workbench
  parsed it and then threw it away — never stored, never shown. Now
  captured on the import batch as `statement_check`, with a real
  `unexplained` figure (opening + this batch's movement vs. the declared
  closing) computed via the actual §15.2 formula, and surfaced in the
  Import history detail panel (green "ties out exactly" vs. an amber
  gap amount) — CSV/Excel correctly show no check at all, since they
  declare no such total to verify against. 2 new backend tests (one
  exercising the real -25.50 gap in the existing MT940 fixture, one
  confirming CSV has no check); 189 passing. `tsc --noEmit`, `npm run
  build`, and the full e2e suite all clean.
- Note: this is a per-batch check (opening/closing declared by one
  statement file vs. that file's own transactions), not the full §15.2
  per-account view across multiple periods/imports that
  `AccountReconciliationFacts`/certification's `explained` field are
  ultimately meant for — that still needs an account-level data model
  the workbench doesn't have. This is the honest subset achievable with
  what already exists.

## Added in this continuation (8 September 2026, fourteenth pass — user-directed unblocking)

The user explicitly authorized three specific unblockers to close P6/P7/P9/P0/P5's remaining gaps: switch P6 to Gemini (API key supplied), generate clearly-labeled mock data for P7/P9, and add standard local-dev infrastructure defaults for P0/P5.

- **P6 LLM — real, working, verified against the live API** (not mocked): `core/agent/llm/` (`base.py`'s provider-neutral `LLMProvider` protocol, `gemini_provider.py`'s REST-based Gemini implementation, `narrative.py`'s §13.2 untrusted-envelope prompt construction + §13.5 deterministic fallback), wired into `workbench/service.py::triage`. Validated the supplied key by hand against the real API first (the model name it was originally tried with had been retired; the API's own error message named the current one, `gemini-3.6-flash`) before building on it. A real AMT-02 discrepancy produced an accurate, well-reasoned investigation note through the full pipeline. `tests/conftest.py` forces the key empty for the automated suite (a real .env key was seen leaking into a test run and hanging on live network calls before this fix) — LLM behavior is tested via a fake provider instead, so the suite stays fast, free and deterministic.
- **P7 scoring — the real calibration/circuit-breaker code exercised against a clearly-labeled synthetic dataset** (`workbench/mock_data.py`, `synthetic: true` throughout, never silently presented as real): isotonic calibration fit on a train split, evaluated on a held-out test split, feeding the real `expected_calibration_error`/`reliability_diagram`/circuit-breaker functions. Surfaced on a new **Model governance** screen (§21.3 screen 16).
- **P9 pilot — a clearly-labeled dummy tenant** (`is_dummy: true`, status `NOT_ONBOARDED`) on a new **Pilot** screen; its "activity to date" numbers are real data from the local workspace, not fabricated pilot KPIs.
- **P0/P5 local infrastructure** — `docker-compose.yml` (Postgres + Redis, matching `core/config.py`'s own defaults so zero further config is needed) and `workbench/scheduler.py` (a Celery beat schedule running the same `reconcile`/`triage` functions the UI calls, against every open period in the actual workbench store). Verified against **real** infrastructure, not just logic tests: started Redis via compose, ran a real Celery worker, dispatched a real task through it, and confirmed it discovered and processed genuine open periods from the live local database.
- 12 dashboard screens now connected (was 9): added Model governance and Pilot.
- Found and fixed 2 more real bugs while wiring this: `triage()`'s run/proposal metadata read the *configured* model name instead of the actual provider instance's model (would silently misreport if they ever diverged); a real `.env`-sourced API key leaking into the test suite caused a 120-second hang on live network calls until `conftest.py` was added.
- 217 backend tests passing (up from 205 before this pass), full Playwright e2e suite green (including new assertions for both new screens), `tsc --noEmit`/`npm run build` clean throughout.

## Added in this continuation (8 September 2026, fifteenth pass — remaining screens)

- **4 more screens, all real data, zero fabrication**: Universe board (§21.3 screen 2 — per-period matched %, break count/value, ageing, autonomy, last run, all computed from real workspace data; core ships no named universes of its own, so this reflects the one implicit SOURCE_A/SOURCE_B pairing workbench actually reconciles), Approval queue (screen 8 — every case awaiting a checker action, across every period, not just the selected one), Certification pack (screen 12 — a real preview of what "Download evidence bundle" contains), Admin (screen 18 — the actual `core.config.get_settings()` values behind matching/budgets/ageing/scheduling, via a new `GET /api/admin-config` endpoint, plus the pack's real roles/routing).
- Found and fixed a real layout bug while building these: the sidebar has no `overflow-y`, and going from 10 to 14 nav items pushed "Workspace settings" and the profile control off-screen with no way to reach them — caught by the existing e2e test failing on a real "element is outside of the viewport" error, not by inspection. Fixed with `overflow-y:auto` on `.sidebar`.
- Found and fixed a second bug: the new Admin screen's roles table was blank because its pack-manifest fetch effect only fired for the Settings/Rule-packs pages, not Admin.
- **All 18 of §21.3's screens are now connected except Match canvas (screen 6) and Journal drafts (screen 9)** — both are real, separate feature builds (a manual group-matching override UI, and the internal-subledger draft/submit/approve/post lifecycle), not more wiring of what already exists.
- 218 backend tests passing, full e2e suite green (with new assertions for all four screens), `tsc --noEmit`/`npm run build` clean.

## Added in this continuation (8 September 2026, sixteenth pass — the last two screens)

- **Journal drafts (§21.3 screen 9 / §14.1's internal subledger path) built end-to-end, not just wired**: new backend functions `create_journal_draft` (maker drafts a correcting entry against an ACTION_PENDING case; rejects unbalanced debits/credits, missing account roles, non-positive amounts, or a second draft while one is already awaiting review) and `decide_journal_draft` (a distinct checker approves or rejects; approval is the *only* thing that posts — there is still no `post_journal` tool anywhere in the codebase for a human or agent to call directly, §12.3's guardrail holds). Approval automatically resolves and closes the linked case, mirroring the external-reference close path but with the journal draft itself as the evidence. Added a `journal_drafts` key to the store's state shape, with a migration helper (`store._migrate`) so a database created before this key existed doesn't `KeyError` — verified against the actual running dev database, not just fresh test databases.
- **Match canvas (§21.3 screen 6) built on a new §22 API surface that didn't exist at all**: `create_manual_match` (a human groups unmatched records the deterministic layers didn't — same net-zero-within-tolerance and same-currency/cross-side rules as automatic group matching, §4.4) and `unmatch` (reason mandatory, reverses a match without deleting its audit history). The UI shows a live net-amount indicator as records are selected, using the exact same CR-positive/DR-negative convention as the real backend check, so what the canvas shows is what the server will actually accept.
- Both features **verified against the real running application**, not just the test suite: scripted a full browser session for each — import two sides, approve a proposal, fill in a journal draft, switch role, approve and watch it post and close the case; separately, select two unmatched records on the Match canvas, confirm the match, then unmatch it — and confirmed the real UI state (badges, toasts, record statuses) matched at every step via screenshots.
- 8 new backend tests (journal draft balance/role/timing validation and the approve/reject paths; manual match net-zero validation and unmatch-twice rejection). 225 backend tests passing, full e2e suite green, `tsc --noEmit`/`npm run build` clean.
- **This closes out §21.3 completely — all 18 screens are now connected to real or clearly-labeled-synthetic data.** What's left in the document past this point is no longer "build the next screen" — it's real auth, the ORM/Postgres data path replacing the local SQLite workbench, a real LLM knowledge corpus for RAG, and things that need people (a pilot customer, real historical match data) rather than more code.

## Added in this continuation (8 September 2026, seventeenth pass — real cost/token metering)

- **§21.5/§24 "cost per case" now uses real numbers, not estimates**: `GeminiProvider` captures the actual `usageMetadata` from every Gemini response (input tokens, output tokens, and thinking tokens broken out separately, since this model spends real output-token budget on an internal reasoning pass before its visible answer). `workbench/service.py::triage` accumulates this per run and computes §24's own target metric — LLM-touched breaks share ≤ 12% — against the real configured threshold (`AgentBudgets.llm_touched_breaks_max_share`), firing a genuine `agent.llm_touched_share.exceeded` audit event on breach (not a hardcoded 12%, whatever the config says). Surfaced in the Agent activity run detail with a visible warning badge when exceeded.
- Verified against the real API, not mocked: a real triage call used 285 input / 93 output tokens and correctly flagged 100% > 12% as a breach, confirmed both via direct API inspection and a real browser screenshot of the rendered warning.
- 3 new backend tests (real token accumulation via a fake provider exposing `last_usage`, the breach-detection math, and the audit event) plus 2 new Gemini-provider unit tests (usage capture, and graceful zero-default when a response omits `usageMetadata`). 228 backend tests passing, full e2e suite green.

## Added in this continuation (8 September 2026, eighteenth pass — real authentication)

- **§6/§18 identity is now real, not a client-trusted header**: added `backend/workbench/auth.py` — PBKDF2-HMAC-SHA256 password hashing (100k iterations, per-user salt), JWT session tokens (HS256, 8-hour expiry, `RECON_JWT_SECRET` override), and a fixed three-account demo roster (`analyst`/`reviewer`/`controller`, one per simulation role) seeded once per process.
- Added `POST /api/auth/login` (`backend/workbench/app.py`) returning a signed token plus the account's actor/role/display name. Every mutating route now derives its actor via `require_actor()`, which verifies the `Authorization: Bearer <token>` signature and checks the username against `service.ACTORS` — replacing the old `X-Actor` header that any client could set to any value. An unauthenticated or forged-identity request now gets a real 401, not a permissive 403-with-a-note.
- Fixed a real performance bug found while wiring this in: naive password seeding on every store read would have added ~1.8s (3× PBKDF2) to every single API request. Fixed by caching the seeded roster via `@lru_cache` in `store.py` and only computing it once per process, with `_migrate()` touching the expensive `users` default only when actually absent from a loaded state — 20 subsequent reads dropped from 1.8s to 0.016s total.
- Frontend: replaced the "simulation role" dropdown with a real login screen (`App.tsx`) that calls `/api/auth/login`, stores the returned JWT in `localStorage`, and sends it as `Authorization: Bearer <token>` on every mutation; a 401 response signs the session out automatically. The topbar now shows the signed-in account's real display name and role with a **Sign out** control instead of a role selector.
- Updated `docs`/`README.md`'s local-evaluation-boundary language: the mechanism (hashing, signature verification, expiry) is now real; only the account roster behind it is a fixed local seed, not a production identity provider.
- Test suite: added `backend/tests/unit/test_auth.py` (12 tests covering hashing, token round-trip/tamper/expiry/wrong-secret rejection, and `authenticate()`), plus login/auth-boundary integration tests in `test_workbench.py` (successful login + mutation, wrong password, unknown username, missing/forged/unauthenticated requests all rejected). The integration suite's `post()` helper now logs in and caches a token per (client, actor) pair instead of trusting a header — no other test call site needed to change. 242 backend tests passing (0 regressions), full e2e suite green after rewriting the two role-switch steps in `workspace.spec.ts` to sign out and sign back in as a different demo account instead of selecting from a dropdown.

## Added in this continuation

- Responsive frontend and a running FastAPI local workspace.
- Transactional persistence across page refreshes and process restarts.
- Source CSV import, column mapping, decimal controls, idempotency, hold/rejection evidence.
- Exact matching that refuses ambiguous duplicate keys and obeys isolation fields.
- Deterministic investigation proposals and record evidence.
- Separate maker, checker and certifier permissions with server-side enforcement, tied to real signed-in accounts (not a client-trusted role header).
- Human reasons and external references before local case closure.
- Human certification and period locking.
- Hash-chain verification and evidence bundle with checksum.
- Test coverage for import, matching, review, closure, rejection and certification controls; desktop/mobile UI checks.

The local evaluation service intentionally lives outside `core/`. It does not silently substitute SQLite or a fixed local account roster for the PostgreSQL/RLS and production identity-provider architecture in the plan.
