# RedMind 로드맵

## v0.1.0 MVP

| 단계 | 기능 | 상태 |
|---|---|---|
| 1 | 기본 Agent Runtime | 완료 |
| 2 | Policy Engine | 완료 |
| 3 | Typed Tool Registry | 완료 |
| 4 | Recon 및 Enumeration Analyst | 완료 |
| 5 | Evidence-driven Attack Path Planner | 완료 |
| 6 | Human Approval workflow | 완료 |
| 7 | Bounded reflection 및 retry | 완료 |
| 8 | AutoPentest AI Adapter | 완료 |
| 9 | 실행 관찰 UI | 완료 |

MVP는 deterministic local execution, deny-by-default policy, human approval,
validated integration boundary와 read-only execution dashboard를 제공합니다.

## v0.2: Durable Operations

| 기능 | 상태 |
|---|---|
| PostgreSQL-compatible trace 및 approval repository | 완료 |
| runtime trace → Observer view model adapter | 완료 |
| authentication과 Viewer/Auditor dashboard RBAC | 완료 |
| server-side HMAC-SHA256 signed audit export | 완료 |
| OpenTelemetry HTTP trace, metric 및 OTLP export | 완료 |

> Structured application logging과 secret rotation runbook은 배포 플랫폼별 구성이 필요해
> v0.3 운영 가이드에서 다룹니다.

## v0.3: Distributed Execution

| 기능 | 상태 |
|---|---|
| bounded local worker queue와 cooperative cancellation | 완료 |
| idempotency key와 재전송 안전성 | 완료 |
| multi-project scope isolation | 완료 |

Redis 없는 local mode를 유지하면서 queue capacity, worker cancellation, project scope를
runtime 경계에서 검증합니다.

## 다음 마일스톤

### v1.0: Stable Research Platform

- versioned public API와 migration policy
- external adapter compatibility test suite
- threat model 재검토와 independent security review
- 운영 배포 가이드 및 복구 절차

## 릴리스 원칙

각 기능은 독립적인 `feat/<기능명>` 브랜치에서 구현하고 테스트한 뒤 `develop`에
통합합니다. `main`에는 전체 품질 검사를 통과한 실행 가능한 릴리스만 반영합니다.

보안 경계는 기능 추가보다 우선합니다. 공인 대상 탐색, 자유 형식 shell, 무제한 retry,
승인 없는 state-changing 작업은 이후 마일스톤에서도 기본적으로 허용하지 않습니다.
