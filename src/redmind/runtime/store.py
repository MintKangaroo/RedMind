"""Trace persistence interfaces and an in-memory reference implementation."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Protocol
from uuid import UUID

from redmind.runtime.exceptions import RunNotFoundError, StepNotFoundError
from redmind.runtime.models import (
    AgentState,
    Evidence,
    FailureDetails,
    JsonObject,
    Message,
    Run,
    RunTrace,
    Step,
    TraceEvent,
    TraceEventType,
)
from redmind.runtime.state_machine import ensure_transition, is_terminal


class TraceStore(Protocol):
    """Persistence boundary required by the runtime engine."""

    async def create_run(self, run: Run) -> None: ...

    async def create_step(self, step: Step) -> None: ...

    async def get_run(self, run_id: UUID) -> Run: ...

    async def get_step(self, step_id: UUID) -> Step: ...

    async def transition_run(
        self,
        run_id: UUID,
        requested: AgentState,
        occurred_at: datetime,
        failure: FailureDetails | None = None,
    ) -> Run: ...

    async def transition_step(
        self,
        step_id: UUID,
        requested: AgentState,
        occurred_at: datetime,
        failure: FailureDetails | None = None,
    ) -> Step: ...

    async def request_cancellation(
        self, run_id: UUID, occurred_at: datetime, reason: str
    ) -> Run: ...

    async def append_message(self, message: Message) -> None: ...

    async def append_evidence(self, evidence: Evidence) -> None: ...

    async def get_trace(self, run_id: UUID) -> RunTrace: ...


class InMemoryTraceStore:
    """Concurrency-safe trace store intended for tests and local development."""

    def __init__(self, id_factory: Callable[[], UUID]) -> None:
        self._id_factory = id_factory
        self._runs: dict[UUID, Run] = {}
        self._steps: dict[UUID, Step] = {}
        self._messages: list[Message] = []
        self._evidence: list[Evidence] = []
        self._events: list[TraceEvent] = []
        self._event_sequences: dict[UUID, int] = {}
        self._lock = asyncio.Lock()

    async def create_run(self, run: Run) -> None:
        async with self._lock:
            if run.id in self._runs:
                raise ValueError(f"run {run.id} already exists")
            self._runs[run.id] = run
            self._append_event(
                run_id=run.id,
                event_type=TraceEventType.RUN_CREATED,
                occurred_at=run.created_at,
                state_to=run.state,
            )

    async def create_step(self, step: Step) -> None:
        async with self._lock:
            self._require_run(step.run_id)
            if step.id in self._steps:
                raise ValueError(f"step {step.id} already exists")
            self._steps[step.id] = step
            self._append_event(
                run_id=step.run_id,
                step_id=step.id,
                event_type=TraceEventType.STEP_CREATED,
                occurred_at=step.created_at,
                state_to=step.state,
                detail={"agent_name": step.agent_name, "sequence": step.sequence},
            )

    async def get_run(self, run_id: UUID) -> Run:
        async with self._lock:
            return self._require_run(run_id)

    async def get_step(self, step_id: UUID) -> Step:
        async with self._lock:
            return self._require_step(step_id)

    async def transition_run(
        self,
        run_id: UUID,
        requested: AgentState,
        occurred_at: datetime,
        failure: FailureDetails | None = None,
    ) -> Run:
        async with self._lock:
            current = self._require_run(run_id)
            ensure_transition(current.state, requested)
            updated = current.model_copy(
                update={
                    "state": requested,
                    "started_at": occurred_at
                    if requested is AgentState.EXECUTING and current.started_at is None
                    else current.started_at,
                    "completed_at": occurred_at if is_terminal(requested) else None,
                    "failure": failure,
                }
            )
            self._runs[run_id] = updated
            self._append_event(
                run_id=run_id,
                event_type=TraceEventType.STATE_TRANSITION,
                occurred_at=occurred_at,
                state_from=current.state,
                state_to=requested,
                detail=self._failure_detail(failure),
            )
            return updated

    async def transition_step(
        self,
        step_id: UUID,
        requested: AgentState,
        occurred_at: datetime,
        failure: FailureDetails | None = None,
    ) -> Step:
        async with self._lock:
            current = self._require_step(step_id)
            ensure_transition(current.state, requested)
            updated = current.model_copy(
                update={
                    "state": requested,
                    "started_at": occurred_at
                    if requested is AgentState.EXECUTING and current.started_at is None
                    else current.started_at,
                    "completed_at": occurred_at if is_terminal(requested) else None,
                    "failure": failure,
                }
            )
            self._steps[step_id] = updated
            self._append_event(
                run_id=current.run_id,
                step_id=step_id,
                event_type=TraceEventType.STATE_TRANSITION,
                occurred_at=occurred_at,
                state_from=current.state,
                state_to=requested,
                detail=self._failure_detail(failure),
            )
            return updated

    async def request_cancellation(self, run_id: UUID, occurred_at: datetime, reason: str) -> Run:
        async with self._lock:
            current = self._require_run(run_id)
            updated = current.model_copy(
                update={
                    "cancellation_requested_at": occurred_at,
                    "cancellation_reason": reason,
                }
            )
            self._runs[run_id] = updated
            self._append_event(
                run_id=run_id,
                event_type=TraceEventType.CANCELLATION_REQUESTED,
                occurred_at=occurred_at,
                detail={"reason": reason},
            )
            return updated

    async def append_message(self, message: Message) -> None:
        async with self._lock:
            self._validate_child(message.run_id, message.step_id)
            self._messages.append(message)
            self._append_event(
                run_id=message.run_id,
                step_id=message.step_id,
                event_type=TraceEventType.MESSAGE_RECORDED,
                occurred_at=message.created_at,
                detail={"message_id": str(message.id)},
            )

    async def append_evidence(self, evidence: Evidence) -> None:
        async with self._lock:
            self._validate_child(evidence.run_id, evidence.step_id)
            self._evidence.append(evidence)
            self._append_event(
                run_id=evidence.run_id,
                step_id=evidence.step_id,
                event_type=TraceEventType.EVIDENCE_RECORDED,
                occurred_at=evidence.collected_at,
                detail={"evidence_id": str(evidence.id)},
            )

    async def get_trace(self, run_id: UUID) -> RunTrace:
        async with self._lock:
            run = self._require_run(run_id)
            return RunTrace(
                run=run,
                steps=tuple(
                    sorted(
                        (step for step in self._steps.values() if step.run_id == run_id),
                        key=lambda step: step.sequence,
                    )
                ),
                messages=tuple(message for message in self._messages if message.run_id == run_id),
                evidence=tuple(item for item in self._evidence if item.run_id == run_id),
                events=tuple(event for event in self._events if event.run_id == run_id),
            )

    def _require_run(self, run_id: UUID) -> Run:
        try:
            return self._runs[run_id]
        except KeyError as exc:
            raise RunNotFoundError(run_id) from exc

    def _require_step(self, step_id: UUID) -> Step:
        try:
            return self._steps[step_id]
        except KeyError as exc:
            raise StepNotFoundError(step_id) from exc

    def _validate_child(self, run_id: UUID, step_id: UUID) -> None:
        self._require_run(run_id)
        step = self._require_step(step_id)
        if step.run_id != run_id:
            raise ValueError("trace record run_id does not match its step")

    def _append_event(
        self,
        *,
        run_id: UUID,
        event_type: TraceEventType,
        occurred_at: datetime,
        step_id: UUID | None = None,
        state_from: AgentState | None = None,
        state_to: AgentState | None = None,
        detail: JsonObject | None = None,
    ) -> None:
        sequence = self._event_sequences.get(run_id, 0) + 1
        self._event_sequences[run_id] = sequence
        self._events.append(
            TraceEvent(
                id=self._id_factory(),
                run_id=run_id,
                step_id=step_id,
                sequence=sequence,
                event_type=event_type,
                occurred_at=occurred_at,
                state_from=state_from,
                state_to=state_to,
                detail=detail or {},
            )
        )

    @staticmethod
    def _failure_detail(failure: FailureDetails | None) -> JsonObject:
        if failure is None:
            return {}
        return {
            "failure_kind": failure.kind.value,
            "failure_message": failure.message,
            "retryable": failure.retryable,
        }
