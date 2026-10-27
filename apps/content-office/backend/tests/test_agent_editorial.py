import pytest
from office.editorial import prepare_source
from office.packaging import attach_packaging
from office.store import Store, WorkflowError

EVIDENCE = [{"claim": "공식 발표에 따르면 도구는 3가지", "numbers": ["3"], "paragraph": 1, "scope": "발표"}]


class FakeProvider:
    def __init__(self, title):
        self.title = title
        self.systems = []
        self.users = []

    def generate(self, role, messages, schema, options=None):
        self.systems.append(messages[0]["content"])
        self.users.append(messages[1]["content"])
        if role in ("gen", "refine"):
            return {"title": self.title, "body": "도구 3가지를 실제 화면으로 비교한다", "video": {"title": "AI 도구 비교", "description": "", "tags": [], "scenes": [{"narration": "세 도구를 직접 비교한다", "caption": "비교", "visual": "화면"}]}}
        return {"role": role, "score": 90, "passed": True, "critical_issues": [], "minor_issues": [], "summary": "검토"}


def idea_job(store, origin="idea"):
    return store.create_job({"id": f"{origin}-1", "title": "기획", "url": "https://example.com/a", "origin": origin, "evidence": EVIDENCE})


def brief():
    return {
        "titles": ["Claude 팀으로 블로그 자동화", "AI 팀이 블로그를 쓰는 법", "블로그 자동화 3단계"],
        "thumbnails": [{"text": "AI 팀 블로그", "visual": "작업 화면"}, {"text": "3단계", "visual": "표"}, {"text": "직접 해봄", "visual": "결과 화면"}],
        "hook": "블로그 자동화를 Claude 팀으로 나눠 맡긴 결과부터 보여 드립니다",
        "logline": "한 명이 에이전트 팀으로 블로그 한 편을 끝내는 과정",
        "reasons": ["검색 수요가 있음", "실제 작업 화면으로 증명 가능"],
    }


def test_idea_job_without_packaging_cannot_draft(tmp_path):
    store = Store(tmp_path)
    job = idea_job(store)
    with pytest.raises(WorkflowError, match="패키징"):
        prepare_source(store, job["id"], provider=FakeProvider("AI 도구 비교"))


def test_gate_report_is_saved_and_blocks_unsupported_title_number(tmp_path):
    store = Store(tmp_path)
    job = idea_job(store, origin="rss")
    prepare_source(store, job["id"], provider=FakeProvider("AI 도구 7가지"))
    packet = store.job(job["id"])["source_packet"]
    assert packet["quality"]["gates"]["status"] == "block"
    assert packet["quality"]["status"] == "blocked"


def test_packaging_reaches_drafting_context_and_packet(tmp_path):
    store = Store(tmp_path)
    job = idea_job(store)
    record = attach_packaging(store, job["id"], brief(), "local-operator")
    provider = FakeProvider("AI 도구 비교")
    prepare_source(store, job["id"], provider=provider)
    assert "AI 팀이 블로그를 쓰는 법" in provider.users[0]
    assert store.job(job["id"])["source_packet"]["packaging_hash"] == record["packaging_hash"]


class FullProvider:
    """gen은 deterministic_checks를 통과하는 원고를, 리뷰는 90점 통과를 돌려준다."""

    def __init__(self, video_title, fail_critique_once=False):
        self.video_title = video_title
        self.fail_critique_once = fail_critique_once
        self.systems = []
        self.users = []
        self.roles = []

    def _packet(self):
        body = "## 질문\n" + "도구 3가지를 실제 화면으로 비교한다 [E1]. " * 20 + "\n## 사례\n" + "입력과 판단 결과를 그대로 보여준다. " * 20 + "\n## 오늘 할 일\n" + "한 가지를 직접 실행해 본다. " * 20
        scenes = [{"narration": "세 도구를 비교한다", "caption": f"장면{i}", "visual": "화면"} for i in range(4)]
        return {"title": "AI 도구 비교", "body": body, "video": {"title": self.video_title, "description": "", "tags": [], "scenes": scenes, "thumbnails": []}}

    def generate(self, role, messages, schema, options=None):
        self.roles.append(role)
        self.systems.append(messages[0]["content"])
        self.users.append(messages[1]["content"])
        if role in ("gen", "refine"):
            return self._packet()
        if role == "critique" and self.fail_critique_once and self.roles.count("critique") == 1:
            return {"role": role, "score": 60, "passed": False, "critical_issues": [], "minor_issues": ["보완"], "summary": "보완 필요"}
        return {"role": role, "score": 90, "passed": True, "critical_issues": [], "minor_issues": [], "summary": "검토"}


def evidence_job(store):
    evidence = [{"id": "E1", "claim": "공식 발표에 따르면 도구는 3가지", "url": "https://example.com/a", "numbers": ["3"], "paragraph": 1, "scope": "발표"}]
    return store.create_job({"id": "rss-1", "title": "기사", "url": "https://example.com/a", "origin": "rss", "evidence": evidence})


def test_gate_block_alone_makes_quality_blocked(tmp_path):
    store = Store(tmp_path)
    job = evidence_job(store)
    provider = FullProvider("AI 도구 7가지")
    prepare_source(store, job["id"], provider=provider)
    quality = store.job(job["id"])["source_packet"]["quality"]
    assert quality["deterministic_checks"]["passed"] is True
    assert quality["gates"]["status"] == "block"
    assert quality["status"] == "blocked" and quality["critical"] is True
    assert "[브랜드 목소리" in provider.systems[0]

    store2 = Store(tmp_path / "ok")
    job2 = evidence_job(store2)
    prepare_source(store2, job2["id"], provider=FullProvider("AI 도구 비교"))
    quality2 = store2.job(job2["id"])["source_packet"]["quality"]
    assert quality2["gates"]["status"] != "block"
    assert quality2["status"] == "passed"


def test_refine_keeps_brand_bundle_and_packaging(tmp_path):
    store = Store(tmp_path)
    job = idea_job(store)
    attach_packaging(store, job["id"], brief(), "local-operator")
    provider = FullProvider("AI 도구 비교", fail_critique_once=True)
    prepare_source(store, job["id"], provider=provider)
    index = provider.roles.index("refine")
    assert "[브랜드 목소리" in provider.systems[index]
    assert "AI 팀이 블로그를 쓰는 법" in provider.users[index]
