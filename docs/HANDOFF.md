# RedMind 세션 인수인계

마지막 갱신: 2026-07-28

## 현재 위치

- GitHub: `https://github.com/MintKangaroo/RedMind`
- 안정 브랜치: `main`
- 다음 릴리스 통합 브랜치: `develop`
- 현재 문서 브랜치: `docs/session-handoff`
- `develop` 기준 최신 커밋: `a37edf2`
- 완료된 구현 단계: 1~5
- 다음 구현 단계: 6단계 Human Approval

`main`은 1단계 안정 버전인 `0437759`에 머물러 있다. 2~5단계는 `develop`에만
통합되어 있으므로, 다음 세션도 반드시 `develop`에서 기능 브랜치를 만들어야 한다.

## 다음 세션 시작 명령

```bash
git switch develop
git pull --ff-only origin develop
git switch -c feat/human-approval
PYTHONPATH=src python3 -m pytest -q -o addopts=''
```

개발 환경에 Python 3.12와 dev dependency가 설치되어 있으면 표준 명령은
`pytest` 또는 `make check`다. 현재 컨테이너의 Python 3.10 환경에서는 coverage
plugin 설치 상태에 따라 위의 `PYTHONPATH` 명령이 필요할 수 있다.

## 완료된 단계

### 1단계: Agent Runtime

- 상태 머신: `proposed`부터 `completed`, `failed`, `rejected`까지
- `Run`, `Step`, `Message`, `Evidence`, `TraceEvent`
- 결정적 mock Agent
- in-memory trace store
- cancellation, timeout, 최대 step
- 커밋: `23aa921`

### 2단계: Policy Engine

- 허가 대상, 도구 allowlist, 위험도, 최대 step/timeout/대상 수 검증
- 공인 IP 차단
- high/critical 승인 요구
- 기능 커밋: `2574238`
- `develop` 병합: `b3b4946`

### 3단계: Tool Registry

- `read_only`, `observation`, `validation`, `state_changing` 분류
- MVP는 `read_only`, `observation`만 활성화
- Pydantic 입력, timeout, permission, audit hook
- shell 계열 도구 및 자유 형식 추가 인자 차단
- 기능 커밋: `e4087f5`
- `develop` 병합: `9570c33`

### 4단계: Recon 및 Enumeration Analyst

- Evidence gap이 있을 때만 구조화된 관찰 제안
- 서비스 Evidence가 있으면 중복 제안하지 않음
- 버전을 근거 없이 추론하지 않음
- 기능 커밋: `cabe2b0`
- `develop` 병합: `af1eb1e`

### 5단계: Attack Path Planner

- `AttackGraphEdge`, `AttackPathCandidate`, `ActionProposal`
- Evidence coverage와 confidence 계산
- 허가 대상 및 허용 도구만 후보로 생성
- 동일 검증 작업 중복 제거
- `command`, `shell`, `payload`, `exploit`, `script` 인자 차단
- 기능 커밋: `54c4674`
- `develop` 병합: `a37edf2`

현재 전체 단위 테스트는 22개이며 모두 통과한다.

## 남은 구현 순서

### 6단계: Human Approval

브랜치: `feat/human-approval`

반드시 포함할 사항:

- 승인 요청 ID, Action Proposal snapshot, 생성/만료 시간
- 승인자 ID와 승인 사유
- 거부 사유와 거부 처리
- 만료 또는 거부 후 새 요청을 만드는 재승인
- 실행 직전에 현재 Policy Engine으로 재검증
- proposal 변경 여부 검출
- append-only 승인 감사 로그

커밋 메시지:

```text
feat(approval): add human-in-the-loop security workflow
```

### 7단계: Reflection과 실패 처리

브랜치: `feat/bounded-reflection`

- 실패 분류
- Evidence 부족 시에만 재계획
- 같은 실패 fingerprint 반복 제한
- 최대 retry
- Agent self-evaluation
- Pydantic 출력 검증

커밋 메시지:

```text
feat(runtime): add bounded reflection and retry controls
```

### 8단계: AutoPentest AI 연동

브랜치: `feat/autopentest-adapter`

- 자산, Finding, Attack Graph 조회
- 승인된 observation 요청
- 응답을 untrusted content로 표시한 뒤 Pydantic 검증
- timeout, 오류 정규화, retry 상한
- 테스트에서는 실제 네트워크를 사용하지 않고 fake transport 사용

커밋 메시지:

```text
feat(integration): connect RedMind to AutoPentest AI
```

### 9단계: 실행 관찰 UI

브랜치: `feat/execution-timeline`

- FastAPI read-only API
- Run Timeline, Agent Step, Tool Call, Evidence, Approval
- token/cost, 실패 원인, 최종 보고서
- React는 선택 사항이며 MVP는 정적 UI 또는 서버 렌더링으로도 가능
- 상태 변경 API는 6단계 승인 API 외에는 추가하지 않음

커밋 메시지:

```text
feat(web): add multi-agent execution timeline
```

## 변경 금지 보안 조건

- Agent는 scope를 변경하거나 target을 추가할 수 없다.
- 자유 형식 shell command를 저장하거나 실행하지 않는다.
- 외부 API의 문자열은 항상 untrusted content다.
- 모델 또는 외부 응답은 Pydantic 검증을 통과한 뒤에만 사용한다.
- 모든 Tool Call과 Approval은 감사 가능해야 한다.
- 실행 시간, step, retry, 비용에는 상한이 있어야 한다.
- 실제 exploit payload나 우회 코드는 생성하지 않는다.

## 브랜치 운영

```text
main                 안정 버전
develop              다음 릴리스 통합
feat/<기능명>        기능 작업
fix/<문제명>         버그 수정
docs/<문서명>        문서 변경
```

각 기능은 기능 브랜치에서 테스트 후 커밋하고, `--no-ff`로 `develop`에 병합한다.
GitHub의 “Compare & pull request” 알림은 원격 기능 브랜치가 남아 있어 표시되는
정상 안내다. 원하면 PR을 만들 수 있지만 현재 이력은 로컬 병합 후 `develop`에
푸시하는 방식으로 관리 중이다. 병합된 기능 브랜치는 나중에 정리해도 된다.

## 주요 파일

- `src/redmind/runtime/models.py`: 실행 및 trace 모델
- `src/redmind/runtime/engine.py`: bounded Agent runtime
- `src/redmind/runtime/policy.py`: 정책 검증
- `src/redmind/runtime/tools.py`: typed tool registry
- `src/redmind/runtime/analysts.py`: Recon/Enumeration Analyst
- `src/redmind/runtime/planner.py`: evidence-driven planner
- `tests/unit/`: 단위 테스트

## 알려진 개선점

- Runtime이 아직 `PolicyEngine`을 자동 호출하지 않는다. 6단계 실행 전 재검증과
  함께 명시적으로 연결해야 한다.
- `analysts.py`의 Action Proposal metadata는 초기 형식이다. 5단계의
  `ActionProposal` 모델로 통일하는 리팩터링이 필요하다.
- PostgreSQL, Redis, LangGraph, OpenTelemetry는 아직 도입하지 않았다.
- README의 구조 목록과 현재 상태는 이 문서 작업에서 1~5단계 기준으로 갱신한다.
