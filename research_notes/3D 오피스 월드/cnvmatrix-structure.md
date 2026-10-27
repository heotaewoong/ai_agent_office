# CnvMatrixV1 구조 노트

조사 2026-10-27 · 보고서 [3D 오피스 월드 배경 조사와 결정](../../reports/3D%20오피스%20월드%20배경%20조사와%20결정.md)

외부 강의 자료로 공유받은 3D 에이전트 공간 프로젝트의 구조를 설계 참고용으로 정리한다. 코드는 가져오지 않았고, 공개 산출물에는 공유 경로·작성자 정보·개인 환경 값을 넣지 않는다. 라이선스는 확인되지 않았다.

## 1. 저장 형태

zip 8개가 1단계부터 8단계(macOS)까지 단계별 전체 프로젝트 폴더를 담고 있다. 각 zip은 `node_modules`(약 150MB)와 `.local/`(검증 로그·화면 캡처)을 포함하며, 7·8단계는 `World/brain/research/`의 로컬 LLM 실험 파일(OpenVINO·GGUF 모델 약 2.3GB)과 목표 지도 앱의 Chromium 바이너리·npm 캐시 때문에 2.5GB에 이른다. 실제 소스는 `src/` 약 260KB, `scripts/` 약 550KB다.

## 2. 디렉터리 (8단계 기준)

```text
CnvMatrixV1/
  AGENTS.md             아키텍트(프로젝트 루트 작업 AI) 지침
  CLAUDE.md             AGENTS.md 참조
  README.md             실행·조작·검증
  docs/                 agent-runtime, architects, multi-engine-plan/usage, world-apps,
                        portability, chat-files-storage
  src/                  Babylon.js 공간(world, player, world-modules, world-landmarks),
                        채팅·에이전트 UI(agents, agent-*), 터미널(architects), HUD
  scripts/              독립 실행 서비스(agent-runtime, engine-worker, engine-catalog,
                        architect-runtime, world-apps, world-storage, world-files,
                        tailnet-*), check-*.mjs 검증 스크립트
  shared/               파일 형식 공통 목록
  World/                에이전트 작업 공간
    AGENTS.md           World 에이전트 지침 (간결, manual/로 위임)
    manual/             공통 기능 안내: agents API, storage, modules, file-links, work-sources
    apps/               goal-map(목표 지도), memory-browser, memory-guide-slides, task-notes
    brain/              집단기억 도구 v0.7 (SQLite, CLI, manual, planning, tests)
    coordination/       멀티에이전트 실증 기록 (PM·작업자·검수자, 증거 JSON, 보고서)
    inbox/              사용자 첨부 원본
    projects/, workspaces/  목표별·세션별 저장소
```

## 3. 실행 구조

- 브라우저 → Vite 개발 서버의 인증 프록시 `/api/agents-runtime` → 독립 Node 실행 서비스(`127.0.0.1:47831`, bearer 인증) → 에이전트별 엔진 프로세스. 서비스는 Vite와 별개 프로세스라 개발 서버·브라우저를 꺼도 세션이 유지된다.
- 등록부·메시지·이벤트는 SQLite(WAL). 생성·메시지 요청에 고유 ID를 두어 재전송해도 중복 실행하지 않는다. 전달 결과가 불명확하면 자동 재전송하지 않는다.
- 아키텍트 터미널: xterm.js → 프록시 → 별도 서비스(`47833`) → node-pty(Windows ConPTY / macOS PTY). 화면 스냅샷과 최근 5,000줄을 서버가 보관해 재접속 시 복원.
- 엔진별 어댑터: Codex(app-server JSONL, `thread/resume`), Claude Code(stream-json, `--resume`, `set_model`), Antigravity(`--conversation`으로 재연결), Kimi(ACP `session/load`). 모델 목록은 CLI에서 조회하며 코드에 고정하지 않는다.
- 플랫폼 계층으로 Windows ARM64·x64, macOS Apple Silicon·Intel을 분기. 사용자 데이터는 `%LOCALAPPDATA%\CnvMatrix` / `~/Library/Application Support/CnvMatrix`.
- 보안: Codex `approvalPolicy=never`, `sandbox=danger-full-access`, Claude·Antigravity 권한 확인 생략. 문서 스스로 "OS 격리가 아닌 로컬 개인용"이라고 명시.

## 4. 참고한 규약

### 4.1 앱 연결 (`World/apps/<앱>/app.json`, schemaVersion 1)

```json
{ "schemaVersion": 1, "name": "앱 이름", "description": "용도",
  "server": { "entry": "server.mjs", "health": "/api/health" },
  "connections": { "records": { "module": "자료실", "export": "records", "version": 1 } },
  "space": { "version": 1, "kind": "goals", "endpoint": "/api/space", "focusParameter": "focus" } }
```

- 공간이 `World/apps` 하위 폴더를 발견해 건물로 표시하고, 열기를 누르면 `node <entry>`를 `HOST`·`PORT`·`CNV_APP_INSTANCE`를 주입해 실행한다. 같은 앱은 서버를 재사용하고 포트를 가능한 한 유지한다.
- `health`는 `{pid, instanceId, ok}`를 돌려줘 다른 프로세스와 혼동하지 않는다.
- `space.kind: "goals"`의 `endpoint`는 `{version, revision, goals:[{id,title,status,agentIds}], conflicts:[{agentId,goalIds}]}`를 돌려주고, 공간은 이를 읽어 깃발과 동료 배치를 갱신한다. 앱을 자동 실행하거나 에이전트에게 메시지를 보내지 않는다. **우리 "공간 투영 v1"의 원형.**

### 4.2 모듈 선언 (`World/<폴더>/world-module.json`)

구역 열기 대상(`openApp`)과 공개 `.mjs` 진입(`exports.{version,entry,factory}`)을 선언한다. 공간은 서버 시작 시 선언을 검증하고 `CNV_WORLD_CONNECTIONS`로 주입한다. 절대 경로·고정 포트 금지.

### 4.3 업무 연결 (work-sources v1)

앱이 `POST /work-sources/{id}`로 `{schemaVersion, revision, title, url, apiUrl, state, items:[{id,title,state,roles:[{role:pm|worker|reviewer, agentId}]}], notices:[{id,itemId,agentId,text}]}`를 2~10초마다 게시한다. 리비전은 증가해야 하고 같은 ID의 알림은 중복 전달하지 않는다. 공간은 채팅의 "연결된 목표·업무"에 표시하고 메시지 전달만 담당한다. **오피스 승인 단계를 비추는 모델로 참고.**

### 4.4 저장소 규약

개인 작업은 `workspaces/<에이전트>/sessions/<세션 키>/`, 목표 작업은 `projects/<메인 목표 ID>/`. 공간이 `/api/world-storage`로 경로를 돌려주며 에이전트가 경로를 추측하지 않는다. 기존 파일은 이동·복제 대신 `linkedArtifacts`로 참조.

### 4.5 지침 분리

- 루트 `AGENTS.md`: 아키텍트 역할. 공간 코드·실행 서비스는 아키텍트 범위, World 에이전트에게 맡기지 않음. 연결 규약을 바꾸면 `World/AGENTS.md`를 함께 갱신.
- `World/AGENTS.md`: 간결한 역할·범위와 기능 안내 목차. 상세는 `manual/`로 위임하고 "필요한 문서만 읽는다".
- 앱마다 `manual/index.md`를 두고 사용·수정 시 매뉴얼을 함께 갱신하는 규칙.

## 5. 집단기억 (`World/brain`)

SQLite 기반 도구. 용어 사전(동의어·다의어), 기억·관계 그래프, 원문 등록·부분 읽기, 검사·백업·복구, 기억 수명·정정·상충·병합, 후보 포착, 모델 없는 검색·회상, 활용·행동·결과·피드백 연결. CLI는 줄 단위 JSON 요청(`contractVersion`, `requestId`, `actorId`, `sessionId`, `expectedStoreId`, `tool`, `input`)으로 호출하며 상태 조회는 저장소를 만들지 않는다. 삭제 정책은 미확정. 로컬 LLM 도입은 측정 후 보류.

## 6. 우리 설계에 반영한 것과 뺀 것

| 반영 | 뺀 것 |
|---|---|
| 투영 API를 읽어 공간을 그리는 단방향 구조 | 에이전트 실행 서비스·터미널(3차에서 재검토) |
| 구역·건물·중앙 기억 모형의 배치 개념 | `World/` 폴더 자동 발견(오피스는 백엔드 API가 단일 출처) |
| 승인·배정을 공간이 만들지 않는 원칙 | 전체 권한 실행 설정 |
| 데이터가 방 수·이름·색을 정하는 방식 | Node `.mjs` 진입 전제(오피스는 Python) |
