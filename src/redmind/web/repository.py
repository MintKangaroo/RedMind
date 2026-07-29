"""Durable SQL repository for observer timelines and approval audit records."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import JSON, Column, DateTime, MetaData, String, Table, delete, insert, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from redmind.runtime.approval import ApprovalAuditEvent, ApprovalRequest
from redmind.web.timeline import RunSummary, RunTimeline

UTC = timezone.utc  # noqa: UP017

metadata = MetaData()

timelines = Table(
    "observer_timelines",
    metadata,
    Column("run_id", String(36), primary_key=True),
    Column("objective", String(2_000), nullable=False),
    Column("state", String(40), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False, index=True),
    Column("document", JSON, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

approval_requests = Table(
    "approval_requests",
    metadata,
    Column("request_id", String(36), primary_key=True),
    Column("status", String(40), nullable=False, index=True),
    Column("expires_at", DateTime(timezone=True), nullable=False, index=True),
    Column("document", JSON, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

approval_audit_events = Table(
    "approval_audit_events",
    metadata,
    Column("event_id", String(36), primary_key=True),
    Column("request_id", String(36), nullable=False, index=True),
    Column("occurred_at", DateTime(timezone=True), nullable=False, index=True),
    Column("document", JSON, nullable=False),
)


class SQLRepository:
    """Async SQLAlchemy repository compatible with SQLite and PostgreSQL."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)

    @classmethod
    def from_url(cls, database_url: str, *, echo: bool = False) -> SQLRepository:
        return cls(create_async_engine(database_url, echo=echo))

    async def initialize(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(metadata.create_all)

    async def close(self) -> None:
        await self.engine.dispose()

    async def ready(self) -> bool:
        try:
            async with self.engine.connect() as connection:
                await connection.execute(select(1))
        except Exception:  # pragma: no cover - dialect-specific connection failures
            return False
        return True

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[AsyncSession]:
        async with self._sessions.begin() as session:
            yield session

    async def save_timeline(self, timeline: RunTimeline) -> None:
        now = datetime.now(UTC)
        values = {
            "run_id": str(timeline.run.id),
            "objective": timeline.run.objective,
            "state": timeline.run.state,
            "started_at": timeline.run.started_at,
            "document": timeline.model_dump(mode="json"),
            "updated_at": now,
        }
        async with self._session() as session:
            await session.execute(delete(timelines).where(timelines.c.run_id == values["run_id"]))
            await session.execute(insert(timelines).values(**values))

    async def list_runs(self, project_id: str = "default") -> tuple[RunSummary, ...]:
        statement = select(timelines.c.document).order_by(timelines.c.started_at.desc())
        async with self._sessions() as session:
            rows = (await session.execute(statement)).scalars()
            return tuple(
                timeline.run
                for document in rows
                if (timeline := RunTimeline.model_validate(document)).run.project_id == project_id
            )

    async def get_run(self, run_id: UUID, project_id: str = "default") -> RunTimeline | None:
        statement = select(timelines.c.document).where(timelines.c.run_id == str(run_id))
        async with self._sessions() as session:
            document = (await session.execute(statement)).scalar_one_or_none()
            if document is None:
                return None
            timeline = RunTimeline.model_validate(document)
            return timeline if timeline.run.project_id == project_id else None

    async def save_approval_request(self, request: ApprovalRequest) -> None:
        values = {
            "request_id": str(request.id),
            "status": request.status.value,
            "expires_at": request.expires_at,
            "document": request.model_dump(mode="json"),
            "updated_at": datetime.now(UTC),
        }
        async with self._session() as session:
            await session.execute(
                delete(approval_requests).where(
                    approval_requests.c.request_id == values["request_id"]
                )
            )
            await session.execute(insert(approval_requests).values(**values))

    async def get_approval_request(self, request_id: UUID) -> ApprovalRequest | None:
        statement = select(approval_requests.c.document).where(
            approval_requests.c.request_id == str(request_id)
        )
        async with self._sessions() as session:
            document = (await session.execute(statement)).scalar_one_or_none()
            return ApprovalRequest.model_validate(document) if document is not None else None

    async def append_approval_event(self, event: ApprovalAuditEvent) -> None:
        async with self._session() as session:
            await session.execute(
                insert(approval_audit_events).values(
                    event_id=str(event.id),
                    request_id=str(event.request_id),
                    occurred_at=event.occurred_at,
                    document=event.model_dump(mode="json"),
                )
            )

    async def list_approval_events(
        self, request_id: UUID | None = None
    ) -> tuple[ApprovalAuditEvent, ...]:
        statement = select(approval_audit_events.c.document)
        if request_id is not None:
            statement = statement.where(approval_audit_events.c.request_id == str(request_id))
        statement = statement.order_by(
            approval_audit_events.c.occurred_at,
            approval_audit_events.c.event_id,
        )
        async with self._sessions() as session:
            rows = (await session.execute(statement)).scalars()
            return tuple(ApprovalAuditEvent.model_validate(document) for document in rows)
