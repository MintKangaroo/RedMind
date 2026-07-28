# RedMind v0.1.0 인수인계

마지막 갱신: 2026-07-28

## 현재 상태

- GitHub: `https://github.com/MintKangaroo/RedMind`
- 통합 브랜치: `develop`
- 현재 기능 브랜치: `feat/execution-timeline`
- 완료된 MVP 단계: 1~9
- 전체 단위 테스트: 54개
- coverage gate: 100%

9단계까지의 runtime, policy, typed tools, analysts, planner, approval, reflection,
AutoPentest adapter 및 read-only Observer dashboard가 구현되어 있습니다.

## 검증 명령

Python 3.12 환경에서:

```bash
python -m pip install -e ".[dev]"
make check
uvicorn redmind.web.app:app --reload
```

Dashboard는 `http://127.0.0.1:8000`, OpenAPI는 `/api/docs`에서 확인합니다.

## 변경 금지 보안 조건

- Agent는 scope를 변경하거나 target을 추가할 수 없습니다.
- 자유 형식 shell command를 저장하거나 실행하지 않습니다.
- 외부 API 문자열은 항상 untrusted content입니다.
- 모델 또는 외부 응답은 Pydantic 검증 후에만 사용합니다.
- 모든 Tool Call과 Approval은 감사 가능해야 합니다.
- 실행 시간, step, retry와 비용에는 상한이 있어야 합니다.
- 실제 exploit payload나 우회 코드는 생성하지 않습니다.

## 다음 작업

다음 기능은 `v0.2` durable operations 범위입니다.

1. runtime trace와 Observer view model 사이 production adapter
2. PostgreSQL 기반 trace/approval repository
3. dashboard authentication과 RBAC
4. server-side signed audit export
5. OpenTelemetry trace/metric/log

구체적인 순서는 [roadmap.md](roadmap.md)를 따릅니다.
