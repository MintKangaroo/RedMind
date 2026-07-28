import asyncio

import pytest
from pydantic import ValidationError

from redmind.runtime import (
    AgentResult,
    AgentRuntime,
    AgentSelfEvaluation,
    AgentState,
    DeterministicMockAgent,
    EvaluationVerdict,
    FailureKind,
    ReflectionController,
    ReflectionPolicy,
    RunRequest,
)


class FlakyAgent:
    name = "flaky"

    def __init__(self, failures):
        self.failures = failures
        self.calls = 0

    async def execute(self, context):
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError("temporary model failure")
        return AgentResult()


def run(coro):
    return asyncio.run(coro)


def test_runtime_retries_agent_error_within_bound():
    runtime = AgentRuntime(reflection_policy=ReflectionPolicy(max_retries=2, max_same_failure=2))
    created = run(runtime.create_run(RunRequest(objective="inspect")))
    agent = FlakyAgent(failures=2)
    trace = run(runtime.execute(created.id, agent))
    assert trace.run.state is AgentState.COMPLETED
    assert agent.calls == 3


def test_retry_exhaustion_is_classified():
    runtime = AgentRuntime(reflection_policy=ReflectionPolicy(max_retries=1, max_same_failure=1))
    created = run(runtime.create_run(RunRequest(objective="inspect")))
    trace = run(runtime.execute(created.id, FlakyAgent(failures=3)))
    assert trace.run.failure is not None
    assert trace.run.failure.kind is FailureKind.RETRY_EXHAUSTED


def test_evidence_gap_replans_but_repetition_is_bounded():
    evaluation = AgentSelfEvaluation(
        verdict=EvaluationVerdict.REPLAN,
        reason="missing service version",
        evidence_sufficient=False,
        failure_fingerprint="missing-version",
    )
    runtime = AgentRuntime(reflection_policy=ReflectionPolicy(max_retries=0, max_same_failure=1))
    created = run(runtime.create_run(RunRequest(objective="inspect", max_steps=3)))
    agent = DeterministicMockAgent(
        [
            AgentResult(complete=False, self_evaluation=evaluation),
            AgentResult(complete=False, self_evaluation=evaluation),
        ]
    )
    trace = run(runtime.execute(created.id, agent))
    assert trace.run.failure is not None
    assert trace.run.failure.kind is FailureKind.REPEATED_FAILURE
    assert len(trace.steps) == 2


def test_invalid_replan_and_self_rejection_fail_closed():
    invalid = AgentSelfEvaluation(
        verdict=EvaluationVerdict.REPLAN,
        reason="contradictory evaluation",
        evidence_sufficient=True,
    )
    runtime = AgentRuntime()
    created = run(runtime.create_run(RunRequest(objective="inspect")))
    trace = run(
        runtime.execute(
            created.id,
            DeterministicMockAgent([AgentResult(complete=False, self_evaluation=invalid)]),
        )
    )
    assert trace.run.failure is not None
    assert trace.run.failure.kind is FailureKind.INVALID_OUTPUT

    rejected = AgentSelfEvaluation(
        verdict=EvaluationVerdict.REJECT,
        reason="output conflicts with validated evidence",
        evidence_sufficient=False,
    )
    runtime = AgentRuntime()
    created = run(runtime.create_run(RunRequest(objective="inspect")))
    trace = run(
        runtime.execute(
            created.id,
            DeterministicMockAgent([AgentResult(self_evaluation=rejected)]),
        )
    )
    assert trace.run.failure is not None
    assert trace.run.failure.kind is FailureKind.SELF_REJECTED


def test_schema_validation_errors_receive_stable_failure_classification():
    with pytest.raises(ValidationError) as caught:
        RunRequest(objective="")
    failure = ReflectionController().classify_exception(caught.value)
    assert failure.kind is FailureKind.INVALID_OUTPUT
    assert failure.retryable is True
