# v6 화면 반영과 오피스 월드 연동 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** API로만 가능한 v6 기능(기획 등록·패키지 확정·성과 CSV·교훈 검토)을 메인 화면에 넣고, 3D 오피스 월드를 메인 앱의 한 화면으로 붙여 앱과 공간이 서로 조작·동기화되게 한다.

**Architecture:** 프런트는 새 패널 파일을 하나씩 만들고 `page.tsx`에는 삽입 지점만 추가한다. 백엔드는 읽기 전용 투영 `GET /api/space`(`office/space.py`)와 CSV 본문을 받는 `POST /api/analytics/studio-csv`를 더한다. 오피스 월드는 Next.js 라우트 핸들러가 `sites/office-world/`를 같은 출처 `/world/`로 제공하고, iframe과 부모가 `postMessage` 계약으로 포커스·열기·요청을 주고받는다. 공간은 세션·쓰기 API를 갖지 않고 앱이 대신 호출한다.

**Tech Stack:** Python 3.12 FastAPI + SQLite(Store), pytest · Next.js 16.4.3 / React 19 / TypeScript 5.9, `node --test` · Babylon.js 정적 사이트(`sites/office-world/app.js`, 빌드 없음)

**Spec:** `docs/superpowers/specs/2026-10-27-ai-content-agent-design.md`(3장 파이프라인, 4장 데이터 모델) · `docs/superpowers/specs/2026-10-28-office-world-design.md`(6장 투영 계약, 12장 앱 연동 수정)

## Global Constraints

- 승인 단계 ⓪ 기획 선택 · ① 원고 · ② 출고 · ③ 회차의 의미를 바꾸지 않고, 에이전트가 승인을 만들지 않는다. 승인 조작은 메인 앱 화면에서만 한다(오피스 월드 설계 12장).
- `database/learning-private/`, `database/class101/`, 파일명에 `PRIVATE`가 있는 자료, 원문 본문, 비밀값은 투영(`/api/space`)에 넣지 않는다. 투영에는 제목·상태·담당 이름만 넣는다.
- 화면·투영 문구에 "게시됨"·"자동"을 쓰지 않는다. 출고 승인 뒤 상태는 "수동 전달 대기"다.
- 백엔드 쓰기 요청은 기존 Origin·CSRF 미들웨어를 그대로 거친다. 새 엔드포인트도 `create_app` 안에 둔다.
- 프런트 새 UI 문구는 한국어, 기존 CSS 클래스(`news-section`, `section-heading`, `button primary|secondary`, `notice error`, `editor-fields`, `table-scroll`, `muted`, `eyebrow`)를 재사용한다. 새 전역 CSS는 `globals.css` 끝에 덧붙이고 클래스 접두어는 `v6-`·`world-`로 한다.
- 백엔드 테스트: `cd apps/content-office/backend && python -m pytest -q`(WSL `~/hb-venv`). 프런트: `cd apps/content-office/frontend && npm run typecheck && npm test`. 오피스 월드 문법: `node --check sites/office-world/app.js`.
- 테스트 ID·고정값은 각 Task의 테스트 코드에 적힌 값을 그대로 쓴다.
- 커밋 메시지는 `feat(ui): …`·`feat(space): …`·`feat(world): …` 형식, 끝에 `Co-Authored-By` 줄.

## Review Focus

1. 패키지 패널에서 제목·훅을 비운 채 "확정"을 누르면 백엔드 409 메시지가 그대로 보여야 하고, 입력이 지워지면 안 된다 → Task 3 Step 1 `validatePackagingBrief` 테스트와 Step 6 컴포넌트 동작.
2. Studio CSV에 합계 행·빈 행·`%` 붙은 값이 섞여 있어도 유효 행만 저장되고 응답에 건수가 와야 한다 → Task 4 Step 1 테스트.
3. `/api/space`는 작업이 하나도 없는 새 Store에서도 방 5개와 빈 `items`를 돌려줘야 한다(공간이 "빈 섬"으로 떨어지지 않게) → Task 5 Step 1 테스트.
4. 오피스 월드 iframe이 다른 출처에서 보낸 메시지는 무시해야 한다 → Task 6 Step 1 `parseWorldMessage`는 origin 판단을 호출부에 두고, `WorldView`는 `event.origin !== window.location.origin`이면 버린다(Step 4).
5. 공간에서 "원고 생성"을 두 번 빠르게 눌러도 앱의 `action()`이 busy 상태에서는 두 번째를 무시해야 한다 → Task 6 Step 4에서 busy면 `result ok:false, message:"이미 처리 중입니다"`를 돌려준다.

---

## 파일 구조

| 파일 | 역할 | Task |
|---|---|---|
| `apps/content-office/frontend/lib/types.ts` | `IdeaInput`, `PackagingRecord`, `StudioCsvResult`, `Job.packaging`, `SourcePacket.packaging_hash` | 1 |
| `apps/content-office/frontend/lib/api.ts` | `addIdea`, `uploadStudioCsv` | 1 |
| `apps/content-office/frontend/app/idea-intake.tsx` | 기획 등록 폼 | 2 |
| `apps/content-office/frontend/app/support-panels.tsx` | `IdeaBank`에 폼 삽입·재조회 | 2 |
| `apps/content-office/frontend/lib/packaging.ts` | 패키지 입력 검사(백엔드 규칙 미러) | 3 |
| `apps/content-office/frontend/app/packaging-panel.tsx` | 패키지 카드 패널 | 3 |
| `apps/content-office/backend/office/analytics.py` | `parse_studio_text` | 4 |
| `apps/content-office/backend/office/api.py` | `POST /api/analytics/studio-csv`, `GET /api/space` | 4, 5 |
| `apps/content-office/frontend/app/performance-panel.tsx` | CSV 업로드 + 교훈 검토 | 4 |
| `apps/content-office/backend/office/space.py` | 투영 계산 | 5 |
| `apps/content-office/frontend/lib/world-files.ts` | `/world/` 파일 경로·타입 해석 | 6 |
| `apps/content-office/frontend/app/world/[[...path]]/route.ts` | 정적 파일 제공 | 6 |
| `apps/content-office/frontend/lib/world-bridge.ts` | postMessage 메시지 파서 | 6 |
| `apps/content-office/frontend/app/world-view.tsx` | iframe + 브리지 | 6 |
| `apps/content-office/frontend/app/page.tsx` | 삽입 지점 4곳 | 3, 4, 6 |
| `sites/office-world/app.js`, `styles.css`, `data/space.json` | embed 모듈·actions 버튼·focus | 7 |
| `apps/content-office/README.md`, `sites/office-world/README.md` | 화면 절차·연동 | 8 |

`page.tsx`는 Task 3(Studio, 1000행 부근) · Task 4(Activity, 2150행 부근) · Task 6(`views` 배열 44행, 화면 분기 668행 부근)이 서로 다른 구간만 고친다. Task 1이 끝난 뒤 Task 2~7은 병렬로 진행할 수 있다.

---

### Task 1: 프런트 타입·API 클라이언트 확장

**Files:**
- Modify: `apps/content-office/frontend/lib/types.ts:130-175, 252-281`
- Modify: `apps/content-office/frontend/lib/api.ts:135-155`

**Interfaces:**
- Produces:
  ```ts
  export type IdeaInput = { title: string; source_url: string; views?: number | null; channel_avg_views?: number | null; demand: number; primary_sources: number; fit: number; covered_before: boolean; policy_flags: string[] };
  export type PackagingRecord = PackagingBrief & { packaging_hash: string; selected_by?: string };
  export type StudioCsvResult = { snapshots: { id: string; external_id: string; period: string }[]; lessons: Lesson[] };
  export type SnapshotChannel = "youtube_long" | "shorts" | "blog_tistory" | "blog_naver" | "newsletter";
  export type SnapshotPeriod = "24h" | "7d" | "28d";
  // Job에 packaging?: PackagingRecord | null; SourcePacket에 packaging_hash?: string; Article에 origin?: string
  api.addIdea(input: IdeaInput): Promise<Idea>
  api.uploadStudioCsv(body: { channel: SnapshotChannel; period: SnapshotPeriod; csv: string; job_id?: string }): Promise<StudioCsvResult>
  ```

- [ ] **Step 1: 타입 추가** — 위 Interfaces를 `types.ts`에 추가. `Article` 타입에 `origin?: string`이 없으면 추가.
- [ ] **Step 2: API 메서드 추가** — `addIdea`는 `POST /ideas`, `uploadStudioCsv`는 `POST /analytics/studio-csv`.
- [ ] **Step 3: 검사** — Run: `cd apps/content-office/frontend && npm run typecheck` Expected: 오류 없음
- [ ] **Step 4: Commit** — `feat(ui): v6 화면용 타입과 API 클라이언트`

---

### Task 2: 기획 등록 폼

**Files:**
- Create: `apps/content-office/frontend/app/idea-intake.tsx`
- Modify: `apps/content-office/frontend/app/support-panels.tsx:549-604` (`IdeaBank`)
- Create: `apps/content-office/frontend/lib/ideas.ts`
- Test: `apps/content-office/frontend/tests/ideas.test.ts`

**Interfaces:**
- Consumes: Task 1 `IdeaInput`, `api.addIdea`
- Produces: `export function ideaInputFromForm(form: Record<string, string | boolean>): { input: IdeaInput } | { error: string }` (`lib/ideas.ts`) · `export function IdeaIntake({ onSaved }: { onSaved: () => void })`

- [ ] **Step 1: 실패하는 테스트**

```ts
import test from "node:test";
import assert from "node:assert/strict";
import { ideaInputFromForm } from "../lib/ideas.ts";

test("제목과 https 출처가 있으면 숫자 필드를 변환한다", () => {
  const r = ideaInputFromForm({ title: " Claude 팀 ", source_url: "https://ex.com/a", views: "12,000", channel_avg_views: "3000", demand: "70", primary_sources: "2", fit: "0.9", covered_before: false, policy_flags: "ymyl, 실존인물" });
  assert.ok("input" in r);
  assert.equal(r.input.title, "Claude 팀");
  assert.equal(r.input.views, 12000);
  assert.deepEqual(r.input.policy_flags, ["ymyl", "실존인물"]);
});
test("출처가 https가 아니면 오류를 돌려준다", () => {
  const r = ideaInputFromForm({ title: "x", source_url: "http://ex.com", demand: "0", primary_sources: "0", fit: "0", covered_before: false, policy_flags: "" });
  assert.ok("error" in r && r.error.includes("https"));
});
test("빈 조회수는 null이고 범위 밖 fit은 오류다", () => {
  const ok = ideaInputFromForm({ title: "x", source_url: "https://a.b", views: "", demand: "10", primary_sources: "1", fit: "1", covered_before: true, policy_flags: "" });
  assert.ok("input" in ok && ok.input.views === null);
  const bad = ideaInputFromForm({ title: "x", source_url: "https://a.b", demand: "10", primary_sources: "1", fit: "1.5", covered_before: false, policy_flags: "" });
  assert.ok("error" in bad);
});
```

- [ ] **Step 2: 실패 확인** — Run: `npm test` Expected: `ideaInputFromForm` 모듈 없음으로 실패
- [ ] **Step 3: `lib/ideas.ts` 구현** — 제목 trim·빈 제목 오류, `https://` 검사, 쉼표 제거 후 정수 변환(빈 값 → null), demand 0~100·fit 0~1 범위 검사, policy_flags는 쉼표 분리·trim·빈 항목 제거.
- [ ] **Step 4: 통과 확인** — Run: `npm test` Expected: PASS
- [ ] **Step 5: `IdeaIntake` 컴포넌트** — `<details>`로 접히는 폼("기획 직접 등록"). 필드: 제목, 출처 URL(https), 조회수, 채널 평균 조회수, 수요(0~100), 1차 출처 수, 적합도(0~1), 전에 다룸(체크), 정책 플래그(쉼표). 제출 시 `ideaInputFromForm` → 오류면 `role="alert"`로 표시, 아니면 `api.addIdea` 후 폼 초기화·`onSaved()`. 응답 `Idea.blocked`가 비어 있지 않으면 "저장됨 · 막힌 이유: …" 안내.
- [ ] **Step 6: `IdeaBank`에 삽입** — 제목 아래에 `<IdeaIntake onSaved={() => void load()} />`. 빈 목록 문구를 "아직 점수를 매긴 기획이 없습니다. 아래에서 직접 등록하세요."로.
- [ ] **Step 7: 검사** — Run: `npm run typecheck && npm test` Expected: PASS
- [ ] **Step 8: Commit** — `feat(ui): 기획 은행에 기획 등록 폼`

---

### Task 3: 패키지 카드 패널

**Files:**
- Create: `apps/content-office/frontend/lib/packaging.ts`
- Create: `apps/content-office/frontend/app/packaging-panel.tsx`
- Modify: `apps/content-office/frontend/app/page.tsx:1000-1035` (Studio, `EvidenceIntake` 바로 위와 "원고 생성 시작" 버튼)
- Test: `apps/content-office/frontend/tests/packaging.test.ts`

**Interfaces:**
- Consumes: Task 1 `PackagingBrief`, `PackagingRecord`, `api.setPackaging`
- Produces: `export function validatePackagingBrief(brief: PackagingBrief): string[]` · `export function packagingRequired(job: Pick<Job, "article" | "packaging">): boolean` · `export function PackagingPanel({ job, busy, action, onSaved }: { job: Job; busy: boolean; action: Action; onSaved: (job: Job) => void })` (`Action` 타입은 `page.tsx`의 `action` 서명 `(label: string, execute: () => Promise<unknown>, success: string) => Promise<void>`; 이미 `page.tsx`에 `type Action`이 있으면 그것을 `export`해 쓴다)

- [ ] **Step 1: 실패하는 테스트** — 백엔드 `office/packaging.py`의 규칙을 그대로 미러한다(TITLE_MAX 45, THUMB_TEXT_MAX 12, HOOK_MAX 120).

```ts
import test from "node:test";
import assert from "node:assert/strict";
import { validatePackagingBrief, packagingRequired } from "../lib/packaging.ts";

const good = { titles: ["Claude 팀으로 블로그 자동화", "AI 팀 블로그", "자동화 3단계"], thumbnails: [{ text: "AI 팀", visual: "화면" }, { text: "AI 팀", visual: "화면" }, { text: "AI 팀", visual: "화면" }], hook: "Claude 팀으로 블로그를 끝낸 결과부터 봅니다", logline: "한 명이 팀처럼 일하는 법", reasons: ["수요", "실제 화면"] };

test("완성된 브리프는 문제 없음", () => assert.deepEqual(validatePackagingBrief(good), []));
test("제목 3안·썸네일 3안·이유 2~3개가 아니면 문제", () => {
  const issues = validatePackagingBrief({ ...good, titles: ["하나"], thumbnails: [], reasons: ["x"] });
  assert.ok(issues.some((i) => i.includes("제목")));
  assert.ok(issues.some((i) => i.includes("썸네일")));
  assert.ok(issues.some((i) => i.includes("이유")));
});
test("길이 상한을 넘으면 문제", () => {
  const issues = validatePackagingBrief({ ...good, titles: ["가".repeat(46), "b", "c"], thumbnails: [{ text: "가".repeat(13), visual: "v" }, { text: "a", visual: "v" }, { text: "a", visual: "v" }], hook: "가".repeat(121) });
  assert.equal(issues.length, 3);
});
test("빈 훅·로그라인은 문제", () => {
  assert.ok(validatePackagingBrief({ ...good, hook: " ", logline: "" }).length >= 2);
});
test("기획에서 시작했고 패키지가 없을 때만 필요", () => {
  assert.equal(packagingRequired({ article: { origin: "idea" } as never, packaging: null }), true);
  assert.equal(packagingRequired({ article: { origin: "idea" } as never, packaging: { packaging_hash: "h" } as never }), false);
  assert.equal(packagingRequired({ article: {} as never }), false);
});
```

- [ ] **Step 2: 실패 확인** — Run: `npm test` Expected: 모듈 없음 실패
- [ ] **Step 3: `lib/packaging.ts` 구현** — 문구는 백엔드와 같게: "제목은 비교용 3안이 필요합니다", "제목 N안이 45자를 넘습니다", "썸네일은 비교용 3안이 필요합니다", "썸네일 N안 글자가 12자를 넘습니다", "훅은 1~120자로 씁니다", "로그라인이 없습니다", "통할 이유는 2~3개입니다". 훅-제목 약속 검사는 백엔드만 한다(클라이언트는 하지 않는다).
- [ ] **Step 4: 통과 확인** — Run: `npm test` Expected: PASS
- [ ] **Step 5: `PackagingPanel` 구현** — `section.v6-packaging`. 상태: `titles[3]`, `thumbnails[3]{text,visual}`, `hook`, `logline`, `reasons[3]`(빈 칸은 제외), `chosenTitle`(라디오, 기본 1안). 초기값은 `job.packaging`이 있으면 그것. 제출: `validatePackagingBrief` 결과가 있으면 목록으로 표시하고 보내지 않음; 없으면 `action("패키지 확정", () => api.setPackaging(job.id, brief), "패키지를 확정했습니다. 이제 원고를 생성할 수 있어요.")`. 409 오류 문구는 `action`이 표시하므로 입력은 유지한다. `job.packaging`이 있으면 헤더에 "확정됨 · 해시 앞 8자"와 "다시 확정" 안내. `job.source_packet?.packaging_hash`가 있고 `job.packaging?.packaging_hash`와 다르면 `notice error`로 "원고는 이전 패키지로 작성됐습니다. 원고를 다시 생성하면 새 패키지가 반영됩니다."
- [ ] **Step 6: `page.tsx` Studio 삽입** — `job.article?.origin === "idea"`일 때 `EvidenceIntake` 위에 `<PackagingPanel job={job} busy={locked} action={action} onSaved={onSaved} />`. "원고 생성 시작" 버튼은 `disabled={locked || packagingRequired(job)}`로 하고, 필요할 때 버튼 아래 `muted`로 "패키지(제목·썸네일·훅)를 먼저 확정하세요."
- [ ] **Step 7: 검사** — Run: `npm run typecheck && npm test` Expected: PASS
- [ ] **Step 8: Commit** — `feat(ui): 작업실에 패키지 카드 확정 패널`

---

### Task 4: 성과 CSV 업로드와 교훈 검토

**Files:**
- Modify: `apps/content-office/backend/office/analytics.py:38-49`
- Modify: `apps/content-office/backend/office/api.py:99-115, 431-436` (모델 추가, `add_snapshot` 바로 뒤에 라우트)
- Test: `apps/content-office/backend/tests/test_analytics.py`, `apps/content-office/backend/tests/test_content_agent_api.py`
- Create: `apps/content-office/frontend/app/performance-panel.tsx`
- Modify: `apps/content-office/frontend/app/page.tsx:2153-2170` (`Activity` 렌더 맨 위 `BudgetStrip` 아래)

**Interfaces:**
- Consumes: Task 1 `api.uploadStudioCsv`, `api.lessons`, `api.reviewLesson`, `StudioCsvResult`
- Produces: `parse_studio_text(text: str) -> list[dict]` (`analytics.py`; `parse_studio_csv(path)`는 이를 호출하도록 리팩터) · `POST /api/analytics/studio-csv` 본문 `{channel, period, csv, job_id?}` → `{"snapshots": [...], "lessons": [...]}` · `export function PerformancePanel()`

- [ ] **Step 1: 백엔드 실패하는 테스트**

```python
# tests/test_analytics.py 에 추가
from office.analytics import parse_studio_text

def test_parse_studio_text_skips_total_and_blank_rows():
    text = "﻿Content,Views,Impressions click-through rate (%),Average percentage viewed (%)\nabc123,1200,4.5%,38.2%\nTotal,9999,,\n,,,\n"
    rows = parse_studio_text(text)
    assert [r["external_id"] for r in rows] == ["abc123"]
    assert rows[0]["views"] == 1200 and rows[0]["ctr"] == 4.5

# tests/test_content_agent_api.py 에 추가
def test_studio_csv_upload_saves_snapshots_and_counts(context):
    store, client, headers = context
    csv = "Content,Views,Impressions click-through rate (%),Average percentage viewed (%)\nvid1,1000,5.0%,40%\nvid2,500,2.0%,45%\nTotal,1500,,\n"
    r = client.post("/api/analytics/studio-csv", json={"channel": "youtube_long", "period": "7d", "csv": csv}, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert [s["external_id"] for s in body["snapshots"]] == ["vid1", "vid2"]
    assert len(store.snapshots("youtube_long")) == 2

def test_studio_csv_without_rows_is_409(context):
    _, client, headers = context
    r = client.post("/api/analytics/studio-csv", json={"channel": "shorts", "period": "24h", "csv": "Content,Views\nTotal,1\n"}, headers=headers)
    assert r.status_code == 409
```

- [ ] **Step 2: 실패 확인** — Run: `python -m pytest tests/test_analytics.py tests/test_content_agent_api.py -q` Expected: ImportError / 404
- [ ] **Step 3: 구현** — `analytics.py`: `_parse_rows(reader)`를 빼내고 `parse_studio_csv(path)`와 `parse_studio_text(text)`(`io.StringIO(text.lstrip("﻿"))`)가 공유. `api.py`: `class StudioCsvInput(BaseModel): channel: Literal[...같은 5개]; period: Literal["24h","7d","28d"]; csv: str = Field(min_length=1, max_length=2_000_000); job_id: str | None = None`. 라우트는 각 행에 대해 `store.save_snapshot(channel, row["external_id"], period, {k: v for k, v in row.items() if k != "external_id"}, job_id)`, 저장 뒤 `add_snapshot`과 같은 방식으로 `baseline`·`propose_lessons`·`store.add_lesson`을 돌려 `lessons`를 모은다(중복은 `add_lesson`이 기존 교훈을 돌려주므로 id로 dedupe). 유효 행이 0이면 `WorkflowError("CSV에서 저장할 행을 찾지 못했습니다. Studio '콘텐츠' 표를 그대로 내보낸 파일인지 확인하세요")`.
- [ ] **Step 4: 통과 확인** — Run: 같은 명령 Expected: PASS
- [ ] **Step 5: Commit** — `feat(space): Studio CSV 본문 업로드 엔드포인트`
- [ ] **Step 6: `PerformancePanel` 구현** — `section.v6-performance`에 두 블록. (a) "성과 스냅샷 올리기": 채널 select(5개, 라벨 유튜브 롱폼·쇼츠·티스토리·네이버·뉴스레터), 기간 select(24h·7d·28d), `<input type="file" accept=".csv,text/csv">`, 파일을 `File.text()`로 읽어 `api.uploadStudioCsv`. 결과: "스냅샷 N건 저장 · 교훈 후보 M건". 오류는 `role="alert"`. (b) "교훈 후보": `api.lessons()` 목록. 각 행에 `kind`, `hypothesis`, `weight_change`가 있으면 "가중치 factor +delta", 상태 배지. `proposed`면 "승인"·"반려" 버튼(`api.reviewLesson`) 후 재조회. 업로드 성공 뒤에도 재조회.
- [ ] **Step 7: `page.tsx` Activity 삽입** — `<BudgetStrip …/>` 바로 아래 `<PerformancePanel />`.
- [ ] **Step 8: 검사** — Run: `npm run typecheck && npm test` Expected: PASS
- [ ] **Step 9: Commit** — `feat(ui): 운영 기록에 성과 CSV 업로드와 교훈 검토`

---

### Task 5: 투영 API `GET /api/space`

**Files:**
- Create: `apps/content-office/backend/office/space.py`
- Modify: `apps/content-office/backend/office/api.py:177-185` (`dashboard` 라우트 바로 뒤), import 추가
- Test: `apps/content-office/backend/tests/test_space.py`
- Modify: `sites/office-world/README.md:23-38` (실시간 연결 절차를 `/world/index.html?api=/api/space`로)

**Interfaces:**
- Produces: `project_space(store, office_url: str = "http://localhost:3110", agents=AGENTS) -> dict` · `GET /api/space` (응답 헤더 `Access-Control-Allow-Origin: *`, `Cache-Control: no-store`)
- 투영 모양(오피스 월드 설계 6장 + 12장): 최상위 `version: 1, generatedAt, office{name,url}, brain{name,notes,sources,label}, stages[], agents[], events[], flows[]`. `stages[]`: `{id, name, approval, color, url, view, items[]}`. `items[]`: `{id, title, state, stateLabel, needsHuman, agentId, view, actions:[{id,label}]}`.

고정 방 5개(순서 고정, `STAGES` 상수):

| id | name | approval | color | view | 들어가는 것 |
|---|---|---|---|---|---|
| inbox | 오늘의 뉴스 | ⓪ 기획 선택 | #f2a444 | news | `store.ideas()` 중 state `candidate`: blocked가 비면 state `candidate`, stateLabel `후보 · 점수 {score}`, needsHuman True; blocked가 있으면 state `blocked`, stateLabel `차단 · {', '.join(blocked)}`, needsHuman False. `selected`는 제외 |
| scripts | 원고 작업실 | ① 원고 승인 | #4f8df7 | studio | job.state ∈ research_ready, drafting, source_review, source_rejected, blocked, needs_reconciliation, failed |
| creative | 제작 스튜디오 | 영상 검토 | #8b6cf0 | delivery | source_approved, production_queued, producing |
| outbox | 제작·출고함 | ② 출고 승인 · ③ 회차 | #3ecfb2 | delivery | release_review, partial_release_review, release_approved |
| ops | 운영 기록 | 교훈 승인 | #e2c15a | activity | `store.lessons("proposed")` 각각 `{id, title: hypothesis, state:"proposed", stateLabel:"사람 승인 대기", needsHuman:True}` + 예산 1건 `{id:"budget", title:f"외부 API 예산 {cap:,}원 중 {reserved+spent:,}원 사용·예약", state:"info", stateLabel:"추정 원가 · 청구 대사 전", needsHuman:False}` |

작업 항목: `id=job["id"]`, `title=job["title"]`, `state=job["state"]`, `stateLabel`은 `STATE_LABELS`(research_ready 근거 준비 · drafting 원고·검수 중 · source_review 사람 승인 대기 ① · source_approved 원고 승인 · source_rejected 원고 거절 · production_queued 제작 대기 · producing 제작 중 · release_review 사람 승인 대기 ② · partial_release_review 일부 제작 완료 · release_approved 출고 승인 ② 완료 · 수동 전달 대기 · blocked 확인 필요 · needs_reconciliation 호출 결과 확인 필요 · failed 실패), `needsHuman` = state ∈ {source_review, release_review, partial_release_review, blocked, needs_reconciliation, failed}, `actions`: research_ready·source_rejected → `[{"id":"draft","label":"원고 생성"}]`, source_approved → `[{"id":"produce","label":"제작 시작"}]`, 그 외 `[]`. `agentId`는 방의 첫 에이전트.

에이전트: `AGENTS` 9명을 방에 배정(research→inbox, editor·critique·eval→scripts, video·qa→creative, release·marketing→outbox, director→ops). `engine`은 `mode` 값, `model`은 editor·critique·eval이면 `store.setting("model") or ""`, 아니면 `""`. `status`: `store.tasks()`에서 kind→agent 매핑(draft→editor, evaluate→critique, produce→video, refresh→research)으로 state ∈ {claimed, running}이면 `running`, 그 kind의 가장 최근 task가 `failed`면 `error`, 방에 needsHuman 항목이 있으면 `waiting`, 아니면 `idle`. `task`는 running이면 `"{kind} 처리 중"`, waiting이면 `"사람 답 대기"`, error면 `"마지막 작업 실패"`, idle이면 `"대기"`.

이벤트: `store.events(limit=20)` → `{time: created_at을 KST HH:MM, stageId: job_id가 있으면 그 작업 상태의 방, 없으면 "ops", text: f"{EVENT_TEXT.get(kind, kind)} · {job title 또는 ''}"}`. `EVENT_TEXT`는 job_created 작업 생성 · idea_saved 기획 저장 · idea_selected ⓪ 기획 선택 · packaging_selected 패키지 확정 · source_saved 원고 저장 · source_review_requested 원고 검토 요청 · source_approved ① 원고 승인 · source_rejected ① 원고 거절 · release_approved ② 출고 승인 · release_rejected ② 출고 거절 · lesson_proposed 교훈 후보 · lesson_reviewed 교훈 검토 · model_started 모델 호출 · model_completed 모델 완료 · thumbnail_selected 썸네일 선택.

흐름: 같은 20건 중 kind별 `FLOW = {idea_selected: (inbox, scripts), job_created: (inbox, scripts), source_approved: (scripts, creative), production_partial: (creative, outbox), release_approved: (outbox, ops)}` → `{from, to, itemId: job_id}`.

뇌: `summary = store.setting("knowledge_summary", {})`; `notes = summary.get("notes") or summary.get("chunks") or summary.get("entries") or 0`, `sources = summary.get("sources") or summary.get("documents") or summary.get("files") or 0`(구현 전 `office/knowledge.py`에서 실제 키를 확인해 첫 후보를 맞춘다), `label: "과거 기획·근거"`.

- [ ] **Step 1: 실패하는 테스트**

```python
# tests/test_space.py
import json
from fastapi.testclient import TestClient
from office.api import create_app
from office.space import project_space
from office.store import Store

FORBIDDEN = ("게시됨", "자동")

def test_empty_store_still_has_five_stages(tmp_path):
    space = project_space(Store(tmp_path))
    assert [s["id"] for s in space["stages"]] == ["inbox", "scripts", "creative", "outbox", "ops"]
    assert all(s["items"] == [] for s in space["stages"][:4])
    assert space["stages"][4]["items"][0]["id"] == "budget"
    assert space["version"] == 1 and len(space["agents"]) == 9

def test_jobs_and_ideas_land_in_their_rooms(tmp_path):
    store = Store(tmp_path)
    store.save_idea({"id": "idea-1", "title": "후보 기획", "score": 82, "blocked": [], "state": "candidate", "reasons": []})
    store.save_idea({"id": "idea-2", "title": "막힌 기획", "score": 10, "blocked": ["1차 출처 없음"], "state": "candidate", "reasons": []})
    job = store.create_job({"id": "a1", "title": "원고 작업", "url": "https://ex.com", "evidence": []})
    store.update_job(job["id"], state="source_approved")
    space = project_space(store)
    inbox = {i["id"]: i for i in space["stages"][0]["items"]}
    assert inbox["idea-1"]["needsHuman"] is True and "82" in inbox["idea-1"]["stateLabel"]
    assert inbox["idea-2"]["state"] == "blocked"
    creative = space["stages"][2]["items"]
    assert creative[0]["id"] == "a1" and creative[0]["actions"] == [{"id": "produce", "label": "제작 시작"}] and creative[0]["view"] == "delivery"

def test_projection_has_no_private_data_or_forbidden_words(tmp_path):
    store = Store(tmp_path)
    job = store.create_job({"id": "b1", "title": "제목만", "url": "https://ex.com", "evidence": [], "body": "본문 database/learning-private/secret.md"})
    dumped = json.dumps(project_space(store), ensure_ascii=False)
    assert "learning-private" not in dumped and "본문" not in dumped
    assert not any(w in dumped for w in FORBIDDEN)

def test_space_endpoint_is_public_read(tmp_path):
    client = TestClient(create_app(Store(tmp_path)), base_url="http://localhost:8510")
    r = client.get("/api/space")
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == "*"
    assert r.json()["office"]["url"].startswith("http")
```

`save_idea`·`create_job`·`update_job`의 실제 서명은 `office/store.py`를 읽어 맞춘다(테스트의 의도는 바꾸지 않는다).

- [ ] **Step 2: 실패 확인** — Run: `python -m pytest tests/test_space.py -q` Expected: ImportError
- [ ] **Step 3: `space.py` 구현** — 위 표·규칙대로. 시간은 `datetime.fromisoformat(created_at)`을 KST(+9)로.
- [ ] **Step 4: 라우트** — `@app.get("/api/space")`는 `JSONResponse(project_space(store, office_url=os.environ.get("OFFICE_URL", "http://localhost:3110")), headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store"})`.
- [ ] **Step 5: 통과 확인** — Run: `python -m pytest tests/test_space.py tests/test_content_agent_api.py -q` Expected: PASS
- [ ] **Step 6: `sites/office-world/README.md`** — "실시간 모드" 절을 앱 안 경로(`/world/index.html?api=/api/space&embed=1`, 메뉴 "오피스 월드")와 단독 실행(`?api=https://서버/api/space`) 둘로 나눠 쓴다. 다음 단계 1번(투영 API)을 완료로 표시.
- [ ] **Step 7: Commit** — `feat(space): 오피스 월드 투영 GET /api/space`

---

### Task 6: 메인 앱의 "오피스 월드" 화면과 브리지

**Files:**
- Create: `apps/content-office/frontend/lib/world-files.ts`
- Create: `apps/content-office/frontend/app/world/[[...path]]/route.ts`
- Create: `apps/content-office/frontend/lib/world-bridge.ts`
- Create: `apps/content-office/frontend/app/world-view.tsx`
- Modify: `apps/content-office/frontend/app/page.tsx:42-55` (`View`, `views`), `:340-360` (page-description), `:668-680` (activity 분기 뒤)
- Modify: `apps/content-office/frontend/app/icons.tsx` (`map` 아이콘 추가)
- Modify: `apps/content-office/frontend/app/globals.css` 끝 (`.world-frame` 높이 `calc(100vh - 220px)`, 최소 480px, 너비 100%, border-radius 12px)
- Test: `apps/content-office/frontend/tests/world-files.test.ts`, `tests/world-bridge.test.ts`

**Interfaces:**
- Consumes: 설계 12장 메시지 계약, Task 5 투영의 `view`·`actions`(런타임)
- Produces:
  ```ts
  // lib/world-files.ts
  export const WORLD_ROOT: string; // resolve(process.cwd(), "..", "..", "..", "sites", "office-world")
  export function resolveWorldFile(root: string, segments: string[] | undefined): { path: string; type: string } | null;
  // lib/world-bridge.ts
  export type WorldMessage = { type: "ready" } | { type: "open"; view: "news" | "studio" | "delivery" | "activity"; itemId: string } | { type: "action"; action: "draft" | "produce"; itemId: string };
  export function parseWorldMessage(data: unknown): WorldMessage | null;
  // app/world-view.tsx
  export function WorldView({ activeId, busy, onOpen, onAction }: { activeId: string; busy: boolean; onOpen: (view: View, itemId: string) => void; onAction: (action: "draft" | "produce", itemId: string) => Promise<void> }): JSX.Element
  ```

- [ ] **Step 1: 실패하는 테스트**

```ts
// tests/world-files.test.ts
import test from "node:test";
import assert from "node:assert/strict";
import { resolveWorldFile } from "../lib/world-files.ts";
const root = "/srv/world";
test("빈 경로는 index.html", () => assert.deepEqual(resolveWorldFile(root, undefined), { path: "/srv/world/index.html", type: "text/html; charset=utf-8" }));
test("확장자별 타입", () => {
  assert.equal(resolveWorldFile(root, ["styles.css"])?.type, "text/css; charset=utf-8");
  assert.equal(resolveWorldFile(root, ["app.js"])?.type, "text/javascript; charset=utf-8");
  assert.equal(resolveWorldFile(root, ["data", "space.json"])?.type, "application/json; charset=utf-8");
});
test("상위 경로·알 수 없는 확장자는 거부", () => {
  assert.equal(resolveWorldFile(root, ["..", "secret.md"]), null);
  assert.equal(resolveWorldFile(root, ["README.md"]), null);
});

// tests/world-bridge.test.ts
import { parseWorldMessage } from "../lib/world-bridge.ts";
test("유효한 메시지만 통과", () => {
  assert.deepEqual(parseWorldMessage({ source: "office-world", type: "open", view: "studio", itemId: "j1" }), { type: "open", view: "studio", itemId: "j1" });
  assert.deepEqual(parseWorldMessage({ source: "office-world", type: "action", action: "draft", itemId: "j1" }), { type: "action", action: "draft", itemId: "j1" });
  assert.equal(parseWorldMessage({ source: "other", type: "open" }), null);
  assert.equal(parseWorldMessage({ source: "office-world", type: "action", action: "approve", itemId: "j1" }), null);
  assert.equal(parseWorldMessage("x"), null);
});
```

- [ ] **Step 2: 실패 확인** — Run: `npm test` Expected: 모듈 없음
- [ ] **Step 3: `world-files.ts`·`world-bridge.ts` 구현** — `resolveWorldFile`: `path.posix.join`으로 합친 뒤 `normalize`한 결과가 root로 시작하지 않으면 null; 허용 확장자 `.html .css .js .json .png .svg .ico`만. `route.ts`: `export async function GET(_req, { params }) { const file = resolveWorldFile(WORLD_ROOT, (await params).path); if (!file) return new Response("Not found", { status: 404 }); return new Response(await readFile(file.path), { headers: { "Content-Type": file.type, "Cache-Control": "no-store" } }); }` (`export const dynamic = "force-dynamic"`).
- [ ] **Step 4: `WorldView` 구현** — `iframe` `src="/world/index.html?api=/api/space&embed=1"` `title="오피스 월드"` `className="world-frame"`. `useEffect`로 `message` 리스너: `event.origin !== window.location.origin`이면 무시, `parseWorldMessage(event.data)`가 null이면 무시. `ready` → 현재 `activeId`로 `focus` 전송. `open` → `onOpen(view, itemId)`. `action` → busy면 `{source:"content-office", type:"result", ok:false, message:"이미 처리 중입니다"}`를 iframe에 post, 아니면 `onAction` 후 `result ok:true, message:"요청했습니다"`와 `refresh` 전송(실패 시 `ok:false, message: 오류 문구`). `activeId`가 바뀌면 `focus` 전송. 모든 post는 `iframeRef.current?.contentWindow?.postMessage(msg, window.location.origin)`.
- [ ] **Step 5: `page.tsx` 연결** — `View`에 `"world"` 추가, `views`에 `{ id: "world", title: "오피스 월드", icon: "map", en: "OFFICE WORLD" }`를 `activity` 앞에 추가. page-description에 `"지금 진행 중인 모든 작업을 한 공간에서 보고, 바로 이동하거나 요청하세요."`. `view === "world"`일 때 `<WorldView activeId={activeId} busy={!!busy || !connected} onOpen={(v, id) => { if (id && dashboard?.jobs.some((j) => j.id === id)) setActiveId(id); setView(v); }} onAction={async (a, id) => { await action(a === "draft" ? "원고 생성" : "제작 시작", () => (a === "draft" ? api.draft(id) : api.produce(id)), a === "draft" ? "원고 생성 작업을 요청했습니다." : "제작을 요청했습니다."); }} />`. `action`이 오류를 삼키므로(상태로 표시) `onAction`은 `action` 뒤 `error` 상태가 비어 있지 않으면 throw해 `WorldView`가 `ok:false`를 보내게 한다 — 구현은 `action`이 반환값으로 성공 여부를 돌려주도록 `action`을 `Promise<boolean>`으로 바꾸는 쪽을 택한다(기존 호출부는 반환값을 무시하므로 영향 없음).
- [ ] **Step 6: 검사** — Run: `npm run typecheck && npm test` Expected: PASS. Run: `npm run dev` 상태에서 `curl -s -o /dev/null -w "%{http_code} %{content_type}\n" http://localhost:3110/world/app.js` Expected: `200 text/javascript; charset=utf-8` (dev 서버를 띄울 수 없으면 생략하고 보고에 적는다).
- [ ] **Step 7: Commit** — `feat(world): 메인 앱에 오피스 월드 화면과 postMessage 브리지`

---

### Task 7: 오피스 월드 embed 모드(actions·열기·focus)

**Files:**
- Modify: `sites/office-world/app.js` (`data.normalize` 100-140행, `hud.openStage` 1174-1195행, 초기화 1340행 부근)
- Modify: `sites/office-world/styles.css` 끝
- Modify: `sites/office-world/data/space.json` (`view`·`actions` 예시 추가)

**Interfaces:**
- Consumes: 설계 12장 메시지 계약, 투영의 `stages[].view`, `items[].view`, `items[].actions`
- Produces: `embed` 모듈 `{ enabled: boolean, init(), post(msg), onMessage(handler) }`

- [ ] **Step 1: `normalize` 확장** — stage에 `view: typeof s.view === "string" ? s.view : ""`, item에 `view: it.view || s.view || ""`, `actions: Array.isArray(it.actions) ? it.actions.filter(a => a && typeof a.id === "string" && typeof a.label === "string").map(a => ({ id: a.id, label: a.label })) : []`.
- [ ] **Step 2: `embed` 모듈** — `enabled = new URLSearchParams(location.search).get("embed") === "1" && window.parent !== window`. `post(msg)`는 `window.parent.postMessage({ source: "office-world", ...msg }, location.origin)`. `init()`은 `message` 리스너: `event.origin !== location.origin` 또는 `event.data?.source !== "content-office"`면 무시; `focus` → 그 `itemId`를 가진 stage를 찾아 `hud.openStage(stage.id)` 후 `.item[data-item-id]`에 `class="active"` 토글; `refresh` → `data.load(false)`; `result` → `$('panel-foot')`의 `.panel-result` 텍스트를 `message`로, `ok`면 `class="panel-result ok"`. 초기 데이터 적용 뒤 `post({ type: "ready" })`.
- [ ] **Step 3: `hud.openStage` 변경** — 각 item에 `data-item-id`, embed면 `actions`마다 `<button type="button" class="item-action" data-action="${id}" data-item="${itemId}">${label}</button>`과 `<button type="button" class="item-link" data-open="${view}" data-item="${itemId}">오피스에서 열기</button>`; embed가 아니면 지금처럼 stage.url 링크. 패널 하단 안내 문구는 embed면 "승인(⓪·①·②·③)은 오피스 화면에서 합니다. 여기서는 열기와 생성·제작 요청만 보냅니다."로. 클릭 위임: `data-action` → `embed.post({ type: "action", action, itemId })` 후 버튼 `disabled`(result 수신 시 복구); `data-open` → `embed.post({ type: "open", view, itemId })`.
- [ ] **Step 4: 스타일** — `.item.active` 왼쪽 테두리 강조, `.item-action` 작은 버튼, `.panel-result`·`.panel-result.ok` 색.
- [ ] **Step 5: 예시 데이터** — `space.json`의 각 stage에 `view`(inbox news · scripts studio · creative delivery · outbox delivery · ops activity), scripts의 `job-116`에 `"actions": [{"id":"draft","label":"원고 생성"}]`.
- [ ] **Step 6: 검사** — Run: `node --check sites/office-world/app.js` Expected: 출력 없음. Run: `grep -c "게시됨\|자동" sites/office-world/data/space.json` Expected: `0`.
- [ ] **Step 7: Commit** — `feat(world): embed 모드 — 열기·요청 버튼·앱 포커스 동기화`

---

### Task 8: 문서와 전체 검증

**Files:**
- Modify: `apps/content-office/README.md` ("## 이번 경계" v6 단락: curl 4줄 대신 화면 절차, "오피스 월드" 메뉴 소개)
- Modify: `docs/superpowers/plans/2026-10-27-ai-content-agent.md` Task 11 Step 3 체크(수동 확인은 EC2 앱이 뜬 뒤)

- [ ] **Step 1: README** — v6 절차를 "오늘의 뉴스 → 기획 직접 등록 → ⓪ 선택 → 작업실 패키지 확정 → 원고 생성 → 검수 패널의 게이트 → 운영 기록에서 Studio CSV 업로드·교훈 승인"으로. "오피스 월드" 메뉴 한 단락: 같은 출처 `/world/`, 열기·요청 버튼, 승인은 앱에서.
- [ ] **Step 2: 백엔드 전체** — Run: `cd apps/content-office/backend && python -m pytest -q` Expected: 기존 243 passed + 새 테스트(약 8개) 통과, `test_runtime` 2건은 worktree 환경 실패로 기록
- [ ] **Step 3: 프런트 전체** — Run: `npm run typecheck && npm test` Expected: PASS. Run: `node --check sites/office-world/app.js`
- [ ] **Step 4: Commit** — `docs: v6 화면 절차와 오피스 월드 연동 안내`

## Self-Review

- 설계 대조: v6 설계 3장 2·3(기획 은행 → Task 2), 4(패키지 → Task 3), 13(측정·교훈 → Task 4). 오피스 월드 6장(투영 → Task 5), 12장(같은 출처 제공·메시지 계약·actions → Task 5·6·7). 승인은 앱에서만(Global Constraints, Task 7 문구).
- 이름 일관성: `parse_studio_text`·`project_space`·`resolveWorldFile`·`parseWorldMessage`·`WorldView`·`PackagingPanel`·`PerformancePanel`·`IdeaIntake`가 Interfaces와 Step에서 같은 서명.
- 병렬 안전: `page.tsx` 삽입 구간이 세 Task에서 겹치지 않음(44행·1000행·2150행·668행). `api.py`는 Task 4가 `add_snapshot` 뒤, Task 5가 `dashboard` 뒤.
- 자리표시: TBD 없음. `knowledge_summary` 키만 구현 시 확인하도록 명시.

## Execution Handoff

실행 방식은 사용자가 이미 정했다: Subagent-Driven(서브 에이전트 병렬). REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Task 1 → (Task 2·3·4·5·6·7 병렬, 각자 worktree) → Task 8.
