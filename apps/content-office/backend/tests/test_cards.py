import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from office import cards as cards_module
from office import worker
from office.api import create_app
from office.brand import load_brand
from office.cards import CARDS_SCHEMA, card_checks, plan_cards
from office.store import Store, WorkflowError

EVIDENCE = [{"id": "E1", "claim": "공식 발표에 따르면 도구는 3가지", "url": "https://example.com/news", "numbers": ["3"]}]


def approved_job(store, approve=True):
    job = store.create_job({"id": "one", "title": "AI 발표", "url": "https://example.com/news", "evidence": EVIDENCE})
    packet = {"title": "AI 도구 3가지 비교", "body": "## 질문\n도구 3가지를 실제 화면으로 비교해요 [E1].\n## 오늘 할 일\n하나를 직접 실행해 봐요.", "evidence": EVIDENCE, "quality": {"status": "passed", "critical": False}}
    source = store.save_source(job["id"], packet)
    if approve:
        store.review_source(job["id"], source["source_hash"], "approved", "operator", {"blog": True})
    return store.job(job["id"])


def good_slides(count=6):
    slides = [{"title": f"{n}. 도구 비교 기준", "body": f"{n}번째 기준은 입력과 판단 결과를 화면으로 확인하는 거예요."} for n in range(1, count + 1)]
    slides[0] = {"title": "AI 뉴스, 왜 남지 않을까요", "body": "읽어도 내 업무에 쓸 사례가 남지 않는 문제부터 짚어요."}
    slides[-1] = {"title": "오늘 할 일", "body": "도구 하나를 골라 직접 실행해 봐요. 무료 AI 업무 적용 점검표 받기"}
    return {"slides": slides}


class FakeCardsProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate(self, role, messages, schema, options=None):
        self.calls.append({"role": role, "system": messages[0]["content"], "user": messages[1]["content"], "schema": schema})
        return json.loads(json.dumps(self.responses.pop(0)))


def test_cards_schema_fixes_six_to_eight_slides():
    slides = CARDS_SCHEMA["properties"]["slides"]
    assert (slides["minItems"], slides["maxItems"]) == (6, 8)
    assert set(slides["items"]["required"]) == {"title", "body"}


def test_cards_require_source_approval(tmp_path):
    store = Store(tmp_path)
    job = approved_job(store, approve=False)
    provider = FakeCardsProvider([good_slides()])
    with pytest.raises(WorkflowError, match="승인①"):
        plan_cards(store, job["id"], provider=provider)
    assert provider.calls == [] and store.job(job["id"]).get("cards") is None


def test_plan_cards_renders_square_pngs_and_registers_artifacts(tmp_path):
    store = Store(tmp_path)
    job = approved_job(store)
    provider = FakeCardsProvider([good_slides(7)])
    result = plan_cards(store, job["id"], provider=provider)
    assert [call["role"] for call in provider.calls] == ["cards"]
    assert "무료 AI 업무 적용 점검표 받기" in provider.calls[0]["user"]
    assert load_brand()["voice"][:20] in provider.calls[0]["system"]
    assert provider.calls[0]["schema"] is CARDS_SCHEMA
    stored = store.job(job["id"])["cards"]
    assert stored["version"] == 1 and stored["source_hash"] == job["source_hash"]
    assert stored["checks"] == {"passed": True, "issues": []}
    assert [slide["index"] for slide in stored["slides"]] == list(range(1, 8))
    for slide in stored["slides"]:
        assert slide["artifact_id"].startswith("asset_")
        path = store.artifacts / slide["artifact"]["path"]
        assert path.is_file() and path.suffix == ".png"
        with Image.open(path) as image:
            assert image.size == (1080, 1080)
    assert len({slide["artifact_id"] for slide in stored["slides"]}) == 7
    assert result["slides"][0]["title"] == "AI 뉴스, 왜 남지 않을까요"
    assert any(e["kind"] == "cards_rendered" for e in store.events(job["id"]))
    plan_cards(store, job["id"], provider=FakeCardsProvider([good_slides()]))
    assert store.job(job["id"])["cards"]["version"] == 2 and len(store.job(job["id"])["cards"]["slides"]) == 6


def test_card_checks_catch_count_length_overflow_terms_claims_and_duplicates():
    brand = load_brand()
    assert card_checks(good_slides(), brand) == {"passed": True, "issues": []}
    assert any("6" in issue and "8" in issue for issue in card_checks(good_slides(5), brand)["issues"])
    assert any("6" in issue and "8" in issue for issue in card_checks(good_slides(9), brand)["issues"])
    bad = good_slides()
    bad["slides"][1]["title"] = "가" * 21
    bad["slides"][2]["body"] = "나" * 71
    bad["slides"][3]["title"] = "클로드 코드 소개"
    bad["slides"][4]["body"] = "3일 완성 — 누구나 가능"
    bad["slides"][5]["title"] = bad["slides"][0]["title"]
    result = card_checks(bad, brand)
    joined = "\n".join(result["issues"])
    assert result["passed"] is False
    assert "2번" in joined and "20자" in joined
    assert "3번" in joined and "70자" in joined
    assert "클로드 코드" in joined and "Claude Code" in joined
    assert "3일 완성" in joined and "줄표" in joined
    assert "6번" in joined and "중복" in joined
    overflow = good_slides()
    overflow["slides"][1]["title"] = "긴제목" * 40
    assert any("2번" in issue and "넘침" in issue for issue in card_checks(overflow, brand)["issues"])


def test_render_failure_keeps_other_slides_and_reports_issue(tmp_path, monkeypatch):
    store = Store(tmp_path)
    job = approved_job(store)
    original = cards_module.render_slide

    def flaky(slide, index, total, path, brand_label):
        if index == 3:
            raise OSError("disk")
        return original(slide, index, total, path, brand_label)

    monkeypatch.setattr(cards_module, "render_slide", flaky)
    result = plan_cards(store, job["id"], provider=FakeCardsProvider([good_slides()]))
    assert result["slides"][2]["artifact_id"] is None
    assert all(slide["artifact_id"] for slide in result["slides"] if slide["index"] != 3)
    assert result["checks"]["passed"] is False and any("3번" in issue for issue in result["checks"]["issues"])


def test_plan_cards_refines_once_when_checks_fail(tmp_path):
    store = Store(tmp_path)
    job = approved_job(store)
    bad = good_slides()
    bad["slides"][1]["title"] = "클로드 소개"
    provider = FakeCardsProvider([bad, good_slides()])
    result = plan_cards(store, job["id"], provider=provider)
    assert [call["role"] for call in provider.calls] == ["cards", "cards"]
    assert "클로드" in provider.calls[1]["user"]
    assert result["checks"]["passed"] is True


def test_worker_dispatches_cards_task(tmp_path, monkeypatch):
    store = Store(tmp_path)
    job = approved_job(store)
    called = []
    monkeypatch.setattr("office.cards.plan_cards", lambda s, job_id, provider=None: called.append(job_id) or {"version": 1, "checks": {"passed": False, "issues": ["x"]}})
    task = store.enqueue("cards", {"job_id": job["id"], "source_hash": job["source_hash"]}, key="cards-test")
    result = worker.process_task(store, task)
    assert called == [job["id"]] and result["passed"] is False


@pytest.fixture
def context(tmp_path):
    store = Store(tmp_path)
    client = TestClient(create_app(store), base_url="http://localhost:8510")
    token = client.get("/api/session").json()["csrf"]
    return store, client, {"Origin": "http://localhost:3110", "X-Office-CSRF": token}


def test_cards_routes_require_approval_then_enqueue_and_serve_images(context):
    store, client, headers = context
    job = approved_job(store, approve=False)
    assert client.post(f"/api/jobs/{job['id']}/cards", headers=headers).status_code == 409
    assert client.get(f"/api/jobs/{job['id']}/cards").json() == {"cards": None}
    store.review_source(job["id"], job["source_hash"], "approved", "operator", {"blog": True})
    response = client.post(f"/api/jobs/{job['id']}/cards", headers=headers)
    assert response.status_code == 202
    task = store.task(response.json()["task_id"])
    assert task["kind"] == "cards" and task["payload"]["source_hash"] == job["source_hash"]
    plan_cards(store, job["id"], provider=FakeCardsProvider([good_slides()]))
    body = client.get(f"/api/jobs/{job['id']}/cards").json()["cards"]
    assert set(body) == {"version", "generated_at", "source_hash", "slides", "checks"}
    assert set(body["slides"][0]) == {"index", "title", "body", "artifact_id"}
    served = client.get(f"/api/artifacts/{body['slides'][0]['artifact_id']}")
    assert served.status_code == 200 and served.headers["content-type"] == "image/png"
    assert client.get("/api/artifacts/asset_missing").status_code == 404
