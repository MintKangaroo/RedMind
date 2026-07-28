# RedMind 로드맵

| 단계 | 기능 | 상태 |
|---|---|---|
| 1 | 기본 Agent Runtime | 완료 |
| 2 | Policy Engine | 완료 |
| 3 | Typed Tool Registry | 완료 |
| 4 | Recon 및 Enumeration Analyst | 완료 |
| 5 | Evidence-driven Attack Path Planner | 완료 |
| 6 | Human Approval workflow | 다음 작업 |
| 7 | Bounded reflection 및 retry | 예정 |
| 8 | AutoPentest AI Adapter | 예정 |
| 9 | 실행 관찰 UI | 예정 |

## 릴리스 흐름

각 단계는 독립적인 `feat/<기능명>` 브랜치에서 구현하고 테스트한 뒤 `develop`에
병합합니다. `main`에는 실행 가능한 안정 버전만 반영합니다.

## 다음 작업

6단계에서는 Action Proposal의 승인 요청, 승인자와 사유, 만료, 거부, 재승인,
실행 직전 정책 재검증 및 append-only 감사 로그를 구현합니다.

구체적인 세션 재개 방법과 구현 체크리스트는 [HANDOFF.md](HANDOFF.md)를
참고하세요.
