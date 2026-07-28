# Architecture

## 현재 상태

`src/redmind/runtime`에 bounded Agent runtime, Policy Engine, typed Tool Registry,
Recon/Enumeration Analyst 및 evidence-driven Attack Path Planner가 구현되어 있습니다.
아직 API, 데이터베이스 또는 외부 네트워크 경계는 없습니다.

## 예정된 경계

Future work may introduce `apps/api`, `apps/worker`, and packages for core, domain,
and integrations. Domain policy must not depend on FastAPI, SQLAlchemy, Celery, or vendor
SDKs. Infrastructure adapters will depend inward on domain interfaces.

## 품질 및 보안 속성

Security defaults are deny-by-default. Inputs are validated at trust boundaries,
errors use a stable machine-readable envelope, logs are structured and redacted, and
external processes receive argument arrays rather than interpolated shell commands.
