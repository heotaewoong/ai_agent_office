"""상품·쿠폰 스냅샷은 새 원고 판본을 요구하고 스토어·쿠폰 API는 호출하지 않는다."""
import pytest
from fastapi.testclient import TestClient

from office.api import create_app
from office.store import Store, WorkflowError
from tests.test_youtube_delivery import released_fixture


def api(store):
    client = TestClient(create_app(store), base_url="http://localhost:8510")
    token = client.get("/api/session").json()["csrf"]
    return client, {"Origin": "http://localhost:3110", "X-Office-CSRF": token}


def test_set_offer_requires_https_and_records_actor(tmp_path):
    store = Store(tmp_path)
    job = store.create_job({"id": "offer-test", "title": "오퍼 시험"})
    client, headers = api(store)
    bad = client.put(f"/api/jobs/{job['id']}/offer", json={"expected_offer_hash": None, "product": "D-30 플래너", "price_krw": 9900, "url": "http://heobrain.kr/planner"}, headers=headers)
    assert bad.status_code == 409
    assert "offer" not in store.job(job["id"])
    empty = client.put(f"/api/jobs/{job['id']}/offer", json={"expected_offer_hash": None, "product": "   ", "price_krw": None, "url": None, "note": None}, headers=headers)
    assert empty.status_code == 409
    ok = client.put(f"/api/jobs/{job['id']}/offer", json={"expected_offer_hash": None, "product": "D-30 플래너", "price_krw": 9900, "url": "https://heobrain.kr/planner", "note": "첫 달 안내"}, headers=headers)
    assert ok.status_code == 200
    offer = ok.json()["offer"]
    assert offer["product"] == "D-30 플래너" and offer["price_krw"] == 9900 and offer["url"] == "https://heobrain.kr/planner" and offer["note"] == "첫 달 안내"
    assert offer["captured_at"] and offer["actor"] == "local-operator"
    assert store.job(job["id"])["offer"] == offer
    cleared = client.delete(f"/api/jobs/{job['id']}/offer", params={"expected_offer_hash": ok.json()["offer_hash"]}, headers=headers)
    assert cleared.status_code == 200 and "offer" not in cleared.json()
    kinds = [e["kind"] for e in store.events(job["id"])]
    assert kinds.index("offer_cleared") < kinds.index("offer_set")


def test_offer_changes_content_version_and_invalidates_current_approvals(tmp_path):
    store, job_id = released_fixture(tmp_path)
    before = store.job(job_id)
    job = store.set_offer(job_id, {"product": "오픽 7일 연습표", "price_krw": None, "url": None, "note": None}, actor="op")
    assert job["offer"]["product"] == "오픽 7일 연습표" and job["offer"]["price_krw"] is None
    assert job["release_approval"] is None and job["source_approval"] is None and job["manifest"] is None
    assert job["source_hash"] != before["source_hash"] and job["source_packet"]["quality"]["status"] == "unverified"
    assert store.events(job_id) and before["release_approval"] is not None
    with pytest.raises(WorkflowError):
        store.set_offer(job_id, {"product": "x", "price_krw": -1, "url": None, "note": None}, actor="op")
    with pytest.raises(WorkflowError):
        store.set_offer(job_id, {"product": "x", "price_krw": None, "url": None, "note": None}, actor="")


def test_blog_export_adds_offer_line_only_when_offer_exists(tmp_path):
    from office.exports import blog_markdown, write_blog_exports
    packet = {"title": "원고", "body": "## 핵심\n\n본문입니다.", "evidence": [{"id": "E1", "url": "https://example.com/a", "claim": "근거"}]}
    plain = blog_markdown(packet)
    assert "함께 보기" not in plain and blog_markdown(packet, None) == plain
    offer = {"product": "D-30 플래너", "price_krw": 9900, "url": "https://heobrain.kr/planner", "note": "첫 달 안내", "captured_at": "2026-10-29T00:00:00+00:00", "actor": "op"}
    with_offer = blog_markdown(packet, offer)
    assert with_offer.startswith(plain) and "함께 보기" in with_offer and "D-30 플래너" in with_offer and "9,900원" in with_offer and "https://heobrain.kr/planner" in with_offer
    files = write_blog_exports(packet, tmp_path / "with", offer) if (tmp_path / "with").mkdir() is None else None
    assert "함께 보기" in (tmp_path / "with" / "tistory.md").read_text(encoding="utf-8")
    assert "D-30 플래너" in (tmp_path / "with" / "naver.txt").read_text(encoding="utf-8")
    (tmp_path / "without").mkdir()
    write_blog_exports(packet, tmp_path / "without")
    assert "함께 보기" not in (tmp_path / "without" / "tistory.md").read_text(encoding="utf-8")


def test_media_produce_passes_job_offer_to_blog_export(tmp_path, monkeypatch):
    from office import media
    from tests.test_media import approved_job
    store, job_id = approved_job(tmp_path, video=False, cards=False)
    store.set_offer(job_id, {"product": "오픽 7일 연습표", "price_krw": None, "url": "https://heobrain.kr/opic", "note": None}, actor="op")
    reapprove_campaign_fixture(store, job_id)
    seen = {}
    real = media.write_blog_exports

    def capture(packet, folder, offer=None):
        seen["offer"] = offer
        return real(packet, folder, offer)
    monkeypatch.setattr(media, "write_blog_exports", capture)
    manifest = media.produce(store, job_id)
    assert seen["offer"]["product"] == "오픽 7일 연습표"
    blog = next(f for f in manifest["files"] if f["name"] == "tistory.md")
    assert "함께 보기" in (store.artifacts / blog["path"]).read_text(encoding="utf-8")


def reapprove_campaign_fixture(store, job_id):
    """Synthetic unit fixture only: explicit new source/release reviews, no renderer or publishing."""
    from office.offers import campaign_packet
    from office.store import digest
    job = store.job(job_id)
    packet = campaign_packet(job["source_packet"], job.get("offer"))
    packet["quality"] = {"status": "passed", "critical": False}
    current = store.save_source(job_id, packet, expected_hash=job["source_hash"])
    store.review_source(job_id, current["source_hash"], "approved", "fixture-operator")
    manifest = {"source_hash": current["source_hash"], "files": [], "completed_outputs": ["blog"]}
    manifest["hash"] = digest(manifest)
    store.save_manifest_if_current(job_id, current["source_hash"], current["selections"], manifest)
    store.review_release(job_id, manifest["hash"], "approved", "fixture-operator", outputs=["blog"])
    return store.job(job_id)


def test_offer_cas_and_missing_tokens_reject_stale_save_delete(tmp_path):
    store = Store(tmp_path)
    job = store.create_job({"id": "offer-cas", "title": "CAS"})
    client, headers = api(store)
    url = f"/api/jobs/{job['id']}/offer"
    body = {"product": "합성 상품", "price_krw": 9900, "url": "https://example.invalid/item"}
    assert client.put(url, json=body, headers=headers).status_code == 422
    first = client.put(url, json={**body, "expected_offer_hash": None}, headers=headers)
    assert first.status_code == 200
    token = first.json()["offer_hash"]
    second = client.put(url, json={**body, "product": "합성 상품 새 판", "expected_offer_hash": token}, headers=headers)
    assert second.status_code == 200 and second.json()["offer_hash"] != token
    assert client.put(url, json={**body, "expected_offer_hash": token}, headers=headers).status_code == 409
    assert client.delete(url, headers=headers).status_code == 422
    assert client.delete(url, params={"expected_offer_hash": token}, headers=headers).status_code == 409
    assert store.job(job["id"])["offer"]["product"] == "합성 상품 새 판"


def coupon_offer(**changes):
    from datetime import datetime, timedelta, timezone
    value = {"product": "합성 편입 단어장", "price_krw": 9900, "url": "https://example.invalid/item", "coupon": {"code": "FIXTURE50", "discount_percent": 50, "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(), "terms": "합성 시험 조건 · 실제 발급 아님", "verified": True}}
    value["coupon"].update(changes)
    return value


def test_unverified_coupon_can_be_recorded_but_not_generated_or_approved(tmp_path):
    from office.editorial import prepare_source
    from office import media
    store, job_id = released_fixture(tmp_path)
    current = store.set_offer(job_id, coupon_offer(code=None, expires_at=None, terms=None, verified=False), "op")
    before = store.events(job_id)
    class ForbiddenProvider:
        def generate(self, *args, **kwargs):
            raise AssertionError("No provider call for an unconfirmed coupon")
    with pytest.raises(WorkflowError, match="미확인"):
        prepare_source(store, job_id, provider=ForbiddenProvider())
    assert store.events(job_id) == before
    with pytest.raises(WorkflowError, match="미확인"):
        store.review_source(job_id, current["source_hash"], "approved", "op")
    with pytest.raises(WorkflowError, match="미확인"):
        media.produce(store, job_id)


def test_coupon_requires_complete_future_conditions_and_rechecks_expiry(tmp_path, monkeypatch):
    from office import offers
    from datetime import datetime, timedelta, timezone
    store, job_id = released_fixture(tmp_path)
    for patch in ({"code": None}, {"terms": None}, {"expires_at": None}, {"expires_at": "2020-01-01T00:00:00Z"}, {"discount_percent": 101}):
        with pytest.raises(WorkflowError):
            store.set_offer(job_id, coupon_offer(**patch), "op")
    saved = store.set_offer(job_id, coupon_offer(), "op")
    source = reapprove_campaign_fixture(store, job_id)
    original = source["source_hash"]
    class FutureDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(timezone.utc) + timedelta(days=2)
    monkeypatch.setattr(offers, "datetime", FutureDateTime)
    with pytest.raises(WorkflowError, match="기간"):
        store.require_source_approval(job_id)
    assert store.job(job_id)["source_hash"] == original


def test_campaign_cta_is_reviewable_idempotent_and_exports_coupon_details(tmp_path):
    from office.offers import campaign_packet, offer_text
    from office.exports import write_video_exports
    offer = coupon_offer()
    packet = {"title": "합성 시험", "body": "합성 본문", "video": {"title": "영상", "description": "합성 설명", "scenes": [{"narration": "본문을 설명해요.", "caption": "본문"}]}}
    promoted = campaign_packet(packet, offer)
    assert len(promoted["video"]["scenes"]) == 2
    assert "50퍼센트" in promoted["video"]["scenes"][-1]["narration"]
    assert "FIXTURE50" in promoted["video"]["scenes"][-1]["caption"]
    assert campaign_packet(promoted, offer) == promoted
    cleared = campaign_packet(promoted, None)
    assert len(cleared["video"]["scenes"]) == 1 and not cleared.get("campaign_offer_hash")
    text = offer_text(offer)
    assert "4,950원" in text and "실제 결제금액은 스토어 확인" in text
    write_video_exports(promoted, tmp_path, offer)
    desc = (tmp_path / "description.txt").read_text(encoding="utf-8")
    assert all(token in desc for token in ("FIXTURE50", "50%", "4,950원", "사용기한", "합성 시험 조건", "https://example.invalid/item"))


def test_old_source_or_render_cannot_return_after_offer_changes(tmp_path):
    from office.offers import campaign_packet
    store, job_id = released_fixture(tmp_path)
    before = store.job(job_id)
    changed = store.set_offer(job_id, coupon_offer(), "op")
    with pytest.raises(WorkflowError, match="버전"):
        store.save_source(job_id, before["source_packet"], expected_hash=before["source_hash"])
    with pytest.raises(WorkflowError):
        store.save_manifest_if_current(job_id, before["source_hash"], before["selections"], before["manifest"])
    with pytest.raises(WorkflowError, match="반영"):
        store.review_source(job_id, changed["source_hash"], "approved", "op")
    packet = campaign_packet(changed["source_packet"], changed["offer"])
    packet["quality"] = {"status": "passed", "critical": False}
    current = store.save_source(job_id, packet, expected_hash=changed["source_hash"])
    approved = store.review_source(job_id, current["source_hash"], "approved", "op")
    same = store.set_offer(job_id, coupon_offer(expires_at=changed["offer"]["coupon"]["expires_at"]), "op", expected_hash=approved["offer_hash"])
    assert same["source_hash"] == approved["source_hash"] and same["source_approval"] == approved["source_approval"]


def test_http_coupon_to_queue_worker_handoff_and_edit_invalidation(tmp_path, monkeypatch):
    """Temp DB + deterministic blog exports only, no real approvals/accounts or provider calls."""
    import io
    import json
    import zipfile
    from office.offers import campaign_packet
    from office.worker import run_once
    from tests.test_media import approved_job
    def forbidden(*args, **kwargs):
        pytest.fail("No external provider or upload in the synthetic HTTP workflow")
    monkeypatch.setattr("office.providers.requests.post", forbidden)
    monkeypatch.setattr("office.worker.prepare_source", forbidden)
    store, job_id = approved_job(tmp_path, video=False)
    client, headers = api(store)
    route = f"/api/jobs/{job_id}"
    offer = coupon_offer()
    recorded = client.put(route + "/offer", json={**offer, "expected_offer_hash": None}, headers=headers)
    assert recorded.status_code == 200
    job = recorded.json()
    assert client.post(route + "/produce", json={}, headers=headers).status_code == 409
    packet = campaign_packet(job["source_packet"], job["offer"])
    packet["quality"] = {"status": "passed", "critical": False, "note": "Synthetic seeded quality, no model evaluation"}
    seeded = store.save_source(job_id, packet, expected_hash=job["source_hash"])
    review = client.post(route + "/reviews/source", json={"version": seeded["source_hash"], "decision": "approved"}, headers=headers)
    assert review.status_code == 200
    queued = client.post(route + "/produce", json={}, headers=headers)
    assert queued.status_code == 202
    assert run_once(store, "synthetic-coupon-worker")
    produced_task = store.task(queued.json()["id"])
    assert produced_task["state"] == "completed", produced_task
    produced = client.get(route).json()
    manifest = produced["manifest"]
    assert manifest["production_contract"]["hash"] == queued.json()["payload"]["production_contract"]
    assert manifest["offer_snapshot"]["coupon"]["code"] == "FIXTURE50"
    assert client.get(route + "/package").status_code == 409
    released = client.post(route + "/reviews/release", json={"version": manifest["hash"], "decision": "approved", "outputs": ["blog"]}, headers=headers)
    assert released.status_code == 200
    bundle = client.get(route + "/package")
    assert bundle.status_code == 200
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        handoff = json.loads(archive.read("channel-handoff.json"))
        assert handoff["source_hash"] == seeded["source_hash"]
        assert "FIXTURE50" in archive.read("threads-main.txt").decode()
        assert "credentials_configured" not in json.dumps(manifest["production_contract"])
    changed = client.put(route + "/offer", json={**coupon_offer(discount_percent=40), "expected_offer_hash": produced["offer_hash"]}, headers=headers)
    assert changed.status_code == 200
    assert changed.json()["source_approval"] is None and changed.json()["release_approval"] is None
    assert client.get(route + "/package").status_code == 409
    assert store.budget()["spent_krw"] == store.budget()["reserved_krw"] == 0
