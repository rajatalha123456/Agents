import pytest
from fastapi.testclient import TestClient

from workbench.app import create_app
from workbench.auth import create_token


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(str(tmp_path / "test.sqlite3")))


_DEMO_PASSWORDS = {"analyst": "analyst-demo-pass", "reviewer": "reviewer-demo-pass", "controller": "controller-demo-pass"}
_token_cache: dict[tuple[int, str], str] = {}


def _token_for(client, actor):
    key = (id(client), actor)
    if key not in _token_cache:
        response = client.post(
            "/api/auth/login",
            json={"username": actor, "password": _DEMO_PASSWORDS[actor]},
            headers={"X-Workspace-Client": "reconcile-local"},
        )
        assert response.status_code == 200, response.text
        _token_cache[key] = response.json()["access_token"]
    return _token_cache[key]


def post(client, url, body=None, actor="analyst"):
    token = _token_for(client, actor)
    return client.post(
        "/api/" + url,
        json=body or {},
        headers={"Authorization": f"Bearer {token}", "X-Workspace-Client": "reconcile-local"},
    )


def csv_body(content=None, side="SOURCE_A"):
    return {"filename": "source.csv", "side": side, "account": "Operating", "period": "2026-09", "content": content or "amount,currency,direction,value_date,reference,description\n10,USD,CR,2026-09-01,R1,Example\n"}


SAMPLE_MT940 = """\
:20:REF001
:25:1234567890
:28C:1
:60F:C260101USD1000,00
:61:2601020102C50,00NTRFNONREF//ext-ref-1
:86:PAYMENT FROM JOHN DOE INV-100
:62F:C260102USD1024,50
-
"""

SAMPLE_BAI2 = "\r\n".join([
    "01,SENDER,RECEIVER,260902,0800,0001,80,,2/",
    "02,RECEIVER,SENDER,1,260902,0800,USD,/",
    "03,1234567890,USD,010,150000,,/",
    "16,115,5000,,BANKREF1,CUSTREF1,PAYMENT FROM JOHN DOE/",
    "16,451,2500,,BANKREF2,CUSTREF2,SERVICE FEE/",
    "49,7500,3/",
    "98,7500,1,5/",
    "99,7500,1,7/",
]) + "\r\n"

SAMPLE_CAMT053 = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">
  <BkToCstmrStmt>
    <Stmt>
      <Id>STMT001</Id>
      <Acct><Id><IBAN>DE1234567890</IBAN></Id></Acct>
      <Ntry>
        <Amt Ccy="EUR">50.00</Amt>
        <CdtDbtInd>CRDT</CdtDbtInd>
        <Sts>BOOK</Sts>
        <BookgDt><Dt>2026-01-02</Dt></BookgDt>
        <ValDt><Dt>2026-01-02</Dt></ValDt>
        <AcctSvcrRef>ext-ref-1</AcctSvcrRef>
        <NtryDtls><TxDtls>
          <Refs><EndToEndId>INV-100</EndToEndId></Refs>
          <RmtInf><Ustrd>PAYMENT FROM JOHN DOE INV-100</Ustrd></RmtInf>
        </TxDtls></NtryDtls>
      </Ntry>
    </Stmt>
  </BkToCstmrStmt>
</Document>
"""


def test_import_retry_persists_once_and_reloads(client):
    first = post(client, "imports", csv_body()).json()
    retry = post(client, "imports", csv_body()).json()
    assert first["batch"]["status"] == "COMMITTED"
    assert retry["duplicate"] is True
    assert len(client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()["records"]) == 1
    other = TestClient(create_app(client.app.state.store.path))
    assert len(other.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(other, 'analyst')}"}).json()["records"]) == 1


def test_bad_row_holds_whole_batch_and_keeps_evidence(client):
    body = csv_body()
    body["content"] += "oops,USD,CR,2026-09-01,R2,Bad row\n"
    response = post(client, "imports", body).json()
    assert response["batch"]["status"] == "HELD"
    assert response["batch"]["errors"][0]["line"] == 3
    assert client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()["records"] == []


def test_matching_and_close_workflow_enforce_human_roles(client):
    post(client, "imports", csv_body())
    body = csv_body(side="SOURCE_B")
    body["content"] = body["content"].replace("10,USD", "9,USD")
    post(client, "imports", body)
    assert post(client, "reconcile", {"period": "2026-09"}).status_code == 200
    assert post(client, "agent-runs", {"period": "2026-09"}).status_code == 200
    case = client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()["breaks"][0]
    assert case["code"] == "AMT-02"
    decision = {"action": "APPROVE", "reason": "Evidence reviewed"}
    url = f"breaks/{case['id']}/decisions"
    assert post(client, url, decision).status_code == 403
    assert post(client, "certify", {"period": "2026-09", "reason": "Reviewed"}, "controller").status_code == 422
    assert post(client, url, decision, "reviewer").json()["status"] == "ACTION_PENDING"
    assert post(client, url, {"action": "CLOSE", "reason": "Correction verified"}, "reviewer").status_code == 422
    assert post(client, url, {"action": "CLOSE", "reason": "Correction verified", "external_ref": "ERP-123"}, "reviewer").json()["status"] == "CLOSED"
    assert post(client, "certify", {"period": "2026-09", "reason": "All source evidence and decisions reviewed"}, "controller").status_code == 200
    assert post(client, "imports", csv_body()).status_code == 422
    assert post(client, "agent-runs", {"period": "2026-09"}).status_code == 422
    state = client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()
    assert state["audit_valid"] is True
    assert all(r["status"] == "EXPLAINED" for r in state["records"])


def test_exact_matching_idempotent_after_completion(client):
    post(client, "imports", csv_body())
    post(client, "imports", csv_body(side="SOURCE_B"))
    assert post(client, "reconcile", {"period": "2026-09"}).json()["matched"] == 1
    assert post(client, "reconcile", {"period": "2026-09"}).status_code == 422
    assert len(client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()["matches"]) == 1


def test_tolerance_matching_covers_value_date_drift_within_window(client):
    post(client, "imports", csv_body())
    body = csv_body(side="SOURCE_B")
    body["content"] = body["content"].replace("2026-09-01", "2026-09-02")
    post(client, "imports", body)
    result = post(client, "reconcile", {"period": "2026-09"}).json()
    assert result["matched"] == 1
    assert result["cases"] == 0
    state = client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()
    assert state["matches"][0]["rule"] == "L2_TOLERANCE"
    assert all(r["status"] == "MATCHED" for r in state["records"])


def test_tolerance_matching_does_not_bridge_an_amount_difference(client):
    post(client, "imports", csv_body())
    body = csv_body(side="SOURCE_B")
    body["content"] = body["content"].replace("2026-09-01", "2026-09-02").replace("10,USD", "9,USD")
    post(client, "imports", body)
    result = post(client, "reconcile", {"period": "2026-09"}).json()
    assert result["matched"] == 0
    assert result["cases"] == 1


def test_reject_and_return_cycle_back_through_triage_to_proposed(client):
    post(client, "imports", csv_body())
    body = csv_body(side="SOURCE_B")
    body["content"] = body["content"].replace("10,USD", "9,USD")
    post(client, "imports", body)
    post(client, "reconcile", {"period": "2026-09"})
    post(client, "agent-runs", {"period": "2026-09"})
    case_id = client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()["breaks"][0]["id"]
    url = f"breaks/{case_id}/decisions"

    rejected = post(client, url, {"action": "REJECT", "reason": "Not enough evidence yet"}, "reviewer").json()
    assert rejected["status"] == "REJECTED"

    post(client, "agent-runs", {"period": "2026-09"})
    reproposed = client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()["breaks"][0]
    assert reproposed["status"] == "PROPOSED"

    returned = post(client, url, {"action": "RETURN", "reason": "Needs more investigation"}, "reviewer").json()
    assert returned["status"] == "RETURNED"

    post(client, "agent-runs", {"period": "2026-09"})
    reproposed_again = client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()["breaks"][0]
    assert reproposed_again["status"] == "PROPOSED"


def test_cannot_review_a_case_that_is_not_proposed(client):
    post(client, "imports", csv_body())
    body = csv_body(side="SOURCE_B")
    body["content"] = body["content"].replace("10,USD", "9,USD")
    post(client, "imports", body)
    post(client, "reconcile", {"period": "2026-09"})
    case_id = client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()["breaks"][0]["id"]
    url = f"breaks/{case_id}/decisions"
    response = post(client, url, {"action": "APPROVE", "reason": "premature"}, "reviewer")
    assert response.status_code == 422


def test_certification_rolls_forward_a_non_blocking_open_break(client):
    post(client, "imports", csv_body())
    body = csv_body(side="SOURCE_B")
    body["content"] = body["content"].replace("2026-09-01", "2026-09-05")
    post(client, "imports", body)
    post(client, "reconcile", {"period": "2026-09"})
    case_before = client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()["breaks"][0]
    assert case_before["code"] == "TIM-01"
    assert case_before["risk"] == "Low"  # TIM-01's registry risk_weight (2) buckets as Low, not a certification blocker

    result = post(client, "certify", {"period": "2026-09", "reason": "Low-risk item carries forward"}, "controller")
    assert result.status_code == 200

    state = client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()
    assert state["periods"]["2026-09"]["status"] == "CERTIFIED"
    rolled = next(b for b in state["breaks"] if b["id"] == case_before["id"])
    assert rolled["status"] == "CARRIED_FORWARD"
    assert rolled["period"] == "2026-10"
    assert rolled["original_period"] == "2026-09"
    assert rolled["carry_forward_count"] == 1
    assert rolled["created_at"] == case_before["created_at"]

    # Re-triaging the new period picks the carried-forward case back up.
    post(client, "agent-runs", {"period": "2026-10"})
    reproposed = client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()["breaks"][0]
    assert reproposed["status"] == "PROPOSED"


def test_certification_blocks_on_high_risk_open_break(client):
    post(client, "imports", csv_body())
    body = csv_body(side="SOURCE_B")
    body["content"] = body["content"].replace("10,USD", "9,USD")
    post(client, "imports", body)
    post(client, "reconcile", {"period": "2026-09"})
    case = client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()["breaks"][0]
    assert case["code"] == "AMT-02"
    assert case["risk"] == "High"
    response = post(client, "certify", {"period": "2026-09", "reason": "Attempting with a high-risk break open"}, "controller")
    assert response.status_code == 422


def test_reopen_requires_certifier_role_and_mandatory_reason_then_recycles_to_proposed(client):
    post(client, "imports", csv_body())
    body = csv_body(side="SOURCE_B")
    body["content"] = body["content"].replace("10,USD", "9,USD")
    post(client, "imports", body)
    post(client, "reconcile", {"period": "2026-09"})
    post(client, "agent-runs", {"period": "2026-09"})
    case_id = client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()["breaks"][0]["id"]
    url = f"breaks/{case_id}/decisions"
    post(client, url, {"action": "APPROVE", "reason": "Evidence reviewed"}, "reviewer")
    post(client, url, {"action": "CLOSE", "reason": "Correction verified", "external_ref": "ERP-9"}, "reviewer")

    # Wrong role is rejected.
    assert post(client, url, {"action": "REOPEN", "reason": "Auditor request"}, "reviewer").status_code == 403
    # Reason is mandatory (schema-level minimum length).
    assert post(client, url, {"action": "REOPEN", "reason": "a"}, "controller").status_code == 422

    reopened = post(client, url, {"action": "REOPEN", "reason": "Auditor requested re-review"}, "controller").json()
    assert reopened["status"] == "TRIAGED"
    assert reopened["proposal"] is None
    assert reopened["external_ref"] is None

    post(client, "agent-runs", {"period": "2026-09"})
    reproposed = client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()["breaks"][0]
    assert reproposed["status"] == "PROPOSED"


def test_cannot_reopen_a_case_that_is_not_closed(client):
    post(client, "imports", csv_body())
    body = csv_body(side="SOURCE_B")
    body["content"] = body["content"].replace("10,USD", "9,USD")
    post(client, "imports", body)
    post(client, "reconcile", {"period": "2026-09"})
    case_id = client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()["breaks"][0]["id"]
    url = f"breaks/{case_id}/decisions"
    assert post(client, url, {"action": "REOPEN", "reason": "Too early"}, "controller").status_code == 422


def test_mt940_import_commits_with_default_field_map(client):
    body = {"filename": "statement.sta", "side": "SOURCE_A", "account": "Operating", "period": "2026-01",
            "content": SAMPLE_MT940, "file_format": "MT940"}
    response = post(client, "imports", body).json()
    assert response["batch"]["status"] == "COMMITTED"
    assert response["batch"]["source_format"] == "MT940"
    record = client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()["records"][0]
    assert record["amount"] == "50.00"
    assert record["currency"] == "USD"
    assert record["direction"] == "CR"
    assert record["value_date"] == "2026-01-02"
    # §15.2: the statement declares opening 1000.00 + this one +50.00
    # transaction = expected 1050.00, but it declares closing 1024.50 —
    # a real -25.50 gap the parser's self-declared balances catch on
    # their own, independent of any matching/break logic.
    check = response["batch"]["statement_check"]
    assert check["opening_balance"] == "1000.00"
    assert check["closing_balance"] == "1024.50"
    assert check["movement"] == "50.00"
    assert check["unexplained"] == "-25.50"


def test_statement_check_absent_for_formats_without_self_declared_balances(client):
    response = post(client, "imports", csv_body()).json()
    assert response["batch"]["statement_check"] is None


def test_camt053_import_commits_with_default_field_map(client):
    body = {"filename": "statement.xml", "side": "SOURCE_B", "account": "Operating", "period": "2026-01",
            "content": SAMPLE_CAMT053, "file_format": "CAMT053"}
    response = post(client, "imports", body).json()
    assert response["batch"]["status"] == "COMMITTED"
    record = client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()["records"][0]
    assert record["amount"] == "50.00"
    assert record["currency"] == "EUR"
    assert record["reference"] == "INV-100"


def test_excel_import_reconciles_against_a_csv_side(client):
    import base64
    import io

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["amount", "currency", "direction", "value_date", "reference", "description"])
    ws.append([10, "USD", "CR", "2026-09-01", "R1", "Example"])
    buf = io.BytesIO()
    wb.save(buf)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")

    excel_body = {"filename": "ledger.xlsx", "side": "SOURCE_B", "account": "Operating", "period": "2026-09",
                  "content": encoded, "file_format": "EXCEL"}
    response = post(client, "imports", excel_body).json()
    assert response["batch"]["status"] == "COMMITTED"
    assert response["batch"]["source_format"] == "EXCEL"

    post(client, "imports", csv_body())
    result = post(client, "reconcile", {"period": "2026-09"}).json()
    assert result["matched"] == 1
    assert result["cases"] == 0


def test_unsupported_format_rejected(client):
    body = csv_body()
    body["file_format"] = "SEPA_XML"
    assert post(client, "imports", body).status_code == 422


def _action_pending_case(client):
    post(client, "imports", csv_body())
    body = csv_body(side="SOURCE_B")
    body["content"] = body["content"].replace("10,USD", "9,USD")
    post(client, "imports", body)
    post(client, "reconcile", {"period": "2026-09"})
    post(client, "agent-runs", {"period": "2026-09"})
    case = client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()["breaks"][0]
    decision = {"action": "APPROVE", "reason": "Evidence reviewed"}
    post(client, f"breaks/{case['id']}/decisions", decision, "reviewer")
    return client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()["breaks"][0]


def test_journal_draft_posts_and_resolves_the_case(client):
    case = _action_pending_case(client)
    assert case["status"] == "ACTION_PENDING"
    lines = [{"side": "DR", "account_role": "NON_PERMISSIBLE_CLEARING", "amount": "1.00"},
             {"side": "CR", "account_role": "SUSPENSE", "amount": "1.00"}]
    draft = post(client, "journal-drafts", {"case_id": case["id"], "lines": lines, "reason": "Correct the fee variance"}).json()
    assert draft["status"] == "SUBMITTED"
    assert draft["maker"] == "analyst"

    # Maker cannot approve their own draft.
    assert post(client, f"journal-drafts/{draft['id']}/decisions", {"action": "APPROVE", "reason": "self-approve"}).status_code == 403

    approved = post(client, f"journal-drafts/{draft['id']}/decisions", {"action": "APPROVE", "reason": "Balanced and correct"}, "reviewer").json()
    assert approved["status"] == "POSTED"

    state = client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()
    resolved_case = next(b for b in state["breaks"] if b["id"] == case["id"])
    assert resolved_case["status"] == "CLOSED"
    assert "journal draft" in resolved_case["external_ref"].lower()
    assert all(r["status"] == "EXPLAINED" for r in state["records"] if r["id"] in case["record_ids"])


def test_journal_draft_rejects_unbalanced_lines(client):
    case = _action_pending_case(client)
    lines = [{"side": "DR", "account_role": "A", "amount": "5.00"}, {"side": "CR", "account_role": "B", "amount": "1.00"}]
    response = post(client, "journal-drafts", {"case_id": case["id"], "lines": lines, "reason": "Unbalanced on purpose"})
    assert response.status_code == 422


def test_journal_draft_requires_action_pending_case(client):
    post(client, "imports", csv_body())
    body = csv_body(side="SOURCE_B")
    body["content"] = body["content"].replace("10,USD", "9,USD")
    post(client, "imports", body)
    post(client, "reconcile", {"period": "2026-09"})
    case = client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()["breaks"][0]
    assert case["status"] == "OPEN"
    lines = [{"side": "DR", "account_role": "A", "amount": "1.00"}, {"side": "CR", "account_role": "B", "amount": "1.00"}]
    response = post(client, "journal-drafts", {"case_id": case["id"], "lines": lines, "reason": "Too early"})
    assert response.status_code == 422


def test_journal_draft_rejection_keeps_case_action_pending(client):
    case = _action_pending_case(client)
    lines = [{"side": "DR", "account_role": "A", "amount": "1.00"}, {"side": "CR", "account_role": "B", "amount": "1.00"}]
    draft = post(client, "journal-drafts", {"case_id": case["id"], "lines": lines, "reason": "Draft to reject"}).json()
    rejected = post(client, f"journal-drafts/{draft['id']}/decisions", {"action": "REJECT", "reason": "Wrong account roles"}, "reviewer").json()
    assert rejected["status"] == "REJECTED"
    state = client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()
    assert next(b for b in state["breaks"] if b["id"] == case["id"])["status"] == "ACTION_PENDING"


def test_bai2_import_commits_with_default_field_map(client):
    body = {"filename": "statement.bai2", "side": "SOURCE_A", "account": "Operating", "period": "2026-09",
            "content": SAMPLE_BAI2, "file_format": "BAI2"}
    response = post(client, "imports", body).json()
    assert response["batch"]["status"] == "COMMITTED"
    assert response["batch"]["source_format"] == "BAI2"
    records = client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()["records"]
    assert len(records) == 2
    assert records[0]["currency"] == "USD"
    assert records[0]["value_date"] == "2026-09-02"


def test_routing_escalates_large_amount_break_to_controller(client):
    header = "amount,currency,direction,value_date,reference,description\n"
    post(client, "imports", {"filename": "a.csv", "side": "SOURCE_A", "account": "Operating", "period": "2026-09",
                              "content": header + "2000000.00,USD,CR,2026-09-01,BIG1,Large settlement\n"})
    post(client, "imports", {"filename": "b.csv", "side": "SOURCE_B", "account": "Operating", "period": "2026-09",
                              "content": header + "1999000.00,USD,CR,2026-09-01,BIG1,Large settlement\n"})
    post(client, "reconcile", {"period": "2026-09"})
    post(client, "agent-runs", {"period": "2026-09"})
    case = client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()["breaks"][0]
    assert case["code"] == "AMT-02"
    assert case["owner"] == "Controller"


def test_triage_uses_a_configured_llm_provider_when_available(client, monkeypatch):
    from workbench import service as workbench_service

    class _FakeProvider:
        name = "fake"
        model = "fake-model-1.0"
        last_usage = None

        def generate(self, *, system_prompt, user_prompt):
            assert "<untrusted_transaction_data>" in user_prompt
            return "The amounts differ; confirm whether a fee applies."

    monkeypatch.setattr(workbench_service, "get_configured_provider", lambda settings: _FakeProvider())
    post(client, "imports", csv_body())
    body = csv_body(side="SOURCE_B")
    body["content"] = body["content"].replace("10,USD", "9,USD")
    post(client, "imports", body)
    post(client, "reconcile", {"period": "2026-09"})
    run = post(client, "agent-runs", {"period": "2026-09"}).json()
    assert run["model"] == "fake-model-1.0"
    assert run["llm_touched"] == 1
    # §24 — 1 of 1 triaged cases used the LLM (100%), which exceeds the
    # 12% default threshold: a real breach, computed from this run's own
    # counts against the real configured budget, not hardcoded.
    assert run["llm_touched_share"] == 1.0
    assert run["llm_share_breach"] is True
    audit_events = [e["event_type"] for e in client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()["audit"]]
    assert "agent.llm_touched_share.exceeded" in audit_events


def test_triage_accumulates_real_token_usage_from_the_provider(client, monkeypatch):
    from dataclasses import dataclass

    from workbench import service as workbench_service

    @dataclass
    class _Usage:
        input_tokens: int
        output_tokens: int
        thoughts_tokens: int
        total_tokens: int

    class _FakeProvider:
        name = "fake"
        model = "fake-model-1.0"

        def __init__(self):
            self.last_usage = None

        def generate(self, *, system_prompt, user_prompt):
            self.last_usage = _Usage(input_tokens=120, output_tokens=40, thoughts_tokens=30, total_tokens=190)
            return "Investigate the timing gap between the two sides."

    monkeypatch.setattr(workbench_service, "get_configured_provider", lambda settings: _FakeProvider())
    post(client, "imports", csv_body())
    body = csv_body(side="SOURCE_B")
    body["content"] = body["content"].replace("10,USD", "9,USD")
    post(client, "imports", body)
    post(client, "reconcile", {"period": "2026-09"})
    run = post(client, "agent-runs", {"period": "2026-09"}).json()
    assert run["llm_input_tokens"] == 120
    assert run["llm_output_tokens"] == 40


def test_triage_falls_back_to_deterministic_template_when_llm_call_fails(client, monkeypatch):
    from workbench import service as workbench_service
    from core.agent.llm.base import LLMError

    class _FailingProvider:
        name = "fake"
        model = "fake-model-1.0"

        def generate(self, *, system_prompt, user_prompt):
            raise LLMError("simulated outage")

    monkeypatch.setattr(workbench_service, "get_configured_provider", lambda settings: _FailingProvider())
    post(client, "imports", csv_body())
    body = csv_body(side="SOURCE_B")
    body["content"] = body["content"].replace("10,USD", "9,USD")
    post(client, "imports", body)
    post(client, "reconcile", {"period": "2026-09"})
    run = post(client, "agent-runs", {"period": "2026-09"}).json()
    assert run["model"] == "No LLM"
    assert run["llm_touched"] == 0
    case = client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()["breaks"][0]
    assert case["proposal"]["method"] == "Deterministic template"
    audit_events = [e["event_type"] for e in client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()["audit"]]
    assert "agent.fallback.engaged" in audit_events


def test_routing_keeps_small_amount_break_with_reviewer(client):
    post(client, "imports", csv_body())
    body = csv_body(side="SOURCE_B")
    body["content"] = body["content"].replace("10,USD", "9,USD")
    post(client, "imports", body)
    post(client, "reconcile", {"period": "2026-09"})
    post(client, "agent-runs", {"period": "2026-09"})
    case = client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()["breaks"][0]
    assert case["owner"] == "Reviewer"


def test_fingerprint_duplicate_requires_matching_amount_not_just_reference(client):
    # A reused reference with a different amount is a different transaction
    # (e.g. two partial payments against the same invoice), not a
    # duplicate (§7.2's fingerprint includes amount) — this used to be
    # misclassified as DUP-01 by a looser reference-only heuristic.
    header = "amount,currency,direction,value_date,reference,description\n"
    post(client, "imports", {"filename": "a.csv", "side": "SOURCE_A", "account": "Operating", "period": "2026-09",
                              "content": header + "10,USD,CR,2026-09-01,REF1,First\n20,USD,CR,2026-09-01,REF1,Second\n"})
    post(client, "reconcile", {"period": "2026-09"})
    breaks = client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()["breaks"]
    assert len(breaks) == 2
    assert all(b["code"] != "DUP-01" for b in breaks)


def test_fingerprint_duplicate_still_detected_when_everything_matches(client):
    header = "amount,currency,direction,value_date,reference,description\n"
    post(client, "imports", {"filename": "a.csv", "side": "SOURCE_A", "account": "Operating", "period": "2026-09",
                              "content": header + "10,USD,CR,2026-09-01,REF1,First\n10,USD,CR,2026-09-01,REF1,First again\n"})
    post(client, "reconcile", {"period": "2026-09"})
    breaks = client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()["breaks"]
    assert len(breaks) == 2
    assert all(b["code"] == "DUP-01" for b in breaks)


def test_manual_match_nets_two_records_and_resolves_a_break(client):
    # Different accounts, opposite directions: L3 auto-matching blocks by
    # (account, currency) so this combination is never discovered
    # automatically — a genuine case for the human override tool.
    header = "amount,currency,direction,value_date,reference,description\n"
    post(client, "imports", {"filename": "a.csv", "side": "SOURCE_A", "account": "Operating", "period": "2026-09",
                              "content": header + "300.00,USD,CR,2026-09-01,DIFF-REF-A,First\n"})
    post(client, "imports", {"filename": "b.csv", "side": "SOURCE_B", "account": "Suspense", "period": "2026-09",
                              "content": header + "300.00,USD,DR,2026-09-01,DIFF-REF-B,Second\n"})
    post(client, "reconcile", {"period": "2026-09"})
    breaks_before = client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()["breaks"]
    assert len(breaks_before) == 2  # unrelated accounts/references -> two independent breaks, not auto-matched
    record_ids = [r["id"] for r in client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()["records"]]

    match = post(client, "matches/manual", {"record_ids": record_ids, "reason": "Confirmed same settlement via bank portal"}).json()
    assert match["rule"] == "MANUAL"
    state = client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()
    assert all(r["status"] == "MATCHED" for r in state["records"])
    assert all(b["status"] == "RESOLVED" for b in state["breaks"])


def test_manual_match_rejects_records_that_do_not_net_to_zero(client):
    header = "amount,currency,direction,value_date,reference,description\n"
    post(client, "imports", {"filename": "a.csv", "side": "SOURCE_A", "account": "Operating", "period": "2026-09",
                              "content": header + "300.00,USD,CR,2026-09-01,R1,First\n"})
    post(client, "imports", {"filename": "b.csv", "side": "SOURCE_B", "account": "Operating", "period": "2026-09",
                              "content": header + "250.00,USD,CR,2026-09-01,R2,Second\n"})
    post(client, "reconcile", {"period": "2026-09"})
    record_ids = [r["id"] for r in client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()["records"]]
    response = post(client, "matches/manual", {"record_ids": record_ids, "reason": "Trying anyway"})
    assert response.status_code == 422


def test_unmatch_requires_reason_and_reverses_a_match(client):
    post(client, "imports", csv_body())
    post(client, "imports", csv_body(side="SOURCE_B"))
    post(client, "reconcile", {"period": "2026-09"})
    match_id = client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()["matches"][0]["id"]

    assert post(client, f"matches/{match_id}/unmatch", {"reason": ""}).status_code == 422
    post(client, f"matches/{match_id}/unmatch", {"reason": "Bank statement was later corrected"})
    state = client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()
    assert all(r["status"] == "UNMATCHED" for r in state["records"])
    assert state["matches"][0]["reversed"] is True

    # A reversed match cannot be unmatched twice.
    assert post(client, f"matches/{match_id}/unmatch", {"reason": "Again"}).status_code == 422


def test_group_matching_nets_one_credit_against_three_debits(client):
    header = "amount,currency,direction,value_date,reference,description\n"
    post(client, "imports", {"filename": "a.csv", "side": "SOURCE_A", "account": "Operating", "period": "2026-09",
                              "content": header + "300,USD,CR,2026-09-01,BULK1,Bulk settlement\n"})
    lines = "".join(f"100,USD,DR,2026-09-01,LINE{i},Invoice {i}\n" for i in range(1, 4))
    post(client, "imports", {"filename": "b.csv", "side": "SOURCE_B", "account": "Operating", "period": "2026-09",
                              "content": header + lines})
    result = post(client, "reconcile", {"period": "2026-09"}).json()
    assert result["matched"] == 1
    assert result["cases"] == 0
    state = client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()
    assert state["matches"][0]["rule"] == "L3_GROUP"
    assert len(state["matches"][0]["record_ids"]) == 4
    assert all(r["status"] == "MATCHED" for r in state["records"])


def test_unauthenticated_and_forged_identity_cannot_mutate_and_foreign_origin_is_denied(client):
    # No Authorization header at all -> the local guard's client header is
    # still required first, so this is still a 403 (origin/client check runs
    # before auth); with the client header present but no token, auth denies it.
    assert client.post("/api/sample", json={}).status_code == 403
    assert client.post("/api/sample", json={}, headers={"X-Workspace-Client": "reconcile-local"}).status_code == 401
    # A token signed for a nonexistent identity is rejected even though it's
    # a well-formed JWT — signature verification alone isn't enough, the
    # username must also resolve to a real account.
    forged = create_token(username="AGENT", role="MAKER", display_name="Not Real")
    assert client.post("/api/sample", json={}, headers={"Authorization": f"Bearer {forged}", "X-Workspace-Client": "reconcile-local"}).status_code == 401
    assert client.post("/api/sample", json={}, headers={"Origin": "https://untrusted.example", "X-Workspace-Client": "reconcile-local"}).status_code == 403


def test_login_succeeds_with_correct_demo_credentials_and_grants_mutation(client):
    response = client.post(
        "/api/auth/login",
        json={"username": "analyst", "password": "analyst-demo-pass"},
        headers={"X-Workspace-Client": "reconcile-local"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["actor"] == "analyst"
    assert body["role"] == "MAKER"
    assert body["display_name"]
    token = body["access_token"]
    assert client.post("/api/sample", json={}, headers={"Authorization": f"Bearer {token}", "X-Workspace-Client": "reconcile-local"}).status_code == 200


def test_login_rejects_wrong_password_and_unknown_username(client):
    wrong_password = client.post(
        "/api/auth/login",
        json={"username": "analyst", "password": "not-the-password"},
        headers={"X-Workspace-Client": "reconcile-local"},
    )
    assert wrong_password.status_code == 401
    unknown_user = client.post(
        "/api/auth/login",
        json={"username": "nobody", "password": "anything"},
        headers={"X-Workspace-Client": "reconcile-local"},
    )
    assert unknown_user.status_code == 401


def test_sample_data_is_explicit_and_auditable(client):
    assert client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()["records"] == []
    assert post(client, "sample").status_code == 200
    state = client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()
    assert state["sample_loaded"] is True
    assert len(state["records"]) == 153
    assert len(state["matches"]) == 68
    assert len(state["breaks"]) == 12
    assert state["audit_valid"] is True
    assert post(client, "sample").status_code == 422


def test_model_governance_endpoint_is_labeled_synthetic(client):
    response = client.get("/api/model-governance")
    assert response.status_code == 200
    body = response.json()
    assert body["synthetic"] is True
    assert body["calibrated_ece"] < body["raw_ece"]
    assert "circuit_breaker" in body


def test_admin_config_endpoint_reflects_real_settings(client):
    response = client.get("/api/admin-config")
    assert response.status_code == 200
    body = response.json()
    assert body["agent_budgets"]["cases_per_run"] == 500
    assert body["ageing_and_roll_forward"]["aged_break_high_risk_days"] == 90
    assert "provider" in body["llm"]


def test_pilot_endpoint_is_labeled_dummy_and_reflects_real_activity(client):
    post(client, "imports", csv_body())
    response = client.get("/api/pilot", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"})
    assert response.status_code == 200
    body = response.json()
    assert body["is_dummy"] is True
    assert body["activity_to_date"]["imports"] == 1


def test_evidence_export_and_pack_manifest(client):
    post(client, "imports", csv_body())
    export = client.get("/api/export", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()
    assert len(export["manifest"]["sha256"]) == 64
    assert len(export["workspace"]["records"]) == 1
    pack = client.get("/api/packs")
    assert pack.status_code == 200
    assert len(pack.json()["break_types"]) == 48


def test_empty_file_returns_validation_error(client):
    body = csv_body()
    body["content"] = ""
    assert post(client, "imports", body).status_code == 422


def test_held_import_can_be_rejected_without_losing_source_evidence(client):
    body = csv_body()
    body["content"] = body["content"].replace("10,USD", "bad,USD")
    batch = post(client, "imports", body).json()["batch"]
    result = post(client, f"imports/{batch['id']}/reject", {"reason": "Source corrected; replacement file requested"})
    assert result.json()["status"] == "REJECTED"
    assert result.json()["raw_source"] == body["content"]
    assert client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()["audit_valid"] is True


def test_fractional_amounts_are_exported_as_exact_decimal_strings(client):
    body = csv_body()
    body["content"] = body["content"].replace("10,USD", "0.00000001,USD")
    assert post(client, "imports", body).json()["batch"]["control_totals"]["USD"]["credit_sum"] == "0.00000001"
    assert client.get("/api/workspace", headers={"Authorization": f"Bearer {_token_for(client, 'analyst')}"}).json()["records"][0]["amount"] == "0.00000001"


def test_private_reads_and_export_exclude_credentials(client):
    import hashlib
    import json
    for path in ("workspace", "export", "pilot"):
        assert client.get("/api/" + path).status_code == 401
    headers = {"Authorization": f"Bearer {_token_for(client, 'analyst')}"}
    workspace = client.get("/api/workspace", headers=headers).json()
    export = client.get("/api/export", headers=headers).json()
    assert "users" not in workspace
    assert "users" not in export["workspace"]
    assert "password_hash" not in json.dumps(export)
    payload = json.dumps(export["workspace"], sort_keys=True, separators=(",", ":"))
    assert export["manifest"]["sha256"] == hashlib.sha256(payload.encode()).hexdigest()


def test_one_click_check_validates_sources_and_is_repeatable(client):
    assert post(client, "check", {"period": "2026-09"}).status_code == 422
    assert post(client, "imports", csv_body()).status_code == 200
    assert post(client, "check", {"period": "2026-09"}).status_code == 422
    body = csv_body(side="SOURCE_B")
    body["content"] += "25,USD,CR,2026-09-02,FEE1,Service fee\n"
    assert post(client, "imports", body).status_code == 200
    assert post(client, "check", {"period": "2026-09"}, actor="reviewer").status_code == 403
    first = post(client, "check", {"period": "2026-09"})
    assert first.status_code == 200, first.text
    assert first.json()["new_matches"] == 1
    assert first.json()["recommendations_prepared"] == 1
    repeat = post(client, "check", {"period": "2026-09"})
    assert repeat.status_code == 200, repeat.text
    assert repeat.json()["new_matches"] == 0
    assert repeat.json()["recommendations_prepared"] == 0
