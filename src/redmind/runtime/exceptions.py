"""Stable exceptions raised by the agent runtime boundary."""

from __future__ import annotations

from uuid import UUID


class RuntimeErrorBase(Exception):
    """Base class for expected RedMind runtime errors."""


class RunNotFoundError(RuntimeErrorBase):
    """Raised when a run identifier is unknown to the trace store."""

    def __init__(self, run_id: UUID) -> None:
        super().__init__(f"run {run_id} was not found")


class ProjectScopeViolationError(RuntimeErrorBase):
    """Raised when a caller addresses a run from another project scope."""

    def __init__(self, run_id: UUID, project_id: str) -> None:
        super().__init__(f"run {run_id} is outside project scope {project_id}")


class IdempotencyConflictError(RuntimeErrorBase):
    """Raised when an idempotency key is concurrently claimed by another run."""

    def __init__(self, project_id: str, idempotency_key: str) -> None:
        super().__init__(
            f"idempotency key {idempotency_key!r} is already claimed in project {project_id}"
        )


class QueueCapacityError(RuntimeErrorBase):
    """Raised when a bounded execution queue cannot accept another job."""

    def __init__(self, capacity: int) -> None:
        super().__init__(f"execution queue capacity {capacity} has been reached")


class QueueClosedError(RuntimeErrorBase):
    """Raised when work is submitted after queue shutdown."""

    def __init__(self) -> None:
        super().__init__("execution queue is closed")


class StepNotFoundError(RuntimeErrorBase):
    """Raised when a step identifier is unknown to the trace store."""

    def __init__(self, step_id: UUID) -> None:
        super().__init__(f"step {step_id} was not found")


class InvalidStateTransitionError(RuntimeErrorBase):
    """Raised when a runtime entity attempts an invalid state transition."""

    def __init__(self, current: str, requested: str) -> None:
        super().__init__(f"cannot transition from {current} to {requested}")


class RunAlreadyExecutingError(RuntimeErrorBase):
    """Raised when two workers attempt to execute the same run."""

    def __init__(self, run_id: UUID) -> None:
        super().__init__(f"run {run_id} is already executing")


class RunNotExecutableError(RuntimeErrorBase):
    """Raised when execution is requested for a non-proposed run."""

    def __init__(self, run_id: UUID, state: str) -> None:
        super().__init__(f"run {run_id} in state {state} cannot be executed")


class RuntimeCancellationError(RuntimeErrorBase):
    """Internal control-flow signal for cooperative cancellation."""


class RuntimeTimeoutError(RuntimeErrorBase):
    """Internal control-flow signal for a bounded execution timeout."""


class ReflectionExhaustedError(RuntimeErrorBase):
    """Raised after a classified agent failure exhausts bounded retries."""

    def __init__(self, failure: object) -> None:
        self.failure = failure
        super().__init__("bounded agent retries were exhausted")
