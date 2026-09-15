import pytest

from core.workflow.maker_checker import ApprovalRequest, MakerCheckerViolation, authorize_approval


def test_distinct_actors_with_role_succeeds():
    authorize_approval(ApprovalRequest(made_by="alice", checked_by="bob", checker_has_required_role=True))


def test_same_actor_cannot_approve_own_submission():
    with pytest.raises(MakerCheckerViolation):
        authorize_approval(ApprovalRequest(made_by="alice", checked_by="alice", checker_has_required_role=True))


def test_checker_without_role_rejected():
    with pytest.raises(MakerCheckerViolation):
        authorize_approval(ApprovalRequest(made_by="alice", checked_by="bob", checker_has_required_role=False))


def test_reopen_requires_permission():
    with pytest.raises(MakerCheckerViolation):
        authorize_approval(ApprovalRequest(
            made_by="alice", checked_by="bob", checker_has_required_role=True,
            is_reopen=True, reopen_permission_granted=False, reopen_reason="audit",
        ))


def test_reopen_requires_mandatory_reason():
    with pytest.raises(MakerCheckerViolation):
        authorize_approval(ApprovalRequest(
            made_by="alice", checked_by="bob", checker_has_required_role=True,
            is_reopen=True, reopen_permission_granted=True, reopen_reason=None,
        ))


def test_reopen_with_permission_and_reason_succeeds():
    authorize_approval(ApprovalRequest(
        made_by="alice", checked_by="bob", checker_has_required_role=True,
        is_reopen=True, reopen_permission_granted=True, reopen_reason="auditor requested review",
    ))
