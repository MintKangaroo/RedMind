"""Bounded reflection, failure classification and repetition controls."""

from __future__ import annotations

from collections import Counter

from pydantic import Field

from redmind.runtime.models import (
    AgentResult,
    EvaluationVerdict,
    FailureDetails,
    FailureKind,
    RuntimeModel,
)


class ReflectionPolicy(RuntimeModel):
    max_retries: int = Field(default=2, ge=0, le=10)
    max_same_failure: int = Field(default=2, ge=1, le=10)


class ReflectionController:
    """Keep retry and replan behavior inside explicit deterministic bounds."""

    def __init__(self, policy: ReflectionPolicy | None = None) -> None:
        self.policy = policy or ReflectionPolicy()
        self._failure_counts: Counter[str] = Counter()

    def classify_exception(self, exception: Exception) -> FailureDetails:
        if exception.__class__.__name__ == "ValidationError":
            return FailureDetails(
                kind=FailureKind.INVALID_OUTPUT,
                message="agent returned output that failed schema validation",
                retryable=True,
            )
        return FailureDetails(
            kind=FailureKind.AGENT_ERROR,
            message=f"agent execution failed: {type(exception).__name__}",
            retryable=True,
        )

    def should_retry(self, failure: FailureDetails, attempt: int) -> bool:
        fingerprint = f"{failure.kind.value}:{failure.message}"
        self._failure_counts[fingerprint] += 1
        return (
            failure.retryable
            and attempt < self.policy.max_retries
            and self._failure_counts[fingerprint] <= self.policy.max_same_failure
        )

    def exhausted(self, failure: FailureDetails, attempts: int) -> FailureDetails:
        return FailureDetails(
            kind=FailureKind.RETRY_EXHAUSTED,
            message=(
                f"{failure.kind.value} persisted after {attempts} bounded "
                f"attempt{'s' if attempts != 1 else ''}"
            ),
            retryable=False,
        )

    def review(self, result: AgentResult) -> tuple[bool, FailureDetails | None]:
        evaluation = result.self_evaluation
        if evaluation is None or evaluation.verdict is EvaluationVerdict.ACCEPT:
            return False, None
        if evaluation.verdict is EvaluationVerdict.REJECT:
            return False, FailureDetails(
                kind=FailureKind.SELF_REJECTED,
                message=f"agent self-evaluation rejected output: {evaluation.reason}",
            )
        if evaluation.evidence_sufficient or result.complete:
            return False, FailureDetails(
                kind=FailureKind.INVALID_OUTPUT,
                message="replan requires incomplete output and insufficient evidence",
            )
        fingerprint = evaluation.failure_fingerprint or evaluation.reason
        key = f"evidence:{fingerprint}"
        self._failure_counts[key] += 1
        if self._failure_counts[key] > self.policy.max_same_failure:
            return False, FailureDetails(
                kind=FailureKind.REPEATED_FAILURE,
                message="identical evidence gap exceeded the repetition limit",
            )
        return True, None
