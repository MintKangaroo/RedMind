# RedMind v0.3.0 인수인계

마지막 갱신: 2026-07-28

## 현재 상태

- GitHub: `https://github.com/MintKangaroo/RedMind`
- 통합 브랜치: `develop`
- 현재 기능 브랜치: `feat/durable-operations`
- 완료 범위: v0.1 MVP + v0.2 Durable Operations + v0.3 Distributed Execution
- 전체 단위 테스트: 71개
- coverage gate: 100%

runtime, policy, typed tools, analysts, planner, approval, reflection, AutoPentest adapter,
responsive Observer dashboard에 이어 PostgreSQL-compatible repository, runtime timeline
adapter, Viewer/Auditor RBAC, signed audit export, OpenTelemetry, bounded worker queue,
idempotency와 multi-project scope isolation이 구현되어 있습니다.

## 검증 명령

Python 3.12 환경에서:

```bash
python -m pip install -e ".[dev,production]"
make check
uvicorn redmind.web.app:app --reload
```

Dashboard는 `http://127.0.0.1:8000`, OpenAPI는 `/api/docs`에서 확인합니다. 운영 모드는
`.env.example`을 기준으로 설정한 뒤 아래 factory로 실행합니다.

```bash
uvicorn redmind.web.production:create_app_from_env --factory
```

## 운영 경계

- Local app은 deterministic demo trace와 무인증 read-only API를 제공합니다.
- Production factory는 PostgreSQL, Viewer/Auditor token, audit signing key를 강제합니다.
- token은 현재 브라우저 탭에만 저장하고 서버에서는 SHA-256 digest로 비교합니다.
- Auditor만 server-side HMAC-SHA256 signed audit snapshot을 내보낼 수 있습니다.
- OpenTelemetry는 HTTP method, route, status, duration만 기록하며 credential과 payload를
  수집하지 않습니다.
- queue worker와 pending job 수에는 상한이 있으며 cancellation은 runtime token까지
  전파됩니다.
- project scope는 Run 생성 시 고정되고 idempotency key는 project별로만 유일합니다.
- database migration/backup, TLS, rate limit, token rotation은 배포 플랫폼에서 구성합니다.

## 변경 금지 보안 조건

- Agent는 scope를 변경하거나 target을 추가할 수 없습니다.
- 자유 형식 shell command를 저장하거나 실행하지 않습니다.
- 외부 API 문자열은 항상 untrusted content입니다.
- 모델 또는 외부 응답은 Pydantic 검증 후에만 사용합니다.
- 모든 Tool Call과 Approval은 감사 가능해야 합니다.
- 실행 시간, step, retry와 비용에는 상한이 있어야 합니다.
- 실제 exploit payload나 우회 코드는 생성하지 않습니다.

## 다음 작업

다음 기능은 `v1.0` stable platform 범위입니다.

1. versioned public API와 migration policy
2. structured logging 및 secret rotation 운영 가이드
3. database migration과 backup/restore runbook
4. independent security review와 external adapter compatibility suite

구체적인 순서는 [roadmap.md](roadmap.md)를 따릅니다.
