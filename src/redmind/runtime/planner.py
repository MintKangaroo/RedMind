"""Evidence-driven attack-path planning without exploit or command generation."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field, field_validator

from redmind.runtime.models import RuntimeModel


class ActionProposal(RuntimeModel):
    """A schema-only validation proposal. It can never contain a shell command."""

    action_type: Annotated[str, Field(min_length=1, max_length=100)]
    target_id: Annotated[str, Field(min_length=1, max_length=200)]
    purpose: Annotated[str, Field(min_length=1, max_length=1_000)]
    required_evidence: tuple[Annotated[str, Field(min_length=1, max_length=200)], ...]
    expected_observation: Annotated[str, Field(min_length=1, max_length=1_000)]
    risk_level: Annotated[str, Field(pattern="^(low|medium|high|critical)$")]
    scope_impact: Annotated[str, Field(pattern="^(none|target_only|multi_target)$")]
    timeout: Annotated[float, Field(gt=0, le=300)]
    rollback_plan: Annotated[str, Field(min_length=1, max_length=1_000)]
    approval_required: bool
    tool_name: Annotated[str, Field(min_length=1, max_length=100)]
    structured_arguments: dict[str, Any] = Field(default_factory=dict)

    @field_validator("structured_arguments")
    @classmethod
    def reject_command_material(cls, value: dict[str, Any]) -> dict[str, Any]:
        forbidden = {"command", "shell", "payload", "exploit", "script"}
        if forbidden.intersection(key.lower() for key in value):
            raise ValueError("command and payload material is forbidden")
        return value


class AttackGraphEdge(RuntimeModel):
    """One non-executable validation hypothesis imported from a threat graph."""

    edge_id: Annotated[str, Field(min_length=1, max_length=200)]
    target_id: Annotated[str, Field(min_length=1, max_length=200)]
    premise: Annotated[str, Field(min_length=1, max_length=1_000)]
    required_evidence: tuple[Annotated[str, Field(min_length=1, max_length=200)], ...]
    validation_action: Annotated[str, Field(min_length=1, max_length=100)]
    expected_observation: Annotated[str, Field(min_length=1, max_length=1_000)]
    tool_name: Annotated[str, Field(min_length=1, max_length=100)]
    risk_level: Annotated[str, Field(pattern="^(low|medium|high|critical)$")] = "low"


class AttackPathCandidate(RuntimeModel):
    edge_id: str
    premise: str
    evidence_coverage: Annotated[float, Field(ge=0, le=1)]
    confidence: Annotated[float, Field(ge=0, le=1)]
    risk_level: str
    validation_plan: ActionProposal


class AttackPathPlanner:
    """Convert authorized graph hypotheses into bounded validation plans."""

    def __init__(
        self,
        *,
        allowed_targets: frozenset[str],
        allowed_tools: frozenset[str],
    ) -> None:
        self.allowed_targets = allowed_targets
        self.allowed_tools = allowed_tools

    def plan(
        self,
        graph: tuple[AttackGraphEdge, ...],
        available_evidence: frozenset[str],
    ) -> tuple[AttackPathCandidate, ...]:
        candidates: list[AttackPathCandidate] = []
        seen: set[tuple[str, str]] = set()
        for edge in graph:
            identity = (edge.target_id, edge.validation_action)
            if identity in seen:
                continue
            if (
                edge.target_id not in self.allowed_targets
                or edge.tool_name not in self.allowed_tools
            ):
                continue
            required = set(edge.required_evidence)
            matched = required & available_evidence
            if not required or not matched:
                continue
            coverage = len(matched) / len(required)
            confidence = round(0.25 + 0.75 * coverage, 3)
            proposal = ActionProposal(
                action_type=edge.validation_action,
                target_id=edge.target_id,
                purpose=f"Validate graph premise: {edge.premise}",
                required_evidence=edge.required_evidence,
                expected_observation=edge.expected_observation,
                risk_level=edge.risk_level,
                scope_impact="target_only",
                timeout=30,
                rollback_plan="No state change; stop the bounded observation on failure.",
                approval_required=edge.risk_level in {"high", "critical"},
                tool_name=edge.tool_name,
                structured_arguments={
                    "target_id": edge.target_id,
                    "evidence_ids": sorted(matched),
                },
            )
            candidates.append(
                AttackPathCandidate(
                    edge_id=edge.edge_id,
                    premise=edge.premise,
                    evidence_coverage=coverage,
                    confidence=confidence,
                    risk_level=edge.risk_level,
                    validation_plan=proposal,
                )
            )
            seen.add(identity)
        return tuple(sorted(candidates, key=lambda item: item.confidence, reverse=True))
