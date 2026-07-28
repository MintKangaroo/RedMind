import pytest
from pydantic import ValidationError

from redmind.runtime import ActionProposal, AttackGraphEdge, AttackPathPlanner


def edge(**updates):
    values = {
        "edge_id": "edge-1",
        "target_id": "lab-1",
        "premise": "observed service may expose an outdated component",
        "required_evidence": ("service:443", "version:known"),
        "validation_action": "validate_service_version",
        "expected_observation": "A version observation with source attribution",
        "tool_name": "service_observer",
        "risk_level": "low",
    }
    values.update(updates)
    return AttackGraphEdge(**values)


def test_planner_calculates_coverage_and_confidence():
    planner = AttackPathPlanner(
        allowed_targets=frozenset({"lab-1"}),
        allowed_tools=frozenset({"service_observer"}),
    )
    candidates = planner.plan((edge(),), frozenset({"service:443"}))
    assert candidates[0].evidence_coverage == 0.5
    assert candidates[0].confidence == 0.625
    assert candidates[0].validation_plan.structured_arguments["target_id"] == "lab-1"


def test_planner_rejects_unscoped_unsupported_and_unfounded_paths():
    planner = AttackPathPlanner(
        allowed_targets=frozenset({"lab-1"}),
        allowed_tools=frozenset({"service_observer"}),
    )
    graph = (
        edge(target_id="public-host"),
        edge(edge_id="edge-2", tool_name="shell"),
        edge(edge_id="edge-3"),
    )
    assert planner.plan(graph, frozenset()) == ()


def test_planner_deduplicates_equivalent_validation_actions():
    planner = AttackPathPlanner(
        allowed_targets=frozenset({"lab-1"}),
        allowed_tools=frozenset({"service_observer"}),
    )
    candidates = planner.plan(
        (edge(), edge(edge_id="duplicate")),
        frozenset({"service:443", "version:known"}),
    )
    assert len(candidates) == 1


def test_action_proposal_rejects_command_or_payload_fields():
    with pytest.raises(ValidationError):
        ActionProposal(
            action_type="observe",
            target_id="lab-1",
            purpose="observe",
            required_evidence=("scope",),
            expected_observation="result",
            risk_level="low",
            scope_impact="target_only",
            timeout=10,
            rollback_plan="stop",
            approval_required=False,
            tool_name="observer",
            structured_arguments={"command": "unsafe"},
        )
