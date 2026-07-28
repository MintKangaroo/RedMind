"""Deterministic policy checks performed before agent execution."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass

from redmind.runtime.models import RunRequest


class PolicyViolation(ValueError):
    """Raised when a run request is outside its configured authorization boundary."""


@dataclass(frozen=True)
class PolicyConfig:
    allowed_targets: frozenset[str] = frozenset()
    allowed_tools: frozenset[str] = frozenset()
    max_steps: int = 10
    max_timeout_seconds: float = 300.0
    max_targets: int = 10
    require_approval_for: frozenset[str] = frozenset({"high", "critical"})
    block_public_ip_targets: bool = True


class PolicyEngine:
    """Validate bounded run requests without changing scope or executing tools."""

    def __init__(self, config: PolicyConfig) -> None:
        self.config = config

    def check(self, request: RunRequest) -> bool:
        if request.max_steps > self.config.max_steps:
            raise PolicyViolation("requested max_steps exceeds policy budget")
        if request.timeout_seconds > self.config.max_timeout_seconds:
            raise PolicyViolation("requested timeout exceeds policy budget")
        if len(request.target_ids) > self.config.max_targets:
            raise PolicyViolation("requested target count exceeds policy limit")
        if set(request.target_ids) - self.config.allowed_targets:
            raise PolicyViolation("target is not in the approved scope")
        if self.config.block_public_ip_targets:
            for target in request.target_ids:
                try:
                    address = ipaddress.ip_address(target)
                except ValueError:
                    continue
                if address.is_global:
                    raise PolicyViolation("public IP targets are blocked")
        if set(request.tool_names) - self.config.allowed_tools:
            raise PolicyViolation("tool is not in the allowlist")
        if (
            request.risk_level in self.config.require_approval_for
            and not request.approval_requested
        ):
            raise PolicyViolation("human approval is required for this risk level")
        return True
