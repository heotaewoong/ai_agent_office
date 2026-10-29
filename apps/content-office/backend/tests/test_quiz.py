import json

import pytest
from fastapi.testclient import TestClient

from office import worker
from office.api import create_app
from office.brand import load_brand
from office.quiz import QUIZ_SCHEMA, generate_quiz, quiz_checks
from office.store import Store, WorkflowError

EVIDENCE = [
    {"id": "E1", "claim": "공식 발표에 따르면 도구는 3가지", "url": "https://example.com/news", "numbers": ["3"]},
    {"id": "E2", "claim": "평가는 20회 반복했다", "url": "https://example.com/eval", "numbers": ["20"]},
]


def approved_job(store, approve=True):
    job = store.create_job({"id": "one", "title": "AI 발표", "url": "https://example.com/news", "evidence": EVIDENCE})
    packet = {"title": "AI 도구 3가지 비교", "body": "## 질문\n도구 3가지를 실제 화면으로 비교해요 [E1].\n## 사례\n평가는 20회 반복했어요 [E2].\n## 오늘 할 일\n하나를 직접 실행해 봐요.", "evidence": EVIDENCE, "quality": {"status": "passed", "critical": False}}
    source = store.save_source(job["id"], packet)
    if approve:
        store.review_source(job["id"], source["source_hash"], "approved", "operator", {"blog": True})
    return store.job(job["id"])


def good_question(number, answer=0, evidence=("E1",)):
    return {"id": f"Q{number}", "question": f"{number}번. 발표에서 비교한 도구는 몇 가지예요?", "choices": ["3가지", "5가지", "7가지", "9가지"], "answer": answer, "explanation": "발표는 도구 3가지를 비교했어요.", "evidence": list(evidence)}


def good_quiz():
    return {"questions": [good_question(n, answer=n % 4) for n in range(1, 6)]}


class FakeQuizProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate(self, role, messages, schema, options=None):
        self.calls.append({"role": role, "system": messages[0]["content"], "user": messages[1]["content"], "schema": schema})
        return json.loads(json.dumps(self.responses.pop(0)))


def test_quiz_schema_fixes_five_questions_with_four_choices():
    questions = QUIZ_SCHEMA["properties"]["questions"]
    assert (questions["minItems"], questions["maxItems"]) == (5, 5)
    choices = questions["items"]["properties"]["choices"]
    assert (choices["minItems"], choices["maxItems"]) == (4, 4)
    assert questions["items"]["properties"]["answer"] == {"type": "integer", "minimum": 0, "maximum": 3}


def test_quiz_requires_source_approval(tmp_path):
    store = Store(tmp_path)
    job = approved_job(store, approve=False)
    provider = FakeQuizProvider([good_quiz()])
    with pytest.raises(WorkflowError, match="승인①"):
        generate_quiz(store, job["id"], provider=provider)
    assert provider.calls == []
    assert store.job(job["id"]).get("quiz") is None


def test_generate_quiz_stores_questions_checks_and_artifact(tmp_path):
    store = Store(tmp_path)
    job = approved_job(store)
    provider = FakeQuizProvider([good_quiz()])
    quiz = generate_quiz(store, job["id"], provider=provider)
    assert [call["role"] for call in provider.calls] == ["quiz"]
    assert "오픈" not in provider.calls[0]["user"]
    assert "무료 AI 업무 적용 점검표 받기" in provider.calls[0]["user"]  # 브리프 CTA
    assert load_brand()["voice"][:20] in provider.calls[0]["system"]
    assert provider.calls[0]["schema"] is QUIZ_SCHEMA
    stored = store.job(job["id"])["quiz"]
    assert stored["version"] == 1 and stored["source_hash"] == job["source_hash"]
    assert len(stored["questions"]) == 5 and stored["questions"][0]["id"] == "Q1"
    assert stored["checks"] == {"passed": True, "issues": []}
    assert stored["artifact_id"].startswith("asset_")
    path = store.artifacts / stored["artifact"]["path"]
    assert path.is_file() and path.name.endswith(".json")
    assert json.loads(path.read_text(encoding="utf-8"))["questions"][4]["id"] == "Q5"
    assert quiz["questions"] == stored["questions"]
    assert any(e["kind"] == "quiz_generated" for e in store.events(job["id"]))
    # 다시 만들면 버전이 오른다
    generate_quiz(store, job["id"], provider=FakeQuizProvider([good_quiz()]))
    assert store.job(job["id"])["quiz"]["version"] == 2


def test_quiz_checks_catch_structure_evidence_and_claims():
    packet = {"evidence": EVIDENCE}
    brand = load_brand()
    quiz = {"questions": [good_question(n) for n in range(1, 5)]}
    issues = quiz_checks(quiz, packet, brand)["issues"]
    assert any("5" in issue for issue in issues)
    bad = good_quiz()
    bad["questions"][0]["choices"] = ["3가지", "3가지", "", "9가지"]
    bad["questions"][1]["answer"] = 7
    bad["questions"][2]["evidence"] = ["E9"]
    bad["questions"][3]["explanation"] = "무조건 합격하는 비법이에요"
    bad["questions"][4]["question"] = "줄표 — 를 쓴 문장?"
    result = quiz_checks(bad, packet, brand)
    assert result["passed"] is False
    joined = "\n".join(result["issues"])
    assert "Q1" in joined and "중복" in joined
    assert "Q2" in joined and "정답" in joined
    assert "Q3" in joined and "E9" in joined
    assert "무조건 합격" in joined
    assert "줄표" in joined
    same_answer = {"questions": [good_question(n, answer=2) for n in range(1, 6)]}
    assert any("정답 번호" in issue for issue in quiz_checks(same_answer, packet, brand)["issues"])
    assert quiz_checks(good_quiz(), packet, brand) == {"passed": True, "issues": []}


def test_generate_quiz_refines_once_then_keeps_issues_visible(tmp_path):
    store = Store(tmp_path)
    job = approved_job(store)
    bad = good_quiz()
    bad["questions"][0]["evidence"] = ["E9"]
    provider = FakeQuizProvider([bad, bad])
    quiz = generate_quiz(store, job["id"], provider=provider)
    assert [call["role"] for call in provider.calls] == ["quiz", "quiz"]
    assert "E9" in provider.calls[1]["user"]
    assert quiz["checks"]["passed"] is False and any("E9" in issue for issue in quiz["checks"]["issues"])
    assert store.job(job["id"])["quiz"]["checks"]["passed"] is False
    assert store.job(job["id"])["quiz"]["artifact_id"] is not None


def test_generate_quiz_refine_success_passes(tmp_path):
    store = Store(tmp_path)
    job = approved_job(store)
    bad = good_quiz()
    bad["questions"][0]["answer"] = 9
    provider = FakeQuizProvider([bad, good_quiz()])
    quiz = generate_quiz(store, job["id"], provider=provider)
    assert len(provider.calls) == 2 and quiz["checks"]["passed"] is True


def test_worker_dispatches_quiz_task(tmp_path, monkeypatch):
    store = Store(tmp_path)
    job = approved_job(store)
    called = []
    monkeypatch.setattr("office.quiz.generate_quiz", lambda s, job_id, provider=None: called.append(job_id) or {"version": 1, "checks": {"passed": True, "issues": []}})
    task = store.enqueue("quiz", {"job_id": job["id"], "source_hash": job["source_hash"]}, key="quiz-test")
    result = worker.process_task(store, task)
    assert called == [job["id"]] and result["version"] == 1
    stale = store.enqueue("quiz", {"job_id": job["id"], "source_hash": "0" * 64}, key="quiz-stale")
    with pytest.raises(WorkflowError, match="변경"):
        worker.process_task(store, stale)


@pytest.fixture
def context(tmp_path):
    store = Store(tmp_path)
    client = TestClient(create_app(store), base_url="http://localhost:8510")
    token = client.get("/api/session").json()["csrf"]
    return store, client, {"Origin": "http://localhost:3110", "X-Office-CSRF": token}


def test_quiz_routes_require_approval_then_enqueue_and_expose_result(context):
    store, client, headers = context
    job = approved_job(store, approve=False)
    assert client.post(f"/api/jobs/{job['id']}/quiz", headers=headers).status_code == 409
    assert client.get(f"/api/jobs/{job['id']}/quiz").json() == {"quiz": None}
    store.review_source(job["id"], job["source_hash"], "approved", "operator", {"blog": True})
    assert client.post(f"/api/jobs/{job['id']}/quiz", headers={"Origin": "http://localhost:3110"}).status_code == 403
    response = client.post(f"/api/jobs/{job['id']}/quiz", headers=headers)
    assert response.status_code == 202
    task = store.task(response.json()["task_id"])
    assert task["kind"] == "quiz" and task["payload"] == {"job_id": job["id"], "source_hash": job["source_hash"]}
    assert client.post(f"/api/jobs/{job['id']}/quiz", headers=headers).json()["task_id"] == task["id"]  # 대기 중 중복 요청은 같은 작업
    generate_quiz(store, job["id"], provider=FakeQuizProvider([good_quiz()]))
    body = client.get(f"/api/jobs/{job['id']}/quiz").json()["quiz"]
    assert set(body) == {"version", "generated_at", "source_hash", "questions", "checks", "artifact_id"}
    assert set(body["questions"][0]) == {"id", "question", "choices", "answer", "explanation", "evidence"}
    served = client.get(f"/api/artifacts/{body['artifact_id']}")
    assert served.status_code == 200 and served.json()["questions"][0]["id"] == "Q1"
    # 완료 후 다시 요청하면 새 작업
    assert client.post(f"/api/jobs/{job['id']}/quiz", headers=headers).json()["task_id"] != task["id"]


def test_produce_task_auto_enqueues_quiz_and_cards_once(tmp_path, monkeypatch):
    from office import media
    from office.cards import plan_cards
    from tests.test_cards import FakeCardsProvider, good_slides
    store = Store(tmp_path)
    job = approved_job(store)
    monkeypatch.setattr(media, "produce", lambda s, job_id, **kw: {"hash": "m", "output_status": {"blog": {"state": "completed"}}, "completed_outputs": ["blog"]})
    task = {"kind": "produce", "payload": {"job_id": job["id"], "source_hash": job["source_hash"]}}
    result = worker.process_task(store, task)
    kinds = sorted((t["kind"], t["state"]) for t in store.tasks(job["id"]))
    assert kinds == [("cards", "queued"), ("quiz", "queued")]
    assert set(result["queued_outputs"]) == {"quiz", "cards"}
    # 같은 원고로 다시 제작해도 대기 중 작업을 중복으로 넣지 않는다
    assert worker.process_task(store, task)["queued_outputs"] == result["queued_outputs"]
    assert len(store.tasks(job["id"])) == 2
    # 현재 버전 결과가 이미 있으면 그 종류는 건너뛴다
    generate_quiz(store, job["id"], provider=FakeQuizProvider([good_quiz()]))
    plan_cards(store, job["id"], provider=FakeCardsProvider([good_slides()]))
    assert worker.process_task(store, task)["queued_outputs"] == {}


def released_job(store):
    import hashlib
    from office.store import digest
    job = approved_job(store)
    (store.artifacts / "tistory.txt").write_bytes(b"demo")
    record = {"id": "asset_one", "name": "tistory.txt", "kind": "text", "path": "tistory.txt", "size": 4, "sha256": hashlib.sha256(b"demo").hexdigest(), "url": "/api/artifacts/asset_one", "outputs": ["blog"]}
    manifest = {"source_hash": job["source_hash"], "files": [record], "completed_outputs": ["blog"], "output_status": {"blog": {"state": "completed"}}, "thumbnail_candidates": [], "media": {}}
    manifest["hash"] = digest(manifest)
    store.save_manifest_if_current(job["id"], job["source_hash"], job["selections"], manifest)
    store.review_release(job["id"], manifest["hash"], "approved", "operator", outputs=["blog"])
    return store.job(job["id"])


def test_package_zip_includes_quiz_json_and_card_pngs(context):
    import io
    import zipfile
    from office.cards import plan_cards
    from tests.test_cards import FakeCardsProvider, good_slides
    store, client, _ = context
    job = released_job(store)
    generate_quiz(store, job["id"], provider=FakeQuizProvider([good_quiz()]))
    plan_cards(store, job["id"], provider=FakeCardsProvider([good_slides()]))
    response = client.get(f"/api/jobs/{job['id']}/package")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        assert "tistory.txt" in names and "quiz/quiz-v1.json" in names and "cards/cards.json" in names
        assert [n for n in names if n.startswith("cards/card-")] == [f"cards/card-{i:02}.png" for i in range(1, 7)]
        assert json.loads(archive.read("quiz/quiz-v1.json"))["questions"][0]["id"] == "Q1"
        assert json.loads(archive.read("cards/cards.json"))["slides"][0]["index"] == 1
        assert json.loads(archive.read("handoff.json"))["extras"][0] == "quiz/quiz-v1.json"
    # 카드 파일이 바뀌면 패키지를 만들지 않는다
    (store.artifacts / store.job(job["id"])["cards"]["slides"][0]["artifact"]["path"]).write_bytes(b"tampered")
    assert client.get(f"/api/jobs/{job['id']}/package").status_code == 409


def test_gates_list_quiz_and_cards_issues_as_non_blocking_warnings(context):
    from office.cards import plan_cards
    from tests.test_cards import FakeCardsProvider, good_slides
    store, client, _ = context
    job = approved_job(store)
    assert client.get(f"/api/jobs/{job['id']}/gates").json()["status"] == "pass"
    bad = good_quiz()
    bad["questions"][0]["evidence"] = ["E9"]
    generate_quiz(store, job["id"], provider=FakeQuizProvider([bad, bad]))
    slides = good_slides()
    slides["slides"][1]["title"] = "클로드 소개"
    plan_cards(store, job["id"], provider=FakeCardsProvider([slides, slides]))
    report = client.get(f"/api/jobs/{job['id']}/gates").json()
    assert report["status"] == "warn"
    rules = {item["rule"] for item in report["items"]}
    assert rules == {"quiz_check", "cards_check"} and all(item["level"] == "warn" for item in report["items"])
    assert any("E9" in item["message"] for item in report["items"]) and any("Claude" in item["message"] for item in report["items"])
    events = [e for e in store.events(job["id"]) if e["kind"] in ("quiz_generated", "cards_rendered")]
    assert {e["kind"]: (e["data"].get("questions") or e["data"].get("slides"), e["data"]["issues"]) for e in events} == {"quiz_generated": (5, 1), "cards_rendered": (6, 1)}


def test_failed_quiz_task_is_recorded_but_does_not_block_the_job(tmp_path, monkeypatch):
    from office.session import start_session
    store = Store(tmp_path)
    start_session(store, minutes=30, source="test")
    job = approved_job(store)
    monkeypatch.setattr("office.quiz.generate_quiz", lambda *a, **k: (_ for _ in ()).throw(WorkflowError("기존 Gemini 연결이 없습니다")))
    store.enqueue("quiz", {"job_id": job["id"], "source_hash": job["source_hash"]}, key="quiz-fail")
    assert worker.run_once(store, "test-worker")
    task = store.tasks(job["id"])[0]
    assert task["state"] == "failed" and "Gemini" in task["result"]["error"]
    assert store.job(job["id"])["state"] == "source_approved" and store.job(job["id"])["error"] is None
    assert any(e["kind"] == "task_failed" and e["data"]["kind"] == "quiz" for e in store.events(job["id"]))
