import asyncio
from datetime import datetime, timedelta, timezone
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from redmind.runtime.approval import (
    ApprovalAuditEvent,
    ApprovalEventType,
    ApprovalRequest,
    ApprovalStatus,
)
from redmind.runtime.models import (
    AgentState,
    Evidence,
    FailureDetails,
    FailureKind,
    Message,
    MessageRole,
    Run,
    RunTrace,
    Step,
    TraceEvent,
    TraceEventType,
)
from redmind.runtime.planner import ActionProposal
from redmind.runtime.tools import ToolCallRecord, ToolCategory
from redmind.web.adapter import RuntimeTimelineAdapter
from redmind.web.app import create_app
from redmind.web.auth import (
    AccessRole,
    AuthenticationError,
    AuthorizationError,
    Principal,
    StaticTokenAuthorizer,
)
from redmind.web.production import create_app_from_env
from redmind.web.repository import SQLRepository
from redmind.web.settings import ObserverSettings
from redmind.web.signing import AuditSigner, SignedAuditExport
from redmind.web.telemetry import ObserverTelemetry, TelemetryRuntime, create_otlp_runtime
from redmind.web.timeline import (
    InMemoryTimelineRepository,
    ReportView,
    UsageView,
    demo_timeline,
    demo_timelines,
)

UTC = timezone.utc  # noqa: UP017
NOW = datetime(2026, 7, 28, 1, 0, tzinfo=UTC)
VIEWER_TOKEN = "viewer-token-" + ("v" * 32)
AUDITOR_TOKEN = "auditor-token-" + ("a" * 32)
SIGNING_KEY = "signing-key-" + ("s" * 32)


def run(coroutine):
    return asyncio.run(coroutine)


def proposal() -> ActionProposal:
    return ActionProposal(
        action_type="observe_service",
        target_id="lab-web-01",
        purpose="Validate an evidence gap",
        required_evidence=("asset",),
        expected_observation="service metadata",
        risk_level="medium",
        scope_impact="target_only",
        timeout=30,
        rollback_plan="Stop the read-only observation.",
        approval_required=True,
        tool_name="service_observer",
        structured_arguments={"target_id": "lab-web-01"},
    )


def approval_request() -> ApprovalRequest:
    return ApprovalRequest(
        id=UUID("a59d0902-8857-4f29-b581-05b6c240c480"),
        proposal=proposal(),
        proposal_digest="a" * 64,
        status=ApprovalStatus.APPROVED,
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=15),
        decided_at=NOW + timedelta(minutes=1),
        decided_by="security-reviewer",
        decision_reason="Authorized lab observation",
    )


def approval_event(
    event_id: UUID | None = None,
    request_id: UUID | None = None,
) -> ApprovalAuditEvent:
    request = approval_request()
    return ApprovalAuditEvent(
        id=event_id or UUID("e4401107-6197-49b9-b4a6-57eb4dd104b4"),
        request_id=request_id or request.id,
        event_type=ApprovalEventType.APPROVED,
        occurred_at=NOW + timedelta(minutes=1),
        actor="security-reviewer",
        reason="Authorized lab observation",
    )


def test_static_token_authentication_and_role_boundaries():
    authorizer = StaticTokenAuthorizer(VIEWER_TOKEN, AUDITOR_TOKEN)
    viewer = authorizer.authenticate(VIEWER_TOKEN)
    assert viewer.role is AccessRole.VIEWER
    assert authorizer.authorize(VIEWER_TOKEN, AccessRole.VIEWER) == viewer
    assert authorizer.authorize(AUDITOR_TOKEN, AccessRole.AUDITOR).role is AccessRole.AUDITOR

    with pytest.raises(AuthenticationError):
        authorizer.authenticate("wrong")
    with pytest.raises(AuthorizationError):
        authorizer.authorize(VIEWER_TOKEN, AccessRole.AUDITOR)
    with pytest.raises(ValueError, match="required"):
        StaticTokenAuthorizer("", AUDITOR_TOKEN)
    with pytest.raises(ValueError, match="different"):
        StaticTokenAuthorizer(VIEWER_TOKEN, VIEWER_TOKEN)


def test_observer_settings_are_fail_closed(monkeypatch):
    local = ObserverSettings()
    assert local.environment == "local"
    assert not local.authentication_enabled

    configured = ObserverSettings(
        viewer_token=VIEWER_TOKEN,
        auditor_token=AUDITOR_TOKEN,
        audit_signing_key=SIGNING_KEY,
    )
    assert configured.authentication_enabled

    with pytest.raises(ValidationError, match="configured together"):
        ObserverSettings(viewer_token=VIEWER_TOKEN)
    with pytest.raises(ValidationError, match="different"):
        ObserverSettings(viewer_token=VIEWER_TOKEN, auditor_token=VIEWER_TOKEN)
    with pytest.raises(ValidationError, match="postgresql"):
        ObserverSettings(environment="production")
    with pytest.raises(ValidationError, match="32 characters"):
        ObserverSettings(
            environment="production",
            database_url="postgresql+asyncpg://localhost/redmind",
            viewer_token="short",  # noqa: S106
            auditor_token="also-short",  # noqa: S106
            audit_signing_key="short",
        )
    with pytest.raises(ValidationError, match="HTTP"):
        ObserverSettings(otlp_endpoint="https://user:secret@example.test?query=1")

    values = {
        "REDMIND_ENVIRONMENT": "production",
        "REDMIND_DATABASE_URL": "postgresql+asyncpg://localhost/redmind",
        "REDMIND_VIEWER_TOKEN": VIEWER_TOKEN,
        "REDMIND_AUDITOR_TOKEN": AUDITOR_TOKEN,
        "REDMIND_AUDIT_SIGNING_KEY": SIGNING_KEY,
        "REDMIND_OTEL_SERVICE_NAME": "redmind-test",
        "REDMIND_OTLP_ENDPOINT": "https://collector.example.test",
    }
    loaded = ObserverSettings.from_env(values)
    assert loaded.otel_service_name == "redmind-test"
    assert loaded.otlp_endpoint == "https://collector.example.test"

    for name, value in values.items():
        monkeypatch.setenv(name, value)
    assert ObserverSettings.from_env().environment == "production"


def test_audit_signer_detects_tampering_and_validates_key_length():
    signer = AuditSigner(SIGNING_KEY, clock=lambda: NOW)
    principal = Principal(subject="audit-user", role=AccessRole.AUDITOR)
    exported = signer.sign(demo_timeline(), principal)

    assert exported.key_id == signer.key_id
    assert exported.issued_to == "audit-user"
    assert signer.verify(exported)

    changed_payload = exported.payload.model_copy(
        update={
            "run": exported.payload.run.model_copy(update={"objective": "tampered"}),
        }
    )
    tampered = exported.model_copy(update={"payload": changed_payload})
    assert not signer.verify(tampered)
    assert SignedAuditExport.model_validate(exported.model_dump(mode="json")) == exported

    with pytest.raises(ValueError, match="32 characters"):
        AuditSigner("too-short")
    assert AuditSigner(SIGNING_KEY).sign(demo_timeline(), principal).issued_at.tzinfo is not None


def test_protected_api_enforces_viewer_and_auditor_roles():
    timeline = demo_timeline()
    signer = AuditSigner(SIGNING_KEY, clock=lambda: NOW)
    app = create_app(
        InMemoryTimelineRepository((timeline,)),
        authorizer=StaticTokenAuthorizer(VIEWER_TOKEN, AUDITOR_TOKEN),
        audit_signer=signer,
        environment="production",
    )

    with TestClient(app) as client:
        metadata = client.get("/api/v1/meta").json()
        assert metadata["authentication_required"]
        assert metadata["signed_exports"]
        assert metadata["environment"] == "production"

        assert client.get("/api/v1/runs").status_code == 401
        assert (
            client.get("/api/v1/runs", headers={"Authorization": "Basic value"}).status_code == 401
        )
        assert (
            client.get("/api/v1/runs", headers={"Authorization": "Bearer wrong"}).status_code == 401
        )

        viewer_headers = {"Authorization": f"Bearer {VIEWER_TOKEN}"}
        auditor_headers = {"Authorization": f"Bearer {AUDITOR_TOKEN}"}
        assert client.get("/api/v1/runs", headers=viewer_headers).status_code == 200
        assert (
            client.get(
                f"/api/v1/runs/{timeline.run.id}/audit-export",
                headers=viewer_headers,
            ).status_code
            == 403
        )
        response = client.get(
            f"/api/v1/runs/{timeline.run.id}/audit-export",
            headers=auditor_headers,
        )
        assert response.status_code == 200
        assert signer.verify(SignedAuditExport.model_validate(response.json()))
        assert (
            client.get(f"/api/v1/runs/{uuid4()}/audit-export", headers=auditor_headers).status_code
            == 404
        )


def test_sql_repository_round_trip_and_approval_audit():
    async def scenario():
        repository = SQLRepository.from_url("sqlite+aiosqlite:///:memory:")
        await repository.initialize()
        assert await repository.ready()
        assert await repository.list_runs() == ()
        assert await repository.get_run(uuid4()) is None
        assert await repository.get_approval_request(uuid4()) is None

        for timeline in reversed(demo_timelines()):
            await repository.save_timeline(timeline)
        summaries = await repository.list_runs()
        assert summaries == tuple(timeline.run for timeline in demo_timelines())

        timeline = demo_timeline()
        changed = timeline.model_copy(
            update={
                "run": timeline.run.model_copy(update={"state": "executing"}),
            }
        )
        await repository.save_timeline(changed)
        assert (await repository.get_run(timeline.run.id)).run.state == "executing"

        request = approval_request()
        await repository.save_approval_request(request)
        updated = request.model_copy(update={"status": ApprovalStatus.EXECUTING})
        await repository.save_approval_request(updated)
        assert await repository.get_approval_request(request.id) == updated

        event = approval_event()
        second = approval_event(event_id=uuid4(), request_id=uuid4()).model_copy(
            update={"occurred_at": NOW + timedelta(minutes=2)}
        )
        await repository.append_approval_event(event)
        await repository.append_approval_event(second)
        assert await repository.list_approval_events(request.id) == (event,)
        assert await repository.list_approval_events() == (event, second)
        with pytest.raises(IntegrityError):
            await repository.append_approval_event(event)
        await repository.close()

    run(scenario())


def test_sql_repository_readiness_handles_connection_failures():
    class BrokenContext:
        async def __aenter__(self):
            raise RuntimeError("database unavailable")

        async def __aexit__(self, *_args):
            return None

    class BrokenEngine:
        def connect(self):
            return BrokenContext()

    repository = SQLRepository(cast(AsyncEngine, BrokenEngine()))
    assert run(repository.ready()) is False


def complete_trace(*, failed: bool = False) -> RunTrace:
    run_id = UUID("694d7319-5ec4-4578-b8af-ed9e37b3dc4e")
    step_id = UUID("dfc4694a-3ef0-41db-9b60-12b7f60c6035")
    failure = (
        FailureDetails(
            kind=FailureKind.AGENT_ERROR,
            message="sanitized agent failure",
            retryable=True,
        )
        if failed
        else None
    )
    state = AgentState.FAILED if failed else AgentState.COMPLETED
    completed_at = NOW + timedelta(seconds=4)
    return RunTrace(
        run=Run(
            id=run_id,
            objective="Observe authorized evidence",
            state=state,
            max_steps=4,
            timeout_seconds=30,
            metadata={"risk_level": "high"},
            created_at=NOW,
            started_at=NOW + timedelta(seconds=1),
            completed_at=completed_at,
            failure=failure,
        ),
        steps=(
            Step(
                id=step_id,
                run_id=run_id,
                sequence=1,
                agent_name="Recon Analyst",
                state=state,
                created_at=NOW,
                started_at=NOW + timedelta(seconds=1),
                completed_at=NOW + timedelta(seconds=3),
                failure=failure,
            ),
        ),
        messages=(
            Message(
                id=uuid4(),
                run_id=run_id,
                step_id=step_id,
                role=MessageRole.AGENT,
                sender="Recon Analyst",
                content="Validated one evidence record.",
                metadata={"title": "Evidence 정규화"},
                created_at=NOW + timedelta(seconds=2),
            ),
        ),
        evidence=(
            Evidence(
                id=uuid4(),
                run_id=run_id,
                step_id=step_id,
                evidence_type="asset",
                source="adapter:test",
                summary="Target belongs to the authorized lab.",
                collected_at=NOW + timedelta(seconds=2),
            ),
        ),
        events=(
            TraceEvent(
                id=uuid4(),
                run_id=run_id,
                step_id=step_id,
                sequence=1,
                event_type=TraceEventType.STATE_TRANSITION,
                occurred_at=completed_at,
                state_from=AgentState.EXECUTING,
                state_to=state,
            ),
        ),
    )


def test_runtime_adapter_maps_trace_approvals_tools_usage_and_failures():
    tools = tuple(
        ToolCallRecord(
            tool_name=f"{category.value}_tool",
            category=category,
            outcome="completed",
        )
        for category in ToolCategory
    )
    usage = UsageView(
        input_tokens=20,
        output_tokens=10,
        estimated_cost_usd=0.01,
        budget_percent=25,
    )
    report = ReportView(recommendations=("Retain the signed audit export.",))

    timeline = RuntimeTimelineAdapter.from_trace(
        complete_trace(),
        approvals=(approval_request(),),
        tool_calls=tools,
        usage=usage,
        report=report,
    )
    assert timeline.run.duration_ms == 3_000
    assert timeline.run.progress_percent == 100
    assert timeline.run.risk_level == "high"
    assert timeline.steps[0].title == "Evidence 정규화"
    assert timeline.steps[0].detail == "Validated one evidence record."
    assert timeline.evidence[0].trust == "untrusted"
    assert tuple(tool.permission for tool in timeline.tool_calls) == (
        "read",
        "observe",
        "validate",
        "write",
    )
    assert timeline.approvals[0].reviewer == "security-reviewer"
    assert timeline.usage == usage
    assert timeline.report == report

    failed = RuntimeTimelineAdapter.from_trace(complete_trace(failed=True))
    assert failed.failure is not None
    assert failed.failure.retryable
    assert failed.steps[0].detail == "sanitized agent failure"


def test_runtime_adapter_fallbacks_are_deterministic():
    run_id = uuid4()
    step_id = uuid4()
    trace = RunTrace(
        run=Run(
            id=run_id,
            objective="Pending trace",
            state=AgentState.EXECUTING,
            max_steps=1,
            timeout_seconds=30,
            metadata={"risk_level": ["invalid"]},
            created_at=NOW,
        ),
        steps=(
            Step(
                id=step_id,
                run_id=run_id,
                sequence=1,
                agent_name="Planner",
                state=AgentState.COMPLETED,
                created_at=NOW,
                completed_at=NOW + timedelta(seconds=1),
            ),
        ),
        messages=(
            Message(
                id=uuid4(),
                run_id=run_id,
                step_id=step_id,
                role=MessageRole.AGENT,
                sender="Planner",
                content="Fallback detail",
                metadata={"title": 42},
                created_at=NOW,
            ),
        ),
        evidence=(),
        events=(),
    )
    timeline = RuntimeTimelineAdapter.from_trace(trace)
    assert timeline.run.started_at == NOW
    assert timeline.run.duration_ms == 1_000
    assert timeline.run.progress_percent == 99
    assert timeline.run.risk_level == "low"
    assert timeline.steps[0].title == "Planner 실행"
    assert timeline.report.unverified
    assert timeline.usage.input_tokens == 0

    assert (
        RuntimeTimelineAdapter._step_detail((), None)
        == "구조화된 실행 상태가 trace에 기록되었습니다."
    )
    assert RuntimeTimelineAdapter._duration_ms(NOW, NOW - timedelta(seconds=1)) == 0


def test_telemetry_middleware_and_runtime_shutdown():
    app = FastAPI()
    ObserverTelemetry().instrument(app)

    @app.get("/ok")
    async def ok():
        return {"status": "ok"}

    @app.get("/explode")
    async def explode():
        raise RuntimeError("expected")

    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/ok").status_code == 200
        assert client.get("/missing").status_code == 404
        assert client.get("/explode").status_code == 500

    calls = []

    class Provider:
        def __init__(self, name):
            self.name = name

        def shutdown(self):
            calls.append(self.name)

    runtime = TelemetryRuntime(
        observer=ObserverTelemetry(),
        tracer_provider=Provider("tracer"),
        meter_provider=Provider("meter"),
    )
    runtime.shutdown()
    assert calls == ["meter", "tracer"]
    TelemetryRuntime(observer=ObserverTelemetry()).shutdown()

    otlp = create_otlp_runtime("redmind-test", "http://127.0.0.1:4318/")
    assert otlp.tracer_provider is not None
    assert otlp.meter_provider is not None
    otlp.shutdown()


def test_production_factory_rejects_local_and_runs_validated_lifespan(monkeypatch):
    monkeypatch.setattr(
        ObserverSettings,
        "from_env",
        classmethod(lambda cls: ObserverSettings()),
    )
    with pytest.raises(RuntimeError, match="REDMIND_ENVIRONMENT"):
        create_app_from_env()

    missing = ObserverSettings.model_construct(
        environment="production",
        database_url="sqlite+aiosqlite:///:memory:",
        viewer_token=None,
        auditor_token=None,
        audit_signing_key=None,
        otel_service_name="test",
        otlp_endpoint=None,
    )
    monkeypatch.setattr(
        ObserverSettings,
        "from_env",
        classmethod(lambda cls: missing),
    )
    with pytest.raises(RuntimeError, match="credentials"):
        create_app_from_env()

    settings = ObserverSettings.model_construct(
        environment="production",
        database_url="sqlite+aiosqlite:///:memory:",
        viewer_token=SecretStr(VIEWER_TOKEN),
        auditor_token=SecretStr(AUDITOR_TOKEN),
        audit_signing_key=SecretStr(SIGNING_KEY),
        otel_service_name="test",
        otlp_endpoint=None,
    )
    monkeypatch.setattr(
        ObserverSettings,
        "from_env",
        classmethod(lambda cls: settings),
    )
    app = create_app_from_env()
    with TestClient(app) as client:
        assert client.get("/health/ready").status_code == 200
        assert (
            client.get(
                "/api/v1/runs",
                headers={"Authorization": f"Bearer {VIEWER_TOKEN}"},
            ).json()
            == []
        )
