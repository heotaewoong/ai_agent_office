"""리드마그넷 동의 장부: 이메일은 전용 표에만, 목록·요약은 마스킹·건수만. 자동 발송 없음."""
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from office.api import create_app
from office.store import Store, WorkflowError


@pytest.fixture
def context(tmp_path):
    store = Store(tmp_path)
    client = TestClient(create_app(store), base_url="http://localhost:8510")
    token = client.get("/api/session").json()["csrf"]
    return store, client, {"Origin": "http://localhost:3110", "X-Office-CSRF": token}


def lead_body(email="Test.Reader@Example.com", magnet="d30-planner", source="homepage"):
    return {"email": email, "magnet_key": magnet, "source": source, "consent_version": "2026-10-v1", "consent_text": "무료 자료와 뉴스레터 수신에 동의합니다"}


def test_register_lead_masks_email_and_stores_lowercase(context):
    store, client, headers = context
    response = client.post("/api/leads", json=lead_body(), headers=headers)
    assert response.status_code == 201
    lead = response.json()["lead"]
    assert lead["email_masked"] == "t***@example.com"
    assert "email" not in lead
    assert lead["magnet_key"] == "d30-planner" and lead["source"] == "homepage"
    assert lead["consent"]["version"] == "2026-10-v1" and lead["consent"]["granted_at"] and lead["consent"]["withdrawn_at"] is None
    assert lead["delivery"] == {"state": "pending", "sent_at": None}
    db = sqlite3.connect(store.db_path)
    rows = db.execute("SELECT email FROM leads").fetchall()
    db.close()
    assert rows == [("test.reader@example.com",)]


def test_same_email_and_magnet_is_idempotent_case_insensitive(context):
    _, client, headers = context
    first = client.post("/api/leads", json=lead_body(), headers=headers)
    second = client.post("/api/leads", json=lead_body(email="TEST.READER@example.com"), headers=headers)
    assert first.status_code == 201 and second.status_code == 200
    assert first.json()["lead"]["id"] == second.json()["lead"]["id"]
    other = client.post("/api/leads", json=lead_body(magnet="opic-7days"), headers=headers)
    assert other.status_code == 201 and other.json()["lead"]["id"] != first.json()["lead"]["id"]


def test_invalid_email_source_or_magnet_is_rejected(context):
    store, client, headers = context
    assert client.post("/api/leads", json=lead_body(email="not-an-email"), headers=headers).status_code == 409
    assert client.post("/api/leads", json=lead_body(source="tiktok"), headers=headers).status_code == 422
    assert client.post("/api/leads", json=lead_body(magnet="has space"), headers=headers).status_code == 409
    assert client.get("/api/leads").json()["leads"] == []
    from office.leads import register_lead
    with pytest.raises(WorkflowError, match="이메일"):
        register_lead(store, email="a@b", magnet_key="x", source="homepage", consent_version="v1", consent_text="동의")


def test_withdraw_sent_summary_and_list_never_expose_email(context):
    store, client, headers = context
    one = client.post("/api/leads", json=lead_body(email="one@example.com"), headers=headers).json()["lead"]
    two = client.post("/api/leads", json=lead_body(email="two@example.com", magnet="opic-7days", source="youtube"), headers=headers).json()["lead"]
    withdrawn = client.post(f"/api/leads/{one['id']}/withdraw", json={}, headers=headers)
    assert withdrawn.status_code == 200 and withdrawn.json()["lead"]["consent"]["withdrawn_at"]
    sent = client.post(f"/api/leads/{two['id']}/sent", json={}, headers=headers)
    assert sent.status_code == 200
    assert sent.json()["lead"]["delivery"]["state"] == "sent_manual" and sent.json()["lead"]["delivery"]["sent_at"]
    summary = client.get("/api/leads/summary").json()
    assert summary == {"total": 2, "consented": 1, "withdrawn": 1, "by_magnet": {"d30-planner": 1, "opic-7days": 1}, "by_source": {"homepage": 1, "youtube": 1}}
    listing = client.get("/api/leads").json()
    assert [lead["id"] for lead in listing["leads"]] == [two["id"], one["id"]]
    text = json.dumps(listing) + json.dumps(summary)
    assert "one@example.com" not in text and "two@example.com" not in text
    assert listing["leads"][0]["email_masked"] == "t***@example.com"
    assert client.post("/api/leads/lead_missing/withdraw", json={}, headers=headers).status_code == 409


def test_emails_live_only_in_the_leads_table(context):
    store, client, headers = context
    client.post("/api/leads", json=lead_body(email="secret@example.com"), headers=headers)
    db = sqlite3.connect(store.db_path)
    for table in ("events", "settings", "jobs", "cache"):
        blob = json.dumps([tuple(r) for r in db.execute(f"SELECT * FROM {table}").fetchall()], ensure_ascii=False)
        assert "secret@example.com" not in blob, table
    db.close()
    kinds = [e["kind"] for e in store.events()]
    assert "lead_registered" in kinds


def test_newsletter_snapshot_deduplicates_email_without_changing_lead_summary(context):
    from office.leads import consent_snapshot
    from office.store import digest

    store, client, headers = context
    first = client.post("/api/leads", json=lead_body(email="same@example.com", magnet="one"), headers=headers).json()["lead"]
    initial = consent_snapshot(store)
    other = client.post("/api/leads", json=lead_body(email="SAME@example.com", magnet="two"), headers=headers).json()["lead"]
    duplicate = consent_snapshot(store)
    assert initial["recipient_count"] == duplicate["recipient_count"] == 1
    assert initial["recipients_hash"] != duplicate["recipients_hash"]
    assert duplicate["recipients_hash"] != digest(sorted([first["id"], other["id"]]))
    assert client.get("/api/leads/summary").json()["consented"] == 2
    assert len(client.get("/api/leads").json()["leads"]) == 2
    assert "same@example.com" not in json.dumps(duplicate) and first["id"] not in json.dumps(duplicate)
    client.post(f"/api/leads/{first['id']}/withdraw", json={}, headers=headers)
    withdrawn_duplicate = consent_snapshot(store)
    assert withdrawn_duplicate["recipient_count"] == 1 and withdrawn_duplicate["recipients_hash"] != duplicate["recipients_hash"]
    client.post(f"/api/leads/{other['id']}/withdraw", json={}, headers=headers)
    assert consent_snapshot(store)["recipient_count"] == 0
