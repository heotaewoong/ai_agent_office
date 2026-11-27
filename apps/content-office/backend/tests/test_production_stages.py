"""나눠 만들기(2026-11-27): 승인① 뒤 글과 카드부터, 영상은 사람이 비용을 보고 누른 뒤에만."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from office.api import create_app
from office.production_graph import run_production, staged
from office.store import Store, WorkflowError
from platform_support import requires_ffmpeg
from tests.test_media import approved_job, cache_social_cards, tone_renderer


def fake_manifest(name, video_state):
    return {"hash": name, "output_status": {"blog": {"state": "completed"}, "video": {"state": video_state}}}


def produce_recorder(calls, *, fail=None):
    def produce(defer_video):
        calls.append(defer_video)
        if fail and not defer_video:
            raise WorkflowError(fail)
        return fake_manifest("m-text" if defer_video else "m-video", "deferred" if defer_video else "completed")
    return produce


def video_request(store, job_id):
    job = store.job(job_id)
    return store.enqueue("produce", {"job_id": job_id, "source_hash": job["source_hash"], "stage": "video"}, key="video-click")


def test_only_mixed_selections_wait_for_the_video_click():
    assert staged({"blog": True, "video": True}) and staged({"cards": True, "video": True})
    assert not staged({"video": True}) and not staged({"blog": True, "cards": True}) and not staged(None)


def test_text_stage_pauses_at_the_video_gate_and_resumes_only_with_a_stored_click(tmp_path):
    store, job_id = approved_job(tmp_path, cards=True)
    calls = []
    first = run_production(store, job_id, task_id="t1", stage="text", contract="c1", produce=produce_recorder(calls))
    assert calls == [True] and first["awaiting_video"] and first["path"] == ["plan", "text_outputs"]
    assert first["manifest"]["hash"] == "m-text"
    with pytest.raises(WorkflowError, match="예상 비용"):
        run_production(store, job_id, task_id="not-a-task", stage="video", contract="c1", produce=produce_recorder(calls))
    assert calls == [True]  # 관문이 막으면 영상 제작을 부르지 않는다
    click = video_request(store, job_id)
    second = run_production(store, job_id, task_id=click["id"], stage="video", contract="c1", produce=produce_recorder(calls))
    assert calls == [True, False] and not second["awaiting_video"]
    assert second["path"] == ["plan", "text_outputs", "video_gate", "video_output"] and second["manifest"]["hash"] == "m-video"


def test_video_only_job_is_made_at_once_without_a_gate(tmp_path):
    store, job_id = approved_job(tmp_path, blog=False)
    calls = []
    result = run_production(store, job_id, task_id="t1", stage="text", contract="c1", produce=produce_recorder(calls))
    assert calls == [False] and not result["awaiting_video"] and result["path"] == ["plan", "text_outputs"]


def test_failed_video_stage_leaves_a_three_field_handoff_and_no_retry(tmp_path):
    store, job_id = approved_job(tmp_path, cards=True)
    calls = []
    click = video_request(store, job_id)
    with pytest.raises(WorkflowError, match="렌더 실패"):
        run_production(store, job_id, task_id=click["id"], stage="video", contract="c2", produce=produce_recorder(calls, fail="렌더 실패"))
    assert calls == [True, False]
    handoff = [e for e in store.events(job_id) if e["kind"] == "production_handoff"][-1]["data"]
    assert handoff["done"] == ["plan", "text_outputs", "video_gate"] and handoff["stopped_at"] == "video_output"
    assert handoff["reason"] == "렌더 실패" and handoff["paid_retry"] is False
    retry = store.enqueue("produce", {**click["payload"]}, key="operator-retry")  # 사람이 다시 누른 요청
    again = run_production(store, job_id, task_id=retry["id"], stage="video", contract="c2", produce=produce_recorder(calls))
    assert calls == [True, False, True, False] and again["path"][-1] == "video_output" and not again["awaiting_video"]


@requires_ffmpeg
def test_worker_makes_blog_and_cards_first_then_video_after_the_click(tmp_path, monkeypatch):
    from office import worker
    store, job_id = approved_job(tmp_path, cards=True)
    cache_social_cards(store, job_id)
    monkeypatch.setattr("office.voice_selection.renderer_for_job", lambda store, job: tone_renderer())
    first_task = store.enqueue("produce", {"job_id": job_id, "source_hash": store.job(job_id)["source_hash"]}, key="first")
    result = worker.process_task(store, first_task)
    job = store.job(job_id)
    assert result["awaiting_video"] and result["partial"] is False
    assert job["manifest"]["completed_outputs"] == ["blog", "cards"] and job["state"] == "release_review"
    assert job["manifest"]["output_status"]["video"] == {"state": "deferred"}
    assert any("영상은 아직 만들지 않았어요" in warning for warning in job["manifest"]["warnings"])
    text_files = {r["path"] for r in job["manifest"]["files"] if {"blog", "cards"} & set(r["outputs"])}
    click = video_request(store, job_id)
    second = worker.process_task(store, click)
    job = store.job(job_id)
    assert not second["awaiting_video"] and second["path"][-2:] == ["video_gate", "video_output"]
    assert job["manifest"]["completed_outputs"] == ["blog", "video", "cards"]
    assert text_files <= {r["path"] for r in job["manifest"]["files"]}  # 글과 카드는 다시 만들지 않고 그대로 쓴다
    assert job["release_approval"] is None and job["state"] == "release_review"


@pytest.fixture
def client(tmp_path):
    store = Store(tmp_path)
    store.save_articles([{"id": "one", "title": "AI 발표", "url": "https://example.com/news", "summary": "공식 발표", "evidence": [],
                          "published_at": datetime.now(timezone.utc).isoformat()}])
    client = TestClient(create_app(store), base_url="http://localhost:8510")
    token = client.get("/api/session").json()["csrf"]
    return store, client, {"Origin": "http://localhost:3110", "X-Office-CSRF": token}


def mixed_job(store, selections):
    job = store.create_job(store.article("one"))
    scenes = [{"narration": "첫 장면입니다.", "caption": "첫 장면", "visual": "노트북"}, {"narration": "둘째 장면.", "caption": "둘째", "visual": "책상"}]
    source = store.save_source(job["id"], {"title": "영상 원고", "body": "완성 원고", "quality": {"status": "passed", "critical": False},
                                           "video": {"title": "영상", "description": "", "scenes": scenes}})
    store.review_source(job["id"], source["source_hash"], "approved", "operator", selections)
    return store.job(job["id"])


def test_paid_clips_are_asked_only_on_the_video_click(client, monkeypatch):
    from office import image_selection, video_selection
    store, http, headers = client
    monkeypatch.setenv("RUNWAYML_API_SECRET", "test-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    http.post("/api/session/window", json={"minutes": 30}, headers=headers)
    image_selection.select_profile(store, "openai-gpt-image", actor="op")
    video_selection.select_profile(store, "runway-grok-lite", actor="op")
    job = mixed_job(store, {"blog": True, "video": True})
    route = f"/api/jobs/{job['id']}"
    assert http.get(route + "/production-estimate").json()["clips"]["paid"] is False
    assert http.get(route + "/production-estimate?stage=video").json()["clips"]["paid"] is True
    early = http.post(route + "/produce", json={"stage": "video", "confirm_paid_clips": True}, headers=headers)
    assert early.status_code == 409 and "먼저" in early.json()["detail"]  # 글과 카드가 먼저다
    text = http.post(route + "/produce", json={}, headers=headers)
    assert text.status_code == 202 and "paid_clips_confirmed" not in text.json()["payload"] and "stage" not in text.json()["payload"]
    store.update_job(job["id"], manifest={**fake_manifest("m-text", "deferred"), "source_hash": job["source_hash"]})
    refused = http.post(route + "/produce", json={"stage": "video"}, headers=headers)
    assert refused.status_code == 409 and "유료: 영상 클립" in refused.json()["detail"]
    clicked = http.post(route + "/produce", json={"stage": "video", "confirm_paid_clips": True}, headers=headers)
    assert clicked.status_code == 202
    assert clicked.json()["payload"]["stage"] == "video" and clicked.json()["payload"]["paid_clips_confirmed"] is True
    assert clicked.json()["id"] != text.json()["id"]
    assert [e["kind"] for e in store.events(job["id"])].count("video_stage_requested") == 1
