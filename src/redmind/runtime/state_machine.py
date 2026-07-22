"""Pure lifecycle validation for RedMind runtime entities."""

from __future__ import annotations

from redmind.runtime.exceptions import InvalidStateTransitionError
from redmind.runtime.models import AgentState

_ALLOWED_TRANSITIONS: dict[AgentState, frozenset[AgentState]] = {
    AgentState.PROPOSED: frozenset(
        {
            AgentState.POLICY_CHECKED,
            AgentState.EXECUTING,
            AgentState.REJECTED,
            AgentState.FAILED,
        }
    ),
    AgentState.POLICY_CHECKED: frozenset(
        {
            AgentState.AWAITING_APPROVAL,
            AgentState.APPROVED,
            AgentState.EXECUTING,
            AgentState.REJECTED,
            AgentState.FAILED,
        }
    ),
    AgentState.AWAITING_APPROVAL: frozenset(
        {AgentState.APPROVED, AgentState.REJECTED, AgentState.FAILED}
    ),
    AgentState.APPROVED: frozenset(
        {AgentState.POLICY_CHECKED, AgentState.EXECUTING, AgentState.REJECTED, AgentState.FAILED}
    ),
    AgentState.EXECUTING: frozenset({AgentState.OBSERVED, AgentState.FAILED}),
    AgentState.OBSERVED: frozenset({AgentState.COMPLETED, AgentState.FAILED}),
    AgentState.REJECTED: frozenset(),
    AgentState.FAILED: frozenset(),
    AgentState.COMPLETED: frozenset(),
}

TERMINAL_STATES = frozenset(
    {AgentState.REJECTED, AgentState.FAILED, AgentState.COMPLETED}
)


def ensure_transition(current: AgentState, requested: AgentState) -> None:
    """Validate a state transition or raise a stable domain exception."""

    if requested not in _ALLOWED_TRANSITIONS[current]:
        raise InvalidStateTransitionError(current, requested)


def is_terminal(state: AgentState) -> bool:
    """Return whether no further state transition is permitted."""

    return state in TERMINAL_STATES
