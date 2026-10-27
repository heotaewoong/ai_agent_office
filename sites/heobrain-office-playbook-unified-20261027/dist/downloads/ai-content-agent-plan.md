# HeoBrain AI 콘텐츠 자동화 에이전트 v6 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 콘텐츠 오피스에 기획 은행·⓪ 기획 선택·패키지 카드·브랜드 번들·품질/정책 게이트·포맷 분기·성과 교훈 루프를 붙여 "편집 통제실"을 만든다.

**Architecture:** 새 기능은 `office/` 아래 작은 순수 모듈(ideas·packaging·brand·gates·formats·analytics)로 두고, 상태는 기존 SQLite `Store`에 테이블 3개(ideas·snapshots·lessons)와 `job.packaging`·`quality.gates` 필드로 저장한다. 원고 생성(`editorial.prepare_source`)은 패키지 확인·브랜드 주입·게이트 기록만 추가하고, FastAPI에 좁은 엔드포인트 8개를 연다. 외부 API 호출은 늘리지 않는다(성과는 Studio CSV·수동 입력부터).

**Tech Stack:** Python 3.12, FastAPI, SQLite, pytest, Next.js 16 / React 19 / TypeScript.

**Spec:** `docs/superpowers/specs/2026-10-27-ai-content-agent-design.md` (근거: `reports/AI 콘텐츠 자동화 에이전트 벤치마킹.md`)

## Global Constraints

- 승인 ① 원고 · ② 출고 · ③ 회차(뉴스레터·홍보 발송)의 기존 의미를 바꾸지 않는다. 새 사람 결정은 ⓪ 기획 선택과 교훈 승인뿐이다.
- 패키지 요구는 `article.origin == "idea"` 작업에만 적용한다. 기존 RSS 작업 흐름과 기존 테스트 결과는 그대로다.
- 새 Python·npm 의존성 0개, 새 외부 API 호출 0개.
- 게이트 임계값(템플릿 유사도 0.5, 제목 45자, 썸네일 글자 12자, 훅 120자, 쇼츠 180초·훅 3초)은 첫 값이며 상수로 둔다.
- 교훈은 `approved` 상태만 점수 가중치에 반영한다. 에이전트는 승인을 만들거나 승인받았다고 주장하지 않는다(기존 BASE 원칙).
- Gemini TTS 단가: `speech_provider.PRICE_VALID_UNTIL`을 2027-01-01 이후로 갱신할 때 `tts_audio_usd_million`을 18.0으로 바꾼다(현재 9.0).
- 이번 계획에서 제외: 생성 영상, 쇼츠 클리핑, YouTube 자동 업로드, 네이버 자동 발행, beehiiv·Postiz 연동, 다른 계열 평가 모델 어댑터.

## Review Focus

- 막힌 기획(1차 출처 없음·YMYL 실존 인물 AI 페르소나·템플릿 반복 표시)은 API로도 선택되지 않는다(Task 2/9).
- 기획 작업은 패키지 없이 원고 생성 단계에 들어가지 못하고, RSS 작업은 영향받지 않는다(Task 3/6).
- 제목·설명·태그의 숫자가 근거·본문에 없으면 원고 품질이 blocked가 된다(Task 5/6).
- 같은 측정 구간 스냅샷은 덮어쓰고, 교훈은 승인 전 점수에 영향을 주지 않는다(Task 2/8).
- 새 변경 엔드포인트도 Origin·CSRF 검사를 통과해야만 동작한다(Task 9).

## File Structure

| 파일 | 책임 |
|---|---|
| `office/ideas.py` | 아웃라이어 구간·점수·차단 사유·정렬 (순수 함수) |
| `office/store.py` | ideas·snapshots·lessons 테이블과 메서드 |
| `office/packaging.py` | 패키지 카드 검증·확정·원고 전 요구 |
| `office/brand.py` + `config/brand/` | 목소리·표기·금지 주장·발음 사전 로드와 프롬프트 주입 |
| `office/gates.py` | 메타데이터 숫자·반복 유사도·YMYL·금지 주장·AI 공개 판단 |
| `office/editorial.py` | 위 셋을 원고 생성에 연결 |
| `office/formats.py` | 승인 해시에서만 포맷 분기, 쇼츠·롱폼 규칙 |
| `office/analytics.py` | Studio CSV 파싱, 기준선, 교훈 후보 |
| `office/api.py` | 엔드포인트 8개 |
| `frontend/lib/*`, `frontend/app/*` | 기획 은행 패널 |

---

### Task 1: 기획 은행 점수

**Files:**
- Create: `apps/content-office/backend/office/ideas.py`
- Test: `apps/content-office/backend/tests/test_ideas.py`

**Interfaces:**
- Consumes: 없음
- Produces: `outlier_ratio(views, channel_avg_views) -> float | None`, `outlier_band(ratio) -> str`, `score_idea(card: dict, weights=None, lessons=()) -> dict`(score·outlier_band·parts·reasons·blocked 추가), `rank_ideas(cards, weights=None, lessons=()) -> list[dict]`, `WEIGHTS`, `BLOCKING_FLAGS`

- [ ] **Step 1: 실패하는 테스트 작성** (`tests/test_ideas.py`)

```python
import pytest
from office.ideas import outlier_band, outlier_ratio, rank_ideas, score_idea
from office.store import Store, WorkflowError


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


def test_outlier_bands_follow_channel_average():
    assert outlier_band(outlier_ratio(12000, 1000)) == "10x+"
    assert outlier_band(outlier_ratio(3000, 1000)) == "2-5x"
    assert outlier_band(outlier_ratio(None, 1000)) == "unknown"


def test_idea_without_primary_source_is_blocked_and_sinks():
    good = {"title": "A", "views": 9000, "channel_avg_views": 1000, "demand": 60, "primary_sources": 2, "fit": 0.8}
    weak = {**good, "title": "B", "primary_sources": 0}
    ranked = rank_ideas([weak, good])
    assert ranked[0]["title"] == "A"
    assert ranked[1]["blocked"] == ["1차 출처 없음"]
    assert ranked[1]["score"] == 0.0


def test_ymyl_ai_persona_flag_blocks():
    assert score_idea({"title": "C", "primary_sources": 3, "policy_flags": ["ai_persona_real_person_ymyl"]})["blocked"]


def test_only_approved_lessons_change_weights():
    card = {"title": "D", "demand": 100, "primary_sources": 3, "fit": 1}
    base = score_idea(card)["score"]
    proposed = {"state": "proposed", "weight_change": {"factor": "demand", "delta": 30}}
    assert score_idea(card, lessons=[proposed])["score"] == base
    assert score_idea(card, lessons=[{**proposed, "state": "approved"}])["score"] > base
```

- [ ] **Step 2: 실패 확인**

Run: `cd apps/content-office/backend && .venv/bin/python -m pytest -q tests/test_ideas.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'office.ideas'`

- [ ] **Step 3: 최소 구현**

```python
"""기획 은행: 신호를 점수화해 사람이 고를 후보를 정렬한다. 점수는 판단 보조이며 성과 예측이 아니다.

demand는 요청마다 최대값을 100으로 맞춘 상대값(네이버 데이터랩 등)이므로 같은 요청 안에서만 비교한다.
"""
from __future__ import annotations

WEIGHTS = {"outlier": 30, "demand": 20, "evidence": 20, "fit": 20, "novelty": 10}
BAND_POINTS = {"10x+": 1.0, "5-10x": 0.8, "2-5x": 0.55, "under-2x": 0.2, "unknown": 0.0}
BLOCKING_FLAGS = {
    "ai_persona_real_person_ymyl": "실존 인물 AI 페르소나의 금융·법률·건강 발언(YouTube 2026-07 수익화 제외 유형)",
    "templated_series": "같은 템플릿 반복 위험(YouTube 비진정성 콘텐츠)",
    "no_primary_source": "1차 출처 없음",
}


def outlier_ratio(views, channel_avg_views):
    if not views or not channel_avg_views or channel_avg_views <= 0:
        return None
    return views / channel_avg_views


def outlier_band(ratio):
    if ratio is None:
        return "unknown"
    if ratio >= 10:
        return "10x+"
    if ratio >= 5:
        return "5-10x"
    if ratio >= 2:
        return "2-5x"
    return "under-2x"


def effective_weights(weights=None, lessons=()):
    result = dict(weights or WEIGHTS)
    for lesson in lessons:
        change = lesson.get("weight_change") or {}
        if lesson.get("state") == "approved" and change.get("factor") in result:
            result[change["factor"]] = max(0, result[change["factor"]] + int(change.get("delta", 0)))
    return result


def score_idea(card, weights=None, lessons=()):
    w = effective_weights(weights, lessons)
    band = outlier_band(outlier_ratio(card.get("views"), card.get("channel_avg_views")))
    sources = int(card.get("primary_sources", 0))
    parts = {
        "outlier": BAND_POINTS[band],
        "demand": min(max(float(card.get("demand", 0)), 0.0), 100.0) / 100,
        "evidence": min(sources, 3) / 3,
        "fit": min(max(float(card.get("fit", 0)), 0.0), 1.0),
        "novelty": 0.0 if card.get("covered_before") else 1.0,
    }
    score = round(100 * sum(w[k] * parts[k] for k in parts) / (sum(w.values()) or 1), 1)
    flags = [f for f in card.get("policy_flags", []) if f in BLOCKING_FLAGS] + ([] if sources else ["no_primary_source"])
    blocked = [BLOCKING_FLAGS[f] for f in dict.fromkeys(flags)]
    reasons = [f"이상치 {band}", f"수요 {card.get('demand', 0)}(상대값)", f"1차 출처 {sources}개"]
    return {**card, "score": 0.0 if blocked else score, "outlier_band": band, "parts": parts, "reasons": reasons, "blocked": blocked}


def rank_ideas(cards, weights=None, lessons=()):
    scored = [score_idea(card, weights, lessons) for card in cards]
    return sorted(scored, key=lambda c: (not c["blocked"], c["score"]), reverse=True)
```

- [ ] **Step 4: 통과 확인**

Run: `cd apps/content-office/backend && .venv/bin/python -m pytest -q tests/test_ideas.py`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
cd "$(git rev-parse --show-toplevel)"
git add apps/content-office/backend/office/ideas.py apps/content-office/backend/tests/test_ideas.py
git commit -m "feat(agent): 기획 은행 점수와 차단 사유"
```

### Task 2: 장부 확장: 기획·성과 스냅샷·교훈

**Files:**
- Modify: `apps/content-office/backend/office/store.py` (`Store.__init__`의 `executescript`, `_budget` 바로 앞에 메서드 추가)
- Test: `apps/content-office/backend/tests/test_ideas.py` (아래 테스트를 파일 끝에 추가)

**Interfaces:**
- Consumes: Task 1 `score_idea`
- Produces: `Store.save_idea(card) -> dict`, `Store.ideas(state=None) -> list`, `Store.select_idea(idea_id, actor) -> dict`, `Store.save_snapshot(channel, external_id, period, metrics, job_id=None) -> dict`, `Store.snapshots(channel=None) -> list`, `Store.add_lesson(lesson) -> dict`, `Store.review_lesson(lesson_id, decision, actor) -> dict`, `Store.lessons(state=None) -> list`

- [ ] **Step 1: 실패하는 테스트 작성** (`tests/test_ideas.py`)

```python
def test_duplicate_idea_is_stored_once(store):
    first = store.save_idea({"title": "Claude 에이전트 팀 실전", "source_url": "https://example.com/a"})
    again = store.save_idea({"title": "  claude 에이전트 팀   실전 ", "source_url": "https://example.com/a"})
    assert first["id"] == again["id"]
    assert len(store.ideas()) == 1


def test_blocked_idea_cannot_be_selected(store):
    idea = store.save_idea(score_idea({"title": "근거 없는 주제", "primary_sources": 0}))
    with pytest.raises(WorkflowError, match="막힌 기획"):
        store.select_idea(idea["id"], "local-operator")


def test_selected_idea_records_actor(store):
    idea = store.save_idea(score_idea({"title": "근거 있는 주제", "primary_sources": 2}))
    selected = store.select_idea(idea["id"], "local-operator")
    assert selected["state"] == "selected" and selected["selected_by"] == "local-operator"
    assert store.ideas("selected")[0]["id"] == idea["id"]
```

- [ ] **Step 2: 실패 확인**

Run: `cd apps/content-office/backend && .venv/bin/python -m pytest -q tests/test_ideas.py tests/test_workflow.py`
Expected: FAIL — `AttributeError: 'Store' object has no attribute 'save_idea'`

- [ ] **Step 3: 최소 구현**

`executescript`의 `drafts` 테이블 줄 바로 아래에 추가:

```python
                CREATE TABLE IF NOT EXISTS ideas(id TEXT PRIMARY KEY, dedup_key TEXT UNIQUE NOT NULL, state TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS snapshots(id TEXT PRIMARY KEY, channel TEXT NOT NULL, external_id TEXT NOT NULL, period TEXT NOT NULL, job_id TEXT, data TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(channel, external_id, period));
                CREATE TABLE IF NOT EXISTS lessons(id TEXT PRIMARY KEY, state TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
```

`@staticmethod def _budget(db):` 바로 앞에 추가:

```python
    # --- 기획 선택⓪ · 성과 스냅샷 · 교훈 (AI 콘텐츠 에이전트 v6)
    @staticmethod
    def _idea_key(card):
        title = " ".join(str(card.get("title", "")).lower().split())
        return digest({"title": title, "source_url": card.get("source_url", "")})

    def save_idea(self, card):
        if not str(card.get("title", "")).strip():
            raise WorkflowError("기획 제목이 필요합니다")
        key = self._idea_key(card)
        with self.connection(transaction=True) as db:
            row = db.execute("SELECT data FROM ideas WHERE dedup_key=?", (key,)).fetchone()
            if row:
                return json.loads(row[0])
            idea = {**card, "id": identifier("idea"), "state": "candidate"}
            db.execute("INSERT INTO ideas VALUES(?,?,?,?,?,?)", (idea["id"], key, "candidate", canonical(idea), now(), now()))
            self._event(db, "idea_saved", {"idea_id": idea["id"], "title": idea["title"]})
            return idea

    def ideas(self, state=None):
        with self.connection() as db:
            rows = db.execute("SELECT data FROM ideas WHERE (? IS NULL OR state=?) ORDER BY created_at", (state, state)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def select_idea(self, idea_id, actor):
        with self.connection(transaction=True) as db:
            row = db.execute("SELECT data FROM ideas WHERE id=?", (idea_id,)).fetchone()
            if not row:
                raise WorkflowError("기획을 찾을 수 없습니다")
            idea = json.loads(row[0])
            if idea.get("blocked"):
                raise WorkflowError("정책·근거 검사에서 막힌 기획은 선택할 수 없습니다")
            idea.update(state="selected", selected_by=actor, selected_at=now())
            db.execute("UPDATE ideas SET state='selected', data=?, updated_at=? WHERE id=?", (canonical(idea), now(), idea_id))
            self._event(db, "idea_selected", {"idea_id": idea_id, "actor": actor})
            return idea

    @staticmethod
    def _snapshot(row):
        return {"id": row["id"], "channel": row["channel"], "external_id": row["external_id"], "period": row["period"], "job_id": row["job_id"], "metrics": json.loads(row["data"])}

    def save_snapshot(self, channel, external_id, period, metrics, job_id=None):
        if period not in ("24h", "7d", "28d"):
            raise WorkflowError("성과 측정 구간은 24h·7d·28d 중 하나입니다")
        with self.connection(transaction=True) as db:
            db.execute("INSERT INTO snapshots VALUES(?,?,?,?,?,?,?) ON CONFLICT(channel, external_id, period) DO UPDATE SET data=excluded.data, job_id=excluded.job_id, created_at=excluded.created_at",
                       (identifier("snap"), channel, external_id, period, job_id, canonical(metrics), now()))
            row = db.execute("SELECT * FROM snapshots WHERE channel=? AND external_id=? AND period=?", (channel, external_id, period)).fetchone()
            return self._snapshot(row)

    def snapshots(self, channel=None):
        with self.connection() as db:
            rows = db.execute("SELECT * FROM snapshots WHERE (? IS NULL OR channel=?) ORDER BY created_at", (channel, channel)).fetchall()
        return [self._snapshot(r) for r in rows]

    def add_lesson(self, lesson):
        record = {**lesson, "id": identifier("lesson"), "state": "proposed"}
        with self.connection(transaction=True) as db:
            db.execute("INSERT INTO lessons VALUES(?,?,?,?,?)", (record["id"], "proposed", canonical(record), now(), now()))
            self._event(db, "lesson_proposed", {"lesson_id": record["id"], "kind": record.get("kind")})
        return record

    def review_lesson(self, lesson_id, decision, actor):
        if decision not in ("approved", "rejected"):
            raise WorkflowError("교훈 검토는 approved 또는 rejected입니다")
        with self.connection(transaction=True) as db:
            row = db.execute("SELECT data FROM lessons WHERE id=?", (lesson_id,)).fetchone()
            if not row:
                raise WorkflowError("교훈을 찾을 수 없습니다")
            record = {**json.loads(row[0]), "state": decision, "reviewed_by": actor, "reviewed_at": now()}
            db.execute("UPDATE lessons SET state=?, data=?, updated_at=? WHERE id=?", (decision, canonical(record), now(), lesson_id))
            self._event(db, "lesson_reviewed", {"lesson_id": lesson_id, "decision": decision, "actor": actor})
            return record

    def lessons(self, state=None):
        with self.connection() as db:
            rows = db.execute("SELECT data FROM lessons WHERE (? IS NULL OR state=?) ORDER BY created_at", (state, state)).fetchall()
        return [json.loads(r[0]) for r in rows]
```

- [ ] **Step 4: 통과 확인**

Run: `cd apps/content-office/backend && .venv/bin/python -m pytest -q tests/test_ideas.py tests/test_workflow.py`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
cd "$(git rev-parse --show-toplevel)"
git add apps/content-office/backend/office/store.py apps/content-office/backend/tests/test_ideas.py
git commit -m "feat(agent): 기획·스냅샷·교훈 장부"
```

### Task 3: 패키지 카드 게이트(G0)

**Files:**
- Create: `apps/content-office/backend/office/packaging.py`
- Test: `apps/content-office/backend/tests/test_packaging.py`

**Interfaces:**
- Consumes: `Store.update_job`, `Store.event`, `office.store.digest`
- Produces: `PACKAGING_SCHEMA`, `validate_packaging(brief) -> {"passed": bool, "issues": list[str]}`, `attach_packaging(store, job_id, brief, actor) -> dict`, `require_packaging(job) -> None`(기획 작업에 패키지가 없으면 `WorkflowError`)

- [ ] **Step 1: 실패하는 테스트 작성** (`tests/test_packaging.py`)

```python
import pytest
from office.packaging import attach_packaging, require_packaging, validate_packaging
from office.store import Store, WorkflowError


def brief(**changes):
    base = {
        "titles": ["Claude 팀으로 블로그 자동화", "AI 팀이 블로그를 쓰는 법", "블로그 자동화 3단계"],
        "thumbnails": [{"text": "AI 팀 블로그", "visual": "작업 화면"}, {"text": "3단계", "visual": "표"}, {"text": "직접 해봄", "visual": "결과 화면"}],
        "hook": "블로그 자동화를 Claude 팀으로 나눠 맡긴 결과부터 보여 드립니다",
        "logline": "한 명이 에이전트 팀으로 블로그 한 편을 끝내는 과정",
        "reasons": ["검색 수요가 있음", "실제 작업 화면으로 증명 가능"],
    }
    return {**base, **changes}


def test_complete_packaging_passes():
    assert validate_packaging(brief()) == {"passed": True, "issues": []}


def test_hook_must_carry_title_promise():
    report = validate_packaging(brief(hook="오늘은 날씨 이야기를 합니다"))
    assert "훅이 제목의 약속을 이어받지 않습니다" in report["issues"]


def test_thumbnail_text_limit():
    long = brief(thumbnails=[{"text": "아주아주아주긴썸네일문구입니다", "visual": "x"}] * 3)
    assert any("썸네일 1안" in issue for issue in validate_packaging(long)["issues"])


def test_idea_job_requires_packaging_before_drafting(tmp_path):
    store = Store(tmp_path)
    job = store.create_job({"id": "idea-1", "title": "기획", "url": "https://example.com", "origin": "idea"})
    with pytest.raises(WorkflowError, match="패키징"):
        require_packaging(store.job(job["id"]))
    attach_packaging(store, job["id"], brief(), "local-operator")
    require_packaging(store.job(job["id"]))


def test_rss_job_keeps_existing_flow(tmp_path):
    store = Store(tmp_path)
    job = store.create_job({"id": "rss-1", "title": "뉴스", "url": "https://example.com"})
    require_packaging(store.job(job["id"]))
```

- [ ] **Step 2: 실패 확인**

Run: `cd apps/content-office/backend && .venv/bin/python -m pytest -q tests/test_packaging.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'office.packaging'`

- [ ] **Step 3: 최소 구현**

```python
"""패키징 우선: 대본 전에 제목 3안·썸네일 3안·훅·로그라인을 정한다.

근거: Ali Abdaal '제목·썸네일·훅을 모르면 대본을 쓰지 않는다', Paddy Galloway 한 장 기획,
YouTube Test & Compare(제목·썸네일 최대 3안, 시청 시간 기준 승자).
"""
from __future__ import annotations

import re

from .store import WorkflowError, digest

TITLE_MAX = 45       # 내부 기준: 모바일 목록에서 잘리지 않게(공식 상한 100자)
THUMB_TEXT_MAX = 12  # 실제 한글 폰트 레이어로 얹는 글자 수
HOOK_MAX = 120
PACKAGING_SCHEMA = {
    "type": "object",
    "properties": {
        "titles": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "string"}},
        "thumbnails": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "object", "properties": {"text": {"type": "string"}, "visual": {"type": "string"}}, "required": ["text", "visual"], "additionalProperties": False}},
        "hook": {"type": "string"},
        "logline": {"type": "string"},
        "reasons": {"type": "array", "minItems": 2, "maxItems": 3, "items": {"type": "string"}},
    },
    "required": ["titles", "thumbnails", "hook", "logline", "reasons"],
    "additionalProperties": False,
}


def _tokens(text):
    return set(re.findall(r"[0-9a-z가-힣]{2,}", text.lower()))


def validate_packaging(brief):
    issues = []
    titles, thumbs = brief.get("titles", []), brief.get("thumbnails", [])
    if len(titles) != 3:
        issues.append("제목은 비교용 3안이 필요합니다")
    issues += [f"제목 {i + 1}안이 {TITLE_MAX}자를 넘습니다" for i, t in enumerate(titles) if len(t) > TITLE_MAX]
    if len(thumbs) != 3:
        issues.append("썸네일은 비교용 3안이 필요합니다")
    issues += [f"썸네일 {i + 1}안 글자가 {THUMB_TEXT_MAX}자를 넘습니다" for i, t in enumerate(thumbs) if len(t.get("text", "")) > THUMB_TEXT_MAX]
    hook = brief.get("hook", "").strip()
    if not 0 < len(hook) <= HOOK_MAX:
        issues.append(f"훅은 1~{HOOK_MAX}자로 씁니다")
    if not brief.get("logline", "").strip():
        issues.append("로그라인이 없습니다")
    if not 2 <= len(brief.get("reasons", [])) <= 3:
        issues.append("통할 이유는 2~3개입니다")
    chosen = brief.get("chosen_title") or (titles[0] if titles else "")
    if chosen and hook and not _tokens(chosen) & _tokens(hook):
        issues.append("훅이 제목의 약속을 이어받지 않습니다")
    return {"passed": not issues, "issues": issues}


def attach_packaging(store, job_id, brief, actor):
    report = validate_packaging(brief)
    if not report["passed"]:
        raise WorkflowError("패키징 보완 필요: " + " / ".join(report["issues"]))
    record = {**brief, "packaging_hash": digest(brief), "selected_by": actor}
    store.update_job(job_id, packaging=record)
    store.event("packaging_selected", {"packaging_hash": record["packaging_hash"], "actor": actor}, job_id)
    return record


def require_packaging(job):
    if job["article"].get("origin") == "idea" and not job.get("packaging"):
        raise WorkflowError("기획에서 시작한 작업은 패키징(제목·썸네일·훅)을 먼저 정해야 합니다")
```

- [ ] **Step 4: 통과 확인**

Run: `cd apps/content-office/backend && .venv/bin/python -m pytest -q tests/test_packaging.py`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
cd "$(git rev-parse --show-toplevel)"
git add apps/content-office/backend/office/packaging.py apps/content-office/backend/tests/test_packaging.py
git commit -m "feat(agent): 원고 전 패키지 카드 게이트"
```

### Task 4: 브랜드 번들

**Files:**
- Create: `apps/content-office/backend/office/brand.py`
- Create: `apps/content-office/backend/config/brand/voice.md`, `glossary.json`, `banned_claims.json`
- Test: `apps/content-office/backend/tests/test_brand.py`

**Interfaces:**
- Consumes: `office.store.digest`
- Produces: `DEFAULT_DIR`, `load_brand(directory=DEFAULT_DIR) -> {"voice","terms","pronunciation","banned","hash"}`, `brand_system_prompt(base, brand) -> str`, `banned_claim_hits(text, brand) -> list[str]`, `tts_text(text, brand) -> str`

- [ ] **Step 1: 실패하는 테스트 작성** (`tests/test_brand.py`)

```python
import json
from office.brand import banned_claim_hits, brand_system_prompt, load_brand, tts_text


def write_brand(folder, voice="친절하고 구체적으로 설명한다"):
    folder.mkdir(exist_ok=True)
    (folder / "voice.md").write_text(voice, encoding="utf-8")
    (folder / "glossary.json").write_text(json.dumps({"terms": {"클로드": "Claude"}, "pronunciation": {"API": "에이피아이"}}), encoding="utf-8")
    (folder / "banned_claims.json").write_text(json.dumps(["수익 보장"]), encoding="utf-8")
    return load_brand(folder)


def test_empty_brand_keeps_base_prompt(tmp_path):
    assert brand_system_prompt("BASE", load_brand(tmp_path / "none")) == "BASE"


def test_voice_change_changes_prompt_and_hash(tmp_path):
    one = write_brand(tmp_path / "a")
    two = write_brand(tmp_path / "b", voice="짧고 단호하게 말한다")
    assert one["hash"] != two["hash"]
    assert brand_system_prompt("BASE", one) != brand_system_prompt("BASE", two)


def test_banned_claims_and_pronunciation(tmp_path):
    brand = write_brand(tmp_path / "c")
    assert banned_claim_hits("이 방법은 수익 보장!", brand) == ["수익 보장"]
    assert tts_text("API와 APIs", brand) == "에이피아이와 APIs"
```

- [ ] **Step 2: 실패 확인**

Run: `cd apps/content-office/backend && .venv/bin/python -m pytest -q tests/test_brand.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'office.brand'`

- [ ] **Step 3: 최소 구현**

```python
"""브랜드 두뇌: 모든 생성 단계가 같은 목소리·표기·금지 주장·발음 사전을 불러온다(Jasper IQ·WRITER Voice Profile 패턴)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .store import digest

DEFAULT_DIR = Path(__file__).resolve().parents[1] / "config" / "brand"


def _json(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def load_brand(directory=DEFAULT_DIR):
    directory = Path(directory)
    voice_path = directory / "voice.md"
    glossary = _json(directory / "glossary.json", {})
    brand = {
        "voice": voice_path.read_text(encoding="utf-8").strip() if voice_path.is_file() else "",
        "terms": glossary.get("terms", {}),
        "pronunciation": glossary.get("pronunciation", {}),
        "banned": _json(directory / "banned_claims.json", []),
    }
    return {**brand, "hash": digest(brand)}


def brand_system_prompt(base, brand):
    if not (brand["voice"] or brand["terms"] or brand["banned"]):
        return base
    terms = "\n".join(f"- {written}: {fixed}" for written, fixed in brand["terms"].items())
    banned = "\n".join(f"- {claim}" for claim in brand["banned"])
    return f"{base}\n\n[브랜드 목소리 {brand['hash'][:12]}]\n{brand['voice']}\n\n[표기 고정]\n{terms}\n\n[쓰지 않는 주장]\n{banned}"


def banned_claim_hits(text, brand):
    return [claim for claim in brand["banned"] if re.search(re.escape(claim), text or "", flags=re.IGNORECASE)]


def tts_text(text, brand):
    for written, spoken in sorted(brand["pronunciation"].items(), key=lambda kv: -len(kv[0])):
        text = re.sub(rf"(?<![0-9A-Za-z]){re.escape(written)}(?![0-9A-Za-z])", spoken, text)
    return text
```

브랜드 번들 초기 파일(내용은 운영자가 계속 고친다):

`apps/content-office/backend/config/brand/voice.md`
```markdown
한국어 AI 입문·실무 독자에게 답을 먼저 쓰고 근거를 붙인다.
완결된 사례의 입력·판단·다음 행동을 보여 준다.
회사 발표·저자 실험·우리 제안을 구분하고, 한계는 필요한 위치에 짧게 남긴다.
자극적 단정·가짜 경험·매출 보장은 쓰지 않는다.
```

`apps/content-office/backend/config/brand/glossary.json`
```json
{"terms": {"클로드": "Claude", "클로드 코드": "Claude Code", "헤르메스": "Hermes"},
 "pronunciation": {"API": "에이피아이", "LLM": "엘엘엠", "MCP": "엠씨피"}}
```

`apps/content-office/backend/config/brand/banned_claims.json`
```json
["수익 보장", "무조건 상위노출", "누구나 월 천만 원"]
```


> 번들 파일이 생기면 생성 system 프롬프트가 바뀌어 모델 캐시 키도 바뀐다(`providers.cache_key`가 실제 메시지를 포함). 의도된 동작이다.

- [ ] **Step 4: 통과 확인**

Run: `cd apps/content-office/backend && .venv/bin/python -m pytest -q tests/test_brand.py`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
cd "$(git rev-parse --show-toplevel)"
git add apps/content-office/backend/office/brand.py apps/content-office/backend/config/brand apps/content-office/backend/tests/test_brand.py
git commit -m "feat(agent): 모든 생성이 물려받는 브랜드 번들"
```

### Task 5: 품질·정책 게이트

**Files:**
- Create: `apps/content-office/backend/office/gates.py`
- Test: `apps/content-office/backend/tests/test_gates.py`

**Interfaces:**
- Consumes: Task 4 `banned_claim_hits`
- Produces: `metadata_fact_check(packet) -> list[item]`, `similarity(a, b) -> float`, `inauthentic_risk(packet, previous_packets, threshold=0.5) -> list[item]`, `disclosure_decision(assets) -> {"youtube_altered_content": bool, "reasons": list}`, `ymyl_persona(packet, assets) -> list[item]`, `run_gates(packet, previous_packets=(), assets=(), brand=None) -> {"status": "pass"|"warn"|"block", "items": list, "disclosure": dict}`. item = `{"level": "warn"|"block", "rule": str, "message": str}`

- [ ] **Step 1: 실패하는 테스트 작성** (`tests/test_gates.py`)

```python
from office.gates import disclosure_decision, run_gates


def packet(title="AI 도구 비교", body="세 가지 도구를 비교한다", narration="에이전트 팀이 원고를 나눠 쓰고 검수까지 마치는 과정을 보여 준다"):
    return {"title": title, "body": body, "evidence": [{"claim": "공식 발표에 따르면 사용자는 120만 명", "numbers": ["120만"]}],
            "video": {"title": "사용자 120만 명", "description": "", "tags": [], "scenes": [{"narration": narration}]}}


def test_metadata_number_without_evidence_blocks():
    report = run_gates(packet(title="AI 도구 7가지"))
    assert report["status"] == "block"
    assert any("숫자 7" in item["message"] for item in report["items"])


def test_metadata_number_only_in_body_warns():
    report = run_gates(packet(title="AI 도구 3가지", body="도구 3가지를 비교한다"))
    assert report["status"] == "warn"


def test_repeated_template_blocks_as_inauthentic():
    previous = [packet()]
    assert [i["rule"] for i in run_gates(packet(), previous)["items"]] == ["inauthentic_template"]
    assert run_gates(packet(narration="완전히 다른 주제로 직접 촬영한 화면을 설명한다"), previous)["status"] == "pass"


def test_disclosure_only_for_realistic_synthetic_assets():
    assert disclosure_decision([{"kind": "stylized_broll"}, {"kind": "own_voice_clone"}])["youtube_altered_content"] is False
    assert disclosure_decision([{"kind": "realistic_person", "label": "가상 인물 인터뷰"}])["reasons"] == ["가상 인물 인터뷰"]


def test_ymyl_persona_and_banned_claim_block():
    p = {**packet(), "topic": "finance"}
    assert run_gates(p, assets=[{"kind": "ai_persona_real_person"}])["status"] == "block"
    brand = {"banned": ["수익 보장"], "voice": "", "terms": {}, "pronunciation": {}}
    assert run_gates(packet(body="이 방법은 수익 보장"), brand=brand)["status"] == "block"
```

- [ ] **Step 2: 실패 확인**

Run: `cd apps/content-office/backend && .venv/bin/python -m pytest -q tests/test_gates.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'office.gates'`

- [ ] **Step 3: 최소 구현**

```python
"""출고 전 품질·정책 게이트. 재현 가능한 규칙으로 막고, 애매하면 경고로 사람에게 넘긴다.

근거: Google '제목·메타 설명·대체 텍스트까지 사실 확인', YouTube 비진정성 콘텐츠(2025-07-15)와
2026-07-16 수익화 제외 유형, 사실적 합성 콘텐츠 고지 규정.
"""
from __future__ import annotations

import re

from .brand import banned_claim_hits

NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
REALISTIC_KINDS = {"realistic_person", "realistic_event", "realistic_place", "voice_clone_other"}
YMYL_TOPICS = {"finance", "law", "health"}


def _numbers(text):
    return set(NUMBER.findall(text or ""))


def narration(packet):
    return " ".join(scene.get("narration", "") for scene in packet.get("video", {}).get("scenes", []))


def metadata_fact_check(packet):
    evidence = _numbers(" ".join(e.get("claim", "") + " " + " ".join(e.get("numbers", [])) for e in packet.get("evidence", [])))
    body = _numbers(packet.get("body", ""))
    video = packet.get("video", {})
    fields = {"블로그 제목": packet.get("title", ""), "영상 제목": video.get("title", ""), "영상 설명": video.get("description", ""), "태그": " ".join(video.get("tags", []))}
    items = []
    for name, text in fields.items():
        for number in sorted(_numbers(text) - evidence):
            level = "warn" if number in body else "block"
            items.append({"level": level, "rule": "metadata_numbers", "message": f"{name}의 숫자 {number}: {'본문에만 있음' if level == 'warn' else '근거·본문에 없음'}"})
    return items


def _shingles(text, n=3):
    words = re.findall(r"[0-9a-z가-힣]+", (text or "").lower())
    return {tuple(words[i:i + n]) for i in range(max(0, len(words) - n + 1))}


def similarity(a, b):
    sa, sb = _shingles(a), _shingles(b)
    return len(sa & sb) / len(sa | sb) if sa and sb else 0.0


def inauthentic_risk(packet, previous_packets, threshold=0.5):
    current = narration(packet)
    worst = max((similarity(current, narration(p)) for p in previous_packets), default=0.0)
    if worst >= threshold:
        return [{"level": "block", "rule": "inauthentic_template", "message": f"이전 영상과 대본 유사도 {worst:.2f}: 템플릿 반복은 수익화 제외 유형"}]
    return []


def disclosure_decision(assets):
    reasons = [asset.get("label", asset["kind"]) for asset in assets if asset.get("kind") in REALISTIC_KINDS]
    return {"youtube_altered_content": bool(reasons), "reasons": reasons}


def ymyl_persona(packet, assets):
    if packet.get("topic") in YMYL_TOPICS and any(asset.get("kind") == "ai_persona_real_person" for asset in assets):
        return [{"level": "block", "rule": "ymyl_ai_persona", "message": "실존 인물 AI 페르소나가 금융·법률·건강을 말하는 영상은 만들지 않습니다"}]
    return []


def run_gates(packet, previous_packets=(), assets=(), brand=None):
    items = metadata_fact_check(packet) + inauthentic_risk(packet, previous_packets) + ymyl_persona(packet, assets)
    if brand:
        text = " ".join([packet.get("title", ""), packet.get("body", ""), narration(packet)])
        items += [{"level": "block", "rule": "banned_claim", "message": f"금지 주장: {hit}"} for hit in banned_claim_hits(text, brand)]
    status = "block" if any(i["level"] == "block" for i in items) else "warn" if items else "pass"
    return {"status": status, "items": items, "disclosure": disclosure_decision(assets)}
```

- [ ] **Step 4: 통과 확인**

Run: `cd apps/content-office/backend && .venv/bin/python -m pytest -q tests/test_gates.py`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
cd "$(git rev-parse --show-toplevel)"
git add apps/content-office/backend/office/gates.py apps/content-office/backend/tests/test_gates.py
git commit -m "feat(agent): 메타데이터·반복·YMYL·공개 게이트"
```

### Task 6: 원고 단계 연결

**Files:**
- Modify: `apps/content-office/backend/office/editorial.py` (`prepare_source`)
- Test: `apps/content-office/backend/tests/test_agent_editorial.py`

**Interfaces:**
- Consumes: Task 3 `require_packaging`, Task 4 `load_brand`·`brand_system_prompt`, Task 5 `run_gates`
- Produces: `source_packet.quality.gates`(게이트 보고서). 기획 작업은 패키지 없이 `prepare_source`가 `WorkflowError`

- [ ] **Step 1: 실패하는 테스트 작성** (`tests/test_agent_editorial.py`)

```python
import pytest
from office.editorial import prepare_source
from office.store import Store, WorkflowError

EVIDENCE = [{"claim": "공식 발표에 따르면 도구는 3가지", "numbers": ["3"], "paragraph": 1, "scope": "발표"}]


class FakeProvider:
    def __init__(self, title):
        self.title = title
        self.systems = []

    def generate(self, role, messages, schema, options=None):
        self.systems.append(messages[0]["content"])
        if role in ("gen", "refine"):
            return {"title": self.title, "body": "도구 3가지를 실제 화면으로 비교한다", "video": {"title": "AI 도구 비교", "description": "", "tags": [], "scenes": [{"narration": "세 도구를 직접 비교한다", "caption": "비교", "visual": "화면"}]}}
        return {"role": role, "score": 90, "passed": True, "critical_issues": [], "minor_issues": [], "summary": "검토"}


def idea_job(store, origin="idea"):
    return store.create_job({"id": f"{origin}-1", "title": "기획", "url": "https://example.com/a", "origin": origin, "evidence": EVIDENCE})


def test_idea_job_without_packaging_cannot_draft(tmp_path):
    store = Store(tmp_path)
    job = idea_job(store)
    with pytest.raises(WorkflowError, match="패키징"):
        prepare_source(store, job["id"], provider=FakeProvider("AI 도구 비교"))


def test_gate_report_is_saved_and_blocks_unsupported_title_number(tmp_path):
    store = Store(tmp_path)
    job = idea_job(store, origin="rss")
    prepare_source(store, job["id"], provider=FakeProvider("AI 도구 7가지"))
    packet = store.job(job["id"])["source_packet"]
    assert packet["quality"]["gates"]["status"] == "block"
    assert packet["quality"]["status"] == "blocked"
```

- [ ] **Step 2: 실패 확인**

Run: `cd apps/content-office/backend && .venv/bin/python -m pytest -q tests/test_agent_editorial.py tests/test_editorial.py tests/test_e2e_workflow.py`
Expected: FAIL — 패키징 검사가 없어 `WorkflowError`가 나지 않음, `KeyError: 'gates'`

- [ ] **Step 3: 최소 구현**

`office/editorial.py` 상단 import에 추가:

```python
from .brand import brand_system_prompt, load_brand
from .gates import run_gates
from .packaging import require_packaging
```

`prepare_source`의 첫 두 줄을 아래로 바꾼다:

```python
    job = store.job(job_id)
    require_packaging(job)
    brand = load_brand()
    store.update_job(job_id, state="drafting", error=None)
```

같은 함수의 `gen` 호출에서 system 메시지를 바꾼다:

```python
        packet = provider.generate("gen", [{"role": "system", "content": brand_system_prompt(BASE, brand)}, {"role": "user", "content": canonical(context)}], DRAFT_SCHEMA, {"max_tokens": 8192, "temperature": 0.6})
```

`if not checks["passed"]:` 블록 바로 뒤에 추가:

```python
    previous = [j["source_packet"] for j in store.jobs() if j["id"] != job_id and j.get("source_packet")]
    packet["quality"]["gates"] = run_gates(packet, previous, packet.get("assets", []), brand)
    if packet["quality"]["gates"]["status"] == "block":
        packet["quality"].update(status="blocked", critical=True)
```

- [ ] **Step 4: 통과 확인**

Run: `cd apps/content-office/backend && .venv/bin/python -m pytest -q tests/test_agent_editorial.py tests/test_editorial.py tests/test_e2e_workflow.py`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
cd "$(git rev-parse --show-toplevel)"
git add apps/content-office/backend/office/editorial.py apps/content-office/backend/tests/test_agent_editorial.py
git commit -m "feat(agent): 원고 단계에 패키지·브랜드·게이트 연결"
```

### Task 7: 포맷 분기 계획

**Files:**
- Create: `apps/content-office/backend/office/formats.py`
- Test: `apps/content-office/backend/tests/test_formats.py`

**Interfaces:**
- Consumes: `office.store.WorkflowError`
- Produces: `FORMATS`, `plan_formats(source_hash, approved_hash, selected) -> list[{"format","parent_hash","delivery","checks"}]`, `check_shorts(durations) -> list[str]`, `retention_beats(total_seconds) -> list[int]`

- [ ] **Step 1: 실패하는 테스트 작성** (`tests/test_formats.py`)

```python
import pytest
from office.formats import check_shorts, plan_formats, retention_beats
from office.store import WorkflowError


def test_formats_branch_only_from_approved_source():
    with pytest.raises(WorkflowError, match="승인①"):
        plan_formats("v2", "v1", ["shorts"])
    plans = plan_formats("v1", "v1", ["blog_naver", "shorts"])
    assert [p["format"] for p in plans] == ["blog_naver", "shorts"]
    assert {p["parent_hash"] for p in plans} == {"v1"}
    assert plans[0]["delivery"] == "manual_paste"


def test_unknown_format_is_rejected():
    with pytest.raises(WorkflowError, match="알 수 없는 포맷"):
        plan_formats("v1", "v1", ["tiktok"])


def test_shorts_length_and_hook():
    assert check_shorts([2.5, 30, 40]) == []
    issues = check_shorts([4.0, 100, 100])
    assert any("180초" in i for i in issues) and any("훅" in i for i in issues)


def test_retention_beats():
    assert retention_beats(400) == [60, 180, 360]
    assert retention_beats(150) == [60]
```

- [ ] **Step 2: 실패 확인**

Run: `cd apps/content-office/backend && .venv/bin/python -m pytest -q tests/test_formats.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'office.formats'`

- [ ] **Step 3: 최소 구현**

```python
"""승인한 원고(①) 하나에서 포맷별 제작 계획을 독립 분기한다. 블로그 게시는 영상·뉴스레터의 선행 조건이 아니다."""
from __future__ import annotations

from .store import WorkflowError

SHORTS_MAX_SECONDS = 180  # 2024-10-15부터 Shorts 최대 3분
SHORTS_HOOK_SECONDS = 3
LONG_BEATS = (60, 180, 360)  # 첫 1분 약속 이행, 3분·6분 재몰입 지점
FORMATS = {
    "blog_tistory": {"delivery": "manual_or_api", "checks": ["제목·메타·대체 텍스트 사실 확인", "AI 활용 고지 문구"]},
    "blog_naver": {"delivery": "manual_paste", "checks": ["직접 경험·실제 화면 포함", "비슷한 글 반복 금지"]},
    "youtube_long": {"delivery": "manual_upload", "checks": ["썸네일 3안 1280×720 이상", "첫 1분에 제목 약속 이행"]},
    "shorts": {"delivery": "manual_upload", "checks": ["3초 안 훅", "180초 이하", "마지막 문장이 첫 장면으로 이어짐"]},
    "newsletter": {"delivery": "approval_3", "checks": ["발송 직전 최신 동의", "회차 키"]},
}


def plan_formats(source_hash, approved_hash, selected):
    if not approved_hash or source_hash != approved_hash:
        raise WorkflowError("승인①한 원고와 현재 원고가 다릅니다. 다시 승인한 뒤 분기합니다")
    unknown = [name for name in selected if name not in FORMATS]
    if unknown:
        raise WorkflowError("알 수 없는 포맷: " + ", ".join(unknown))
    return [{"format": name, "parent_hash": source_hash, **FORMATS[name]} for name in selected]


def check_shorts(durations):
    issues, total = [], sum(durations)
    if total > SHORTS_MAX_SECONDS:
        issues.append(f"쇼츠 길이 {total:.0f}초가 {SHORTS_MAX_SECONDS}초를 넘습니다")
    if durations and durations[0] > SHORTS_HOOK_SECONDS:
        issues.append(f"첫 장면이 {durations[0]:.1f}초라 훅이 {SHORTS_HOOK_SECONDS}초 안에 끝나지 않습니다")
    return issues


def retention_beats(total_seconds):
    return [beat for beat in LONG_BEATS if beat < total_seconds]
```

- [ ] **Step 4: 통과 확인**

Run: `cd apps/content-office/backend && .venv/bin/python -m pytest -q tests/test_formats.py`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
cd "$(git rev-parse --show-toplevel)"
git add apps/content-office/backend/office/formats.py apps/content-office/backend/tests/test_formats.py
git commit -m "feat(agent): 승인 원고에서만 포맷 분기"
```

### Task 8: 성과 스냅샷과 교훈 후보

**Files:**
- Create: `apps/content-office/backend/office/analytics.py`
- Test: `apps/content-office/backend/tests/test_analytics.py`

**Interfaces:**
- Consumes: Task 2 `Store.save_snapshot`·`snapshots`·`add_lesson`·`review_lesson`·`lessons`
- Produces: `parse_studio_csv(path) -> list[dict]`, `baseline(snapshots) -> {"ctr","avp"}`(중앙값), `propose_lessons(snapshot, base) -> list[lesson]`(kind: packaging·promise_mismatch·hook)

- [ ] **Step 1: 실패하는 테스트 작성** (`tests/test_analytics.py`)

```python
import pytest
from office.analytics import baseline, parse_studio_csv, propose_lessons
from office.store import Store

CSV = """Content,Impressions,Impressions click-through rate (%),Views,Average percentage viewed (%),Average view duration
Total,30000,5.0,1500,40,0:02:00
vid-a,10000,2.0,200,55,0:03:25
"""


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


def test_studio_csv_skips_total_and_parses_duration(tmp_path):
    path = tmp_path / "export.csv"
    path.write_text(CSV, encoding="utf-8")
    rows = parse_studio_csv(path)
    assert len(rows) == 1
    assert rows[0]["external_id"] == "vid-a" and rows[0]["avd_seconds"] == 205.0 and rows[0]["ctr"] == 2.0


def test_low_ctr_high_retention_proposes_packaging_lesson(store):
    for vid, ctr in (("b1", 5.0), ("b2", 6.0), ("b3", 4.0)):
        store.save_snapshot("youtube_long", vid, "7d", {"ctr": ctr, "avp": 40})
    snap = store.save_snapshot("youtube_long", "vid-a", "7d", {"ctr": 2.0, "avp": 55})
    lessons = propose_lessons(snap, baseline(store.snapshots("youtube_long")))
    assert [l["kind"] for l in lessons] == ["packaging"]


def test_snapshot_period_is_upserted(store):
    store.save_snapshot("shorts", "s1", "24h", {"views": 100, "engaged_views": 80})
    store.save_snapshot("shorts", "s1", "24h", {"views": 400, "engaged_views": 120})
    snaps = store.snapshots("shorts")
    assert len(snaps) == 1 and snaps[0]["metrics"]["views"] == 400
    assert [l["kind"] for l in propose_lessons(snaps[0], {"ctr": None, "avp": None})] == ["hook"]


def test_lessons_wait_for_approval(store):
    lesson = store.add_lesson({"kind": "packaging", "weight_change": {"factor": "outlier", "delta": 5}})
    assert store.lessons("approved") == []
    store.review_lesson(lesson["id"], "approved", "local-operator")
    assert store.lessons("approved")[0]["reviewed_by"] == "local-operator"
```

- [ ] **Step 2: 실패 확인**

Run: `cd apps/content-office/backend && .venv/bin/python -m pytest -q tests/test_analytics.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'office.analytics'`

- [ ] **Step 3: 최소 구현**

```python
"""성과 환류: 24시간·7일 스냅샷을 채널 기준선과 비교해 교훈 후보를 만든다.

교훈은 사람이 승인해야 기획 점수에 반영된다(darkzOGx/youtube-automation-agent 패턴).
CTR·노출수는 YouTube Analytics API에 없고 Reporting API 대량 보고서나 Studio 내보내기에만 있으므로 CSV 가져오기부터 시작한다.
"""
from __future__ import annotations

import csv
import statistics
from pathlib import Path

COLUMNS = {
    "external_id": ("Content", "콘텐츠"),
    "impressions": ("Impressions", "노출수"),
    "ctr": ("Impressions click-through rate (%)", "노출 클릭률(%)"),
    "views": ("Views", "조회수"),
    "engaged_views": ("Engaged views", "참여 조회수"),
    "avp": ("Average percentage viewed (%)", "평균 조회율(%)"),
    "avd_seconds": ("Average view duration", "평균 시청 지속 시간"),
}


def _number(value):
    value = (value or "").strip().replace(",", "")
    if ":" in value:
        seconds = 0
        for part in value.split(":"):
            seconds = seconds * 60 + int(part)
        return float(seconds)
    return float(value) if value else None


def parse_studio_csv(path):
    rows = []
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            row = {}
            for key, names in COLUMNS.items():
                cell = next((raw[n] for n in names if n in raw), None)
                row[key] = cell.strip() if key == "external_id" and cell else _number(cell) if cell is not None else None
            if row["external_id"] and row["external_id"].lower() not in ("total", "합계"):
                rows.append(row)
    return rows


def baseline(snapshots):
    ctr = [s["metrics"]["ctr"] for s in snapshots if s["metrics"].get("ctr")]
    avp = [s["metrics"]["avp"] for s in snapshots if s["metrics"].get("avp")]
    return {"ctr": statistics.median(ctr) if ctr else None, "avp": statistics.median(avp) if avp else None}


def propose_lessons(snapshot, base):
    m, lessons = snapshot["metrics"], []
    evidence = {"snapshot_id": snapshot["id"], "external_id": snapshot["external_id"], "period": snapshot["period"]}
    if m.get("ctr") and m.get("avp") and base.get("ctr") and base.get("avp"):
        if m["ctr"] < 0.8 * base["ctr"] and m["avp"] >= base["avp"]:
            lessons.append({"kind": "packaging", "hypothesis": "본 사람은 끝까지 봤지만 클릭이 적다: 다음 기획에서 제목·썸네일 3안 비교를 강화한다", "weight_change": {"factor": "outlier", "delta": 5}, "evidence": evidence})
        if m["ctr"] >= 1.2 * base["ctr"] and m["avp"] < 0.8 * base["avp"]:
            lessons.append({"kind": "promise_mismatch", "hypothesis": "클릭은 많고 유지가 낮다: 첫 1분이 제목의 약속을 이행하는지 점검한다", "weight_change": None, "evidence": evidence})
    if snapshot["channel"] == "shorts" and m.get("views") and m.get("engaged_views") is not None and m["engaged_views"] / m["views"] < 0.5:
        lessons.append({"kind": "hook", "hypothesis": "쇼츠 참여 조회 비율이 50% 미만: 3초 안 훅과 반복 연결을 바꾼다", "weight_change": None, "evidence": evidence})
    return lessons
```

- [ ] **Step 4: 통과 확인**

Run: `cd apps/content-office/backend && .venv/bin/python -m pytest -q tests/test_analytics.py`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
cd "$(git rev-parse --show-toplevel)"
git add apps/content-office/backend/office/analytics.py apps/content-office/backend/tests/test_analytics.py
git commit -m "feat(agent): 스냅샷 기준선과 교훈 후보"
```

### Task 9: API 연결

**Files:**
- Modify: `apps/content-office/backend/office/api.py`
- Test: `apps/content-office/backend/tests/test_content_agent_api.py`

**Interfaces:**
- Consumes: Task 1~8 전부
- Produces: `GET /api/ideas`, `POST /api/ideas`, `POST /api/ideas/{idea_id}/select`(작업 생성, `article.origin="idea"`), `POST /api/jobs/{job_id}/packaging`, `GET /api/jobs/{job_id}/gates`, `POST /api/analytics/snapshots`, `GET /api/lessons`, `POST /api/lessons/{lesson_id}/review`. 변경 요청은 기존 Origin·CSRF 미들웨어를 그대로 통과해야 한다

- [ ] **Step 1: 실패하는 테스트 작성** (`tests/test_content_agent_api.py`)

```python
import pytest
from fastapi.testclient import TestClient
from office.api import create_app
from office.store import Store


@pytest.fixture
def context(tmp_path):
    store = Store(tmp_path)
    client = TestClient(create_app(store), base_url="http://localhost:8510")
    token = client.get("/api/session").json()["csrf"]
    return store, client, {"Origin": "http://localhost:3110", "X-Office-CSRF": token}


def test_idea_to_packaged_job(context):
    store, client, headers = context
    saved = client.post("/api/ideas", json={"title": "Claude 팀 블로그 자동화", "primary_sources": 2, "demand": 70, "fit": 0.9}, headers=headers).json()
    assert saved["score"] > 0 and saved["blocked"] == []
    chosen = client.post(f"/api/ideas/{saved['id']}/select", json={}, headers=headers).json()
    job_id = chosen["job"]["id"]
    bad = client.post(f"/api/jobs/{job_id}/packaging", json={"titles": ["하나"], "thumbnails": [], "hook": "", "logline": "", "reasons": []}, headers=headers)
    assert bad.status_code == 409
    good = {"titles": ["Claude 팀으로 블로그 자동화", "AI 팀 블로그", "자동화 3단계"], "thumbnails": [{"text": "AI 팀", "visual": "화면"}] * 3,
            "hook": "Claude 팀으로 블로그를 끝낸 결과부터 봅니다", "logline": "한 명이 팀처럼 일하는 법", "reasons": ["수요", "실제 화면"]}
    assert client.post(f"/api/jobs/{job_id}/packaging", json=good, headers=headers).status_code == 200
    assert store.job(job_id)["packaging"]["packaging_hash"]


def test_blocked_idea_cannot_be_selected(context):
    _, client, headers = context
    saved = client.post("/api/ideas", json={"title": "출처 없는 소문"}, headers=headers).json()
    assert saved["blocked"] == ["1차 출처 없음"]
    assert client.post(f"/api/ideas/{saved['id']}/select", json={}, headers=headers).status_code == 409


def test_snapshot_creates_lesson_that_needs_review(context):
    _, client, headers = context
    for vid, ctr in (("b1", 5.0), ("b2", 6.0)):
        client.post("/api/analytics/snapshots", json={"channel": "youtube_long", "external_id": vid, "period": "7d", "metrics": {"ctr": ctr, "avp": 40}}, headers=headers)
    result = client.post("/api/analytics/snapshots", json={"channel": "youtube_long", "external_id": "vid-a", "period": "7d", "metrics": {"ctr": 2.0, "avp": 55}}, headers=headers).json()
    lesson = result["lessons"][0]
    assert lesson["kind"] == "packaging" and lesson["state"] == "proposed"
    reviewed = client.post(f"/api/lessons/{lesson['id']}/review", json={"decision": "approved"}, headers=headers).json()
    assert reviewed["state"] == "approved"
```

- [ ] **Step 2: 실패 확인**

Run: `cd apps/content-office/backend && .venv/bin/python -m pytest -q tests/test_content_agent_api.py tests/test_api.py`
Expected: FAIL — 404 Not Found

- [ ] **Step 3: 최소 구현**

`office/api.py`의 `from .runtime import window_open` 아래에 추가:

```python
from .analytics import baseline, propose_lessons
from .brand import load_brand
from .gates import run_gates
from .ideas import rank_ideas, score_idea
from .packaging import attach_packaging
```

`class EvidenceInput` 정의 바로 아래에 추가:

```python
class IdeaInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    source_url: str = ""
    views: int | None = None
    channel_avg_views: int | None = None
    demand: float = Field(default=0, ge=0, le=100)
    primary_sources: int = Field(default=0, ge=0)
    fit: float = Field(default=0, ge=0, le=1)
    covered_before: bool = False
    policy_flags: list[str] = []


class PackagingInput(BaseModel):
    titles: list[str]
    thumbnails: list[dict]
    hook: str
    logline: str
    reasons: list[str]
    chosen_title: str | None = None


class SnapshotInput(BaseModel):
    channel: Literal["youtube_long", "shorts", "blog_tistory", "blog_naver", "newsletter"]
    external_id: str = Field(min_length=1, max_length=200)
    period: Literal["24h", "7d", "28d"]
    metrics: dict[str, float | int | None]
    job_id: str | None = None


class LessonReview(BaseModel):
    decision: Literal["approved", "rejected"]
```

`create_app` 끝의 `return app` 바로 앞에 추가:

```python
    @app.get("/api/ideas")
    def list_ideas():
        return {"ideas": rank_ideas(store.ideas(), lessons=store.lessons("approved"))}

    @app.post("/api/ideas")
    def add_idea(idea: IdeaInput):
        return store.save_idea(score_idea(idea.model_dump(), lessons=store.lessons("approved")))

    @app.post("/api/ideas/{idea_id}/select")
    def choose_idea(idea_id: str):
        idea = store.select_idea(idea_id, "local-operator")
        job = store.create_job({"id": idea_id, "title": idea["title"], "url": idea.get("source_url", ""), "origin": "idea", "evidence": []})
        return {"idea": idea, "job": job}

    @app.post("/api/jobs/{job_id}/packaging")
    def set_packaging(job_id: str, brief: PackagingInput):
        return attach_packaging(store, job_id, brief.model_dump(exclude_none=True), "local-operator")

    @app.get("/api/jobs/{job_id}/gates")
    def job_gates(job_id: str):
        packet = store.job(job_id).get("source_packet") or {}
        previous = [j["source_packet"] for j in store.jobs() if j["id"] != job_id and j.get("source_packet")]
        return run_gates(packet, previous, packet.get("assets", []), load_brand())

    @app.post("/api/analytics/snapshots")
    def add_snapshot(snapshot: SnapshotInput):
        saved = store.save_snapshot(snapshot.channel, snapshot.external_id, snapshot.period, snapshot.metrics, snapshot.job_id)
        base = baseline([s for s in store.snapshots(snapshot.channel) if s["period"] == snapshot.period and s["id"] != saved["id"]])
        return {"snapshot": saved, "lessons": [store.add_lesson(lesson) for lesson in propose_lessons(saved, base)]}

    @app.get("/api/lessons")
    def list_lessons():
        return {"lessons": store.lessons()}

    @app.post("/api/lessons/{lesson_id}/review")
    def review_lesson(lesson_id: str, review: LessonReview):
        return store.review_lesson(lesson_id, review.decision, "local-operator")
```

- [ ] **Step 4: 통과 확인**

Run: `cd apps/content-office/backend && .venv/bin/python -m pytest -q tests/test_content_agent_api.py tests/test_api.py`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
cd "$(git rev-parse --show-toplevel)"
git add apps/content-office/backend/office/api.py apps/content-office/backend/tests/test_content_agent_api.py
git commit -m "feat(agent): 기획·패키지·게이트·성과 API"
```

### Task 10: 화면 — 기획 은행 패널

**Files:**
- Modify: `apps/content-office/frontend/lib/types.ts` (파일 끝에 타입 추가)
- Modify: `apps/content-office/frontend/lib/api.ts` (import와 `api` 객체 끝)
- Modify: `apps/content-office/frontend/app/support-panels.tsx` (import와 파일 끝)
- Modify: `apps/content-office/frontend/app/page.tsx` (import와 뉴스 화면)

**Interfaces:**
- Consumes: Task 9 API
- Produces: `api.ideas()`, `api.selectIdea(id)`, `api.setPackaging(jobId, brief)`, `api.gates(jobId)`, `api.lessons()`, `api.reviewLesson(id, decision)`, 컴포넌트 `IdeaBank({ onSelected })`

- [ ] **Step 1: 타입 검사가 실패하도록 먼저 사용처를 넣는다** — `app/page.tsx`의 `./support-panels` import 목록에 `IdeaBank,`를 `KnowledgeDrawer,` 앞에 추가하고, 뉴스 화면의 `<section className="news-section" aria-labelledby="news-heading">` 바로 앞에 `<IdeaBank />`를 넣는다.

- [ ] **Step 2: 실패 확인**

Run: `cd apps/content-office/frontend && npm run typecheck`
Expected: FAIL — `Module '"./support-panels"' has no exported member 'IdeaBank'`

- [ ] **Step 3: 구현**

`lib/types.ts` 끝에 추가:

```tsx
export type Idea = {
  id: string;
  title: string;
  source_url?: string;
  state: "candidate" | "selected";
  score: number;
  outlier_band: string;
  reasons: string[];
  blocked: string[];
};
export type Lesson = {
  id: string;
  kind: string;
  hypothesis: string;
  state: "proposed" | "approved" | "rejected";
  weight_change?: { factor: string; delta: number } | null;
};
export type PackagingBrief = {
  titles: string[];
  thumbnails: { text: string; visual: string }[];
  hook: string;
  logline: string;
  reasons: string[];
  chosen_title?: string;
};
export type GateReport = {
  status: "pass" | "warn" | "block";
  items: { level: "warn" | "block"; rule: string; message: string }[];
  disclosure: { youtube_altered_content: boolean; reasons: string[] };
};
```

`lib/api.ts`의 `from "./types"` import에 `Idea, Lesson, PackagingBrief, GateReport`를 추가하고, `api` 객체의 `selectThumbnail` 항목 뒤에 추가:

```tsx
  ideas: () => request<{ ideas: Idea[] }>("/ideas"),
  selectIdea: (id: string) =>
    request<{ idea: Idea; job: Job }>(
      `/ideas/${encodeURIComponent(id)}/select`,
      "POST",
      {},
    ),
  setPackaging: (jobId: string, brief: PackagingBrief) =>
    request(`/jobs/${encodeURIComponent(jobId)}/packaging`, "POST", brief),
  gates: (jobId: string) =>
    request<GateReport>(`/jobs/${encodeURIComponent(jobId)}/gates`),
  lessons: () => request<{ lessons: Lesson[] }>("/lessons"),
  reviewLesson: (id: string, decision: "approved" | "rejected") =>
    request<Lesson>(`/lessons/${encodeURIComponent(id)}/review`, "POST", {
      decision,
    }),
```

`app/support-panels.tsx`의 타입 import를 `import type { Idea, Job, KnowledgeSearch, Task, OutputKind } from "../lib/types";`로 바꾸고 파일 끝에 추가:

```tsx
export function IdeaBank({ onSelected }: { onSelected?: (job: Job) => void }) {
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  async function load() {
    try {
      setIdeas((await api.ideas()).ideas);
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "기획 은행을 읽지 못했습니다.");
    }
  }
  useEffect(() => {
    void load();
  }, []);
  async function choose(id: string) {
    setBusy(id);
    try {
      const result = await api.selectIdea(id);
      onSelected?.(result.job);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "기획을 선택하지 못했습니다.");
    } finally {
      setBusy(null);
    }
  }
  return (
    <section className="news-section" aria-labelledby="idea-bank-heading">
      <div className="section-heading">
        <div className="section-title">
          <h2 id="idea-bank-heading">기획 은행 · ⓪ 기획 선택</h2>
          <span className="count-pill">{ideas.length}</span>
        </div>
      </div>
      {error && <p role="alert">{error}</p>}
      {ideas.length === 0 && !error && <p>아직 점수를 매긴 기획이 없습니다.</p>}
      <ol>
        {ideas.map((idea) => (
          <li key={idea.id}>
            <strong>{idea.title}</strong> · {idea.score}점 · 이상치 {idea.outlier_band}
            {idea.blocked.length > 0 && <p>막힌 이유: {idea.blocked.join(", ")}</p>}
            <button
              className="button secondary"
              type="button"
              disabled={idea.blocked.length > 0 || idea.state === "selected" || busy === idea.id}
              onClick={() => void choose(idea.id)}
            >
              {idea.state === "selected" ? "선택됨" : "이 기획으로 작업 만들기"}
            </button>
          </li>
        ))}
      </ol>
    </section>
  );
}
```

- [ ] **Step 4: 통과 확인**

Run: `cd apps/content-office/frontend && npm run typecheck && npm test`
Expected: PASS (타입 오류 0, 기존 단위 테스트 통과)

- [ ] **Step 5: 커밋**

```bash
cd "$(git rev-parse --show-toplevel)"
git add apps/content-office/frontend/lib/types.ts apps/content-office/frontend/lib/api.ts apps/content-office/frontend/app/support-panels.tsx apps/content-office/frontend/app/page.tsx
git commit -m "feat(agent): 뉴스 화면에 기획 은행과 ⓪ 기획 선택"
```

### Task 11: 전체 검증과 인계

- [ ] **Step 1: 백엔드 전체 테스트**

Run: `cd apps/content-office/backend && .venv/bin/python -m pytest -q`
Expected: PASS — 기존 189 passed·1 skipped에 새 테스트 33개가 더해진다(작성 시점 검증: 새 33개 포함 전부 통과).

- [ ] **Step 2: 화면 검사**

Run: `cd apps/content-office/frontend && npm run typecheck && npm test`
Expected: PASS

- [ ] **Step 3: 수동 확인** — 로컬 앱에서 기획 1건 저장 → ⓪ 선택 → 패키지 확정 → 초안 생성 → 승인 화면에서 `quality.gates` 사유가 보이는지 확인. Studio CSV 1개를 `POST /api/analytics/snapshots` 형식으로 넣어 교훈 카드가 `proposed`로 생기는지 확인.

- [ ] **Step 4: 커밋**

```bash
cd "$(git rev-parse --show-toplevel)"
git add -A apps/content-office
git commit -m "chore(agent): v6 편집 통제실 1차 연결 검증"
```

## Self-Review

- 설계서 범위 대조: 0 브랜드(Task 4), 2 기획 은행(Task 1·2), 3 ⓪ 선택(Task 2·9·10), 4 패키지(Task 3·6·9), 6 원고 루프 연결(Task 6), 7 게이트(Task 5·6), 9 포맷 분기(Task 7), 13 측정·교훈(Task 2·8·9). 1 신호 수집기(YouTube·DataLab 클라이언트)와 12 배포 자동화는 설계서에서 P1 후속·P3로 분리했다.
- 자리표시 검사: TBD·TODO 없음. 모든 코드 단계에 실제 코드가 있다.
- 이름 일관성: `score_idea`·`save_idea`·`select_idea`·`attach_packaging`·`require_packaging`·`load_brand`·`run_gates`·`plan_formats`·`propose_lessons`가 Task 간 같은 서명으로 쓰인다.
- 작성 시점 검증: 저장소를 건드리지 않은 임시 사본에서 Task 1~10 코드를 적용해 백엔드 전체 테스트(새 33개 포함)와 `tsc --noEmit`·화면 단위 테스트가 통과했다.

## Execution Handoff

계획은 `docs/superpowers/plans/2026-10-27-ai-content-agent.md`에 있다. 실행 방식은 둘 중 하나다.

1. **Subagent-Driven(권장)** — 작업마다 새 하위 에이전트, 작업 사이 검토. REQUIRED SUB-SKILL: superpowers:subagent-driven-development
2. **Inline Execution** — 한 세션에서 체크포인트를 두고 일괄 실행. REQUIRED SUB-SKILL: superpowers:executing-plans
