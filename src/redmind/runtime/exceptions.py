"""Stable exceptions raised by the agent runtime boundary."""

from __future__ import annotations

from uuid import UUID


class RuntimeErrorBase(Exception):
    """Base class for expected RedMind runtime errors."""


class RunNotFoundError(RuntimeErrorBase):
    """Raised when a run identifier is unknown to the trace store."""

    def __init__(self, run_id: UUID) -> None:
        super().__init__(f"run {run_id} was not found")


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
