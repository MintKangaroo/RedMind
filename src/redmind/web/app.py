"""FastAPI application exposing a read-only execution timeline."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from redmind.web.timeline import (
    InMemoryTimelineRepository,
    RunSummary,
    RunTimeline,
    TimelineRepository,
    demo_timelines,
)

STATIC_DIR = Path(__file__).with_name("static")


def create_app(repository: TimelineRepository | None = None) -> FastAPI:
    app = FastAPI(
        title="RedMind Execution Observer",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url=None,
    )
    repo = repository or InMemoryTimelineRepository(demo_timelines())
    app.state.timeline_repository = repo

    @app.get("/health/live", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/runs", response_model=tuple[RunSummary, ...], tags=["timeline"])
    async def list_runs() -> tuple[RunSummary, ...]:
        return await repo.list_runs()

    @app.get("/api/v1/runs/{run_id}", response_model=RunTimeline, tags=["timeline"])
    async def get_run(run_id: UUID) -> RunTimeline:
        timeline = await repo.get_run(run_id)
        if timeline is None:
            raise HTTPException(status_code=404, detail="run not found")
        return timeline

    app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()
