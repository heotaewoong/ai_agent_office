# HeoBrain Content Office Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for the core implementation and dispatch isolated support tasks with explicit file ownership. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 공식 RSS 기사 3건을 검증 원고와 승인 기반 블로그·YouTube 산출물로 연결하는 로컬 오피스 구현.

**Architecture:** Next.js 화면이 FastAPI의 좁은 업무 API를 호출한다. SQLite 장부와 별도 Python 작업자가 승인·버전·비용·재시작을 관리하고 기존 Python/FFmpeg의 검증 가능한 제작 패턴을 재사용한다.

**Tech Stack:** Python 3.12, FastAPI, SQLite, pytest, FFmpeg, Next.js/React/TypeScript.

**Spec:** `docs/superpowers/specs/2026-10-26-content-office-design.md`

## Global Constraints

- 작업 구간 2026-10-26 02:20–08:20 KST, 외부 API 총 10,000원 한도.
- 원본 Markdown·참고 소스·운영 Marketplace 수정 없음. 신규 앱 `apps/content-office`.
- 원고 승인① 전 미디어 제작 금지, 출고 승인② 전 외부 게시·발송 금지.
- Critique/Eval 분리 및 동일 버전 재검사, Refine 최대 2회.
- 성공 자산·열린 비용·외부 ID 보존, 불확실 호출 자동 재송 금지.

## Review Focus

- RSS 날짜 없음/시간대/미래 날짜·실패 피드는 최신 뉴스로 오표시하지 않는다(Task 2).
- 원고가 바뀐 뒤 옛 승인·파생물을 재사용하지 않는다(Task 1/4).
- 동시에 두 호출을 예약해 합계 예산이 초과되지 않는다(Task 3).
- 브라우저 새로고침/서버 재시작 뒤 같은 업무·결과·다음 행동이 유지된다(Task 1/5).
- 외부 자료 속 지시·임의 URL/파일 경로·타 Origin이 승인/게시를 실행하지 못한다(Task 2/5).

## Task 1: 영속 작업·버전·승인

Files: `apps/content-office/backend/office/store.py`, `models.py`, `tests/test_workflow.py`.
Interfaces: `Store(root)`, `create_job(article)`, `save_source(job_id, packet)`, `review_source(job_id, version, decision, actor)`, `require_source_approval(job_id)`, `enqueue(kind, payload)`, `claim()`.

- [x] 승인 없는 제작, 옛 버전 승인, 거절·중대 오류, 재시작 상태, 중복 큐 요청 테스트를 먼저 작성·실패 확인.
- [x] SQLite 트랜잭션·불변 버전·승인/작업 이벤트 구현.
- [x] 관련 테스트와 전체 Python suite 통과 확인.

## Task 2: RSS·근거·선정

Files: `office/feeds.py`, `office/evidence.py`, `tests/test_feeds.py`, `config/feeds.json`.
Interfaces: `parse_feed(xml, feed, now) -> list[Article]`, `collect_feeds(config) -> FeedReport`, `rank_articles(articles, now) -> list[Article]`.

- [x] RSS/Atom·누락/미래 날짜·URL 중복·로컬호스트·응답 제한·실패 구분 테스트 RED.
- [x] 실제 공개 피드 수집, 원문 근거 저장, 동일 이벤트 묶기, 설명 가능한 TOP3 구현.
- [x] 수집 시각과 raw hash·실패를 보존하고 라이브 수집 검증.

## Task 3: 에이전트 작성·품질·예산

Files: `office/providers.py`, `office/editorial.py`, `office/budget.py`, `tests/test_editorial.py`, `tests/test_budget.py`.
Interfaces: `Provider.generate(role, messages, schema, options)`, `prepare_source(job_id)`, `reserve_cost(...)`, `settle_cost(...)`.

- [x] 실제 payload/rubric 캐시 변화, Critique/Eval 입력 독립, 2회 수정 상한, 중대 지적 차단, 동시 예산 테스트 RED.
- [x] 자격·단가 확인한 제공자만 연결. 모델 결과와 독립 검증/사람 승인을 분리.
- [x] 기사 3건의 실제 근거·원고·평가를 저장. 미승인 상태 유지.

## Task 4: 블로그·영상·썸네일·자료

Files: `office/media.py`, `office/exports.py`, `tests/test_media.py`, `tests/test_exports.py`.
Interfaces: `produce(job_id, selections) -> ArtifactManifest`, `render_short(plan, assets)`, `release_package(job_id, release_hash)`.

- [x] 원고 승인 검사·부분 실패 자산 보존·음성60초 초과·자막 실제 길이·출고 전 다운로드 조건 테스트 RED.
- [x] HTML/MD/텍스트, 음성·장면 PNG·MP4/SRT, 5개 썸네일, 선택 PDF/권리 기록 구현.
- [x] ffprobe·프레임·오디오·자막 검증과 승인된 합성 자료/허용 기사 산출물 검수.

## Task 5: API·검토 대시보드·작업자

Files: `office/api.py`, `office/worker.py`, `frontend/app/*`, `tests/test_api.py`, `scripts/run-*`.
Interfaces: `GET /api/dashboard`, `GET /api/jobs/{id}`, `POST /api/refresh`, `POST /api/jobs`, `POST /api/jobs/{id}/draft`, `PUT /api/jobs/{id}/source`, `POST /api/jobs/{id}/reviews/source`, `POST /api/jobs/{id}/produce`, `POST /api/jobs/{id}/reviews/release`, `GET /api/artifacts/{id}`.

- [x] 승인 actor/session·Origin·잘못된ID/경로·重複 요청·큐 재시작 API 테스트 RED.
- [x] 실데이터 기반 한국어 Next.js 화면과 독립 worker/health/status 구현.
- [x] 브라우저 조작→API→SQLite 저장→다시 조회→파일 다운로드 검증. 좁은 폭·키보드·실패 상태 확인.

## Task 6: 지속 실행·검수·인계

Files: `scripts/watch-window.py`, `research/content-office-2026-10-26/progress.jsonl`, `README.md`, 최종 보고서.

- [x] 마감 전 주기적 실제 RSS 재조회·상태/예산·필수 검사 실행, 자동 마감·중복 실행 방지 테스트.
- [x] 독립 코드/내용/화면 검수의 주요 문제를 회귀 테스트로 수정.
- [x] 원본 hash·실제 비용·파일·미완료·실제 작업 시간·접속/실행법 기록. 마감에 추적 종료 확인.

## 실행 판정

현재 폴더는 Git 저장소가 아니다. worktree/commit 명령을 만들기 위해 원본 전체를 새 저장소로 변경하지 않는다. 작업별 실제 파일·테스트·판정은 `research/content-office-2026-10-26/progress.md`에 남긴다. 사용자 명시 상세규격과 구현 요청에 따라 독립 구현 작업은 계속 진행하며 게시·발송 같은 새 외부 효과만 실제 승인 경계에 둔다.
