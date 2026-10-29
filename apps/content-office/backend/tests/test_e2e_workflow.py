"""HTTP -> SQLite queue -> real worker -> handoff; no model or real-news approval.

Run OFFICE_REAL_MEDIA_E2E=1 pytest -q tests/test_e2e_workflow.py to also
exercise installed Korean SAPI speech and FFmpeg. The source/quality are an
explicit synthetic seed, not evidence of generation or factual verification.
"""
import hashlib
import io
import json
import os
import shutil
import zipfile

import pytest
from fastapi.testclient import TestClient

from office.store import Store, now
from office.worker import run_once


@pytest.mark.parametrize("video", [False, pytest.param(True, marks=pytest.mark.skipif(os.environ.get("OFFICE_REAL_MEDIA_E2E") != "1", reason="Set OFFICE_REAL_MEDIA_E2E=1 for installed Korean SAPI/FFmpeg integration"))])
def test_synthetic_http_worker_download_and_source_invalidation(tmp_path, monkeypatch, video):
    # office.api has a module-level ASGI app; isolate it before first import too.
    monkeypatch.setenv("OFFICE_STATE_DIR", str(tmp_path / "e2e-state"))
    from office.api import create_app
    def forbidden_model(*args, **kwargs):
        pytest.fail("Synthetic workflow must never call a model")
    monkeypatch.setattr("office.worker.prepare_source", forbidden_model)
    monkeypatch.setattr("office.providers.requests.post", forbidden_model)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    store = Store(tmp_path / "e2e-state")
    article = {"id": "synthetic-fixture", "title": "[합성] 승인 흐름 검증", "url": "https://example.com/synthetic-fixture", "published_at": now(), "evidence": [{"id": "SYNTH-E1", "url": "https://example.com/synthetic-fixture", "claim": "실제 뉴스가 아닌 합성 fixture"}]}
    store.save_articles([article])
    with TestClient(create_app(store), base_url="http://localhost:8510") as client:
        csrf = client.get("/api/session").json()["csrf"]
        headers = {"Origin": "http://localhost:3110", "X-Office-CSRF": csrf}
        response = client.post("/api/jobs", json={"article_ids": [article["id"]]}, headers=headers)
        assert response.status_code == 200
        job_id = response.json()["jobs"][0]["id"]
        assert store.job(job_id)["state"] == "research_ready"
        assert client.post(f"/api/jobs/{job_id}/produce", json={}, headers=headers).status_code == 409
        # Explicitly seed initial draft/quality; all approvals go through HTTP.
        packet = {"title": article["title"], "body": "## 합성 자료\n\n실제 뉴스가 아닌 기능검증 자료입니다. 외부 게시 금지.", "evidence": article["evidence"], "quality": {"status": "passed", "critical": False, "note": "Synthetic seeded status; no model evaluation"}, "video": {"title": "합성 자료 승인 검증", "description": "실제 뉴스 아님 · 외부 게시 금지", "scenes": [{"narration": "기능검증용 합성 자료입니다.", "caption": "합성 자료 · 외부 게시 금지", "visual": "explanation", "source_url": article["url"], "evidence_ids": ["SYNTH-E1"]}], "thumbnails": [{"title": "합성 자료 승인 검증", "subtitle": "외부 게시 금지", "angle": "기능검증"} for _ in range(5)]}}
        seeded = store.save_source(job_id, packet)
        selections = {"blog": True, "video": video, "pdf": False, "cards": False}
        approved = client.post(f"/api/jobs/{job_id}/reviews/source", json={"version": seeded["source_hash"], "decision": "approved", "selections": selections}, headers=headers)
        assert approved.status_code == 200
        assert client.post(f"/api/jobs/{job_id}/produce", json={}, headers=headers).status_code == 202
        assert [task["kind"] for task in store.tasks(job_id)] == ["produce"]
        assert run_once(store, "synthetic-test-worker")
        tasks_by_kind = {task["kind"]: task for task in store.tasks(job_id)}
        assert tasks_by_kind["produce"]["state"] == "completed", store.tasks(job_id)
        # 제작과 함께 같은 원고의 퀴즈·카드뉴스가 자동으로 줄을 선다(모델 호출은 아직 없음)
        assert {tasks_by_kind["quiz"]["state"], tasks_by_kind["cards"]["state"]} == {"queued"}
        produced = client.get(f"/api/jobs/{job_id}").json()
        manifest = produced["manifest"]
        assert produced["state"] == "release_review"
        assert client.get(f"/api/jobs/{job_id}/package").status_code == 409
        if video:
            assert shutil.which("ffmpeg") and shutil.which("powershell.exe")
            assert "Heami" in manifest["media"]["voice"]
            assert manifest["media"]["resolution"] == [1080, 1920]
            assert 0 < manifest["media"]["duration"] <= 60
            assert len(manifest["thumbnail_candidates"]) == 5
            assert client.post(f"/api/jobs/{job_id}/reviews/release", json={"version": manifest["hash"], "decision": "approved", "media_reviewed": True}, headers=headers).status_code == 409
            selected = client.post(f"/api/jobs/{job_id}/thumbnail", json={"artifact_id": manifest["thumbnail_candidates"][1]["id"]}, headers=headers)
            assert selected.status_code == 200
            changed = selected.json()["manifest"]
            assert changed["hash"] != manifest["hash"]
            assert client.post(f"/api/jobs/{job_id}/reviews/release", json={"version": manifest["hash"], "decision": "approved", "media_reviewed": True}, headers=headers).status_code == 409
            manifest = changed
            assert client.post(f"/api/jobs/{job_id}/reviews/release", json={"version": manifest["hash"], "decision": "approved"}, headers=headers).status_code == 409
        release = client.post(f"/api/jobs/{job_id}/reviews/release", json={"version": manifest["hash"], "decision": "approved", "media_reviewed": video}, headers=headers)
        assert release.status_code == 200
        download = client.get(f"/api/jobs/{job_id}/package")
        assert download.status_code == 200
        with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
            assert set(archive.namelist()) == {f["name"] for f in manifest["files"]} | {"handoff.json"}
            for record in manifest["files"]:
                assert hashlib.sha256(archive.read(record["name"])).hexdigest() == record["sha256"]
            handoff = json.loads(archive.read("handoff.json"))
            assert handoff["external_published"] is False
            assert handoff["release"]["version"] == manifest["hash"]
            assert handoff["source_hash"] == seeded["source_hash"]
        # A fresh app/store must read the same durable job and approvals.
        with TestClient(create_app(Store(store.root)), base_url="http://localhost:8510") as restarted:
            assert restarted.get(f"/api/jobs/{job_id}").json()["release_approval"] == release.json()["release_approval"]
        edited = client.put(f"/api/jobs/{job_id}/source", json={"version": seeded["source_hash"], "packet": {**packet, "body": packet["body"] + "\n\n합성 수정."}}, headers=headers)
        assert edited.status_code == 200
        assert edited.json()["source_approval"] is None
        assert edited.json()["release_approval"] is None
        assert client.post(f"/api/jobs/{job_id}/reviews/source", json={"version": seeded["source_hash"], "decision": "approved", "selections": selections}, headers=headers).status_code == 409
        assert client.post(f"/api/jobs/{job_id}/produce", json={}, headers=headers).status_code == 409
        assert client.get(f"/api/jobs/{job_id}/package").status_code == 409
        assert store.budget()["spent_krw"] == store.budget()["reserved_krw"] == 0
        with store.connection() as db:
            assert db.execute("SELECT count(*) FROM costs").fetchone()[0] == 0
