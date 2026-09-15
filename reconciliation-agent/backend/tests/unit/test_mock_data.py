from __future__ import annotations

from workbench.mock_data import model_governance_snapshot, pilot_tenant_snapshot


def test_model_governance_snapshot_is_labeled_synthetic():
    snapshot = model_governance_snapshot()
    assert snapshot["synthetic"] is True
    assert "no real historical match dispositions" in snapshot["note"].lower()


def test_model_governance_calibration_reduces_ece_versus_raw():
    snapshot = model_governance_snapshot()
    assert snapshot["calibrated_ece"] < snapshot["raw_ece"]


def test_model_governance_reliability_diagram_covers_all_test_samples():
    snapshot = model_governance_snapshot()
    assert sum(b["count"] for b in snapshot["reliability_diagram"]) == snapshot["sample_size"]["test"]


def test_model_governance_is_deterministic_across_calls():
    a = model_governance_snapshot()
    b = model_governance_snapshot()
    assert a["raw_ece"] == b["raw_ece"]
    assert a["calibrated_ece"] == b["calibrated_ece"]


def test_pilot_tenant_snapshot_is_labeled_dummy():
    snapshot = pilot_tenant_snapshot({"breaks": [], "runs": [], "imports": []})
    assert snapshot["is_dummy"] is True
    assert snapshot["tenant"]["status"] == "NOT_ONBOARDED"


def test_pilot_tenant_snapshot_activity_reflects_real_state():
    state = {
        "breaks": [{"status": "OPEN"}, {"status": "CLOSED"}],
        "runs": [{"kind": "AGENT"}, {"kind": "MATCHING"}, {"kind": "MATCHING"}],
        "imports": [{}, {}],
    }
    snapshot = pilot_tenant_snapshot(state)
    assert snapshot["activity_to_date"] == {
        "imports": 2, "breaks_created": 2, "breaks_resolved": 1,
        "agent_runs": 1, "reconciliation_runs": 2,
    }
