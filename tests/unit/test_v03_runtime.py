import asyncio
from datetime import datetime
from uuid import uuid4

import pytest

from redmind.runtime import (
    AgentResult,
    AgentRuntime,
    BoundedExecutionQueue,
    DeterministicMockAgent,
    IdempotencyConflictError,
    ProjectScopeViolationError,
    QueueCapacityError,
    QueueClosedError,
    Run,
    RunRequest,
)
from redmind.runtime.models import AgentState
from redmind.runtime.store import InMemoryTraceStore


def run(coroutine):
    return asyncio.run(coroutine)


def test_idempotency_returns_same_run_and_project_scope_isolated():
    async def scenario():
        runtime = AgentRuntime()
        request = RunRequest(
            objective="idempotent observation",
            project_id="project-a",
            idempotency_key="request-2026-01",
        )
        first = await runtime.create_run(request)
        retry = await runtime.create_run(request)
        assert retry == first

        other = await runtime.create_run(request.model_copy(update={"project_id": "project-b"}))
        assert other.id != first.id
        with pytest.raises(ProjectScopeViolationError):
            await runtime.get_trace(first.id, project_id="project-b")
        with pytest.raises(ProjectScopeViolationError):
            await runtime.execute(
                first.id, DeterministicMockAgent([AgentResult()]), project_id="project-b"
            )

    run(scenario())


def test_store_rejects_duplicate_idempotency_identity():
    async def scenario():
        store = InMemoryTraceStore(uuid4)
        base = Run(
            id=uuid4(),
            objective="one",
            max_steps=1,
            timeout_seconds=10,
            created_at=datetime.now(),
            project_id="scope-a",
            idempotency_key="same-request",
        )
        duplicate = base.model_copy(update={"id": uuid4()})
        await store.create_run(base)
        with pytest.raises(IdempotencyConflictError):
            await store.create_run(duplicate)

    run(scenario())


def test_runtime_recovers_from_store_idempotency_race(monkeypatch):
    async def scenario():
        runtime = AgentRuntime()
        request = RunRequest(objective="race", idempotency_key="race-key-2026")
        existing = Run(
            id=uuid4(),
            objective=request.objective,
            max_steps=request.max_steps,
            timeout_seconds=request.timeout_seconds,
            created_at=datetime.now(),
            idempotency_key=request.idempotency_key,
        )

        async def claim(_run):
            raise IdempotencyConflictError(request.project_id, request.idempotency_key)

        calls = 0

        async def find(_project_id, _key):
            nonlocal calls
            calls += 1
            return None if calls == 1 else existing

        monkeypatch.setattr(runtime._store, "create_run", claim)
        monkeypatch.setattr(runtime._store, "get_run_by_idempotency", find)
        assert await runtime.create_run(request) == existing

    run(scenario())


def test_bounded_queue_limits_pending_work_and_executes_workers():
    async def scenario():
        runtime = AgentRuntime()
        queue = BoundedExecutionQueue(runtime, max_workers=1, max_pending=1)
        first = await runtime.create_run(RunRequest(objective="first"))
        second = await runtime.create_run(RunRequest(objective="second"))
        third = await runtime.create_run(RunRequest(objective="third"))
        handle_one = await queue.submit(
            first.id, DeterministicMockAgent([AgentResult()], delay_seconds=0.05)
        )
        await asyncio.sleep(0.01)
        handle_two = await queue.submit(second.id, DeterministicMockAgent([AgentResult()]))
        assert queue.active_workers == 1
        assert queue.pending_count == 1
        with pytest.raises(QueueCapacityError, match="capacity 1"):
            await queue.submit(third.id, DeterministicMockAgent([AgentResult()]))
        assert (await handle_one.result()).run.state is AgentState.COMPLETED
        assert (await handle_two.result()).run.state is AgentState.COMPLETED
        await queue.join()
        await queue.close()
        await queue.close()
        with pytest.raises(QueueClosedError):
            await queue.submit(third.id, DeterministicMockAgent([AgentResult()]))

    run(scenario())


def test_queue_cancel_propagates_to_running_agent_and_close_releases_pending():
    async def scenario():
        runtime = AgentRuntime()
        queue = BoundedExecutionQueue(runtime, max_workers=1, max_pending=1)
        running = await runtime.create_run(RunRequest(objective="cancel me"))
        pending = await runtime.create_run(RunRequest(objective="pending"))
        running_handle = await queue.submit(
            running.id,
            DeterministicMockAgent([AgentResult()], delay_seconds=1),
        )
        await asyncio.sleep(0.01)
        pending_handle = await queue.submit(pending.id, DeterministicMockAgent([AgentResult()]))
        assert await running_handle.cancel("operator stop")
        await queue.close()
        assert (await running_handle.result()).run.failure is not None
        with pytest.raises(QueueClosedError):
            await pending_handle.result()

        finished = await runtime.create_run(RunRequest(objective="already done"))
        await runtime.execute(finished.id, DeterministicMockAgent([AgentResult()]))
        error_queue = BoundedExecutionQueue(runtime)
        error_handle = await error_queue.submit(
            finished.id, DeterministicMockAgent([AgentResult()])
        )
        with pytest.raises(Exception, match="cannot be executed"):
            await error_handle.result()
        await error_queue.close()

        interrupted = await runtime.create_run(RunRequest(objective="worker interruption"))
        interruption_queue = BoundedExecutionQueue(runtime, max_workers=1)
        interruption_handle = await interruption_queue.submit(
            interrupted.id,
            DeterministicMockAgent([AgentResult()], delay_seconds=1),
        )
        await asyncio.sleep(0.01)
        interruption_queue._workers[0].cancel()
        with pytest.raises(QueueClosedError):
            await interruption_handle.result()
        await interruption_queue.close()

    run(scenario())


def test_queue_configuration_validation():
    runtime = AgentRuntime()
    with pytest.raises(ValueError, match="max_workers"):
        BoundedExecutionQueue(runtime, max_workers=0)
    with pytest.raises(ValueError, match="max_pending"):
        BoundedExecutionQueue(runtime, max_pending=-1)
