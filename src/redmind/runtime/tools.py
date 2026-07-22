"""Typed, allowlisted and auditable tool registry for safe observations."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class ToolCategory(str, Enum):
    READ_ONLY = "read_only"
    OBSERVATION = "observation"
    VALIDATION = "validation"
    STATE_CHANGING = "state_changing"


class ToolPermission(str, Enum):
    READ = "read"
    OBSERVE = "observe"
    VALIDATE = "validate"
    WRITE = "write"


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EmptyToolInput(ToolInput):
    """Explicit empty input for tools that accept no arguments."""


class ToolCallRecord(ToolInput):
    tool_name: str = Field(min_length=1, max_length=100)
    category: ToolCategory
    arguments: dict[str, Any] = Field(default_factory=dict)
    outcome: str = Field(min_length=1, max_length=30)


InputT = TypeVar("InputT", bound=ToolInput)
OutputT = TypeVar("OutputT")
ToolHandler = Callable[[InputT], Awaitable[OutputT]]
AuditHook = Callable[[ToolCallRecord], Awaitable[None]]


class ToolSpec(Generic[InputT, OutputT]):
    def __init__(self, name: str, category: ToolCategory, permission: ToolPermission,
                 input_model: type[InputT], handler: ToolHandler[InputT],
                 timeout_seconds: float = 30.0) -> None:
        if not name or any(char.isspace() for char in name) or "shell" in name.lower():
            raise ValueError("tool name must be a non-shell identifier")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.name, self.category, self.permission = name, category, permission
        self.input_model, self.handler, self.timeout_seconds = input_model, handler, timeout_seconds


class ToolRegistry:
    """Registry that only exposes explicitly enabled non-mutating tools."""

    def __init__(self, *, enabled_categories: frozenset[ToolCategory] | None = None,
                 audit_hook: AuditHook | None = None) -> None:
        self.enabled_categories = enabled_categories or frozenset({ToolCategory.READ_ONLY, ToolCategory.OBSERVATION})
        self.audit_hook = audit_hook
        self._tools: dict[str, ToolSpec[Any, Any]] = {}

    def register(self, spec: ToolSpec[Any, Any]) -> None:
        if spec.category not in self.enabled_categories:
            raise ValueError(f"tool category {spec.category.value} is disabled")
        if spec.name in self._tools:
            raise ValueError(f"tool {spec.name} is already registered")
        self._tools[spec.name] = spec

    async def execute(self, name: str, arguments: dict[str, Any] | ToolInput) -> Any:
        try:
            spec = self._tools[name]
        except KeyError as exc:
            raise KeyError(f"tool {name} is not registered") from exc
        validated = arguments if isinstance(arguments, ToolInput) else spec.input_model.model_validate(arguments)
        try:
            result = await asyncio.wait_for(spec.handler(validated), timeout=spec.timeout_seconds)
        except Exception:
            await self._audit(spec, validated, "failed")
            raise
        await self._audit(spec, validated, "completed")
        return result

    async def _audit(self, spec: ToolSpec[Any, Any], arguments: ToolInput, outcome: str) -> None:
        if self.audit_hook:
            await self.audit_hook(ToolCallRecord(tool_name=spec.name, category=spec.category,
                                                  arguments=arguments.model_dump(), outcome=outcome))
