import json
import threading

import pytest

from sampling.audit_trail import AuditTrail, GENESIS_HASH


def test_five_events_chain_and_verify(tmp_path):
    trail = AuditTrail(str(tmp_path / "trail.jsonl"), tenant_id="t1")
    for i in range(5):
        trail.append("auditor1", "test.action", f"subject{i}", {"i": i})
    report = trail.verify()
    assert report.valid is True
    assert report.events_checked == 5


def test_altering_payload_is_caught_with_correct_sequence(tmp_path):
    path = tmp_path / "trail.jsonl"
    trail = AuditTrail(str(path), tenant_id="t1")
    for i in range(5):
        trail.append("auditor1", "test.action", f"subject{i}", {"i": i})

    lines = path.read_text(encoding="utf-8").splitlines()
    event = json.loads(lines[2])
    event["payload"] = {"i": 999}
    lines[2] = json.dumps(event)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = trail.verify()
    assert report.valid is False
    assert report.first_invalid_sequence == 2
    assert report.reason == "content altered"


def test_deleting_event_caught_as_sequence_gap(tmp_path):
    path = tmp_path / "trail.jsonl"
    trail = AuditTrail(str(path), tenant_id="t1")
    for i in range(5):
        trail.append("auditor1", "test.action", f"subject{i}", {"i": i})

    lines = path.read_text(encoding="utf-8").splitlines()
    del lines[2]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = trail.verify()
    assert report.valid is False
    assert report.reason in ("sequence gap", "chain break: previous_hash mismatch")


def test_empty_trail_verifies():
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        trail = AuditTrail(os.path.join(d, "trail.jsonl"), tenant_id="t1")
        report = trail.verify()
        assert report.valid is True
        assert trail.head_hash() == GENESIS_HASH


def test_concurrent_appends_produce_contiguous_verifiable_chain(tmp_path):
    trail = AuditTrail(str(tmp_path / "trail.jsonl"), tenant_id="t1")
    errors = []

    def worker(i):
        try:
            trail.append("auditor1", "test.action", f"subject{i}", {"i": i})
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    report = trail.verify()
    assert report.valid is True
    assert report.events_checked == 50
    sequences = sorted(e.sequence for e in trail.events())
    assert sequences == list(range(50))


def test_for_subject_filters():
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        trail = AuditTrail(os.path.join(d, "trail.jsonl"), tenant_id="t1")
        trail.append("a", "act", "subjectA", {})
        trail.append("a", "act", "subjectB", {})
        trail.append("a", "act", "subjectA", {})
        events = trail.for_subject("subjectA")
        assert len(events) == 2
