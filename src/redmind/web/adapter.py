"""Transform immutable runtime traces into observer timeline view models."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from redmind.runtime.approval import ApprovalRequest
from redmind.runtime.models import AgentState, Message, RunTrace
from redmind.runtime.tools import ToolCallRecord, ToolCategory
from redmind.web.timeline import (
    ApprovalView,
    EvidenceView,
    FailureView,
    ReportView,
    RunSummary,
    RunTimeline,
    TimelineStep,
    ToolCallView,
    UsageView,
)

TERMINAL_STATES = {
    AgentState.COMPLETED,
    AgentState.FAILED,
    AgentState.REJECTED,
}
PERMISSIONS = {
    ToolCategory.READ_ONLY: "read",
    ToolCategory.OBSERVATION: "observe",
    ToolCategory.VALIDATION: "validate",
    ToolCategory.STATE_CHANGING: "write",
}


class RuntimeTimelineAdapter:
    """Build the presentation snapshot without mutating runtime state."""

    @classmethod
    def from_trace(
        cls,
        trace: RunTrace,
        *,
        approvals: Iterable[ApprovalRequest] = (),
        tool_calls: Iterable[ToolCallRecord] = (),
        usage: UsageView | None = None,
        report: ReportView | None = None,
    ) -> RunTimeline:
        started_at = trace.run.started_at or trace.run.created_at
        ended_at = cls._ended_at(trace, started_at)
        messages_by_step = cls._messages_by_step(trace.messages)
        steps = tuple(
            TimelineStep(
                sequence=step.sequence,
                agent_name=step.agent_name,
                title=cls._step_title(messages_by_step.get(step.id, ()), step.agent_name),
                state=step.state.value,
                occurred_at=step.started_at or step.created_at,
                duration_ms=cls._duration_ms(
                    step.started_at or step.created_at,
                    step.completed_at or ended_at,
                ),
                detail=cls._step_detail(messages_by_step.get(step.id, ()), step.failure),
            )
            for step in sorted(trace.steps, key=lambda item: item.sequence)
        )
        approval_views = tuple(
            ApprovalView(
                request_id=str(request.id),
                action_type=request.proposal.action_type,
                status=request.status.value,
                reviewer=request.decided_by,
                reason=request.decision_reason,
                expires_at=request.expires_at,
            )
            for request in approvals
        )
        tool_views = tuple(
            ToolCallView(
                name=record.tool_name,
                category=record.category.value,
                permission=PERMISSIONS[record.category],
                outcome=record.outcome,
                duration_ms=0,
                occurred_at=ended_at,
            )
            for record in tool_calls
        )
        evidence = tuple(
            EvidenceView(
                evidence_type=item.evidence_type,
                source=item.source,
                summary=item.summary,
                trust="untrusted",
                occurred_at=item.collected_at,
            )
            for item in trace.evidence
        )
        failure = (
            FailureView(
                kind=trace.run.failure.kind.value,
                message=trace.run.failure.message,
                retryable=trace.run.failure.retryable,
            )
            if trace.run.failure is not None
            else None
        )
        resolved_report = report or ReportView(
            facts=tuple(item.summary for item in trace.evidence),
            unverified=(
                ("실행이 완료되지 않아 최종 검증 결과가 없습니다.",)
                if trace.run.state is not AgentState.COMPLETED
                else ()
            ),
        )
        return RunTimeline(
            run=RunSummary(
                id=trace.run.id,
                objective=trace.run.objective,
                project_id=trace.run.project_id,
                state=trace.run.state.value,
                started_at=started_at,
                duration_ms=cls._duration_ms(started_at, ended_at),
                progress_percent=cls._progress(trace),
                risk_level=cls._risk_level(trace),
            ),
            steps=steps,
            tool_calls=tool_views,
            evidence=evidence,
            approvals=approval_views,
            usage=usage
            or UsageView(
                input_tokens=0,
                output_tokens=0,
                estimated_cost_usd=0,
                budget_percent=0,
            ),
            failure=failure,
            report=resolved_report,
        )

    @staticmethod
    def _ended_at(trace: RunTrace, fallback: datetime) -> datetime:
        candidates = [
            *(event.occurred_at for event in trace.events),
            *(step.completed_at for step in trace.steps if step.completed_at is not None),
        ]
        if trace.run.completed_at is not None:
            candidates.append(trace.run.completed_at)
        return max(candidates, default=fallback)

    @staticmethod
    def _duration_ms(started_at: datetime, ended_at: datetime) -> int:
        return max(0, round((ended_at - started_at).total_seconds() * 1_000))

    @staticmethod
    def _messages_by_step(messages: tuple[Message, ...]) -> dict[object, tuple[Message, ...]]:
        grouped: dict[object, list[Message]] = {}
        for message in messages:
            grouped.setdefault(message.step_id, []).append(message)
        return {
            step_id: tuple(sorted(items, key=lambda item: item.created_at))
            for step_id, items in grouped.items()
        }

    @staticmethod
    def _step_title(messages: tuple[Message, ...], agent_name: str) -> str:
        for message in messages:
            title = message.metadata.get("title")
            if isinstance(title, str) and title.strip():
                return title[:200]
        return f"{agent_name} 실행"

    @staticmethod
    def _step_detail(messages: tuple[Message, ...], failure: object | None) -> str:
        if failure is not None:
            message = getattr(failure, "message", None)
            if isinstance(message, str):
                return message
        if messages:
            return messages[-1].content[:500]
        return "구조화된 실행 상태가 trace에 기록되었습니다."

    @staticmethod
    def _progress(trace: RunTrace) -> int:
        if trace.run.state in TERMINAL_STATES:
            return 100
        completed = sum(step.state in TERMINAL_STATES for step in trace.steps)
        return min(99, round(completed / max(1, trace.run.max_steps) * 100))

    @staticmethod
    def _risk_level(trace: RunTrace) -> str:
        value = trace.run.metadata.get("risk_level", "low")
        if isinstance(value, str) and value in {"low", "medium", "high", "critical"}:
            return value
        return "low"
