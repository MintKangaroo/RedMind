"""FastAPI application exposing an authenticated, read-only execution timeline."""

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, cast
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
from starlette.types import Lifespan

from redmind.web.auth import (
    AccessRole,
    AuthenticationError,
    AuthorizationError,
    Principal,
    StaticTokenAuthorizer,
)
from redmind.web.signing import AuditSigner, SignedAuditExport
from redmind.web.telemetry import ObserverTelemetry
from redmind.web.timeline import (
    InMemoryTimelineRepository,
    RunSummary,
    RunTimeline,
    TimelineRepository,
    demo_timelines,
)

STATIC_DIR = Path(__file__).with_name("static")
ReadinessCheck = Callable[[], Awaitable[bool]]


class ObserverMeta(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str
    environment: str
    authentication_required: bool
    signed_exports: bool


def create_app(
    repository: TimelineRepository | None = None,
    *,
    authorizer: StaticTokenAuthorizer | None = None,
    audit_signer: AuditSigner | None = None,
    telemetry: ObserverTelemetry | None = None,
    readiness: ReadinessCheck | None = None,
    lifespan: Lifespan[FastAPI] | None = None,
    environment: str = "local",
) -> FastAPI:
    app = FastAPI(
        title="RedMind Execution Observer",
        version="0.2.0",
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    repo = repository or InMemoryTimelineRepository(demo_timelines())
    app.state.timeline_repository = repo
    security = HTTPBearer(auto_error=False)

    async def require_role(
        credentials: HTTPAuthorizationCredentials | None,
        role: AccessRole,
    ) -> Principal:
        if authorizer is None:
            return Principal(subject="local-observer", role=AccessRole.AUDITOR)
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise HTTPException(
                status_code=401,
                detail="bearer credential is required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            return authorizer.authorize(credentials.credentials, role)
        except AuthenticationError as exc:
            raise HTTPException(
                status_code=401,
                detail=str(exc),
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    async def viewer(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    ) -> Principal:
        return await require_role(credentials, AccessRole.VIEWER)

    async def auditor(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    ) -> Principal:
        return await require_role(credentials, AccessRole.AUDITOR)

    @app.get("/health/live", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    async def ready(response: Response) -> dict[str, str]:
        is_ready = True if readiness is None else await readiness()
        if not is_ready:
            response.status_code = 503
        return {"status": "ready" if is_ready else "unavailable"}

    @app.get("/api/v1/meta", response_model=ObserverMeta, tags=["observer"])
    async def metadata() -> ObserverMeta:
        return ObserverMeta(
            version="0.2.0",
            environment=environment,
            authentication_required=authorizer is not None,
            signed_exports=audit_signer is not None,
        )

    @app.get(
        "/api/v1/runs",
        response_model=tuple[RunSummary, ...],
        tags=["timeline"],
        dependencies=[Depends(viewer)],
    )
    async def list_runs() -> tuple[RunSummary, ...]:
        return await repo.list_runs()

    @app.get(
        "/api/v1/runs/{run_id}",
        response_model=RunTimeline,
        tags=["timeline"],
        dependencies=[Depends(viewer)],
    )
    async def get_run(run_id: UUID) -> RunTimeline:
        timeline = await repo.get_run(run_id)
        if timeline is None:
            raise HTTPException(status_code=404, detail="run not found")
        return timeline

    @app.get(
        "/api/v1/runs/{run_id}/audit-export",
        response_model=SignedAuditExport,
        tags=["audit"],
    )
    async def export_audit(
        run_id: UUID,
        principal: Annotated[object, Depends(auditor)],
    ) -> SignedAuditExport:
        if audit_signer is None:
            raise HTTPException(status_code=503, detail="signed audit export is not configured")
        timeline = await repo.get_run(run_id)
        if timeline is None:
            raise HTTPException(status_code=404, detail="run not found")
        return audit_signer.sign(timeline, cast(Principal, principal))

    app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    (telemetry or ObserverTelemetry()).instrument(app)
    return app


app = create_app()
