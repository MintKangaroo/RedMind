# Architecture

## 개요

RedMind는 허가된 cyber range에서 Evidence를 분석하고 다음 검증 단계를 계획하는
정책 통제형 multi-agent runtime입니다. 핵심 domain은 framework와 분리되어 있으며,
FastAPI와 외부 HTTP는 각각 read-only observer 및 integration boundary에만 존재합니다.

## 구성 요소

| Component | Responsibility |
|---|---|
| `runtime/models.py` | Run, Step, Message, Evidence 및 trace domain model |
| `runtime/engine.py` | step/time budget, cancellation, output validation |
| `runtime/policy.py` | target scope, risk, tool allowlist 및 budget decision |
| `runtime/tools.py` | typed permission, timeout과 audit hook을 가진 Tool Registry |
| `runtime/analysts.py` | Evidence gap 기반 Recon/Enumeration proposal |
| `runtime/planner.py` | coverage와 confidence 기반 attack path candidate |
| `runtime/approval.py` | immutable proposal snapshot과 human approval audit |
| `runtime/reflection.py` | failure fingerprint와 bounded retry/replan |
| `integrations/autopentest.py` | 고정 HTTP operation과 untrusted response validation |
| `web/` | read-only timeline repository, FastAPI와 static dashboard |

## Trust boundary

```text
Operator / Config
       │ validated scope + budget
       ▼
Agent Runtime ──► Analysts ──► Planner
       │                          │
       │ trace                    ▼
       │                    Policy Engine
       │                     │ deny │ approval
       │                     ▼      ▼
       │                 Audit    Human Review
       │                            │ revalidate
       │                            ▼
       └────────────────────► Typed Tool / Adapter
                                    │ untrusted response
                                    ▼
                              Schema Validation
                                    │
                                    ▼
                                Evidence
```

Agent와 외부 API는 신뢰 경계 밖에 있습니다. proposal과 외부 응답은 Pydantic model로
검증되며, 자유 형식 command, payload, exploit, script argument는 차단됩니다.

## Runtime invariants

- scope와 target set은 Run 생성 후 Agent가 변경할 수 없습니다.
- 모든 Run/Step 전이는 명시적 상태 머신 규칙을 따릅니다.
- 실행 시간, step 수, target 수, retry 수와 비용에는 상한이 있습니다.
- high/critical 또는 state-changing proposal은 Human Approval이 필요합니다.
- 승인은 proposal snapshot에 묶이며 실행 직전 현재 policy로 재검증됩니다.
- Tool Call, Approval과 상태 전이는 append-only audit event로 추적합니다.
- 외부 문자열은 검증 이후에도 untrusted provenance를 유지합니다.

## Observer

Observer는 `TimelineRepository` protocol에만 의존합니다. 기본 application은 세 가지
deterministic demo trace를 제공하며, production 환경에서는 동일 protocol을 구현하는
durable adapter를 주입할 수 있습니다.

HTTP API는 `GET` endpoint만 노출합니다. 대시보드의 검색과 감사 JSON 내보내기는
브라우저에 이미 전달된 timeline을 대상으로 수행하므로 서버 상태를 변경하지 않습니다.

## Deployment boundary

현재 `v0.1.0`은 단일 프로세스 local/cyber-range MVP입니다. production 배포에는
별도의 authentication, authorization, durable repository, TLS termination과 signed
audit export가 필요합니다. 이는 [roadmap](roadmap.md)의 v0.2 범위입니다.
