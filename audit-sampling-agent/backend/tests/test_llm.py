import pytest

from sampling.llm import (
    LLMOrchestrator,
    check_grounding,
    validate_preprocessing_plan,
)


class FakeClient:
    def __init__(self, response: str):
        self.response = response

    def complete(self, system: str, user: str, max_tokens: int = 1500) -> str:
        return self.response


def test_plan_validator_rejects_data_removal():
    plan = [{"step": "drop_outliers", "params": {"column": "amount"}}]
    result = validate_preprocessing_plan(plan, available_columns={"amount"})
    assert result.valid is False
    assert any("forbidden" in e for e in result.errors)


def test_plan_validator_rejects_code_execution():
    plan = [{"step": "execute_python", "params": {"code": "os.system('rm -rf /')"}}]
    result = validate_preprocessing_plan(plan, available_columns=set())
    assert result.valid is False


def test_plan_validator_rejects_unknown_columns():
    plan = [{"step": "parse_type", "params": {"column": "ghost", "target_type": "float"}}]
    result = validate_preprocessing_plan(plan, available_columns={"amount"})
    assert result.valid is False
    assert any("unknown column" in e for e in result.errors)


def test_plan_validator_accepts_allowed_step():
    plan = [{"step": "strip_whitespace", "params": {"column": "amount"}}]
    result = validate_preprocessing_plan(plan, available_columns={"amount"})
    assert result.valid is True
    assert len(result.validated_plan) == 1


def test_grounding_accepts_figures_present_in_evidence():
    evidence = {"amount": 5000.0, "risk_score": 82.5}
    narrative = "This item has an amount of 5000.00 and a risk score of 82.5."
    report = check_grounding(narrative, evidence)
    assert report.grounded is True


def test_grounding_rejects_invented_numbers():
    evidence = {"amount": 5000.0}
    narrative = "This item was flagged with a risk score of 999.99."
    report = check_grounding(narrative, evidence)
    assert report.grounded is False
    assert "999.99" in report.ungrounded_numbers


def test_orchestrator_withholds_ungrounded_narrative():
    client = FakeClient("Suspiciously the amount was 123456.78 which is very high")
    orch = LLMOrchestrator(client, model_identifier="fake-1", prompt_version="v1")
    result = orch.narrate_challenge("Why was this selected?", {"amount": 5000.0})
    assert result["narrative"] is None
    assert "fallback_message" in result
    assert result["evidence"] == {"amount": 5000.0}


def test_orchestrator_returns_grounded_narrative():
    client = FakeClient("The amount is 5000.0.")
    orch = LLMOrchestrator(client, model_identifier="fake-1", prompt_version="v1")
    result = orch.narrate_challenge("Why was this selected?", {"amount": 5000.0})
    assert result["narrative"] is not None
    assert result["grounding"]["grounded"] is True
