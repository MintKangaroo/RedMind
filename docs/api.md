# Observer API

RedMind Observer API는 실행 trace 조회 전용 FastAPI application입니다. 기본 URL은
`http://127.0.0.1:8000`이며 Swagger UI는 `/api/docs`에서 확인할 수 있습니다.

## 실행

```bash
uvicorn redmind.web.app:app --reload
```

## Endpoint

### `GET /health/live`

프로세스 liveness를 반환합니다.

```json
{"status": "ok"}
```

### `GET /api/v1/runs`

`started_at` 내림차순으로 `RunSummary` 목록을 반환합니다.

```json
[
  {
    "id": "5bdece5b-53fd-4a81-b326-cb0894963463",
    "objective": "승인된 lab-web-01의 서비스 Evidence gap 검증",
    "state": "completed",
    "started_at": "2026-07-28T09:14:22Z",
    "duration_ms": 18420,
    "progress_percent": 100,
    "risk_level": "medium"
  }
]
```

### `GET /api/v1/runs/{run_id}`

Run summary와 step, tool call, evidence, approval, usage, failure 및 report를 포함한
`RunTimeline`을 반환합니다. 존재하지 않는 UUID는 `404`와 `run not found` detail을
반환합니다.

## View model

모든 view model은 `extra="forbid"`와 `frozen=True`를 사용합니다.

- `RunSummary`
- `TimelineStep`
- `ToolCallView`
- `EvidenceView`
- `ApprovalView`
- `UsageView`
- `FailureView`
- `ReportView`
- `RunTimeline`

## Repository 주입

Application은 `TimelineRepository` protocol을 통해 storage와 분리되어 있습니다.

```python
from redmind.web import InMemoryTimelineRepository, create_app
from redmind.web.timeline import demo_timeline

repository = InMemoryTimelineRepository((demo_timeline(),))
app = create_app(repository)
```

Production adapter는 아래 두 async method를 구현해야 합니다.

```python
class TimelineRepository(Protocol):
    async def list_runs(self) -> tuple[RunSummary, ...]: ...
    async def get_run(self, run_id: UUID) -> RunTimeline | None: ...
```

## 보안 특성

- 상태 변경 HTTP endpoint 없음
- response model을 통한 output validation
- UUID path validation
- 외부 Evidence trust label 보존
- Swagger 이외의 vendor-specific SDK 의존성 없음

인증과 RBAC는 현재 local MVP 범위가 아니므로 dashboard server를 공인 네트워크에 직접
노출하지 마세요.
