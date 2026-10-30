"""공개 리드 신청: 운영자 세션 없이 열리는 경로는 POST /api/public/leads·GET /api/public/magnets 두 개뿐이다.

- 동의 문구는 서버 카탈로그가 정하고, 장부 저장·마스킹·멱등은 leads.register_lead와 같다.
- 응답은 이미 신청한 이메일인지 드러내지 않는다. 원본 IP는 어디에도 저장하지 않는다.
"""
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from office import public_leads
from office.api import create_app
from office.store import Store

PUBLIC = "https://office.example.kr"
HOMEPAGE = "https://www.heobrain.kr"
SUCCESS = {"status": "received", "message": "신청을 받았어요. 자료는 운영자가 확인 후 이메일로 보내 드려요."}


@pytest.fixture
def office(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFICE_PUBLIC_ORIGIN", PUBLIC)
    monkeypatch.setenv("OFFICE_LEAD_ALLOWED_ORIGINS", HOMEPAGE)
    store = Store(tmp_path / "state")
    app = create_app(store)
    return store, app


@pytest.fixture
def client(office):
    return TestClient(office[1], base_url="http://localhost:8510")


def current():
    return next(m for m in public_leads.load_catalog() if m["key"] == "exam-d30-planner")


def body(email="Reader.One@Example.com", **patch):
    magnet = current()
    payload = {"email": email, "magnet_key": magnet["key"], "source": "youtube", "consent_version": magnet["consent_version"], "consent_checked": True, "hp": ""}
    payload.update(patch)
    return payload


def post(client, payload, origin=PUBLIC, **headers):
    if origin is not None:
        headers["Origin"] = origin
    return client.post("/api/public/leads", json=payload, headers=headers)


def lead_rows(store):
    db = sqlite3.connect(store.db_path)
    try:
        return db.execute("SELECT email, magnet_key, data FROM leads").fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        db.close()


def dump_db(store):
    db = sqlite3.connect(store.db_path)
    try:
        lines = []
        for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            lines.extend(repr(row) for row in db.execute(f"SELECT * FROM {name}"))
        return "\n".join(lines)
    finally:
        db.close()


def events(store, kind):
    return [event for event in store.events(limit=200) if event["kind"] == kind]


def test_catalog_has_the_d30_planner_draft_and_public_list_hides_private_entries(client, monkeypatch, tmp_path):
    magnet = current()
    assert magnet["title"] == "시험 D-30 복습 플래너" and magnet["public"] is True
    for phrase in ("이메일", "1년", "철회", "거부"):
        assert phrase in magnet["consent_text"]
    response = client.get("/api/public/magnets")
    assert response.status_code == 200
    listed = response.json()["magnets"]
    assert {m["key"] for m in listed} >= {"exam-d30-planner"}
    assert set(listed[0]) == {"key", "title", "description", "consent_version", "consent_text"}
    catalog = tmp_path / "magnets.json"
    catalog.write_text(json.dumps([{**magnet, "key": "hidden-one", "public": False}, magnet], ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(public_leads, "CATALOG_PATH", catalog)
    assert [m["key"] for m in client.get("/api/public/magnets").json()["magnets"]] == ["exam-d30-planner"]
    assert "count" not in json.dumps(client.get("/api/public/magnets").json())


def test_happy_path_stores_masked_lead_with_server_consent_text_and_event_without_email(office, client):
    store, _ = office
    response = post(client, body())
    assert response.status_code == 202 and response.json() == SUCCESS
    assert response.headers["cache-control"] == "no-store"
    rows = lead_rows(store)
    assert len(rows) == 1 and rows[0][0] == "reader.one@example.com" and rows[0][1] == "exam-d30-planner"
    data = json.loads(rows[0][2])
    assert data["source"] == "youtube"
    assert data["consent"]["version"] == current()["consent_version"] and data["consent_text"] == current()["consent_text"]
    signup = events(store, "lead_public_signup")
    assert [e["data"] for e in signup] == [{"magnet_key": "exam-d30-planner", "source": "youtube"}]
    assert "reader.one" not in json.dumps(store.events(limit=200)).lower()
    listing = TestClient(office[1], base_url="http://localhost:8510").get("/api/leads").json()["leads"]
    assert listing[0]["email_masked"] == "r***@example.com" and "email" not in listing[0]


def test_homepage_origin_and_new_sources_are_accepted(office, client):
    store, _ = office
    for index, source in enumerate(("homepage", "blog", "newsletter", "threads")):
        assert post(client, body(f"r{index}@example.com", source=source), origin=HOMEPAGE).status_code == 202
    assert len(lead_rows(store)) == 4


def test_duplicate_email_gets_identical_response_and_one_row(office, client):
    store, _ = office
    first = post(client, body())
    second = post(client, body("READER.ONE@example.com"))
    assert first.status_code == second.status_code == 202
    assert first.content == second.content
    assert len(lead_rows(store)) == 1


def test_honeypot_answers_like_success_but_stores_nothing(office, client):
    store, _ = office
    response = post(client, body(hp="https://spam.example"))
    assert response.status_code == 202 and response.json() == SUCCESS
    assert lead_rows(store) == [] and events(store, "lead_public_signup") == []


@pytest.mark.parametrize("origin", [None, "https://evil.example", "http://www.heobrain.kr", "https://www.heobrain.kr.evil.example"])
def test_bad_or_missing_origin_is_rejected(office, client, origin):
    store, _ = office
    assert post(client, body(), origin=origin).status_code == 403
    assert lead_rows(store) == []


@pytest.mark.parametrize("patch", [
    {"consent_checked": False},
    {"consent_checked": "true"},
    {"consent_version": "2020-01-old"},
    {"magnet_key": "no-such-magnet"},
    {"source": "tiktok"},
    {"email": "not-an-email"},
    {"consent_text": "클라이언트가 바꾼 동의 문구"},
])
def test_invalid_submissions_are_rejected_and_store_nothing(office, client, patch):
    store, _ = office
    response = post(client, body(**patch))
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)
    assert lead_rows(store) == []


def test_missing_consent_field_is_rejected(office, client):
    store, _ = office
    payload = body()
    del payload["consent_checked"]
    assert post(client, payload).status_code == 422
    assert lead_rows(store) == []


def test_non_public_magnet_is_rejected(office, client, monkeypatch, tmp_path):
    store, _ = office
    catalog = tmp_path / "magnets.json"
    catalog.write_text(json.dumps([{**current(), "public": False}], ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(public_leads, "CATALOG_PATH", catalog)
    assert post(client, body()).status_code == 422
    assert lead_rows(store) == []


def test_oversized_body_is_rejected(office, client):
    store, _ = office
    response = client.post("/api/public/leads", content=json.dumps(body(hp="", email="a@example.com")) + " " * 5000, headers={"Origin": PUBLIC, "Content-Type": "application/json"})
    assert response.status_code == 413
    assert lead_rows(store) == []


def test_rate_limit_per_ip_hour_and_day(office, monkeypatch):
    store, app = office
    proxy = TestClient(app, base_url="http://localhost:8510", client=("127.0.0.1", 50000))
    clock = [1_800_000_000.0]
    monkeypatch.setattr(public_leads, "clock", lambda: clock[0])
    for index in range(5):
        assert post(proxy, body(f"a{index}@example.com"), **{"X-Forwarded-For": "203.0.113.7"}).status_code == 202
    assert post(proxy, body("a5@example.com"), **{"X-Forwarded-For": "203.0.113.7"}).status_code == 429
    # 다른 독자(IP)는 영향받지 않는다
    assert post(proxy, body("b0@example.com"), **{"X-Forwarded-For": "198.51.100.9"}).status_code == 202
    # 프록시가 덧붙인 오른쪽 주소가 실제 독자다. 왼쪽에 위조한 값은 무시한다
    assert post(proxy, body("a6@example.com"), **{"X-Forwarded-For": "10.9.9.9, 203.0.113.7"}).status_code == 429
    # 시간 한도는 한 시간이 지나면 풀리고, 하루 한도 20건은 남는다
    for hour in range(1, 4):
        clock[0] += 3601
        for index in range(5):
            assert post(proxy, body(f"h{hour}-{index}@example.com"), **{"X-Forwarded-For": "203.0.113.7"}).status_code == 202
    clock[0] += 3601
    assert post(proxy, body("over@example.com"), **{"X-Forwarded-For": "203.0.113.7"}).status_code == 429
    clock[0] += 86400
    assert post(proxy, body("next-day@example.com"), **{"X-Forwarded-For": "203.0.113.7"}).status_code == 202


def test_forwarded_for_is_ignored_unless_the_peer_is_the_local_proxy(office, client, monkeypatch):
    monkeypatch.setattr(public_leads, "clock", lambda: 1_800_000_000.0)
    for index in range(5):
        assert post(client, body(f"x{index}@example.com"), **{"X-Forwarded-For": f"192.0.2.{index}"}).status_code == 202
    assert post(client, body("x5@example.com"), **{"X-Forwarded-For": "192.0.2.99"}).status_code == 429


def test_raw_ip_and_email_never_leave_their_places(office):
    store, app = office
    proxy = TestClient(app, base_url="http://localhost:8510", client=("127.0.0.1", 50000))
    assert post(proxy, body("keep.private@example.com"), **{"X-Forwarded-For": "203.0.113.77"}).status_code == 202
    dump = dump_db(store)
    assert "203.0.113.77" not in dump
    assert dump.count("keep.private@example.com") == 1  # leads 표의 email 열 한 곳
    assert "keep.private" not in json.dumps(store.events(limit=200))


@pytest.mark.parametrize("method,path", [
    ("post", "/api/leads"),
    ("post", "/api/leads/lead_x/withdraw"),
    ("post", "/api/leads/lead_x/sent"),
    ("post", "/api/refresh"),
    ("post", "/api/public/leads/"),
    ("put", "/api/public/leads"),
    ("post", "/api/public/magnets"),
])
def test_other_write_routes_still_require_the_operator_session(office, client, method, path):
    store, _ = office
    response = getattr(client, method)(path, json=body(), headers={"Origin": PUBLIC})
    assert response.status_code == 403
    assert lead_rows(store) == []


def test_homepage_origin_does_not_open_operator_routes(client):
    assert client.get("/api/leads", headers={"Origin": HOMEPAGE}).status_code == 403
    assert client.get("/api/dashboard", headers={"Origin": HOMEPAGE}).status_code == 403
    assert client.post("/api/leads", json=body(), headers={"Origin": HOMEPAGE}).status_code == 403


def test_operator_public_form_route_lists_links_material(client):
    response = client.get("/api/leads/public-form")
    assert response.status_code == 200
    data = response.json()
    assert data["public_origin"] == PUBLIC
    assert "exam-d30-planner" in [m["key"] for m in data["magnets"]]
    assert data["sources"] == ["homepage", "youtube", "instagram", "threads", "blog", "newsletter", "other"]


def test_lead_allowed_origins_must_be_https_origins(monkeypatch):
    monkeypatch.setenv("OFFICE_LEAD_ALLOWED_ORIGINS", "https://www.heobrain.kr, https://heobrain.kr/")
    assert public_leads.lead_allowed_origins() == {"https://www.heobrain.kr", "https://heobrain.kr"}
    for bad in ("http://www.heobrain.kr", "https://*.heobrain.kr", "https://heobrain.kr/path", "https://user@heobrain.kr"):
        monkeypatch.setenv("OFFICE_LEAD_ALLOWED_ORIGINS", bad)
        with pytest.raises(Exception):
            public_leads.lead_allowed_origins()
    monkeypatch.delenv("OFFICE_LEAD_ALLOWED_ORIGINS")
    assert public_leads.lead_allowed_origins() == set()
