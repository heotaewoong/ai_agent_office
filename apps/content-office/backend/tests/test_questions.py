import pytest
from fastapi.testclient import TestClient

from office.api import create_app
from office.questions import convert_question, group_key, list_questions, receive_question
from office.store import Store, WorkflowError


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


@pytest.fixture
def context(tmp_path):
    store = Store(tmp_path)
    client = TestClient(create_app(store), base_url="http://localhost:8510")
    headers = {"Origin": "http://localhost:3110", "X-Office-CSRF": client.get("/api/session").json()["csrf"]}
    return store, client, headers


def test_group_key_normalises_case_space_and_punctuation():
    assert group_key("오픽 IM에서 IH로, 어떻게 올려요?") == group_key("오픽 im에서 ih로 어떻게 올려요")
    assert len(group_key("가" * 100)) == 40


def test_received_questions_group_and_count(store):
    first = receive_question(store, "homepage", "오픽 IM에서 IH로 어떻게 올려요?")
    second = receive_question(store, "comment", "오픽 im에서 ih로, 어떻게 올려요", channel_key="youtube_ko")
    other = receive_question(store, "dm", "정처기 실기 C언어 어디부터 봐요?")
    assert first["group_key"] == second["group_key"] != other["group_key"]
    assert second["count"] == 2 and first["count"] == 1 and other["count"] == 1
    assert second["state"] == "new" and second["channel_key"] == "youtube_ko" and first["channel_key"] is None
    assert set(first) == {"id", "source", "text", "channel_key", "created_at", "group_key", "count", "state"}
    listed = list_questions(store)
    assert [q["id"] for q in listed["questions"]] == [other["id"], second["id"], first["id"]]
    assert listed["groups"][0]["count"] == 2 and listed["groups"][0]["question_ids"] == [first["id"], second["id"]]
    assert set(listed["groups"][0]) == {"group_key", "sample_text", "count", "question_ids"}
    assert [e["kind"] for e in store.events(limit=3)].count("question_received") == 3


def test_rejects_bad_source_or_length(store):
    with pytest.raises(WorkflowError, match="출처"):
        receive_question(store, "phone", "충분히 긴 질문입니다")
    with pytest.raises(WorkflowError, match="5"):
        receive_question(store, "homepage", "짧다")
    with pytest.raises(WorkflowError, match="1000"):
        receive_question(store, "homepage", "가" * 1001)


def test_convert_marks_group_and_builds_idea(store):
    text = "정처기 실기 C언어 포인터 문제는 어디부터 봐야 하나요? 기출을 풀어도 자꾸 틀려요"
    first = receive_question(store, "homepage", text)
    receive_question(store, "comment", text + "!!")
    idea = convert_question(store, first["id"], brief_preset="exam-info-processing")
    assert idea["origin"] == "question" and idea["demand"] == 40 and idea["primary_sources"] == 0 and idea["fit"] == 0.7
    assert idea["policy_flags"] == [] and idea["source_url"] is None and idea["title"] == text[:60]
    assert idea["brief"]["preset"] == "exam-info-processing" and idea["brief"]["problem"] == text
    assert idea["id"] in {i["id"] for i in store.ideas()}
    assert all(q["state"] == "converted" for q in list_questions(store)["questions"])
    assert any(e["kind"] == "question_converted" and e["data"]["idea_id"] == idea["id"] for e in store.events(limit=5))
    titled = convert_question(store, first["id"], title="직접 정한 제목")
    assert titled["title"] == "직접 정한 제목" and titled["brief"]["preset"] == "ai-agent"
    with pytest.raises(WorkflowError, match="질문"):
        convert_question(store, "q_missing")


def test_convert_caps_demand_at_100(store):
    ids = [receive_question(store, "other", "같은 질문이 여섯 번 들어와요 어떻게 해요")["id"] for _ in range(6)]
    assert convert_question(store, ids[0])["demand"] == 100


def test_questions_api_contract(context):
    store, client, headers = context
    bad = client.post("/api/questions", json={"source": "phone", "text": "충분히 긴 질문입니다"}, headers=headers)
    assert bad.status_code == 422
    assert client.post("/api/questions", json={"source": "homepage", "text": "짧다"}, headers=headers).status_code == 422
    created = client.post("/api/questions", json={"source": "homepage", "text": "오픽 IM에서 IH로 어떻게 올려요?", "channel_key": None}, headers=headers)
    assert created.status_code == 200
    question = created.json()["question"]
    assert set(question) == {"id", "source", "text", "channel_key", "created_at", "group_key", "count", "state"}
    assert question["count"] == 1 and question["state"] == "new"
    client.post("/api/questions", json={"source": "dm", "text": "오픽 im에서 ih로 어떻게 올려요", "channel_key": "youtube_ko"}, headers=headers)
    listed = client.get("/api/questions").json()
    assert set(listed) == {"questions", "groups"} and listed["questions"][0]["source"] == "dm"
    assert listed["groups"][0]["count"] == 2 and len(listed["groups"][0]["question_ids"]) == 2
    converted = client.post(f"/api/questions/{question['id']}/idea", json={"brief_preset": "exam-opic", "title": None}, headers=headers)
    assert converted.status_code == 200
    idea = converted.json()["idea"]
    assert idea["origin"] == "question" and idea["brief"]["preset"] == "exam-opic" and "score" in idea and "timeliness" in idea
    assert all(q["state"] == "converted" for q in client.get("/api/questions").json()["questions"])
    assert client.post("/api/questions/q_missing/idea", json={}, headers=headers).status_code == 409
    assert client.post("/api/questions", json={"source": "homepage", "text": "세션 없이 보내는 질문이에요"}).status_code == 403
