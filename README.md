# RedMind

RedMind는 허가된 보안 실습 환경의 데이터를 분석하고 다음 검증 단계를 계획하는
정책 통제형 Multi-Agent Security Research Platform입니다. 실제 공격 도구를
무제한 자동 실행하지 않으며, 위험한 작업은 Human Approval을 거칩니다.

## 현재 상태

1단계 Agent Runtime이 구현되어 있습니다.

- `Run`, `Step`, `Message`, `Evidence`, `TraceEvent` Pydantic 모델
- 명시적 Agent 상태 머신과 유효하지 않은 전이 차단
- 네트워크 없이 재현 가능한 `DeterministicMockAgent`
- In-memory trace store와 append-only 실행 이벤트
- 실행 횟수·시간 제한, cooperative cancellation, timeout
- Agent 출력 스키마 검증 및 실패 원인 분류

다음 단계(Policy Engine, typed tool registry, 분석 Agent, 승인 workflow 등)는 아직
활성화되지 않았습니다.

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

RedMind는 소유자 또는 명시적으로 허가받은 시스템, 로컬/Docker 실습 환경, CTF와
교육용 cyber range에서만 사용해야 합니다. 공인 인터넷 탐색, 자격 증명 탈취,
지속성 확보, 방어 통제 우회, 악성코드 전달, 파괴·유출 행위는 범위에 포함되지
않습니다. 자세한 내용은 [SECURITY.md](SECURITY.md)와
[docs/threat-model.md](docs/threat-model.md)를 참고하세요.

## 구조

```text
src/redmind/runtime/
├── models.py         # 상태·trace 도메인 모델
├── state_machine.py  # lifecycle 전이 규칙
├── agents.py         # Agent protocol 및 deterministic mock
├── store.py          # TraceStore와 in-memory 구현
└── engine.py         # bounded async runtime
```

설계 원칙은 [docs/architecture.md](docs/architecture.md)에, 단계별 계획은
[docs/roadmap.md](docs/roadmap.md)에 정리되어 있습니다.

## 라이선스

MIT License. 자세한 내용은 [LICENSE](LICENSE)를 확인하세요.
