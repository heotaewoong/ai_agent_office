"""그림 기억 이야기: 글은 모델(가짜 제공자), 그림은 코드. 검사, 그리기, 작업 큐, 화면 경로를 본다."""
import copy
import io

import pytest
from PIL import Image

from office import worker
from office.memory_story import MAX_PAGES, STORY_SCHEMA, generate_story, story_checks
from office.store import Store, WorkflowError
from test_quiz import FakeQuizProvider, approved_job

BRAND = {"banned": ["무조건 합격"]}


def page(anchor, text, backdrop="desk", props=(), mood="happy", place="left", evidence=()):
    return {"anchor": anchor, "text": text, "evidence": list(evidence),
            "scene": {"backdrop": backdrop, "props": [{"name": name, "place": "right"} for name in props], "hero": {"mood": mood, "place": place}}}


def good_story():
    return {
        "title": "도구 3가지를 기억하는 법",
        "pages": [
            page("화면으로 비교", "뇌리는 노트북을 열고 도구를 화면으로 비교해요.", props=("laptop",), evidence=("E1",)),
            page("도구 3가지", "비교할 도구 3가지를 하나씩 카드로 넘겨요.", backdrop="library", props=("card",), mood="curious"),
            page("20회 반복", "평가는 20회 반복했어요. 시계를 보며 같은 걸 다시 해요.", props=("clock",), mood="thinking", evidence=("E2",)),
            page("직접 실행", "마지막엔 하나를 직접 실행해 봐요. 깃발을 꽂아요.", backdrop="park", props=("flag",), mood="proud"),
        ],
        "recall": [{"question": "도구를 비교한 방법은?", "answer": "화면으로 비교"}, {"question": "평가는 몇 번 반복했나요?", "answer": "20회 반복"}],
    }


def packet_of(job):
    return job["source_packet"]


def test_schema_limits_pages_and_closed_vocabulary():
    pages = STORY_SCHEMA["properties"]["pages"]
    assert (pages["minItems"], pages["maxItems"]) == (4, MAX_PAGES)
    scene = pages["items"]["properties"]["scene"]["properties"]
    assert "enum" in scene["backdrop"] and "enum" in scene["props"]["items"]["properties"]["name"]
    assert scene["hero"]["properties"]["mood"]["enum"]


def test_good_story_passes_every_check(tmp_path):
    job = approved_job(Store(tmp_path))
    assert story_checks(good_story(), packet_of(job), BRAND) == {"passed": True, "issues": []}


@pytest.mark.parametrize("change,needle", [
    (lambda s: s["pages"][0].update(text="뇌리는 러닝머신 위에서 도구를 화면으로 비교해요."), "러닝머신"),  # 그림 계약
    (lambda s: s["pages"][1].update(text="비교할 도구를 하나씩 카드로 넘겨요."), "기억할 것 '도구 3가지'"),
    (lambda s: s["pages"][3].update(text="직접 실행해야 해요. 교훈을 명심해요."), "교훈"),
    (lambda s: s["pages"][2].update(text="평가는 20회 반복했어요. 정답률은 87%였어요."), "원고에 없는 숫자 87"),
    (lambda s: s["pages"][0].update(evidence=["E9"]), "근거 ID E9"),
    (lambda s: s["recall"][0].update(answer="전혀 다른 답"), "정답이 어느 장"),
    (lambda s: s["pages"][0]["scene"]["props"].append({"name": "spaceship", "place": "left"}), "그릴 수 없는 소품"),
    (lambda s: s["pages"][0].update(text="화면으로 비교 " + "가나다라마바사아자차" * 9), "공백 빼고 80자"),
    (lambda s: s.update(pages=s["pages"][:3]), "장 수는"),
    (lambda s: s["pages"][1].update(anchor="화면으로 비교", text="화면으로 비교를 또 해요. 카드를 넘겨요."), "겹쳐요"),
    (lambda s: s["pages"][0].update(text="뇌리는 노트북으로 공책 대신 화면으로 비교해요."), "'노트'"),  # 노트북은 노트가 아니다, 공책은 노트다
    (lambda s: s.update(title="무조건 합격 비법"), "과장 광고"),
])
def test_checks_catch_broken_stories(tmp_path, change, needle):
    job = approved_job(Store(tmp_path))
    story = copy.deepcopy(good_story())
    change(story)
    result = story_checks(story, packet_of(job), BRAND)
    assert result["passed"] is False and any(needle in issue for issue in result["issues"]), result["issues"]


def test_generate_draws_every_page_and_records_files(tmp_path):
    store = Store(tmp_path)
    job = approved_job(store)
    provider = FakeQuizProvider([good_story()])
    record = generate_story(store, job["id"], provider=provider)
    assert [call["role"] for call in provider.calls] == ["story"] and record["refined"] is False
    assert record["checks"]["passed"] is True and record["version"] == 1
    kinds = [file["kind"] for file in record["files"]]
    assert kinds == ["cover", "page", "page", "page", "page", "recall", "answers"]
    for file in record["files"]:
        path = store.artifacts / file["artifact"]["path"]
        with Image.open(path) as image:
            assert image.format == "PNG" and image.size == (1080, 1440)
    saved = store.job(job["id"])["story"]
    assert saved["source_hash"] == job["source_hash"] and saved["sheet"]["artifact"]["name"].endswith("sheet.jpg")
    assert "그림은 코드" in saved["note"] and store.job(job["id"]).get("release_review") is None  # 승인②는 건드리지 않는다


def test_generate_refines_once_then_keeps_issues_for_people(tmp_path):
    store = Store(tmp_path)
    job = approved_job(store)
    broken = copy.deepcopy(good_story())
    broken["pages"][0]["text"] = "뇌리는 러닝머신 위에서 도구를 화면으로 비교해요."
    provider = FakeQuizProvider([broken, broken])
    record = generate_story(store, job["id"], provider=provider)
    assert [call["role"] for call in provider.calls] == ["story", "story"] and record["refined"] is True
    assert record["checks"]["passed"] is False and any("러닝머신" in issue for issue in record["checks"]["issues"])
    assert "issues" in provider.calls[1]["user"]


def test_story_requires_source_approval(tmp_path):
    store = Store(tmp_path)
    job = approved_job(store, approve=False)
    provider = FakeQuizProvider([good_story()])
    with pytest.raises(WorkflowError, match="승인①"):
        generate_story(store, job["id"], provider=provider)
    assert provider.calls == [] and store.job(job["id"]).get("story") is None


def test_worker_runs_story_and_a_failure_does_not_block_the_job(tmp_path, monkeypatch):
    from office import memory_story
    store = Store(tmp_path)
    job = approved_job(store)
    task = store.enqueue("story", {"job_id": job["id"], "source_hash": job["source_hash"]}, key="story-1")
    monkeypatch.setattr(memory_story, "Provider", lambda store, job_id=None: FakeQuizProvider([good_story()]))
    result = worker.process_task(store, task)
    assert result["passed"] is True and result["version"] == 1
    stale = store.enqueue("story", {"job_id": job["id"], "source_hash": "0" * 64}, key="story-stale")
    with pytest.raises(WorkflowError, match="변경"):
        worker.process_task(store, stale)


def test_api_requests_and_serves_story_without_touching_release(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from office.api import create_app
    from office.session import start_session
    store = Store(tmp_path)
    job = approved_job(store)
    client = TestClient(create_app(store), base_url="http://localhost:8510")
    headers = {"Origin": "http://localhost:3110", "X-Office-CSRF": client.get("/api/session").json()["csrf"]}
    assert client.get(f"/api/jobs/{job['id']}/story").json() == {"story": None}
    store.set_setting("work_window", {"status": "closed"})
    closed = client.post(f"/api/jobs/{job['id']}/story", headers=headers)
    assert closed.status_code == 409  # 작업 시간이 닫혀 있으면 줄 세우지 않는다
    start_session(store, minutes=30, source="test")
    queued = client.post(f"/api/jobs/{job['id']}/story", headers=headers)
    assert queued.status_code == 202 and queued.json()["state"] == "queued"
    again = client.post(f"/api/jobs/{job['id']}/story", headers=headers)
    assert again.json()["task_id"] == queued.json()["task_id"]  # 같은 원고는 한 번만
    generate_story(store, job["id"], provider=FakeQuizProvider([good_story()]))
    payload = client.get(f"/api/jobs/{job['id']}/story").json()["story"]
    assert payload["current"] is True and len(payload["files"]) == 7 and payload["sheet_url"].startswith("/api/artifacts/")
    image = client.get(payload["files"][1]["url"])
    assert image.status_code == 200 and Image.open(io.BytesIO(image.content)).size == (1080, 1440)
    assert store.job(job["id"]).get("release_review") is None
