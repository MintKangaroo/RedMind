"""Agent protocol and a deterministic, network-free test implementation."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Protocol

from pydantic import Field

from redmind.runtime.models import (
    AgentResult,
    Evidence,
    Message,
    Run,
    RuntimeModel,
    Step,
)


class CancellationToken:
    """Cooperative cancellation signal exposed to agents."""

    def __init__(self) -> None:
        self._event = asyncio.Event()
        self._reason = "cancellation requested"

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> str:
        return self._reason

    def cancel(self, reason: str) -> None:
        self._reason = reason
        self._event.set()

    async def wait(self) -> None:
        await self._event.wait()


class AgentContext(RuntimeModel):
    """Read-only context made available to one agent invocation."""

    run: Run
    step: Step
    messages: tuple[Message, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    cancellation: CancellationToken = Field(exclude=True)

    model_config = RuntimeModel.model_config | {"arbitrary_types_allowed": True}


class Agent(Protocol):
    """Minimal asynchronous contract implemented by every runtime agent."""

    @property
    def name(self) -> str:
        """Stable agent name included in trace records."""

    async def execute(self, context: AgentContext) -> AgentResult:
        """Produce schema-valid observations without mutating runtime state."""


class DeterministicMockAgent:
    """Scripted agent used to exercise runtime behavior without a model or tools."""

    def __init__(
        self,
        results: Sequence[AgentResult],
        *,
        name: str = "deterministic_mock",
        delay_seconds: float = 0.0,
    ) -> None:
        if not results:
            raise ValueError("at least one scripted result is required")
        if delay_seconds < 0:
            raise ValueError("delay_seconds must not be negative")
        self._results = tuple(results)
        self._name = name
        self._delay_seconds = delay_seconds

    @property
    def name(self) -> str:
        return self._name

    async def execute(self, context: AgentContext) -> AgentResult:
        if self._delay_seconds:
            await asyncio.sleep(self._delay_seconds)
        index = context.step.sequence - 1
        if index >= len(self._results):
            raise RuntimeError("mock script exhausted")
        return self._results[index].model_copy(deep=True)
