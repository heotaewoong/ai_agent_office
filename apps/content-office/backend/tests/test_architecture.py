"""구조도 화면: 저장소 문서 + 서버가 채우는 실행 사실(커밋·배포·테스트·키·비용)."""
import json

import pytest

from office.store import Store, WorkflowError


def test_repository_doc_has_every_section_and_the_four_human_gates():
    from office.architecture import load_doc
    doc = load_doc()
    gates = [step["mark"] for step in doc["flow"] if step["kind"] == "gate"]
    assert gates == ["⓪", "①", "②", "③"]
    assert all(step["title"] and step["items"] for step in doc["flow"] if step["kind"] == "stage")
    assert {"card_image", "gen", "korean"} <= {row["role"] for row in doc["unit_costs"]}
    assert doc["rails"] and doc["status"]


def test_broken_doc_is_reported(tmp_path):
    from office.architecture import load_doc
    path = tmp_path / "a.json"
    path.write_text('{"headline": "x"}', encoding="utf-8")
    with pytest.raises(WorkflowError, match="summary|flow"):
        load_doc(path)


def test_test_summaries_are_parsed():
    from office.architecture import parse_node_test, parse_pytest
    assert parse_pytest("434 passed, 7 skipped in 46.84s") == {"passed": 434, "failed": 0, "skipped": 7, "errors": 0}
    assert parse_pytest("2 failed, 421 passed, 16 skipped in 33.5s")["failed"] == 2
    assert parse_node_test("ℹ tests 54\nℹ pass 54\nℹ fail 0") == {"passed": 54, "failed": 0}


def test_usage_sums_model_events_and_image_receipts(tmp_path):
    from office.architecture import usage
    store = Store(tmp_path)
    store.event("model_completed", {"role": "gen", "model": "gpt-5.4-mini", "estimated_krw": 22.5})
    store.event("model_completed", {"role": "gen", "model": "gpt-5.4-mini", "estimated_krw": 20.0})
    store.event("model_completed", {"role": "card_ko", "model": "gemini-3.5-flash-lite", "estimated_krw": 1.0})
    assets = store.root / "image-assets"
    assets.mkdir()
    (assets / "a.json").write_text(json.dumps({"status": "complete", "card_index": 0, "estimated_krw": 28.4, "image_metadata": {"model": "gpt-image-2.5-flare"}}), encoding="utf-8")
    (assets / "b.json").write_text(json.dumps({"status": "received", "card_index": 1, "estimated_krw": 99}), encoding="utf-8")
    rows = {(r["role"], r["model"]): r for r in usage(store)}
    assert rows[("gen", "gpt-5.4-mini")] == {"role": "gen", "model": "gpt-5.4-mini", "calls": 2, "krw": 42.5, "per_call": 21.2}
    assert rows[("card_image", "gpt-image-2.5-flare")]["calls"] == 1
    assert ("card_image", "?") not in rows  # 끝나지 않은 영수증은 세지 않는다


def test_overview_reports_build_keys_and_never_key_values(tmp_path, monkeypatch):
    from office.architecture import git_info, overview, record_build_info
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value")
    monkeypatch.delenv("RUNWAYML_API_SECRET", raising=False)
    store = Store(tmp_path)
    record_build_info(store.root, backend_summary="434 passed, 7 skipped in 46.84s", frontend_summary="ℹ pass 54\nℹ fail 0")
    data = overview(store)
    assert data["keys"]["openai"] is True and data["keys"]["runway"] is False
    assert "sk-secret-value" not in json.dumps(data, ensure_ascii=False)
    assert data["build"]["tests"]["backend"]["passed"] == 434 and data["build"]["tests"]["frontend"]["passed"] == 54
    assert data["doc"]["flow"] and data["profiles"]["text"]
    if git_info()["commit"]:
        assert data["build_matches_running_code"] is True and data["git"]["recent"]


def test_api_route(tmp_path):
    from fastapi.testclient import TestClient
    from office.api import create_app
    client = TestClient(create_app(Store(tmp_path)), base_url="http://localhost:8510")
    client.get("/api/session")
    body = client.get("/api/architecture").json()
    assert body["doc"]["headline"] and "usage" in body and "keys" in body
