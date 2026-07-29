"""Bounded local execution queue with cooperative cancellation propagation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Generic, TypeVar
from uuid import UUID

from redmind.runtime.agents import Agent
from redmind.runtime.engine import AgentRuntime
from redmind.runtime.exceptions import QueueCapacityError, QueueClosedError
from redmind.runtime.models import RunTrace

ResultT = TypeVar("ResultT")


@dataclass(frozen=True)
class ExecutionHandle(Generic[ResultT]):  # noqa: UP046 - Python 3.10 tooling compatibility
    """A stable handle for awaiting or cancelling one queued execution."""

    run_id: UUID
    project_id: str
    _future: asyncio.Future[ResultT]
    _runtime: AgentRuntime

    async def result(self) -> ResultT:
        return await self._future

    async def cancel(self, reason: str = "queue cancellation requested") -> bool:
        return await self._runtime.cancel(self.run_id, reason, project_id=self.project_id)


@dataclass(frozen=True)
class _ExecutionJob:
    run_id: UUID
    agent: Agent
    project_id: str
    future: asyncio.Future[RunTrace]


class BoundedExecutionQueue:
    """Run at most ``max_workers`` agents and reject excess pending work."""

    def __init__(
        self,
        runtime: AgentRuntime,
        *,
        max_workers: int = 2,
        max_pending: int = 16,
    ) -> None:
        if max_workers <= 0:
            raise ValueError("max_workers must be positive")
        if max_pending < 0:
            raise ValueError("max_pending must not be negative")
        self.runtime = runtime
        self.max_workers = max_workers
        self.max_pending = max_pending
        self._queue: asyncio.Queue[_ExecutionJob] = asyncio.Queue(maxsize=max_pending)
        self._workers: list[asyncio.Task[None]] = []
        self._closed = False

    @property
    def pending_count(self) -> int:
        return self._queue.qsize()

    @property
    def active_workers(self) -> int:
        return sum(not worker.done() for worker in self._workers)

    async def submit(
        self,
        run_id: UUID,
        agent: Agent,
        *,
        project_id: str = "default",
    ) -> ExecutionHandle[RunTrace]:
        if self._closed:
            raise QueueClosedError()
        self._ensure_workers()
        future: asyncio.Future[RunTrace] = asyncio.get_running_loop().create_future()
        job = _ExecutionJob(run_id, agent, project_id, future)
        try:
            self._queue.put_nowait(job)
        except asyncio.QueueFull as exc:
            raise QueueCapacityError(self.max_pending) from exc
        return ExecutionHandle(run_id, project_id, future, self.runtime)

    async def join(self) -> None:
        await self._queue.join()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        while not self._queue.empty():
            job = self._queue.get_nowait()
            if not job.future.done():
                job.future.set_exception(QueueClosedError())
            self._queue.task_done()
        await self._queue.join()
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    def _ensure_workers(self) -> None:
        if self._workers:
            return
        self._workers = [
            asyncio.create_task(self._worker(), name=f"redmind-execution-worker-{index + 1}")
            for index in range(self.max_workers)
        ]

    async def _worker(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                if not job.future.done():
                    result = await self.runtime.execute(
                        job.run_id, job.agent, project_id=job.project_id
                    )
                    job.future.set_result(result)
            except asyncio.CancelledError:
                if not job.future.done():
                    job.future.set_exception(QueueClosedError())
                raise
            except Exception as exc:  # noqa: BLE001 - preserve runtime boundary errors
                if not job.future.done():
                    job.future.set_exception(exc)
            finally:
                self._queue.task_done()
