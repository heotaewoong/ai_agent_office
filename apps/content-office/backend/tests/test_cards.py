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
    slides = [{"title": f"{n}. 도구 비교 기준", "body": f"{n}번째 기준은 입력과 결과를 화면으로 확인하는 거예요.", "visual": "노트북 화면 앞에서 두 도구를 나란히 비교하는 장면"} for n in range(1, count + 1)]
    slides[0] = {"title": "AI 뉴스, 왜 안 남을까요", "body": "읽어도 내 업무에 쓸 사례가 남지 않는 문제를 짚어요.", "visual": "쌓인 뉴스 기사 더미 앞에서 고민하는 책상"}
    slides[-1] = {"title": "오늘 할 일", "body": "도구 하나를 골라 직접 실행해 봐요.", "visual": "체크리스트와 커피잔이 놓인 책상"}
    return {"slides": slides}


class FakeCardsProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate(self, role, messages, schema, options=None):
        self.calls.append({"role": role, "system": messages[0]["content"], "user": messages[1]["content"], "schema": schema})
        if role == "cards_review":
            # 검토 응답을 따로 주지 않으면 '문제 없음'으로 답한다
            if self.responses and isinstance(self.responses[0], dict) and "cards" in self.responses[0]:
                return json.loads(json.dumps(self.responses.pop(0)))
            return {"cards": []}
        return json.loads(json.dumps(self.responses.pop(0)))


def test_cards_schema_fixes_six_to_eight_slides():
    slides = CARDS_SCHEMA["properties"]["slides"]
    assert (slides["minItems"], slides["maxItems"]) == (6, 8)
    assert set(slides["items"]["required"]) == {"title", "body", "visual"}


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
    assert [call["role"] for call in provider.calls] == ["cards", "cards_review"]
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
    assert result["slides"][0]["title"] == "AI 뉴스, 왜 안 남을까요"
    assert any(e["kind"] == "cards_rendered" for e in store.events(job["id"]))
    plan_cards(store, job["id"], provider=FakeCardsProvider([good_slides()]))
    assert store.job(job["id"])["cards"]["version"] == 2 and len(store.job(job["id"])["cards"]["slides"]) == 6


def test_card_checks_catch_count_length_overflow_terms_claims_and_duplicates():
    brand = load_brand()
    assert card_checks(good_slides(), brand) == {"passed": True, "issues": []}
    assert any("6" in issue and "8" in issue for issue in card_checks(good_slides(5), brand)["issues"])
    assert any("6" in issue and "8" in issue for issue in card_checks(good_slides(9), brand)["issues"])
    bad = good_slides()
    bad["slides"][1]["title"] = "가" * 19
    bad["slides"][2]["body"] = "나" * 61
    bad["slides"][3]["title"] = "클로드 코드 소개"
    bad["slides"][4]["body"] = "3일 완성 — 누구나 가능"
    bad["slides"][5]["title"] = bad["slides"][0]["title"]
    result = card_checks(bad, brand)
    joined = "\n".join(result["issues"])
    assert result["passed"] is False
    assert "2번" in joined and "18자" in joined
    assert "3번" in joined and "60자" in joined
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

    def flaky(slide, index, total, path, brand_label, **kwargs):
        if index == 3:
            raise OSError("disk")
        return original(slide, index, total, path, brand_label, **kwargs)

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
    assert [call["role"] for call in provider.calls] == ["cards", "cards_review", "cards"]
    assert "클로드" in provider.calls[1]["user"]
    assert result["checks"]["passed"] is True


def test_worker_dispatches_cards_task(tmp_path, monkeypatch):
    store = Store(tmp_path)
    job = approved_job(store)
    called = []
    monkeypatch.setattr("office.cards.plan_cards", lambda s, job_id, provider=None, images=None: called.append(job_id) or {"version": 1, "checks": {"passed": False, "issues": ["x"]}})
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
    assert set(body["slides"][0]) == {"index", "title", "body", "artifact_id", "visual", "template", "background"}
    served = client.get(f"/api/artifacts/{body['slides'][0]['artifact_id']}")
    assert served.status_code == 200 and served.headers["content-type"] == "image/png"
    assert client.get("/api/artifacts/asset_missing").status_code == 404



def test_render_templates_cover_body_cta_and_optional_background(tmp_path):
    from office.cards import render_slide
    from office.exports import korean_font
    assert korean_font("bold").is_file()
    slides = good_slides(6)["slides"]
    cover = tmp_path / "c.png"; body = tmp_path / "b.png"; cta = tmp_path / "e.png"
    assert render_slide(slides[0], 1, 6, cover)["template"] == "cover"
    assert render_slide(slides[2], 3, 6, body)["template"] == "body"
    last = render_slide(slides[-1], 6, 6, cta, cta="무료 AI 업무 적용 점검표 받기")
    assert last["template"] == "cta" and last["cta"] == "무료 AI 업무 적용 점검표 받기"
    for path in (cover, body, cta):
        with Image.open(path) as image:
            assert image.size == (1080, 1080)
    picture = tmp_path / "bg.png"
    Image.new("RGB", (1024, 1024), "#ff8800").save(picture)
    with_bg = render_slide(slides[2], 3, 6, tmp_path / "b2.png", background=picture)
    assert with_bg["template"] == "body" and with_bg["background"] == "generated"
    with Image.open(tmp_path / "b2.png") as image:
        r, g, b = image.getpixel((540, 330))  # 이미지가 그대로 보이는 위쪽
        assert r > 200 and b < 80
        r, g, b = image.getpixel((1050, 1060))  # 글자가 놓이는 아래쪽은 짙게 어둡다
        assert r < 60
    assert render_slide(slides[2], 3, 6, tmp_path / "b3.png")["background"] == "gradient"


def test_plan_cards_puts_a_topic_image_behind_every_card_but_the_last(tmp_path):
    store = Store(tmp_path)
    job = approved_job(store)
    calls = []

    def renderer(index, slide, path):
        calls.append((index, slide["visual"]))
        Image.new("RGB", (1024, 1024), "#2244aa").save(path)
        return {"model": "gpt-image-test"}
    result = plan_cards(store, job["id"], provider=FakeCardsProvider([good_slides(6)]), background_renderer=renderer)
    assert [c[0] for c in calls] == [0, 1, 2, 3, 4]
    assert calls[0][1] == "쌓인 뉴스 기사 더미 앞에서 고민하는 책상"
    assert result["visual_source"] == "generated_topic_images_plus_first_party_text"
    assert [s["background"] for s in result["slides"]] == ["generated"] * 5 + ["solid"]
    assert result["slides"][-1]["cta"] and len(result["images"]) == 5

    attempts = []

    def failing(index, slide, path):
        attempts.append(index)
        raise WorkflowError("카드 이미지 업무당 3,200원 한도")
    again = plan_cards(store, job["id"], provider=FakeCardsProvider([good_slides(6)]), background_renderer=failing)
    assert attempts == [0]  # 한 번 실패하면 같은 실패를 비용 들여 반복하지 않는다
    assert again["checks"]["passed"] is True and {s["background"] for s in again["slides"][:-1]} == {"gradient"}
    assert any("주제 이미지 없이" in note for note in again["notes"])


def test_images_false_or_no_openai_key_never_builds_a_paid_renderer(tmp_path, monkeypatch):
    import office.image_provider as image_provider
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(image_provider, "make_openai_card_image_renderer", lambda *a, **k: (_ for _ in ()).throw(AssertionError("paid renderer built")))
    store = Store(tmp_path)
    job = approved_job(store)
    assert plan_cards(store, job["id"], provider=FakeCardsProvider([good_slides()]), images=False)["visual_source"] == "first_party_gradient_and_text"
    assert plan_cards(store, job["id"], provider=FakeCardsProvider([good_slides()]))["visual_source"] == "first_party_gradient_and_text"


@pytest.mark.parametrize("explicit_none", [False, True])
def test_default_card_images_respect_none_profile_with_openai_text_key(tmp_path, monkeypatch, explicit_none):
    import office.image_provider as image_provider
    from office.cards import _card_renderer
    from office.image_selection import select_profile

    monkeypatch.setenv("OPENAI_API_KEY", "test-placeholder-not-a-real-key")
    monkeypatch.setattr(image_provider, "make_openai_card_image_renderer", lambda *a, **k: (_ for _ in ()).throw(AssertionError("default none profile selected a paid image renderer")))
    store = Store(tmp_path)
    job = approved_job(store)
    if explicit_none:
        select_profile(store, "none", actor="test-operator")
    notes = []
    assert _card_renderer(store, job["id"], None, None, notes) is None
    assert notes == [] and store.budget()["spent_krw"] == 0


def test_explicit_card_images_preserve_openai_opt_in_with_none_profile(tmp_path, monkeypatch):
    import office.image_provider as image_provider
    from office.cards import _card_renderer

    marker, calls = object(), []
    monkeypatch.setenv("OPENAI_API_KEY", "test-placeholder-not-a-real-key")
    monkeypatch.setattr(image_provider, "make_openai_card_image_renderer", lambda store, **kwargs: calls.append(kwargs) or marker)
    store = Store(tmp_path)
    job = approved_job(store)
    assert _card_renderer(store, job["id"], True, None, []) is marker
    assert calls == [{"job_id": job["id"], "allow_paid": True}]


def test_failed_refine_keeps_the_first_plan_instead_of_failing(tmp_path):
    store = Store(tmp_path)
    job = approved_job(store)

    class Provider(FakeCardsProvider):
        def generate(self, role, messages, schema, options=None):
            if role == "cards" and any(c["role"] == "cards_review" for c in self.calls):
                self.calls.append({"role": role})
                raise WorkflowError("모델 출력이 길이 제한에서 잘렸습니다")
            return super().generate(role, messages, schema, options)
    review = {"cards": [{"index": 2, "ok": False, "problems": ["주어가 없어요"]}]}
    result = plan_cards(store, job["id"], provider=Provider([good_slides(), review]), images=False)
    assert result["refined"] is False and len(result["slides"]) == 6 and all(s["artifact_id"] for s in result["slides"])
    assert result["checks"]["passed"] is False and any("주어가 없어요" in i for i in result["checks"]["issues"])
    assert any("수정 단계 실패" in n for n in result["notes"])
