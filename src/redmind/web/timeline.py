"""Read-only view models for the multi-agent execution timeline."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ViewModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RunSummary(ViewModel):
    id: UUID
    objective: str
    project_id: str = "default"
    state: str
    started_at: datetime
    duration_ms: int = Field(ge=0)
    progress_percent: int = Field(ge=0, le=100)
    risk_level: str


class TimelineStep(ViewModel):
    sequence: int = Field(ge=1)
    agent_name: str
    title: str
    state: str
    occurred_at: datetime
    duration_ms: int = Field(ge=0)
    detail: str


class ToolCallView(ViewModel):
    name: str
    category: str
    permission: str
    outcome: str
    duration_ms: int = Field(ge=0)
    occurred_at: datetime


class EvidenceView(ViewModel):
    evidence_type: str
    source: str
    summary: str
    trust: str = "untrusted"
    occurred_at: datetime


class ApprovalView(ViewModel):
    request_id: str
    action_type: str
    status: str
    reviewer: str | None = None
    reason: str | None = None
    expires_at: datetime


class UsageView(ViewModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)
    budget_percent: int = Field(ge=0, le=100)


class FailureView(ViewModel):
    kind: str
    message: str
    retryable: bool


class ReportView(ViewModel):
    facts: tuple[str, ...] = ()
    inferences: tuple[str, ...] = ()
    unverified: tuple[str, ...] = ()
    recommendations: tuple[str, ...] = ()


class RunTimeline(ViewModel):
    run: RunSummary
    steps: tuple[TimelineStep, ...]
    tool_calls: tuple[ToolCallView, ...]
    evidence: tuple[EvidenceView, ...]
    approvals: tuple[ApprovalView, ...]
    usage: UsageView
    failure: FailureView | None = None
    report: ReportView


class TimelineRepository(Protocol):
    async def list_runs(self, project_id: str = "default") -> tuple[RunSummary, ...]: ...

    async def get_run(self, run_id: UUID, project_id: str = "default") -> RunTimeline | None: ...


class InMemoryTimelineRepository:
    def __init__(self, timelines: Iterable[RunTimeline] = ()) -> None:
        self._timelines = {timeline.run.id: timeline for timeline in timelines}

    async def list_runs(self, project_id: str = "default") -> tuple[RunSummary, ...]:
        return tuple(
            sorted(
                (
                    timeline.run
                    for timeline in self._timelines.values()
                    if timeline.run.project_id == project_id
                ),
                key=lambda run: run.started_at,
                reverse=True,
            )
        )

    async def get_run(self, run_id: UUID, project_id: str = "default") -> RunTimeline | None:
        timeline = self._timelines.get(run_id)
        return timeline if timeline is not None and timeline.run.project_id == project_id else None


def demo_timeline() -> RunTimeline:
    """Deterministic showcase data, clearly labeled by the web interface."""

    utc = timezone.utc  # noqa: UP017
    started = datetime(2026, 7, 28, 9, 14, 22, tzinfo=utc)
    run_id = UUID("5bdece5b-53fd-4a81-b326-cb0894963463")
    return RunTimeline(
        run=RunSummary(
            id=run_id,
            objective="승인된 lab-web-01의 서비스 Evidence gap 검증",
            state="completed",
            started_at=started,
            duration_ms=18_420,
            progress_percent=100,
            risk_level="medium",
        ),
        steps=(
            TimelineStep(
                sequence=1,
                agent_name="Scope Guard",
                title="허가 범위와 실행 예산 검증",
                state="completed",
                occurred_at=started,
                duration_ms=83,
                detail="등록된 사설 대상, 최대 8 step, 120초 예산 확인",
            ),
            TimelineStep(
                sequence=2,
                agent_name="Recon Analyst",
                title="기존 자산 정보 분석",
                state="completed",
                occurred_at=datetime(2026, 7, 28, 9, 14, 23, tzinfo=utc),
                duration_ms=1_104,
                detail="소유권과 DNS Evidence 확인, 서비스 버전 Evidence gap 식별",
            ),
            TimelineStep(
                sequence=3,
                agent_name="Enumeration Analyst",
                title="서비스 관찰 제안",
                state="completed",
                occurred_at=datetime(2026, 7, 28, 9, 14, 25, tzinfo=utc),
                duration_ms=2_315,
                detail="중복 없는 read-only service observation 생성",
            ),
            TimelineStep(
                sequence=4,
                agent_name="Risk Reviewer",
                title="Human Approval 검토",
                state="approved",
                occurred_at=datetime(2026, 7, 28, 9, 14, 29, tzinfo=utc),
                duration_ms=5_820,
                detail="target_only 영향과 rollback 계획 확인 후 승인",
            ),
            TimelineStep(
                sequence=5,
                agent_name="Report Agent",
                title="관찰 결과 정리",
                state="completed",
                occurred_at=datetime(2026, 7, 28, 9, 14, 38, tzinfo=utc),
                duration_ms=1_278,
                detail="사실·추론·미검증 항목을 분리한 최종 보고서 생성",
            ),
        ),
        tool_calls=(
            ToolCallView(
                name="asset_inventory",
                category="read_only",
                permission="read",
                outcome="completed",
                duration_ms=214,
                occurred_at=datetime(2026, 7, 28, 9, 14, 24, tzinfo=utc),
            ),
            ToolCallView(
                name="service_observer",
                category="observation",
                permission="observe",
                outcome="completed",
                duration_ms=1_684,
                occurred_at=datetime(2026, 7, 28, 9, 14, 35, tzinfo=utc),
            ),
        ),
        evidence=(
            EvidenceView(
                evidence_type="asset",
                source="autopentest:asset_inventory",
                summary="lab-web-01은 승인 레코드 LAB-2026-014에 포함됨",
                occurred_at=datetime(2026, 7, 28, 9, 14, 24, tzinfo=utc),
            ),
            EvidenceView(
                evidence_type="service",
                source="autopentest:service_observer",
                summary="TCP 443에서 HTTPS 서비스 메타데이터 관찰",
                occurred_at=datetime(2026, 7, 28, 9, 14, 36, tzinfo=utc),
            ),
        ),
        approvals=(
            ApprovalView(
                request_id="APR-2026-0042",
                action_type="observe_service",
                status="approved",
                reviewer="security-reviewer",
                reason="승인된 단일 대상의 비침습 관찰",
                expires_at=datetime(2026, 7, 28, 9, 29, 29, tzinfo=utc),
            ),
        ),
        usage=UsageView(
            input_tokens=8_420,
            output_tokens=2_180,
            estimated_cost_usd=0.0418,
            budget_percent=34,
        ),
        report=ReportView(
            facts=(
                "대상은 유효한 승인 범위에 포함되어 있다.",
                "TCP 443 HTTPS 서비스가 관찰되었다.",
            ),
            inferences=("버전 식별을 위한 추가 Evidence가 필요하다.",),
            unverified=("구체적인 제품 버전과 취약 여부는 검증되지 않았다.",),
            recommendations=(
                "승인된 구성 관리 자료와 서비스 버전을 대조한다.",
                "관찰 결과를 자산 인벤토리에 반영한다.",
            ),
        ),
    )


def demo_timelines() -> tuple[RunTimeline, ...]:
    """Return deterministic traces that exercise the dashboard's main states."""

    completed = demo_timeline()
    utc = timezone.utc  # noqa: UP017

    running = RunTimeline(
        run=RunSummary(
            id=UUID("fb991b76-c92e-4a40-9ae5-dd05cce4d13f"),
            objective="승인된 lab-api-02의 노출 서비스 인벤토리 대조",
            state="executing",
            started_at=datetime(2026, 7, 28, 8, 42, 8, tzinfo=utc),
            duration_ms=9_860,
            progress_percent=62,
            risk_level="low",
        ),
        steps=(
            TimelineStep(
                sequence=1,
                agent_name="Scope Guard",
                title="대상 및 실행 한도 검증",
                state="completed",
                occurred_at=datetime(2026, 7, 28, 8, 42, 8, tzinfo=utc),
                duration_ms=71,
                detail="lab-api-02의 유효한 허가 레코드와 read-only 정책 확인",
            ),
            TimelineStep(
                sequence=2,
                agent_name="Recon Analyst",
                title="자산 Evidence 정규화",
                state="completed",
                occurred_at=datetime(2026, 7, 28, 8, 42, 9, tzinfo=utc),
                duration_ms=1_406,
                detail="외부 응답을 untrusted content로 표시하고 스키마 검증 완료",
            ),
            TimelineStep(
                sequence=3,
                agent_name="Attack Path Planner",
                title="검증 후보 평가",
                state="executing",
                occurred_at=datetime(2026, 7, 28, 8, 42, 11, tzinfo=utc),
                duration_ms=8_383,
                detail="Evidence coverage를 계산하고 중복 관찰 제안을 제거하는 중",
            ),
        ),
        tool_calls=(
            ToolCallView(
                name="asset_inventory",
                category="read_only",
                permission="read",
                outcome="completed",
                duration_ms=319,
                occurred_at=datetime(2026, 7, 28, 8, 42, 9, tzinfo=utc),
            ),
        ),
        evidence=(
            EvidenceView(
                evidence_type="asset",
                source="autopentest:asset_inventory",
                summary="lab-api-02 자산 레코드의 허가 만료 시간이 유효함",
                occurred_at=datetime(2026, 7, 28, 8, 42, 10, tzinfo=utc),
            ),
        ),
        approvals=(),
        usage=UsageView(
            input_tokens=4_920,
            output_tokens=1_040,
            estimated_cost_usd=0.0226,
            budget_percent=21,
        ),
        report=ReportView(
            facts=("대상 자산의 허가 범위가 확인되었다.",),
            unverified=("서비스 인벤토리 대조는 아직 진행 중이다.",),
        ),
    )

    rejected = RunTimeline(
        run=RunSummary(
            id=UUID("106dca73-0bd7-44f8-9608-32f664e74111"),
            objective="등록되지 않은 대상이 포함된 관찰 제안 검토",
            state="rejected",
            started_at=datetime(2026, 7, 28, 7, 18, 44, tzinfo=utc),
            duration_ms=1_204,
            progress_percent=25,
            risk_level="high",
        ),
        steps=(
            TimelineStep(
                sequence=1,
                agent_name="Scope Guard",
                title="허가 범위 검증",
                state="completed",
                occurred_at=datetime(2026, 7, 28, 7, 18, 44, tzinfo=utc),
                duration_ms=54,
                detail="등록된 lab-web-01과 추가 대상의 범위를 각각 검증",
            ),
            TimelineStep(
                sequence=2,
                agent_name="Policy Engine",
                title="미등록 대상 차단",
                state="rejected",
                occurred_at=datetime(2026, 7, 28, 7, 18, 45, tzinfo=utc),
                duration_ms=1_150,
                detail="allowlist에 없는 대상이 발견되어 전체 제안을 deny-by-default 처리",
            ),
        ),
        tool_calls=(),
        evidence=(),
        approvals=(
            ApprovalView(
                request_id="APR-2026-0039",
                action_type="observe_service",
                status="rejected",
                reviewer="scope-guard",
                reason="허가 레코드가 없는 대상 포함",
                expires_at=datetime(2026, 7, 28, 7, 33, 45, tzinfo=utc),
            ),
        ),
        usage=UsageView(
            input_tokens=1_180,
            output_tokens=204,
            estimated_cost_usd=0.0041,
            budget_percent=5,
        ),
        failure=FailureView(
            kind="policy_denied",
            message="대상이 실행 allowlist에 포함되어 있지 않습니다.",
            retryable=False,
        ),
        report=ReportView(
            facts=("미등록 대상이 포함된 제안은 실행 전에 차단되었다.",),
            recommendations=("소유권과 허가 기간을 확인한 뒤 새 승인 요청을 생성한다.",),
        ),
    )
    return (completed, running, rejected)
