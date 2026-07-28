# RedMind

RedMind는 허가된 보안 실습 환경에서 수집한 데이터를 분석하고 다음 검증 단계를
계획하는 정책 통제형 Multi-Agent Security Research Platform입니다. 실제 공격
도구를 무제한으로 자동 실행하지 않으며, 위험한 작업은 Human Approval을 거칩니다.

## 현재 상태

현재 `develop` 브랜치에는 1~5단계가 구현되어 있습니다.

- `Run`, `Step`, `Message`, `Evidence`, `TraceEvent` Pydantic 모델
- 명시적인 Agent 상태 머신과 잘못된 상태 전이 차단
- 네트워크 없이 재현 가능한 `DeterministicMockAgent`
- In-memory trace store와 append-only 실행 이벤트
- 실행 횟수·시간 제한, cooperative cancellation, timeout
- Agent 출력 스키마 검증과 실패 원인 분류
- 승인 대상·도구·예산·위험도를 검증하는 Policy Engine
- Pydantic 입력과 감사 hook을 갖춘 Tool Registry
- Evidence gap 기반 Recon 및 Enumeration Analyst
- Evidence coverage와 confidence를 계산하는 Attack Path Planner

다음 단계는 Human Approval workflow입니다. 전체 진행 상황은
[docs/roadmap.md](docs/roadmap.md), 다음 개발 세션 인수인계는
[docs/HANDOFF.md](docs/HANDOFF.md)를 참고하세요.

## 설치

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## 테스트 및 품질 검사

```bash
pytest
make check
```

## 안전 경계

RedMind는 소유자 또는 명시적으로 허가받은 시스템, 로컬/Docker 실습 환경, CTF 및
교육용 cyber range에서만 사용해야 합니다.

다음 행위는 범위에 포함되지 않습니다.

- 공인 인터넷 탐색
- 자격 증명 탈취 및 지속성 확보
- 방어 통제 우회
- 악성코드 전달
- 파괴적 행위 또는 데이터 유출

자세한 내용은 [SECURITY.md](SECURITY.md)와
[docs/threat-model.md](docs/threat-model.md)를 참고하세요.

## 구조

```text
src/redmind/runtime/
├── models.py         # 상태 및 trace 도메인 모델
├── state_machine.py  # lifecycle 전이 규칙
├── agents.py         # Agent protocol 및 결정적 mock Agent
├── analysts.py       # Recon 및 Enumeration Analyst
├── policy.py         # scope, risk, budget 정책
├── tools.py          # typed 및 auditable Tool Registry
├── planner.py        # Evidence 기반 Attack Path Planner
├── store.py          # TraceStore와 in-memory 구현
└── engine.py         # 제한된 비동기 runtime
```

설계 원칙은 [docs/architecture.md](docs/architecture.md)에, 단계별 계획은
[docs/roadmap.md](docs/roadmap.md)에 정리되어 있습니다.

## 라이선스

MIT License입니다. 자세한 내용은 [LICENSE](LICENSE)를 확인하세요.
