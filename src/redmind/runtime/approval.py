"""Human approval workflow with expiry, reapproval and immutable audit events."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from enum import Enum
from hashlib import sha256
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import Field

from redmind.runtime.models import RunRequest, RuntimeModel
from redmind.runtime.planner import ActionProposal
from redmind.runtime.policy import PolicyEngine, PolicyViolation


UTC = timezone.utc


class ApprovalStatus(str, Enum):
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    EXECUTING = "executing"


class ApprovalEventType(str, Enum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    REAPPROVAL_REQUESTED = "reapproval_requested"
    POLICY_REVALIDATED = "policy_revalidated"
    EXECUTION_AUTHORIZED = "execution_authorized"


class ApprovalError(ValueError):
    """Stable boundary error for invalid approval operations."""


class ApprovalRequest(RuntimeModel):
    id: UUID
    proposal: ActionProposal
    proposal_digest: Annotated[str, Field(min_length=64, max_length=64)]
    status: ApprovalStatus
    created_at: datetime
    expires_at: datetime
    previous_request_id: UUID | None = None
    decided_at: datetime | None = None
    decided_by: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    decision_reason: Annotated[str, Field(min_length=1, max_length=1_000)] | None = None


class ApprovalAuditEvent(RuntimeModel):
    id: UUID
    request_id: UUID
    event_type: ApprovalEventType
    occurred_at: datetime
    actor: Annotated[str, Field(min_length=1, max_length=200)]
    reason: Annotated[str, Field(min_length=1, max_length=1_000)]


Clock = Callable[[], datetime]
IdFactory = Callable[[], UUID]


def utc_now() -> datetime:
    return datetime.now(UTC)


class ApprovalService:
    """In-memory reference workflow; persistence can implement the same semantics."""

    def __init__(
        self,
        policy_engine: PolicyEngine,
        *,
        clock: Clock = utc_now,
        id_factory: IdFactory = uuid4,
        max_ttl_seconds: int = 3_600,
    ) -> None:
        self.policy_engine = policy_engine
        self.clock = clock
        self.id_factory = id_factory
        self.max_ttl_seconds = max_ttl_seconds
        self._requests: dict[UUID, ApprovalRequest] = {}
        self._events: list[ApprovalAuditEvent] = []

    def request(
        self,
        proposal: ActionProposal,
        *,
        ttl_seconds: int = 900,
        actor: str = "system",
        previous_request_id: UUID | None = None,
    ) -> ApprovalRequest:
        self._require_text(actor, "actor")
        if ttl_seconds <= 0 or ttl_seconds > self.max_ttl_seconds:
            raise ApprovalError("approval TTL is outside the configured bound")
        if previous_request_id is not None:
            previous = self.get(previous_request_id)
            self._expire_if_needed(previous)
            previous = self.get(previous_request_id)
            if previous.status not in {ApprovalStatus.REJECTED, ApprovalStatus.EXPIRED}:
                raise ApprovalError("reapproval requires a rejected or expired request")
        now = self.clock()
        request = ApprovalRequest(
            id=self.id_factory(),
            proposal=proposal,
            proposal_digest=self._digest(proposal),
            status=ApprovalStatus.AWAITING_APPROVAL,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
            previous_request_id=previous_request_id,
        )
        self._requests[request.id] = request
        event = (
            ApprovalEventType.REAPPROVAL_REQUESTED
            if previous_request_id
            else ApprovalEventType.REQUESTED
        )
        self._audit(request.id, event, actor, "human approval requested")
        return request

    def approve(self, request_id: UUID, *, approver: str, reason: str) -> ApprovalRequest:
        self._require_text(approver, "approver")
        self._require_text(reason, "reason")
        request = self._pending(request_id)
        updated = request.model_copy(
            update={
                "status": ApprovalStatus.APPROVED,
                "decided_at": self.clock(),
                "decided_by": approver,
                "decision_reason": reason,
            }
        )
        self._requests[request_id] = updated
        self._audit(request_id, ApprovalEventType.APPROVED, approver, reason)
        return updated

    def reject(self, request_id: UUID, *, approver: str, reason: str) -> ApprovalRequest:
        self._require_text(approver, "approver")
        self._require_text(reason, "reason")
        request = self._pending(request_id)
        updated = request.model_copy(
            update={
                "status": ApprovalStatus.REJECTED,
                "decided_at": self.clock(),
                "decided_by": approver,
                "decision_reason": reason,
            }
        )
        self._requests[request_id] = updated
        self._audit(request_id, ApprovalEventType.REJECTED, approver, reason)
        return updated

    def reapprove(
        self,
        previous_request_id: UUID,
        proposal: ActionProposal,
        *,
        ttl_seconds: int = 900,
        actor: str = "system",
    ) -> ApprovalRequest:
        return self.request(
            proposal,
            ttl_seconds=ttl_seconds,
            actor=actor,
            previous_request_id=previous_request_id,
        )

    def authorize_execution(
        self,
        request_id: UUID,
        proposal: ActionProposal,
        run_request: RunRequest,
    ) -> ApprovalRequest:
        request = self.get(request_id)
        self._expire_if_needed(request)
        request = self.get(request_id)
        if request.status is not ApprovalStatus.APPROVED:
            raise ApprovalError("approval is not valid for execution")
        if request.proposal_digest != self._digest(proposal):
            raise ApprovalError("action proposal changed after approval")
        if proposal.target_id not in run_request.target_ids:
            raise PolicyViolation("approved target is absent from the run scope")
        if proposal.tool_name not in run_request.tool_names:
            raise PolicyViolation("approved tool is absent from the run allowlist")
        revalidation_request = run_request.model_copy(update={"approval_requested": True})
        self.policy_engine.check(revalidation_request)
        self._audit(
            request_id,
            ApprovalEventType.POLICY_REVALIDATED,
            "system",
            "current execution policy accepted the approved proposal",
        )
        updated = request.model_copy(update={"status": ApprovalStatus.EXECUTING})
        self._requests[request_id] = updated
        self._audit(
            request_id,
            ApprovalEventType.EXECUTION_AUTHORIZED,
            "system",
            "single execution authorization issued",
        )
        return updated

    def get(self, request_id: UUID) -> ApprovalRequest:
        try:
            return self._requests[request_id]
        except KeyError as exc:
            raise ApprovalError("approval request was not found") from exc

    def audit_log(self, request_id: UUID | None = None) -> tuple[ApprovalAuditEvent, ...]:
        return tuple(
            event
            for event in self._events
            if request_id is None or event.request_id == request_id
        )

    def _pending(self, request_id: UUID) -> ApprovalRequest:
        request = self.get(request_id)
        self._expire_if_needed(request)
        request = self.get(request_id)
        if request.status is not ApprovalStatus.AWAITING_APPROVAL:
            raise ApprovalError("approval request is no longer pending")
        return request

    def _expire_if_needed(self, request: ApprovalRequest) -> None:
        if (
            request.status in {ApprovalStatus.AWAITING_APPROVAL, ApprovalStatus.APPROVED}
            and self.clock() >= request.expires_at
        ):
            updated = request.model_copy(update={"status": ApprovalStatus.EXPIRED})
            self._requests[request.id] = updated
            self._audit(
                request.id,
                ApprovalEventType.EXPIRED,
                "system",
                "approval request expired",
            )

    def _audit(
        self,
        request_id: UUID,
        event_type: ApprovalEventType,
        actor: str,
        reason: str,
    ) -> None:
        self._events.append(
            ApprovalAuditEvent(
                id=self.id_factory(),
                request_id=request_id,
                event_type=event_type,
                occurred_at=self.clock(),
                actor=actor,
                reason=reason,
            )
        )

    @staticmethod
    def _digest(proposal: ActionProposal) -> str:
        return sha256(proposal.model_dump_json().encode("utf-8")).hexdigest()

    @staticmethod
    def _require_text(value: str, field: str) -> None:
        if not value.strip():
            raise ApprovalError(f"{field} must not be blank")
