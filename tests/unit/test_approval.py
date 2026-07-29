from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from redmind.runtime import (
    ActionProposal,
    ApprovalError,
    ApprovalEventType,
    ApprovalService,
    ApprovalStatus,
    PolicyConfig,
    PolicyEngine,
    PolicyViolation,
    RunRequest,
)

UTC = timezone.utc  # noqa: UP017


class Clock:
    def __init__(self):
        self.value = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += timedelta(seconds=seconds)


def proposal(**updates):
    values = {
        "action_type": "observe_service",
        "target_id": "lab-1",
        "purpose": "confirm service metadata",
        "required_evidence": ("scope",),
        "expected_observation": "service metadata",
        "risk_level": "high",
        "scope_impact": "target_only",
        "timeout": 30,
        "rollback_plan": "stop observation",
        "approval_required": True,
        "tool_name": "service_observer",
        "structured_arguments": {"target_id": "lab-1"},
    }
    values.update(updates)
    return ActionProposal(**values)


def service(clock):
    policy = PolicyEngine(
        PolicyConfig(
            allowed_targets=frozenset({"lab-1"}),
            allowed_tools=frozenset({"service_observer"}),
            max_steps=3,
            max_timeout_seconds=60,
        )
    )
    return ApprovalService(policy, clock=clock)


def run_request(**updates):
    values = {
        "objective": "validate",
        "max_steps": 3,
        "timeout_seconds": 60,
        "target_ids": ("lab-1",),
        "tool_names": ("service_observer",),
        "risk_level": "high",
    }
    values.update(updates)
    return RunRequest(**values)


def test_approval_authorizes_once_after_policy_revalidation():
    clock = Clock()
    workflow = service(clock)
    action = proposal()
    request = workflow.request(action)
    approved = workflow.approve(request.id, approver="reviewer-1", reason="lab scope verified")
    assert approved.status is ApprovalStatus.APPROVED
    authorized = workflow.authorize_execution(request.id, action, run_request())
    assert authorized.status is ApprovalStatus.EXECUTING
    assert [event.event_type for event in workflow.audit_log(request.id)] == [
        ApprovalEventType.REQUESTED,
        ApprovalEventType.APPROVED,
        ApprovalEventType.POLICY_REVALIDATED,
        ApprovalEventType.EXECUTION_AUTHORIZED,
    ]
    with pytest.raises(ApprovalError):
        workflow.authorize_execution(request.id, action, run_request())


def test_expiry_rejection_and_reapproval():
    clock = Clock()
    workflow = service(clock)
    first = workflow.request(proposal(), ttl_seconds=10)
    clock.advance(11)
    with pytest.raises(ApprovalError):
        workflow.approve(first.id, approver="reviewer", reason="late")
    assert workflow.get(first.id).status is ApprovalStatus.EXPIRED
    second = workflow.reapprove(first.id, proposal(), actor="planner")
    rejected = workflow.reject(second.id, approver="reviewer", reason="need evidence")
    assert rejected.status is ApprovalStatus.REJECTED
    third = workflow.reapprove(second.id, proposal(), actor="planner")
    assert third.previous_request_id == second.id


def test_changed_proposal_and_changed_scope_are_rejected():
    clock = Clock()
    workflow = service(clock)
    action = proposal()
    request = workflow.request(action)
    workflow.approve(request.id, approver="reviewer", reason="approved")
    with pytest.raises(ApprovalError):
        workflow.authorize_execution(
            request.id,
            proposal(expected_observation="different"),
            run_request(),
        )
    with pytest.raises(PolicyViolation):
        workflow.authorize_execution(
            request.id,
            action,
            run_request(target_ids=("other",)),
        )


def test_approval_rejects_invalid_ttl_lineage_text_and_unknown_ids():
    workflow = service(Clock())
    action = proposal()
    with pytest.raises(ApprovalError, match="TTL"):
        workflow.request(action, ttl_seconds=0)
    with pytest.raises(ApprovalError, match="blank"):
        workflow.request(action, actor=" ")

    pending = workflow.request(action)
    with pytest.raises(ApprovalError, match="rejected or expired"):
        workflow.reapprove(pending.id, action, actor="planner")
    with pytest.raises(ApprovalError, match="not found"):
        workflow.get(uuid4())


def test_execution_revalidation_rejects_tool_removed_from_run_allowlist():
    workflow = service(Clock())
    action = proposal()
    request = workflow.request(action)
    workflow.approve(request.id, approver="reviewer", reason="scope verified")
    with pytest.raises(PolicyViolation, match="tool"):
        workflow.authorize_execution(
            request.id,
            action,
            run_request(tool_names=()),
        )
