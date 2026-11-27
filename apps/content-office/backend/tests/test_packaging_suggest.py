import pytest

from office.packaging import attach_packaging
from office.packaging_suggest import SUGGEST_SCHEMA, packaging_for, suggest_packaging
from office.store import Store, WorkflowError


class Fake:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def generate(self, role, messages, schema, options=None):
        self.calls.append((role, messages, schema))
        return self.result


GOOD = {
    "titles": ["AI 에이전트로 시뮬레이션 만들기", "시뮬레이션, 에이전트에게 맡기는 법", "에이전트가 시뮬레이션을 대신 짤까요?"],
    "hooks": ["AI 에이전트로 시뮬레이션을 만드는 흐름을 NVIDIA 사례로 볼게요",
              "시뮬레이션을 에이전트에게 맡기면 사람이 할 일이 달라져요",
              "에이전트가 시뮬레이션 코드를 짜는 장면부터 볼게요"],
    "hook": "AI 에이전트로 시뮬레이션을 만드는 흐름을 NVIDIA 사례로 볼게요",
    "thumbnails": [{"text": "에이전트 시뮬", "visual": "화면"}, {"text": "맡기는 법", "visual": "표"}, {"text": "대신 짤까", "visual": "질문"}],
    "logline": "시뮬레이션을 에이전트와 나눠 만드는 방법을 알아요",
    "reasons": ["검색 수요가 있어요", "공식 사례가 있어요"],
}


def idea_job(store, origin="idea"):
    return store.create_job({"id": f"{origin}-1", "title": "AI 에이전트로 시뮬레이션 만드는 법", "url": "https://example.com/a",
                             "origin": origin, "evidence": []})


def test_suggestion_is_not_saved_and_every_title_passes_rules(tmp_path):
    store = Store(tmp_path)
    job = idea_job(store)
    fake = Fake(GOOD)
    out = suggest_packaging(store, job["id"], provider=fake)
    assert fake.calls[0][0] == "packaging" and fake.calls[0][2] is SUGGEST_SCHEMA
    assert out["issues"] == [[], [], []]
    assert store.job(job["id"]).get("packaging") is None
    # 2안을 골라도 그 제목의 훅이 들어가 저장 규칙을 통과해요.
    record = attach_packaging(store, job["id"], packaging_for(out["suggestion"], 1), "local-operator")
    assert record["chosen_title"] == GOOD["titles"][1] and record["hook"] == GOOD["hooks"][1]


def test_rule_issues_are_reported_not_hidden(tmp_path):
    store = Store(tmp_path)
    job = idea_job(store)
    long = {**GOOD, "titles": ["가" * 50, *GOOD["titles"][1:]]}
    out = suggest_packaging(store, job["id"], provider=Fake(long))
    assert any("45자" in issue for issue in out["issues"][0])


def test_only_idea_jobs_and_well_formed_answers(tmp_path):
    store = Store(tmp_path)
    rss = idea_job(store, origin="rss")
    with pytest.raises(WorkflowError, match="기획"):
        suggest_packaging(store, rss["id"], provider=Fake(GOOD))
    job = idea_job(store)
    with pytest.raises(WorkflowError, match="3개"):
        suggest_packaging(store, job["id"], provider=Fake({**GOOD, "titles": ["하나"]}))
    with pytest.raises(WorkflowError):
        packaging_for(suggest_packaging(store, job["id"], provider=Fake(GOOD))["suggestion"], 3)
