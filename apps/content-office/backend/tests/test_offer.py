"""상품 오퍼 스냅샷: 작업에 붙는 안내 정보. 승인①②를 건드리지 않고 스토어·쿠폰 API는 호출하지 않는다."""
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
    bad = client.put(f"/api/jobs/{job['id']}/offer", json={"product": "D-30 플래너", "price_krw": 9900, "url": "http://heobrain.kr/planner"}, headers=headers)
    assert bad.status_code == 409
    assert "offer" not in store.job(job["id"])
    empty = client.put(f"/api/jobs/{job['id']}/offer", json={"product": "   ", "price_krw": None, "url": None, "note": None}, headers=headers)
    assert empty.status_code == 409
    ok = client.put(f"/api/jobs/{job['id']}/offer", json={"product": "D-30 플래너", "price_krw": 9900, "url": "https://heobrain.kr/planner", "note": "첫 달 안내"}, headers=headers)
    assert ok.status_code == 200
    offer = ok.json()["offer"]
    assert offer["product"] == "D-30 플래너" and offer["price_krw"] == 9900 and offer["url"] == "https://heobrain.kr/planner" and offer["note"] == "첫 달 안내"
    assert offer["captured_at"] and offer["actor"] == "local-operator"
    assert store.job(job["id"])["offer"] == offer
    cleared = client.delete(f"/api/jobs/{job['id']}/offer", headers=headers)
    assert cleared.status_code == 200 and "offer" not in cleared.json()
    kinds = [e["kind"] for e in store.events(job["id"])]
    assert kinds.index("offer_cleared") < kinds.index("offer_set")


def test_offer_does_not_touch_approvals(tmp_path):
    store, job_id = released_fixture(tmp_path)
    before = store.job(job_id)
    job = store.set_offer(job_id, {"product": "오픽 7일 연습표", "price_krw": None, "url": None, "note": None}, actor="op")
    assert job["offer"]["product"] == "오픽 7일 연습표" and job["offer"]["price_krw"] is None
    assert job["release_approval"] == before["release_approval"] and job["source_approval"] == before["source_approval"] and job["state"] == before["state"]
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
