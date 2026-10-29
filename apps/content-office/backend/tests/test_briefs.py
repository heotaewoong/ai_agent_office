"""Reader briefs: presets per business axis, per-job overrides, and propagation into every editorial call."""
import json

import pytest

from office.store import Store, WorkflowError

EVIDENCE = [{"id": "E1", "url": "https://example.com/a", "claim": "공식 발표에 따르면 도구는 3가지", "numbers": ["3"], "paragraph": 1, "scope": "발표"}]


class RecordingProvider:
    def __init__(self):
        self.calls = []

    def generate(self, role, messages, schema, options=None):
        self.calls.append((role, messages[0]["content"], messages[1]["content"]))
        if role in ("gen", "refine"):
            body = "## 질문\n\n오픽 IM에서 막힌 분이 먼저 할 일은 하나예요.\n\n## 답\n\n" + "도구 3가지를 실제 화면으로 비교해요. " * 60 + "\n\n## 오늘 할 일\n\n퀴즈 세 문제를 풀어 보세요. [E1]"
            return {"title": "오픽 IM 탈출", "body": body, "video": {"title": "오픽 IM 탈출 3단계", "description": "", "tags": [], "thumbnails": [{"title": f"안 {i}", "subtitle": "", "angle": "a"} for i in range(5)], "scenes": [{"narration": "세 도구를 직접 비교해요", "caption": "비교", "visual": "화면"}] * 3}}
        return {"role": role, "score": 90, "passed": True, "critical_issues": [], "minor_issues": [], "summary": "검토"}


def test_presets_cover_both_axes_and_legacy_default():
    from office.briefs import PRESETS, DEFAULT_PRESET, build_brief
    from office.editorial import AUDIENCE
    assert DEFAULT_PRESET == "ai-agent"
    assert {"ai-agent", "exam-opic", "exam-info-processing", "transfer-admission", "productivity-automation"} <= set(PRESETS)
    axes = {p["axis"] for p in PRESETS.values()}
    assert axes == {"A", "B"}
    for key, preset in PRESETS.items():
        for field in ("axis", "topic", "reader", "prior_knowledge", "problem", "outcome", "tone", "language"):
            assert preset[field], (key, field)
    legacy = build_brief("ai-agent")
    for field in ("topic", "reader", "prior_knowledge", "problem", "outcome", "tone"):
        assert legacy[field] == AUDIENCE[field]
    assert legacy["preset"] == "ai-agent" and legacy["language"] == "ko"


def test_build_brief_applies_trimmed_overrides_and_rejects_bad_input():
    from office.briefs import build_brief
    brief = build_brief("exam-opic", {"reader": "  오픽 IM2에서 막힌 28살 취준생 ", "problem": "", "cta": "무료 문법 PDF 받기", "language": "ko"})
    assert brief["preset"] == "exam-opic" and brief["axis"] == "A"
    assert brief["reader"] == "오픽 IM2에서 막힌 28살 취준생"
    assert brief["problem"] == build_brief("exam-opic")["problem"]
    assert brief["cta"] == "무료 문법 PDF 받기"
    with pytest.raises(WorkflowError, match="프리셋"):
        build_brief("midjourney")
    with pytest.raises(WorkflowError, match="500"):
        build_brief("exam-opic", {"problem": "가" * 501})
    with pytest.raises(WorkflowError, match="언어"):
        build_brief("exam-opic", {"language": "fr"})
    with pytest.raises(WorkflowError, match="필드"):
        build_brief("exam-opic", {"secret": "x"})


def test_job_brief_defaults_and_can_be_replaced_with_event(tmp_path):
    from office.briefs import brief_for_job, build_brief
    store = Store(tmp_path)
    job = store.create_job({"id": "rss-1", "title": "기사", "url": "https://example.com/a", "evidence": EVIDENCE})
    assert brief_for_job(job) == build_brief("ai-agent")
    updated = store.set_brief(job["id"], build_brief("exam-opic", {"cta": "무료 문법 PDF 받기"}), "local-operator")
    assert updated["brief"]["preset"] == "exam-opic" and updated["brief"]["cta"] == "무료 문법 PDF 받기"
    assert brief_for_job(store.job(job["id"]))["axis"] == "A"
    assert any(e["kind"] == "brief_set" and e["data"]["preset"] == "exam-opic" for e in store.events(job["id"]))
    with pytest.raises(WorkflowError, match="프리셋"):
        store.set_brief(job["id"], {"preset": "nope"}, "local-operator")
    created = store.create_job({"id": "idea-9", "title": "기획", "url": "https://example.com/b", "origin": "idea", "evidence": EVIDENCE}, brief=build_brief("transfer-admission"))
    assert created["brief"]["preset"] == "transfer-admission"


def test_brief_reaches_generation_review_refine_and_packet(tmp_path):
    from office.briefs import build_brief
    from office.editorial import prepare_source
    store = Store(tmp_path)
    job = store.create_job({"id": "rss-2", "title": "기사", "url": "https://example.com/a", "evidence": EVIDENCE}, brief=build_brief("exam-opic", {"reader": "오픽 IM2에서 막힌 28살 취준생", "cta": "무료 문법 PDF 받기"}))
    provider = RecordingProvider()
    prepare_source(store, job["id"], provider=provider)
    roles = [c[0] for c in provider.calls]
    assert roles[:3] == ["gen", "critique", "eval"]
    for role, system, user in provider.calls:
        payload = json.loads(user)
        assert payload["audience"]["preset"] == "exam-opic", role
        assert payload["audience"]["reader"] == "오픽 IM2에서 막힌 28살 취준생", role
        assert payload["audience"]["cta"] == "무료 문법 PDF 받기", role
        assert "AI 뉴스" not in payload["audience"]["problem"], role
    packet = store.job(job["id"])["source_packet"]
    assert packet["audience"]["preset"] == "exam-opic" and packet["brief_preset"] == "exam-opic"


def test_api_accepts_brief_on_idea_and_on_job(tmp_path):
    from fastapi.testclient import TestClient
    from office.api import create_app
    from office.ideas import score_idea
    store = Store(tmp_path)
    client = TestClient(create_app(store), base_url="http://localhost:8510")
    headers = {"Origin": "http://localhost:3110", "X-Office-CSRF": client.get("/api/session").json()["csrf"]}
    body = {"title": "오픽 IM에서 막힌 분을 위한 첫 7일", "source_url": "https://example.com/opic", "demand": 50, "primary_sources": 2, "fit": 0.8, "covered_before": False, "policy_flags": [],
            "brief_preset": "exam-opic", "brief": {"reader": "오픽 IM2 취준생", "problem": "단어는 외웠는데 말이 안 나옴", "cta": "무료 문법 PDF 받기"}}
    idea = client.post("/api/ideas", json=body, headers=headers).json()
    assert idea["brief"]["preset"] == "exam-opic" and idea["brief"]["problem"] == "단어는 외웠는데 말이 안 나옴"
    selected = client.post(f"/api/ideas/{idea['id']}/select", headers=headers).json()
    assert selected["job"]["brief"]["preset"] == "exam-opic" and selected["job"]["brief"]["cta"] == "무료 문법 PDF 받기"
    viewed = client.get(f"/api/jobs/{selected['job']['id']}").json()
    changed = client.put(f"/api/jobs/{selected['job']['id']}/brief", json={"preset": "productivity-automation", "overrides": {"problem": "같은 정리를 매주 반복"}, "expected_brief_hash": viewed["brief_hash"]}, headers=headers)
    assert changed.status_code == 200 and changed.json()["brief"]["axis"] == "B" and changed.json()["brief"]["problem"] == "같은 정리를 매주 반복"
    assert client.get("/api/briefs").json()["default"] == "ai-agent"
    assert any(p["id"] == "exam-opic" and p["axis"] == "A" for p in client.get("/api/briefs").json()["presets"])
    assert client.post("/api/ideas", json={**body, "brief_preset": "nope"}, headers=headers).status_code in (409, 422)
    assert score_idea(body)["score"] > 0


def test_brief_update_rejects_same_preset_from_an_old_tab(tmp_path):
    from fastapi.testclient import TestClient
    from office.api import create_app
    from office.store import digest

    store = Store(tmp_path)
    job = store.create_job({"id": "two-tabs", "title": "기사", "url": "https://example.com/a"})
    client = TestClient(create_app(store), base_url="http://localhost:8510")
    headers = {"Origin": "http://localhost:3110", "X-Office-CSRF": client.get("/api/session").json()["csrf"]}
    viewed = client.get(f"/api/jobs/{job['id']}").json()
    viewed_hash = viewed["brief_hash"]
    first = client.put(f"/api/jobs/{job['id']}/brief", json={"preset": job["brief"]["preset"], "overrides": {"reader": "다른 탭의 새 독자"}, "expected_brief_hash": viewed_hash}, headers=headers)
    assert first.status_code == 200
    after_first = store.job(job["id"])
    event_count = len(store.events(job["id"]))
    stale = client.put(f"/api/jobs/{job['id']}/brief", json={"preset": job["brief"]["preset"], "overrides": {"reader": "옛 탭의 독자", "cta": "내가 편집한 CTA"}, "expected_brief_hash": viewed_hash}, headers=headers)
    assert stale.status_code == 409
    assert store.job(job["id"]) == after_first
    assert len(store.events(job["id"])) == event_count
    assert viewed["brief_hash"] == digest(viewed["brief"])
    assert first.json()["brief_hash"] == digest(first.json()["brief"])


@pytest.mark.parametrize("token", [{}, {"expected_brief_hash": None}, {"expected_brief_hash": "short"}, {"expected_brief_hash": "g" * 64}])
def test_brief_api_requires_a_valid_viewed_token(tmp_path, token):
    from fastapi.testclient import TestClient
    from office.api import create_app

    store = Store(tmp_path)
    job = store.create_job({"id": "invalid-token", "title": "기사", "url": "https://example.com/a"})
    client = TestClient(create_app(store), base_url="http://localhost:8510")
    headers = {"Origin": "http://localhost:3110", "X-Office-CSRF": client.get("/api/session").json()["csrf"]}
    before = store.job(job["id"])
    events = store.events(job["id"])
    response = client.put(f"/api/jobs/{job['id']}/brief", json={"preset": "ai-agent", "overrides": {"reader": "저장하지 않을 독자"}, **token}, headers=headers)
    assert response.status_code == 422
    assert store.job(job["id"]) == before and store.events(job["id"]) == events


def test_brief_compare_and_set_is_atomic_and_preserves_approvals(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from office.briefs import build_brief
    from office.store import digest

    store = Store(tmp_path)
    job = store.create_job({"id": "competing-briefs", "title": "기사", "url": "https://example.com/a"})
    original = store.update_job(job["id"], source_hash="original-source", source_approval={"decision": "approved", "version": "original-source"}, release_approval={"decision": "approved", "version": "original-manifest"}, manifest={"hash": "original-manifest"})
    expected = digest(original["brief"])
    barrier = Barrier(2)

    def update(reader):
        barrier.wait(timeout=5)
        try:
            store.set_brief(job["id"], build_brief("ai-agent", {"reader": reader}), "operator", expected_hash=expected)
            return "saved"
        except WorkflowError as error:
            assert "브리프가 변경" in str(error)
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(update, ["첫 탭 독자", "둘째 탭 독자"]))
    assert sorted(results) == ["conflict", "saved"]
    current = store.job(job["id"])
    for key in ("source_hash", "source_approval", "release_approval", "manifest"):
        assert current[key] == original[key]
    assert len([event for event in store.events(job["id"]) if event["kind"] == "brief_set"]) == 1
