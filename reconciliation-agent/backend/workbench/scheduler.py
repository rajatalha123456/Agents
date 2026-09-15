"""
§11.1 `schedule.cron` trigger, as a local-dev default: a Celery beat
schedule that periodically runs the exact same `reconcile`/`triage`
functions the UI calls, against the same local SQLite workbench store —
not a second, parallel pipeline. Standard local defaults, per the team's
own framing: a developer runs `docker compose up -d redis` (see
docker-compose.yml) and then

    celery -A workbench.scheduler worker --beat --loglevel=info

from `backend/`, and every open period gets reconciled and triaged on an
interval instead of only when a human clicks the buttons.

The actual work is factored into `run_scheduled_cycle_sync`, callable and
testable with zero Celery/Redis dependency — the Celery task is a thin
wrapper around it, not where the logic lives.
"""
from __future__ import annotations

import os
from pathlib import Path

from celery import Celery

from workbench import service
from workbench.store import Store

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
SCHEDULE_INTERVAL_SECONDS = float(os.environ.get("RECON_SCHEDULE_INTERVAL_SECONDS", "300"))
# The local simulation identity a scheduled run acts as (§11.1's trigger
# is automatic, but every workbench mutation still needs one of the three
# simulation roles — this is not a claim that "analyst" is a real user).
SCHEDULED_ACTOR = "analyst"

_DEFAULT_DB_PATH = str(Path(__file__).resolve().parents[2] / ".data" / "workbench.sqlite3")

app = Celery("reconciliation_agent", broker=REDIS_URL, backend=REDIS_URL)
app.conf.timezone = "UTC"
app.conf.beat_schedule = {
    "scheduled-reconciliation-and-triage": {
        "task": "workbench.scheduler.run_scheduled_cycle",
        "schedule": SCHEDULE_INTERVAL_SECONDS,
    },
}


def _store() -> Store:
    return Store(os.environ.get("RECON_WORKBENCH_DB", _DEFAULT_DB_PATH))


def _candidate_periods(state: dict) -> list[str]:
    """Every period with data, except one already certified (§4.3's
    CERTIFIED/LOCKED periods reject further mutation via `ensure_open`
    anyway — skipping them here avoids raising and catching that on
    every single cycle for a period that will never need it again).
    """
    periods = {r["period"] for r in state["records"]} | {b["period"] for b in state["breaks"]}
    open_periods = {p for p in periods if state["periods"].get(p, {}).get("status") != "CERTIFIED"}
    return sorted(open_periods)


def run_scheduled_cycle_sync() -> dict:
    store = _store()
    summary: dict = {"periods_processed": [], "reconcile_runs": 0, "agent_runs": 0, "skipped": [], "errors": []}
    for period in _candidate_periods(store.read()):
        summary["periods_processed"].append(period)
        try:
            with store.transaction() as state:
                service.reconcile(state, SCHEDULED_ACTOR, period)
            summary["reconcile_runs"] += 1
        except ValueError:
            # Nothing left to reconcile this cycle (already matched, or no
            # unmatched records) — an expected steady state, not a failure.
            summary["skipped"].append(f"{period}: reconcile — nothing unmatched")
        try:
            with store.transaction() as state:
                service.triage(state, SCHEDULED_ACTOR, period)
            summary["agent_runs"] += 1
        except ValueError as exc:
            summary["errors"].append(f"{period}: triage — {exc}")
    return summary


@app.task(name="workbench.scheduler.run_scheduled_cycle")
def run_scheduled_cycle() -> dict:
    return run_scheduled_cycle_sync()
