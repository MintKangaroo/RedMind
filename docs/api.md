# Observer API

RedMind Observer API는 인증된 실행 trace 조회 전용 FastAPI application입니다. 기본 URL은
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

### `GET /health/ready`

저장소 연결 준비 여부를 `ready`로 반환하며, 사용할 수 없으면 HTTP `503`입니다.

### `GET /api/v1/meta`

인증 없이 UI가 배포 모드를 확인할 수 있는 비민감 metadata만 반환합니다.

```json
{
  "version": "0.2.0",
  "environment": "production",
  "authentication_required": true,
  "signed_exports": true
}
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

### `GET /api/v1/runs/{run_id}/audit-export`

Auditor token이 필요합니다. timeline snapshot, 발급 시각·대상, key ID와 canonical
HMAC-SHA256 signature를 포함한 `redmind.signed-audit.v1` envelope을 반환합니다.

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

읽기 경계는 아래 두 async method를 구현합니다.

```python
class TimelineRepository(Protocol):
    async def list_runs(self) -> tuple[RunSummary, ...]: ...
    async def get_run(self, run_id: UUID) -> RunTimeline | None: ...
```

내장 `SQLRepository`는 이 protocol과 timeline/approval write method를 구현하며
`sqlite+aiosqlite` 테스트와 `postgresql+asyncpg` 운영 연결을 지원합니다.

## 보안 특성

- 상태 변경 HTTP endpoint 없음
- digest-backed bearer token과 constant-time compare
- Viewer 조회 / Auditor 서명 내보내기 역할 분리
- HMAC-SHA256 canonical signed export
- response model을 통한 output validation
- UUID path validation
- 외부 Evidence trust label 보존
- Swagger 이외의 vendor-specific SDK 의존성 없음

Local app은 deterministic demo를 위해 인증 없이 동작합니다. Production factory는
인증·서명·PostgreSQL 설정을 강제하지만, 인터넷 노출 시에는 반드시 별도 TLS termination,
rate limiting, secret rotation과 network access control을 함께 구성해야 합니다.
