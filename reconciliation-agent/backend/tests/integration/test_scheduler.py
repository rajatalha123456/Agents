"""
§11.1's schedule.cron trigger, exercised without any Celery/Redis
dependency — `run_scheduled_cycle_sync` is plain Python over the same
Store/service functions the API uses, and the Celery task is a one-line
wrapper around it (see workbench/scheduler.py's docstring). Real broker
behavior (Celery beat actually firing on schedule, a worker picking the
task up) needs a live Redis and is out of scope for the automated suite —
this proves the scheduled *work* is correct.
"""
from __future__ import annotations

from workbench import scheduler, service
from workbench.store import Store


def _seeded_store(tmp_path):
    store = Store(str(tmp_path / "scheduler_test.sqlite3"))
    header = "amount,currency,direction,value_date,reference,description\n"
    with store.transaction() as state:
        service.import_csv(state, "analyst", filename="a.csv", content=header + "10,USD,CR,2026-09-01,R1,Example\n",
                            side="SOURCE_A", account="Operating", period="2026-09")
    with store.transaction() as state:
        service.import_csv(state, "analyst", filename="b.csv", content=header + "9,USD,CR,2026-09-01,R1,Example\n",
                            side="SOURCE_B", account="Operating", period="2026-09")
    return store


def test_scheduled_cycle_reconciles_and_triages_an_open_period(tmp_path, monkeypatch):
    store = _seeded_store(tmp_path)
    monkeypatch.setattr(scheduler, "_store", lambda: store)

    summary = scheduler.run_scheduled_cycle_sync()

    assert "2026-09" in summary["periods_processed"]
    assert summary["reconcile_runs"] == 1
    assert summary["agent_runs"] == 1
    assert summary["errors"] == []

    state = store.read()
    assert state["breaks"][0]["status"] == "PROPOSED"  # triage ran and produced a proposal


def test_scheduled_cycle_skips_reconcile_once_everything_is_matched(tmp_path, monkeypatch):
    # Unlike the mismatched-amount fixture above (which leaves both
    # records permanently UNMATCHED — that's the whole point of an AMT-02
    # break), an exact match clears every record to MATCHED after one
    # cycle, so a second reconcile() call has nothing left to do.
    store = Store(str(tmp_path / "matched.sqlite3"))
    header = "amount,currency,direction,value_date,reference,description\n"
    with store.transaction() as state:
        service.import_csv(state, "analyst", filename="a.csv", content=header + "10,USD,CR,2026-09-01,R1,Example\n",
                            side="SOURCE_A", account="Operating", period="2026-09")
    with store.transaction() as state:
        service.import_csv(state, "analyst", filename="b.csv", content=header + "10,USD,CR,2026-09-01,R1,Example\n",
                            side="SOURCE_B", account="Operating", period="2026-09")
    monkeypatch.setattr(scheduler, "_store", lambda: store)

    first = scheduler.run_scheduled_cycle_sync()
    assert first["reconcile_runs"] == 1

    second = scheduler.run_scheduled_cycle_sync()
    assert second["reconcile_runs"] == 0
    assert any("nothing unmatched" in s for s in second["skipped"])
    assert second["errors"] == []


def test_scheduled_cycle_skips_certified_periods(tmp_path, monkeypatch):
    store = _seeded_store(tmp_path)
    monkeypatch.setattr(scheduler, "_store", lambda: store)
    with store.transaction() as state:
        state["periods"]["2026-09"] = {"status": "CERTIFIED", "actor": "controller", "created_at": "x", "reason": "done"}

    summary = scheduler.run_scheduled_cycle_sync()
    assert summary["periods_processed"] == []


def test_scheduled_cycle_handles_an_empty_workspace(tmp_path, monkeypatch):
    store = Store(str(tmp_path / "empty.sqlite3"))
    monkeypatch.setattr(scheduler, "_store", lambda: store)
    summary = scheduler.run_scheduled_cycle_sync()
    assert summary["periods_processed"] == []
    assert summary["errors"] == []
