import asyncio
from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from redmind.runtime import (
    AgentContext,
    AgentResult,
    AgentRuntime,
    AgentState,
    CancellationToken,
    DeterministicMockAgent,
    EvidenceDraft,
    FailureKind,
    InMemoryTraceStore,
    Message,
    MessageDraft,
    MessageRole,
    ReflectionController,
    Run,
    RunRequest,
    Step,
)
from redmind.runtime.exceptions import (
    InvalidStateTransitionError,
    RunAlreadyExecutingError,
    RunNotExecutableError,
    RunNotFoundError,
    RuntimeTimeoutError,
    StepNotFoundError,
)
from redmind.runtime.state_machine import ensure_transition


def run(coro):
    return asyncio.run(coro)


def test_successful_mock_agent_records_trace():
    result = AgentResult(
        messages=(MessageDraft(role=MessageRole.AGENT, sender="mock", content="done"),),
        evidence=(EvidenceDraft(evidence_type="observation", source="mock", summary="ok"),),
    )
    runtime = AgentRuntime()
    created = run(runtime.create_run(RunRequest(objective="inspect lab")))
    trace = run(runtime.execute(created.id, DeterministicMockAgent([result])))
    assert trace.run.state is AgentState.COMPLETED
    assert trace.steps[0].state is AgentState.COMPLETED
    assert len(trace.messages) == len(trace.evidence) == 1
    assert any(event.event_type.value == "state_transition" for event in trace.events)


def test_max_steps_is_bounded():
    runtime = AgentRuntime()
    created = run(runtime.create_run(RunRequest(objective="inspect", max_steps=2)))
    result = AgentResult(complete=False)
    trace = run(runtime.execute(created.id, DeterministicMockAgent([result, result])))
    assert trace.run.state is AgentState.FAILED
    assert trace.run.failure is not None
    assert trace.run.failure.kind is FailureKind.MAX_STEPS
    assert len(trace.steps) == 2


def test_timeout_and_cancellation_are_terminal():
    runtime = AgentRuntime()
    timed = run(runtime.create_run(RunRequest(objective="slow", timeout_seconds=0.01)))
    trace = run(runtime.execute(timed.id, DeterministicMockAgent([AgentResult()], delay_seconds=1)))
    assert trace.run.failure is not None and trace.run.failure.kind is FailureKind.TIMEOUT

    runtime = AgentRuntime()
    cancelled = run(runtime.create_run(RunRequest(objective="cancel")))

    async def scenario():
        task = asyncio.create_task(
            runtime.execute(cancelled.id, DeterministicMockAgent([AgentResult()], delay_seconds=1))
        )
        await asyncio.sleep(0.01)
        await runtime.cancel(cancelled.id, "operator stop")
        return await task

    trace = run(scenario())
    assert trace.run.failure is not None and trace.run.failure.kind is FailureKind.CANCELLED


def test_state_machine_rejects_invalid_transition():
    with pytest.raises(InvalidStateTransitionError):
        ensure_transition(AgentState.COMPLETED, AgentState.EXECUTING)


def test_mock_agent_and_run_request_validation_boundaries():
    with pytest.raises(ValueError, match="scripted result"):
        DeterministicMockAgent([])
    with pytest.raises(ValueError, match="negative"):
        DeterministicMockAgent([AgentResult()], delay_seconds=-1)
    with pytest.raises(ValidationError, match="objective"):
        RunRequest(objective=" ")

    runtime = AgentRuntime()
    created = run(runtime.create_run(RunRequest(objective="exhaust script", max_steps=2)))
    trace = run(
        runtime.execute(
            created.id,
            DeterministicMockAgent([AgentResult(complete=False)]),
        )
    )
    assert trace.run.failure is not None
    assert trace.run.failure.kind is FailureKind.RETRY_EXHAUSTED


def test_duplicate_and_terminal_execution_requests_are_rejected():
    async def scenario():
        runtime = AgentRuntime()
        active = await runtime.create_run(RunRequest(objective="active"))
        task = asyncio.create_task(
            runtime.execute(
                active.id,
                DeterministicMockAgent([AgentResult()], delay_seconds=1),
            )
        )
        await asyncio.sleep(0.01)
        with pytest.raises(RunAlreadyExecutingError):
            await runtime.execute(active.id, DeterministicMockAgent([AgentResult()]))
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        completed = await runtime.create_run(RunRequest(objective="completed"))
        await runtime.execute(completed.id, DeterministicMockAgent([AgentResult()]))
        assert (await runtime.get_trace(completed.id)).run.state is AgentState.COMPLETED
        assert await runtime.cancel(completed.id) is False
        with pytest.raises(RunNotExecutableError):
            await runtime.execute(completed.id, DeterministicMockAgent([AgentResult()]))

    run(scenario())


def test_preflight_and_between_step_cancellation_paths():
    class SelfCancellingAgent:
        name = "self-cancelling"

        async def execute(self, context):
            context.cancellation.cancel("cancel after this observation")
            return AgentResult(complete=False)

    async def scenario():
        runtime = AgentRuntime()
        preflight = await runtime.create_run(RunRequest(objective="preflight cancel"))
        await runtime._store.request_cancellation(
            preflight.id,
            preflight.created_at,
            "cancelled before execution",
        )
        trace = await runtime.execute(
            preflight.id,
            DeterministicMockAgent([AgentResult()]),
        )
        assert trace.run.failure is not None
        assert trace.run.failure.kind is FailureKind.CANCELLED

        inactive = await runtime.create_run(RunRequest(objective="inactive cancel"))
        assert await runtime.cancel(inactive.id, "operator denied") is True
        assert (await runtime.get_trace(inactive.id)).run.failure is not None

        between_steps = await runtime.create_run(RunRequest(objective="between steps", max_steps=2))
        trace = await runtime.execute(between_steps.id, SelfCancellingAgent())
        assert trace.run.failure is not None
        assert trace.run.failure.kind is FailureKind.CANCELLED

    run(scenario())


def test_immediate_timeout_and_unexpected_reflection_error_are_contained(monkeypatch):
    class FailingAgent:
        name = "failing"

        async def execute(self, context):
            raise RuntimeError("agent boundary failure")

    runtime = AgentRuntime()
    immediate = run(
        runtime.create_run(RunRequest(objective="immediate timeout", timeout_seconds=1e-12))
    )
    trace = run(runtime.execute(immediate.id, DeterministicMockAgent([AgentResult()])))
    assert trace.run.failure is not None
    assert trace.run.failure.kind is FailureKind.TIMEOUT

    def broken_classifier(self, exception):
        raise LookupError("classifier failed")

    monkeypatch.setattr(ReflectionController, "classify_exception", broken_classifier)
    created = run(runtime.create_run(RunRequest(objective="contain failure")))
    trace = run(runtime.execute(created.id, FailingAgent()))
    assert trace.run.failure is not None
    assert trace.run.failure.kind is FailureKind.AGENT_ERROR


def test_retry_invocation_rejects_exhausted_time_budget():
    async def scenario():
        runtime = AgentRuntime()
        created = await runtime.create_run(RunRequest(objective="retry timeout"))
        step = Step(
            id=uuid4(),
            run_id=created.id,
            sequence=1,
            agent_name="mock",
            created_at=created.created_at,
        )
        token = CancellationToken()
        context = AgentContext(
            run=created,
            step=step,
            cancellation=token,
        )
        with pytest.raises(RuntimeTimeoutError):
            await runtime._invoke_with_retries(
                DeterministicMockAgent([AgentResult()]),
                context,
                token,
                0,
                ReflectionController(),
            )

    run(scenario())


def test_trace_store_duplicate_missing_and_cross_run_guards():
    async def scenario():
        store = InMemoryTraceStore(uuid4)
        now = datetime(2026, 1, 1)
        first = Run(
            id=uuid4(),
            objective="first",
            max_steps=1,
            timeout_seconds=10,
            created_at=now,
        )
        second = first.model_copy(update={"id": uuid4(), "objective": "second"})
        await store.create_run(first)
        with pytest.raises(ValueError, match="already exists"):
            await store.create_run(first)
        await store.create_run(second)

        first_step = Step(
            id=uuid4(),
            run_id=first.id,
            sequence=1,
            agent_name="first-agent",
            created_at=now,
        )
        second_step = first_step.model_copy(
            update={"id": uuid4(), "run_id": second.id, "agent_name": "second-agent"}
        )
        await store.create_step(first_step)
        with pytest.raises(ValueError, match="already exists"):
            await store.create_step(first_step)
        await store.create_step(second_step)
        assert await store.get_step(first_step.id) == first_step

        with pytest.raises(RunNotFoundError):
            await store.get_run(uuid4())
        with pytest.raises(StepNotFoundError):
            await store.get_step(uuid4())
        with pytest.raises(ValueError, match="does not match"):
            await store.append_message(
                Message(
                    id=uuid4(),
                    run_id=first.id,
                    step_id=second_step.id,
                    role=MessageRole.AGENT,
                    sender="agent",
                    content="cross-run message",
                    created_at=now,
                )
            )

    run(scenario())
