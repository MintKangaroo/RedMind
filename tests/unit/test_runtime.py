import asyncio

import pytest

from redmind.runtime import (
    AgentResult,
    AgentRuntime,
    AgentState,
    DeterministicMockAgent,
    EvidenceDraft,
    FailureKind,
    MessageDraft,
    MessageRole,
    RunRequest,
)
from redmind.runtime.exceptions import InvalidStateTransitionError
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
