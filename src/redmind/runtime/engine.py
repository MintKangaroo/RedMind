"""Bounded asynchronous execution engine for schema-validated agents."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from datetime import datetime, timezone
from typing import Any, cast
from uuid import UUID, uuid4

from redmind.runtime.agents import Agent, AgentContext, CancellationToken
from redmind.runtime.exceptions import (
    ReflectionExhaustedError,
    RunAlreadyExecutingError,
    RunNotExecutableError,
    RuntimeCancellationError,
    RuntimeTimeoutError,
)
from redmind.runtime.models import (
    AgentResult,
    AgentState,
    Evidence,
    FailureDetails,
    FailureKind,
    Message,
    Run,
    RunRequest,
    RunTrace,
    Step,
)
from redmind.runtime.reflection import ReflectionController, ReflectionPolicy
from redmind.runtime.state_machine import is_terminal
from redmind.runtime.store import InMemoryTraceStore, TraceStore

UTC = timezone.utc  # noqa: UP017

Clock = Callable[[], datetime]
IdFactory = Callable[[], UUID]


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""

    return datetime.now(UTC)


class AgentRuntime:
    """Runs agents within explicit step, time, and cancellation bounds."""

    def __init__(
        self,
        store: TraceStore | None = None,
        *,
        clock: Clock = utc_now,
        id_factory: IdFactory = uuid4,
        reflection_policy: ReflectionPolicy | None = None,
    ) -> None:
        self._id_factory = id_factory
        self._clock = clock
        self._store = store or InMemoryTraceStore(id_factory)
        self._tokens: dict[UUID, CancellationToken] = {}
        self._active_runs: set[UUID] = set()
        self._reflection_policy = reflection_policy or ReflectionPolicy()

    async def create_run(self, request: RunRequest) -> Run:
        """Create a proposed run without starting agent execution."""

        run = Run(
            id=self._id_factory(),
            objective=request.objective,
            max_steps=request.max_steps,
            timeout_seconds=request.timeout_seconds,
            metadata=request.metadata,
            created_at=self._clock(),
        )
        await self._store.create_run(run)
        self._tokens[run.id] = CancellationToken()
        return run

    async def execute(self, run_id: UUID, agent: Agent) -> RunTrace:
        """Execute a proposed run to a terminal state and return its trace."""

        if run_id in self._active_runs:
            raise RunAlreadyExecutingError(run_id)
        run = await self._store.get_run(run_id)
        if run.state is not AgentState.PROPOSED:
            raise RunNotExecutableError(run_id, run.state)

        token = self._tokens.setdefault(run_id, CancellationToken())
        if run.cancellation_requested_at is not None:
            await self._fail_run(
                run_id,
                FailureDetails(
                    kind=FailureKind.CANCELLED,
                    message=run.cancellation_reason or "cancellation requested",
                ),
            )
            return await self._store.get_trace(run_id)

        self._active_runs.add(run_id)
        reflection = ReflectionController(self._reflection_policy)
        started_at = asyncio.get_running_loop().time()
        try:
            await self._store.transition_run(run_id, AgentState.EXECUTING, self._clock())
            for sequence in range(1, run.max_steps + 1):
                remaining = run.timeout_seconds - (asyncio.get_running_loop().time() - started_at)
                if remaining <= 0:
                    await self._fail_run(run_id, self._timeout_failure(run.timeout_seconds))
                    break
                if token.is_cancelled:
                    await self._fail_run(run_id, self._cancellation_failure(token.reason))
                    break

                step = Step(
                    id=self._id_factory(),
                    run_id=run_id,
                    sequence=sequence,
                    agent_name=agent.name,
                    created_at=self._clock(),
                )
                await self._store.create_step(step)
                step = await self._store.transition_step(
                    step.id, AgentState.EXECUTING, self._clock()
                )
                trace = await self._store.get_trace(run_id)
                context = AgentContext(
                    run=trace.run,
                    step=step,
                    messages=trace.messages,
                    evidence=trace.evidence,
                    cancellation=token,
                )

                try:
                    result = await self._invoke_with_retries(
                        agent,
                        context,
                        token,
                        remaining,
                        reflection,
                    )
                except RuntimeCancellationError as exc:
                    await self._fail_step_and_run(
                        step.id, run_id, self._cancellation_failure(str(exc))
                    )
                    break
                except RuntimeTimeoutError:
                    await self._fail_step_and_run(
                        step.id, run_id, self._timeout_failure(run.timeout_seconds)
                    )
                    break
                except ReflectionExhaustedError as exc:
                    await self._fail_step_and_run(
                        step.id,
                        run_id,
                        cast(FailureDetails, exc.failure),
                    )
                    break
                except Exception as exc:  # noqa: BLE001 - agent boundary must contain failures
                    await self._fail_step_and_run(
                        step.id,
                        run_id,
                        FailureDetails(
                            kind=FailureKind.AGENT_ERROR,
                            message=f"agent execution failed: {type(exc).__name__}",
                        ),
                    )
                    break

                replan, reflection_failure = reflection.review(result)
                if reflection_failure is not None:
                    await self._fail_step_and_run(
                        step.id,
                        run_id,
                        reflection_failure,
                    )
                    break
                await self._record_result(run_id, step.id, result)
                await self._store.transition_step(step.id, AgentState.OBSERVED, self._clock())
                await self._store.transition_step(step.id, AgentState.COMPLETED, self._clock())
                if result.complete:
                    await self._store.transition_run(run_id, AgentState.OBSERVED, self._clock())
                    await self._store.transition_run(run_id, AgentState.COMPLETED, self._clock())
                    break
                if replan:
                    continue
            else:
                await self._fail_run(
                    run_id,
                    FailureDetails(
                        kind=FailureKind.MAX_STEPS,
                        message=f"run reached its maximum of {run.max_steps} steps",
                    ),
                )
        except asyncio.CancelledError:
            await asyncio.shield(
                self._fail_run(
                    run_id,
                    self._cancellation_failure("execution task was cancelled"),
                )
            )
            raise
        finally:
            self._active_runs.discard(run_id)

        return await self._store.get_trace(run_id)

    async def cancel(self, run_id: UUID, reason: str = "cancellation requested") -> bool:
        """Request prompt cancellation, returning false for an already terminal run."""

        run = await self._store.get_run(run_id)
        if is_terminal(run.state):
            return False
        await self._store.request_cancellation(run_id, self._clock(), reason)
        token = self._tokens.setdefault(run_id, CancellationToken())
        token.cancel(reason)
        if run_id not in self._active_runs:
            await self._fail_run(run_id, self._cancellation_failure(reason))
        return True

    async def get_trace(self, run_id: UUID) -> RunTrace:
        """Return a consistent trace snapshot for a run."""

        return await self._store.get_trace(run_id)

    async def _invoke(
        self,
        operation: Coroutine[Any, Any, AgentResult],
        token: CancellationToken,
        timeout_seconds: float,
    ) -> AgentResult:
        agent_task = asyncio.create_task(operation)
        cancellation_task = asyncio.create_task(token.wait())
        done, pending = await asyncio.wait(
            {agent_task, cancellation_task},
            timeout=timeout_seconds,
            return_when=asyncio.FIRST_COMPLETED,
        )
        try:
            if agent_task in done:
                return agent_task.result()
            if cancellation_task in done:
                raise RuntimeCancellationError(token.reason)
            raise RuntimeTimeoutError
        finally:
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    async def _invoke_with_retries(
        self,
        agent: Agent,
        context: AgentContext,
        token: CancellationToken,
        timeout_seconds: float,
        reflection: ReflectionController,
    ) -> AgentResult:
        started_at = asyncio.get_running_loop().time()
        attempt = 0
        while True:
            remaining = timeout_seconds - (asyncio.get_running_loop().time() - started_at)
            if remaining <= 0:
                raise RuntimeTimeoutError
            try:
                raw_result = await self._invoke(
                    agent.execute(context),
                    token,
                    remaining,
                )
                return AgentResult.model_validate(raw_result)
            except (RuntimeCancellationError, RuntimeTimeoutError):
                raise
            except Exception as exc:  # noqa: BLE001 - retry boundary classifies failures
                failure = reflection.classify_exception(exc)
                if reflection.should_retry(failure, attempt):
                    attempt += 1
                    continue
                raise ReflectionExhaustedError(reflection.exhausted(failure, attempt + 1)) from exc

    async def _record_result(self, run_id: UUID, step_id: UUID, result: AgentResult) -> None:
        for message_draft in result.messages:
            await self._store.append_message(
                Message(
                    **message_draft.model_dump(),
                    id=self._id_factory(),
                    run_id=run_id,
                    step_id=step_id,
                    created_at=self._clock(),
                )
            )
        for evidence_draft in result.evidence:
            await self._store.append_evidence(
                Evidence(
                    **evidence_draft.model_dump(),
                    id=self._id_factory(),
                    run_id=run_id,
                    step_id=step_id,
                    collected_at=self._clock(),
                )
            )

    async def _fail_step_and_run(
        self, step_id: UUID, run_id: UUID, failure: FailureDetails
    ) -> None:
        await self._store.transition_step(step_id, AgentState.FAILED, self._clock(), failure)
        await self._fail_run(run_id, failure)

    async def _fail_run(self, run_id: UUID, failure: FailureDetails) -> None:
        run = await self._store.get_run(run_id)
        if not is_terminal(run.state):
            await self._store.transition_run(run_id, AgentState.FAILED, self._clock(), failure)

    @staticmethod
    def _cancellation_failure(reason: str) -> FailureDetails:
        return FailureDetails(kind=FailureKind.CANCELLED, message=reason)

    @staticmethod
    def _timeout_failure(timeout_seconds: float) -> FailureDetails:
        return FailureDetails(
            kind=FailureKind.TIMEOUT,
            message=f"run exceeded its {timeout_seconds:g} second timeout",
        )
