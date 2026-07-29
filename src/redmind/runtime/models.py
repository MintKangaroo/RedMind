"""Validated domain models for agent execution and trace data."""

from __future__ import annotations

import sys
from datetime import datetime
from enum import Enum
from typing import Annotated
from uuid import UUID

if sys.version_info >= (3, 11):  # noqa: UP036 - local Python 3.10 test tooling
    from enum import StrEnum as StrEnum  # pragma: no cover - runtime-version branch
else:  # pragma: no cover - compatibility for local Python 3.10 tooling

    class StrEnum(str, Enum):  # noqa: UP042
        """Backport of enum.StrEnum for supported tooling on Python 3.10."""

        def __str__(self) -> str:
            return str(self.value)


from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

JsonObject = dict[str, JsonValue]


class RuntimeModel(BaseModel):
    """Base model that rejects unexpected data at runtime boundaries."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class AgentState(StrEnum):
    """Lifecycle states shared by runs and individual agent steps."""

    PROPOSED = "proposed"
    POLICY_CHECKED = "policy_checked"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    EXECUTING = "executing"
    OBSERVED = "observed"
    REJECTED = "rejected"
    FAILED = "failed"
    COMPLETED = "completed"


class MessageRole(StrEnum):
    """The semantic role of a message in an agent trace."""

    SYSTEM = "system"
    USER = "user"
    AGENT = "agent"


class FailureKind(StrEnum):
    """Machine-readable bounded-runtime failure categories."""

    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    AGENT_ERROR = "agent_error"
    INVALID_OUTPUT = "invalid_output"
    MAX_STEPS = "max_steps"
    EVIDENCE_INSUFFICIENT = "evidence_insufficient"
    REPEATED_FAILURE = "repeated_failure"
    RETRY_EXHAUSTED = "retry_exhausted"
    SELF_REJECTED = "self_rejected"


class EvaluationVerdict(StrEnum):
    """Schema-constrained result of an agent's self-evaluation."""

    ACCEPT = "accept"
    REPLAN = "replan"
    REJECT = "reject"


class TraceEventType(StrEnum):
    """Events retained by the execution trace."""

    RUN_CREATED = "run_created"
    STEP_CREATED = "step_created"
    STATE_TRANSITION = "state_transition"
    MESSAGE_RECORDED = "message_recorded"
    EVIDENCE_RECORDED = "evidence_recorded"
    CANCELLATION_REQUESTED = "cancellation_requested"


class FailureDetails(RuntimeModel):
    """Sanitized failure information safe to retain in a trace."""

    kind: FailureKind
    message: Annotated[str, Field(min_length=1, max_length=500)]
    retryable: bool = False


class RunRequest(RuntimeModel):
    """Caller-supplied bounds and objective for a new run."""

    objective: Annotated[str, Field(min_length=1, max_length=2_000)]
    project_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")] = "default"
    idempotency_key: Annotated[str, Field(min_length=8, max_length=128)] | None = None
    max_steps: Annotated[int, Field(ge=1, le=1_000)] = 10
    timeout_seconds: Annotated[float, Field(gt=0, le=86_400)] = 300.0
    target_ids: tuple[Annotated[str, Field(min_length=1, max_length=200)], ...] = ()
    tool_names: tuple[Annotated[str, Field(min_length=1, max_length=100)], ...] = ()
    risk_level: Annotated[str, Field(pattern="^(low|medium|high|critical)$")] = "low"
    approval_requested: bool = False
    metadata: JsonObject = Field(default_factory=dict)

    @field_validator("objective")
    @classmethod
    def objective_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("objective must not be blank")
        return value


class Run(RuntimeModel):
    """Top-level bounded agent execution."""

    id: UUID
    objective: str
    state: AgentState = AgentState.PROPOSED
    max_steps: int
    timeout_seconds: float
    metadata: JsonObject = Field(default_factory=dict)
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cancellation_requested_at: datetime | None = None
    cancellation_reason: str | None = None
    failure: FailureDetails | None = None
    project_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")] = "default"
    idempotency_key: Annotated[str, Field(min_length=8, max_length=128)] | None = None


class Step(RuntimeModel):
    """One invocation of an agent within a run."""

    id: UUID
    run_id: UUID
    sequence: Annotated[int, Field(ge=1)]
    agent_name: Annotated[str, Field(min_length=1, max_length=100)]
    state: AgentState = AgentState.PROPOSED
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failure: FailureDetails | None = None


class MessageDraft(RuntimeModel):
    """Validated message output before trace identifiers are assigned."""

    role: MessageRole
    sender: Annotated[str, Field(min_length=1, max_length=100)]
    recipient: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    content: Annotated[str, Field(min_length=1, max_length=20_000)]
    metadata: JsonObject = Field(default_factory=dict)


class Message(MessageDraft):
    """A message retained as part of the execution trace."""

    id: UUID
    run_id: UUID
    step_id: UUID
    created_at: datetime


class EvidenceDraft(RuntimeModel):
    """Validated observation before trace identifiers are assigned."""

    evidence_type: Annotated[str, Field(min_length=1, max_length=100)]
    source: Annotated[str, Field(min_length=1, max_length=200)]
    summary: Annotated[str, Field(min_length=1, max_length=2_000)]
    payload: JsonObject = Field(default_factory=dict)


class Evidence(EvidenceDraft):
    """An immutable observation produced by an agent step."""

    id: UUID
    run_id: UUID
    step_id: UUID
    collected_at: datetime


class AgentSelfEvaluation(RuntimeModel):
    """Validated reflection output; it cannot request tools or mutate scope."""

    verdict: EvaluationVerdict
    reason: Annotated[str, Field(min_length=1, max_length=1_000)]
    evidence_sufficient: bool
    failure_fingerprint: Annotated[str, Field(min_length=1, max_length=200)] | None = None


class AgentResult(RuntimeModel):
    """Only output shape accepted from an agent implementation."""

    messages: tuple[MessageDraft, ...] = ()
    evidence: tuple[EvidenceDraft, ...] = ()
    complete: bool = True
    self_evaluation: AgentSelfEvaluation | None = None


class TraceEvent(RuntimeModel):
    """Append-only runtime event for reconstructing execution history."""

    id: UUID
    run_id: UUID
    step_id: UUID | None = None
    sequence: Annotated[int, Field(ge=1)]
    event_type: TraceEventType
    occurred_at: datetime
    state_from: AgentState | None = None
    state_to: AgentState | None = None
    detail: JsonObject = Field(default_factory=dict)


class RunTrace(RuntimeModel):
    """Consistent snapshot of a run and all append-only trace records."""

    run: Run
    steps: tuple[Step, ...]
    messages: tuple[Message, ...]
    evidence: tuple[Evidence, ...]
    events: tuple[TraceEvent, ...]
