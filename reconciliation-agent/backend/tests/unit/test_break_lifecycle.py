import pytest

from core.breaks.lifecycle import IllegalTransition, TransitionRequest, transition
from core.models.break_case import BreakCaseStatus as S


def test_happy_path_open_to_closed():
    path = [S.OPEN, S.TRIAGED, S.PROPOSED, S.UNDER_REVIEW, S.APPROVED, S.ACTION_PENDING, S.RESOLVED, S.CLOSED]
    for current, target in zip(path, path[1:]):
        assert transition(TransitionRequest(case_status=current, target=target)) == target


def test_rejected_and_returned_go_back_to_triaged():
    assert transition(TransitionRequest(case_status=S.UNDER_REVIEW, target=S.REJECTED)) == S.REJECTED
    assert transition(TransitionRequest(case_status=S.REJECTED, target=S.TRIAGED)) == S.TRIAGED
    assert transition(TransitionRequest(case_status=S.UNDER_REVIEW, target=S.RETURNED)) == S.RETURNED
    assert transition(TransitionRequest(case_status=S.RETURNED, target=S.TRIAGED)) == S.TRIAGED


def test_skipping_states_is_illegal():
    with pytest.raises(IllegalTransition):
        transition(TransitionRequest(case_status=S.OPEN, target=S.APPROVED))


def test_reopen_requires_reason():
    with pytest.raises(IllegalTransition):
        transition(TransitionRequest(case_status=S.CLOSED, target=S.REOPENED))
    assert transition(TransitionRequest(case_status=S.CLOSED, target=S.REOPENED, reason="auditor request")) == S.REOPENED


def test_reopened_lands_back_in_triaged():
    assert transition(TransitionRequest(case_status=S.REOPENED, target=S.TRIAGED)) == S.TRIAGED


def test_period_close_carries_forward_open_case():
    result = transition(TransitionRequest(case_status=S.UNDER_REVIEW, target=S.CARRIED_FORWARD, is_period_close=True))
    assert result == S.CARRIED_FORWARD


def test_period_close_cannot_carry_forward_a_closed_case():
    with pytest.raises(IllegalTransition):
        transition(TransitionRequest(case_status=S.CLOSED, target=S.CARRIED_FORWARD, is_period_close=True))


def test_carried_forward_returns_to_triaged_next_period():
    assert transition(TransitionRequest(case_status=S.CARRIED_FORWARD, target=S.TRIAGED)) == S.TRIAGED
