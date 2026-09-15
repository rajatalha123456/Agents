# Reconcile

A reconciliation backend and a connected React operations workspace, based on Build Plan v3.

## Open the application

Frontend: **http://127.0.0.1:5178**  
API documentation: **http://127.0.0.1:8765/docs**

On Windows, double-click **Start-Reconcile.cmd** after installing dependencies. It starts both services in the background, with logs in `.data/`, and prints their addresses. It does not stop services already running on those ports.

Or use two terminals from the repository root:

```powershell
# Terminal 1
.\.venv\Scripts\python.exe -m uvicorn workbench.app:app --app-dir backend --host 127.0.0.1 --port 8765
```

```powershell
# Terminal 2
cd frontend
npm.cmd run dev
```

## Install dependencies

Python 3.11+ (3.12 recommended), Node.js 22+ and npm are required.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,bankformats]"
cd frontend
npm.cmd ci --cache .npm-cache
```

Add the `jobs` extra (`pip install -e ".[dev,bankformats,jobs]"`) if you want to run the local Celery scheduler described below.

The frontend lockfile is committed for reproducible npm installs. `npm.cmd` avoids PowerShell's restriction on executing `npm.ps1`.

## Try the connected workflow

1. Sign in as **analyst** / `analyst-demo-pass` (see **Authentication** below for all three demo accounts).
2. Open the workspace and choose **Load sample workspace**, or import a CSV for each source. Samples are synthetic and explicitly labelled.
3. As the analyst (MAKER), import, run reconciliation and run the deterministic agent.
4. Open **Break queue** and inspect a case's source evidence and proposal.
5. Sign out and sign back in as **reviewer** / `reviewer-demo-pass` (CHECKER) to approve, return or reject with a reason. Approval moves a case to action pending. It does not post a financial entry.
6. Record a verified external action/evidence reference and reason to close the case.
7. Once all records are matched or explained, all breaks are resolved and held imports are addressed, sign in as **controller** / `controller-demo-pass` (CERTIFIER) to certify the period.
8. Inspect **Audit trail** or download the evidence bundle. Certified periods are locked against further mutations.

The UI includes Overview, Break queue, Ageing, Imports with column mapping and validation details, Agent activity (with a per-run match-layer breakdown), Period close, Audit trail, Rule packs, Model governance, Pilot, Settings, and a responsive break-review drawer. Search, queue filters, period selection, exports, imports and decisions are wired to the API.

## CSV contract

One account and period per file. Select the same account on both source imports. The field mapping maps canonical fields to exact source headers.

```csv
amount,currency,direction,value_date,reference,description
1250.00,USD,CR,2026-09-01,INV-1001,Customer settlement
25.00,USD,DR,2026-09-02,FEE-1001,Processing charge
```

- Amounts: nonnegative decimal strings, up to 20 integer and 8 fractional digits. No thousands separators, scientific notation in the UI, or floating-point monetary arithmetic.
- Direction: `CR` or `DR`. Both sources must use the same accounting sign convention; direction inversion is not inferred.
- Dates: `YYYY-MM-DD`, within the selected `YYYY-MM` period.
- Currency: recognized ISO currency code. Reference must normalize to a nonempty alphanumeric value.
- Description is optional. Its header can be mapped or absent.
- Maximum upload: 2 MB. Invalid rows hold the entire batch; no partial records commit.
- Optional declared row count is checked. Decimal debit/credit totals are shown per currency; currencies are never netted together.
- Identical bytes for the same account/side/period produce the same batch identity. Changed mapping alone does not create a new import. To correct a held import, reject it with a reason and supply corrected source bytes; in-place remapping/revalidation is not implemented yet.
- Held/rejected batch sources and errors remain available in evidence exports. Rejection does not delete source evidence.

## Local evaluation boundary

**This workspace is not the finished production system in Build Plan v3.**

`backend/workbench/` is an explicitly isolated, loopback-only evaluation API. It uses transactional SQLite storage at `.data/workbench.sqlite3`, supports one local workspace, and requires signing in as one of three fixed demo accounts (see **Authentication** below). Those accounts are real credentials with a real signed session — the mechanism is production-shaped — but the roster behind them is a fixed local seed, not a production identity provider or user-management system. Do not expose this API on a network or put real production financial data into it. The SQLite store is not encrypted or protected by PostgreSQL RLS. Its audit hashes detect content changes but are not an independently anchored immutable archive.

The existing production-oriented SQLAlchemy models and PostgreSQL migrations remain in `backend/core/models/` and `backend/migrations/`. They are not replaced by the local store. Set `RECON_WORKBENCH_DB` to use another evaluation database.

The local matching flow implements exact (L1), tolerance (L2) and group (L3) matching, each layer only acting on what the previous layer left unmatched. Proposal narratives use Gemini when `GEMINI_API_KEY` is configured (see below), falling back to deterministic templates otherwise — this is not the full RAG-backed pipeline with citations/traces, since no knowledge corpus exists yet. Calibration and the false-match circuit breaker run on a clearly-labeled synthetic dataset (Model governance screen), since no real historical match dispositions exist. The 48-code registry is loaded from the existing pack.

Production RBAC/RLS wiring, bank-format UI polish, comprehensive account-close balances, RAG ingestion/retrieval, pack activation workflows and production operations remain to be implemented. See [implementation status](docs/IMPLEMENTATION_STATUS.md).

## Local infrastructure defaults

None of these are required to run the connected workbench above — it works standalone on SQLite with deterministic templates and a built-in login screen. They exist as standard local-dev defaults for the pieces that otherwise need external infrastructure.

**Authentication.** The workbench requires a real sign-in — there is no way to mutate the workspace without it. Three fixed demo accounts are seeded on first run (`backend/workbench/auth.py::seed_users`):

| Username | Password | Role |
|---|---|---|
| `analyst` | `analyst-demo-pass` | MAKER |
| `reviewer` | `reviewer-demo-pass` | CHECKER |
| `controller` | `controller-demo-pass` | CERTIFIER |

`POST /api/auth/login` verifies the password (PBKDF2-HMAC-SHA256, per-user salt) and returns a signed JWT (`RECON_JWT_SECRET` overrides the local-dev default secret; 8-hour expiry). Every mutating route derives the acting user from that token's verified signature — never from a client-supplied header — via `backend/workbench/app.py::require_actor`. The frontend's login screen stores the token in `localStorage` and sends it as `Authorization: Bearer <token>`; signing out clears it. This is still the local-evaluation boundary described above: real password hashing and signature verification, against a fixed non-production roster.

**LLM (Gemini).** Create a `.env` file at the repo root (gitignored, never committed):

```
GEMINI_API_KEY=your-key-here
```

With a key configured, `workbench/service.py::triage` drafts break narratives with Gemini (`core/agent/llm/`, a provider-neutral adapter — `core/agent/llm/base.py::LLMProvider` is the whole interface a different provider would implement) instead of the deterministic templates, wrapping all transaction data in an untrusted-data envelope per §13.2. Any failure (missing key, network error, malformed response) falls back to the deterministic template automatically — the core reconciliation flow never blocks on an LLM being reachable. The automated test suite never calls the real API (`backend/tests/conftest.py` forces the key empty for every test); LLM behavior is tested against a fake provider.

**Postgres + Redis.** `docker compose up -d` starts a local Postgres (matching `core/config.py`'s default `database_url` — zero further config needed) and a local Redis (matching `workbench/scheduler.py`'s default broker). Apply migrations with `cd backend && ../.venv/Scripts/python.exe -m alembic upgrade head`.

**Scheduled agent runs (Celery).** With Redis running, `cd backend && ../.venv/Scripts/python.exe -m celery -A workbench.scheduler worker --beat --loglevel=info` runs the same `reconcile`/`triage` functions the UI calls on an interval (`RECON_SCHEDULE_INTERVAL_SECONDS`, default 300s) against every open period in the workbench's own SQLite store — §11.1's `schedule.cron` trigger, as a local default, not a second pipeline. `workbench/scheduler.py::run_scheduled_cycle_sync` is the actual logic and is tested with zero Celery/Redis dependency; the Celery task is a one-line wrapper around it.

## Verify

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
cd frontend
npm.cmd run build
npm.cmd run test:e2e
```

UI tests expect both local servers to be running and Google Chrome installed. They use a seeded local sample workspace and simulate a review decision; use a separate `RECON_WORKBENCH_DB` if you want to keep your evaluation data independent. Screenshots are written to `frontend/test-results/`.

PostgreSQL tests skip when no live migrated database is configured — a skip is not evidence RLS was verified. To actually verify it, start a Postgres 16 container with the credentials in `.data/postgres-test.env` on `127.0.0.1:55432`, then run `scripts/Test-Database.ps1` (Windows) — it runs `alembic upgrade head` against it and re-runs the full suite with `RECON_REQUIRE_DATABASE_TESTS=1`, which turns the DB-dependent tests' skip into a hard failure if the database isn't actually reachable, so a broken setup can't silently report as "passing." This has been run and passes: cross-tenant RLS isolation, `audit_event` insert-only, `canonical_record.raw_payload` immutability, the isolating-dimension `match_group` block, and the `agent_runtime` role's read+draft-only grants are all confirmed against a live, migrated database, not just asserted in code.

## Repository

- `frontend/src/App.tsx`: connected screens and interactions.
- `frontend/src/styles.css`: visual system and responsive layouts.
- `backend/workbench/`: local API, transaction store and workflow integration; `mock_data.py` (labeled synthetic calibration/pilot data) and `scheduler.py` (Celery local scheduling default) live here too.
- `backend/core/`: existing domain-neutral services plus matching, breaks, workflow and close logic; `core/agent/llm/` is the provider-neutral LLM adapter (Gemini implementation included).
- `backend/packs/core/manifest.yaml`: core registry, roles and routing rules.
- `backend/tests/`, `frontend/tests/`: backend control tests and UI workflow checks.
- `docker-compose.yml`: local Postgres + Redis defaults.
- `docs/Reconciliation_Agent_Plan_v3_full.md`: full source plan supplied by the user.
