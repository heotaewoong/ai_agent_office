"""외부 조사: 주장 종류로 조사 여부를 정하고, 무료 공개 출처에서 후보만 찾는다. 고른 것만 창고에 들어간다."""
import json

import pytest
from fastapi.testclient import TestClient

from office import external_research
from office.external_research import (
    add_trusted, build_queries, delete_trusted, guess_area, list_trusted, research_plan, run_research,
)
from office.public_evidence import looks_like_reference_list
from office.source_library import add_links, example_urls, item_detail, library_overview, update_item
from office.store import Store, WorkflowError

ARTICLE = "<html><head><title>아침 루틴 후기</title></head><body>" + "".join(
    f"<p>문단 {n}. 아침에 일어나서 물을 마시고 십 분 동안 책상에 앉아 오늘 할 일을 적는 습관을 석 달 동안 이어 갔습니다.</p>" for n in range(1, 8)) + "</body></html>"
ESEARCH = json.dumps({"esearchresult": {"idlist": ["111", "222"]}})
ESUMMARY = json.dumps({"result": {"uids": ["111", "222"],
                                  "111": {"title": "Spaced repetition and long-term memory.", "pubdate": "2021 Mar", "source": "Mem Cognit"},
                                  "222": {"title": "Distributed practice in classrooms.", "pubdate": "2019", "source": "Psychol Sci"}}})
OPENALEX = json.dumps({"results": [
    {"title": "Retrieval practice review", "publication_year": 2020, "doi": "https://doi.org/10.1/abc", "cited_by_count": 1234,
     "open_access": {"oa_url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC123"},
     "primary_location": {"landing_page_url": "https://doi.org/10.1/abc", "source": {"display_name": "Learning Journal"}}},
    {"title": "Paywalled", "publication_year": 2018, "doi": None, "open_access": {"oa_url": "http://insecure.example/x.pdf"},
     "primary_location": {"landing_page_url": None}}]})
ARXIV = ('<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom"><entry>'
         "<id>http://arxiv.org/abs/2501.01234v2</id><title>Agents with  tools</title><summary>We study tool use.</summary>"
         "<published>2025-01-03T00:00:00Z</published></entry></feed>")
GITHUB = json.dumps({"items": [
    {"full_name": "openclaw/openclaw", "html_url": "https://github.com/openclaw/openclaw", "description": "Personal agent",
     "stargazers_count": 51000, "pushed_at": "2026-11-20T01:00:00Z", "archived": False},
    {"full_name": "tiny/fork", "html_url": "https://github.com/tiny/fork", "description": "", "stargazers_count": 3, "pushed_at": "2026-01-01T00:00:00Z"}]})


def rss(*entries, title="루틴 연구소"):
    items = "".join(f"<item><title>{name}</title><link>{link}</link><description>{text}</description>"
                    "<pubDate>Mon, 16 Nov 2026 09:00:00 +0000</pubDate></item>" for name, link, text in entries)
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>{title}</title>{items}</channel></rss>'


CREATOR_FEED = rss(("아침 루틴을 석 달 해 본 후기", "https://www.youtube.com/watch?v=abc123xyz00", "기상 직후 루틴을 바꿔 본 기록"),
                   ("책상 정리 브이로그", "https://blog.example/desk", "서랍을 비웠습니다"),
                   ("주간 일기", "https://blog.example/diary", "이번 주 있었던 일"),
                   ("여행 준비물", "https://blog.example/trip", "가방 싸는 날"))


def routed(pages):
    calls = []

    def fetch(url, *, maximum):
        calls.append(url)
        for prefix, value in pages.items():
            if url.startswith(prefix):
                if isinstance(value, Exception):
                    raise value
                body, kind = value if isinstance(value, tuple) else (value, "application/json")
                return body.encode("utf-8"), url, kind
        raise OSError("not found")
    fetch.calls = calls
    return fetch


def offline(url, *, maximum):
    raise AssertionError(f"밖으로 나가면 안 되는 요청: {url}")


def no_library(root, title):
    return 0


@pytest.fixture(autouse=True)
def fresh_feed_cache():
    external_research._feed_cache.clear()


@pytest.mark.parametrize("title, area, need, fact, example, providers", [
    ("간격 복습이 기억에 미치는 효과", None, "required", "required", "none", ["pubmed", "openalex"]),
    ("Hermes와 OpenClaw 차이", None, "required", "required", "recommended", ["official", "github", "arxiv"]),
    ("정보처리기사 실기 접수 일정", None, "required", "required", "none", ["official"]),
    ("아침 루틴 만드는 방법", None, "recommended", "none", "recommended", []),
    ("퇴사하고 느낀 것들", "D", "recommended", "none", "recommended", []),
    ("집중 시간이 2배 늘어난 자기계발 습관", "D", "required", "required", "recommended", ["pubmed", "openalex"]),
    ("Claude Code 시작하기", "B", "recommended", "recommended", "recommended", ["official", "github", "arxiv"]),
    ("공부가 잘되는 책상", "C", "required", "required", "none", ["pubmed", "openalex"]),
])
def test_plan_follows_the_claims_the_topic_makes(title, area, need, fact, example, providers):
    plan = research_plan(title, area=area)
    assert (plan["need"], plan["fact"]["need"], plan["example"]["need"]) == (need, fact, example)
    assert plan["fact"]["providers"] == providers and plan["summary"].startswith(
        {"required": "외부 조사 필수", "recommended": "외부 조사 권장"}[need])
    assert plan["area_guessed"] is (area is None)


def test_experience_first_topics_stay_inside_and_warn_about_numbers():
    plan = research_plan("석 달 만에 집중 시간이 30% 늘어난 내 방법", area="D", experience_first=True)
    assert plan["need"] == "none" and plan["fact"]["providers"] == [] and "수치" in plan["warning"]
    assert research_plan("회사를 그만두고 배운 것", area="D", experience_first=True)["warning"] is None


def test_area_is_guessed_only_when_missing():
    assert [guess_area(text) for text in ("토익 900점 공부", "MCP 서버 만들기", "암기가 안 될 때", "자취방 청소 순서", "내가 일하는 이유")] == list("ABCED")
    assert research_plan("MCP 서버 만들기", area="E")["area"] == "E"


def test_queries_translate_known_words_and_respect_the_operators_own_query():
    made = build_queries("간격 복습이 기억에 미치는 효과")
    assert made["english"] == "spaced repetition memory" and {"복습", "기억", "효과", "spaced"} <= set(made["terms"]) and made["custom"] is False
    assert build_queries("Hermes와 OpenClaw 차이")["english"] == "Hermes OpenClaw"
    custom = build_queries("미루는 습관 고치기", "procrastination intervention")
    assert custom == {**custom, "english": "procrastination intervention", "custom": True}
    assert build_queries("퇴사 후기")["english"] == ""


def test_paper_search_returns_candidates_and_marks_what_is_already_stored(tmp_path):
    add_links(tmp_path, ["https://pubmed.ncbi.nlm.nih.gov/222/"], area="C", fetch=routed({"https://": (ARTICLE, "text/html")}))
    fetch = routed({"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch": ESEARCH,
                    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary": ESUMMARY, "https://api.openalex.org/": OPENALEX})
    result = run_research(tmp_path, "간격 복습이 기억에 미치는 효과", fetch=fetch, fact_sources=no_library)
    rows = {row["url"]: row for row in result["candidates"]}
    assert list(rows) == ["https://pubmed.ncbi.nlm.nih.gov/111/", "https://pubmed.ncbi.nlm.nih.gov/222/", "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC123"]
    first = rows["https://pubmed.ncbi.nlm.nih.gov/111/"]
    assert first["lane"] == "fact" and first["year"] == 2021 and first["snippet"] == "Mem Cognit · 2021 Mar" and first["in_library"] is False
    assert rows["https://pubmed.ncbi.nlm.nih.gov/222/"]["in_library"] is True
    assert "인용 1,234회" in rows["https://www.ncbi.nlm.nih.gov/pmc/articles/PMC123"]["snippet"]
    assert result["searched"] is True and "spaced+repetition+memory" in fetch.calls[0] + fetch.calls[1]
    assert library_overview(tmp_path)["stats"]["items"] == 1  # 후보는 저장하지 않는다.


def test_ai_topics_search_official_feeds_code_and_papers(tmp_path, monkeypatch):
    monkeypatch.setattr(external_research, "_official_sources", lambda area: [{"name": "공식 블로그", "feed_url": "https://official.example/rss"}])
    official = rss(("OpenClaw 2.0 release notes", "https://official.example/openclaw-2", "What changed in OpenClaw"),
                   ("Quarterly results", "https://official.example/q3", "Revenue"), ("Hiring", "https://official.example/jobs", "Join us"),
                   ("Office tour", "https://official.example/tour", "Photos"), title="공식")
    fetch = routed({"https://official.example/rss": (official, "application/rss+xml"), "https://api.github.com/": GITHUB,
                    "https://export.arxiv.org/": (ARXIV, "application/atom+xml")})
    result = run_research(tmp_path, "Hermes와 OpenClaw 차이", fetch=fetch, fact_sources=no_library)
    by_provider = {row["provider"]: row for row in result["candidates"]}
    assert by_provider["official"]["url"] == "https://official.example/openclaw-2" and by_provider["official"]["provider_label"] == "공식 블로그"
    assert by_provider["github"]["title"] == "openclaw/openclaw" and "별 51,000개" in by_provider["github"]["snippet"]
    assert by_provider["arxiv"]["url"] == "https://arxiv.org/abs/2501.01234" and by_provider["arxiv"]["title"] == "Agents with tools"
    assert [row["url"] for row in result["candidates"] if row["provider"] == "github"] == ["https://github.com/openclaw/openclaw"]
    assert any(note.startswith("사례·참고: 이 분야에 등록한 크리에이터가 없어요") for note in result["notes"])


def test_topics_that_need_nothing_never_leave_the_server(tmp_path):
    result = run_research(tmp_path, "회사를 그만두고 배운 것", area="D", experience_first=True, fetch=offline, fact_sources=no_library)
    assert result["candidates"] == [] and result["searched"] is False and result["plan"]["need"] == "none"


def test_library_candidate_count_never_skips_fact_search(tmp_path):
    result = run_research(tmp_path, "간격 복습이 기억에 미치는 효과", fact_sources=lambda root, title: 2,
                          fetch=routed({"https://eutils": ESEARCH.replace('"111", "222"', ""), "https://api.openalex.org/": '{"results": []}'}))
    assert result["searched"] is True
    assert result["library"] == {"fact_sources": 2, "sufficient": False}


def test_korean_only_topics_ask_for_an_english_query_and_one_slow_source_does_not_hide_the_rest(tmp_path):
    asked = run_research(tmp_path, "책상 높이가 자세에 주는 영향", area="C", fetch=offline, fact_sources=no_library)
    assert asked["candidates"] == [] and all("영어 검색어가 필요해요" in note for note in asked["notes"]) and len(asked["notes"]) == 2
    fetch = routed({"https://eutils": OSError("slow"), "https://api.openalex.org/": OPENALEX})
    partial = run_research(tmp_path, "책상 높이가 자세에 주는 영향", area="C", query="desk study environment", fetch=fetch, fact_sources=no_library)
    assert [row["provider"] for row in partial["candidates"]] == ["openalex"] and "PubMed 논문: 지금 응답이 없어요" in partial["notes"][0]


def test_trusted_creators_are_found_from_a_page_and_searched_only_in_their_area(tmp_path):
    page = '<html><head><link rel="alternate" type="application/rss+xml" href="/feed.xml?a=1&amp;b=2"></head><body>채널</body></html>'
    fetch = routed({"https://creator.example/feed.xml": (CREATOR_FEED, "application/rss+xml"), "https://creator.example/": (page, "text/html")})
    source = add_trusted(tmp_path, "https://creator.example/", area="D", lane="example", fetch=fetch)
    assert source["feed_url"] == "https://creator.example/feed.xml?a=1&b=2" and source["name"] == "루틴 연구소" and source["recent"] == 4
    assert [row["name"] for row in list_trusted(tmp_path)] == ["루틴 연구소"] and list_trusted(tmp_path)[0]["lane_label"] == "사례·참고"
    with pytest.raises(WorkflowError, match="이미 등록"):
        add_trusted(tmp_path, "https://creator.example/feed.xml?a=1&b=2", area="D", lane="example", fetch=fetch)
    result = run_research(tmp_path, "아침 루틴 만드는 방법", fetch=fetch, fact_sources=no_library)
    [row] = result["candidates"]
    assert row["lane"] == "example" and row["provider_label"] == "루틴 연구소" and row["needs_paste"] is True and "후기" in row["title"]
    other = run_research(tmp_path, "자취방 청소 꿀팁", fetch=offline, fact_sources=no_library)
    assert other["candidates"] == [] and any("등록한 크리에이터가 없어요" in note for note in other["notes"])
    assert delete_trusted(tmp_path, source["id"]) == {"deleted": source["id"]} and list_trusted(tmp_path) == []
    with pytest.raises(WorkflowError):
        delete_trusted(tmp_path, source["id"])


def test_trusted_source_rejects_pages_without_a_feed_and_bad_labels(tmp_path):
    with pytest.raises(WorkflowError, match="RSS"):
        add_trusted(tmp_path, "https://plain.example/", area="B", lane="example", fetch=routed({"https://plain.example/": ("<html><body>글</body></html>", "text/html")}))
    for bad in ({"url": "http://creator.example/", "area": "B", "lane": "example"}, {"url": "https://creator.example/", "area": "Z", "lane": "example"},
                {"url": "https://creator.example/", "area": "B", "lane": "opinion"}):
        with pytest.raises(WorkflowError):
            add_trusted(tmp_path, fetch=offline, **bad)


def test_chosen_candidates_enter_the_library_switched_on_in_their_lane(tmp_path):
    fetch = routed({"https://": (ARTICLE, "text/html")})
    [added] = add_links(tmp_path, ["https://creator.example/routine"], area="D", origin="research", lane="example", use_as_evidence=True, fetch=fetch)
    item = added["item"]
    assert item["lane"] == "example" and item["lane_label"] == "사례·참고" and item["use_as_evidence"] is True and item["origin"] == "research"
    assert example_urls(tmp_path) == {"https://creator.example/routine"}
    [again] = add_links(tmp_path, ["https://creator.example/routine"], area="D", fetch=fetch)
    assert again["result"] == "exists" and again["item"]["use_as_evidence"] is True
    [unread] = add_links(tmp_path, ["https://www.youtube.com/watch?v=abc123xyz00"], area="D", lane="example", use_as_evidence=True,
                         fetch=routed({"https://www.youtube.com/oembed": ('{"title": "루틴 영상"}', "application/json")}))
    assert unread["item"]["status"] == "needs_check" and unread["item"]["use_as_evidence"] is False
    assert update_item(tmp_path, item["id"], {"lane": "fact"})["lane"] == "fact" and example_urls(tmp_path) == {"https://www.youtube.com/watch?v=abc123xyz00"}
    with pytest.raises(WorkflowError):
        update_item(tmp_path, item["id"], {"lane": "rumor"})
    assert item_detail(tmp_path, item["id"])["lane"] == "fact"


def test_example_sources_reach_the_writer_as_examples_not_facts():
    from office.editorial import _with_approved_public_references
    references = [{"id": "a" * 64, "url": url, "title": "제목", "paragraph": 1, "quote": "인용", "source_sha256": "b" * 64, "quote_sha256": "c" * 64}
                  for url in ("https://creator.example/routine", "https://pubmed.ncbi.nlm.nih.gov/111/")]
    example, fact = _with_approved_public_references([], references, frozenset({"https://creator.example/routine"}))
    assert "사례·참고" in example["claim"] and "사실 주장의 근거로 쓰지 않음" in example["scope"] and example["id"] == "E1"
    assert fact["claim"] == "기획 승인⓪에서 선택한 공개 원문 발췌" and fact["scope"] == "원문 해당 문단의 서술. 독립 검증 미실시"
    assert _with_approved_public_references([], references)[0]["claim"] == fact["claim"]


def test_reference_lists_are_not_evidence():
    names = ("MemEvolve (Zhang et al., 2025h)\nCREATOR (Qian et al., 2023)\nGorilla (Patil et al., 2024)\nToolRerank (Zheng et al., 2024b)\n"
             "Voyager (Wang et al., 2024b)\nRepairAgent (Bouzenia et al., 2024)\nToolLLM (Qin et al., 2024a)")
    numbered = ("niques-for-maximizing-llm-performance-2, 2023.\n[167] J. Chen, H. Lin, X. Han, and L. Sun, “Benchmarking large language models in "
                "retrieval-augmented generation,” arXiv preprint arXiv:2309.01431, 2023.\n[168] Y. Liu, L. Huang, S. Li, S. Chen, H. Zhou, F. Meng")
    prose = ("Spaced practice improves retention compared with massed practice (Cepeda et al., 2006). Learners who reviewed material after a delay "
             "remembered more a week later, and the benefit grew with longer gaps between sessions, which suggests that forgetting a little before "
             "each review is part of what makes the review effective in classrooms.")
    assert looks_like_reference_list(names) and looks_like_reference_list(numbered)
    assert not looks_like_reference_list(prose) and not looks_like_reference_list("2024년에 3번 시험을 봤고 2025년에 합격했습니다. " * 4)


def client(tmp_path):
    from office.api import create_app
    api = TestClient(create_app(Store(tmp_path)), base_url="http://localhost:8510")
    api.headers.update({"Origin": "http://localhost:3110", "X-Office-CSRF": api.get("/api/session").json()["csrf"]})
    return api


def test_api_plans_many_topics_without_network_and_runs_one_search(tmp_path, monkeypatch):
    api = client(tmp_path)
    monkeypatch.setattr(external_research, "fetch_public", offline)
    plans = api.post("/api/source-library/research/plans", json={"topics": [
        {"id": "idea-1", "title": "간격 복습이 기억에 미치는 효과"}, {"id": "idea-2", "title": "회사를 그만두고 배운 것", "area": "D", "experience_first": True}]})
    assert plans.status_code == 200 and [(row["id"], row["need"]) for row in plans.json()["plans"]] == [("idea-1", "required"), ("idea-2", "none")]
    seen = {}
    monkeypatch.setattr("office.api_source_library.run_research", lambda root, title, **options: seen.update(title=title, **options) or {"candidates": []})
    run = api.post("/api/source-library/research", json={"title": "간격 복습", "area": "C", "query": "spacing effect", "force": True})
    assert callable(seen.pop("translate"))
    assert run.status_code == 200 and seen == {"title": "간격 복습", "summary": "", "area": "C", "kind": None, "experience_first": False, "query": "spacing effect", "force": True}
    assert api.post("/api/source-library/research", json={"title": ""}).status_code == 422
    assert api.post("/api/source-library/research", json={"title": "a", "force": "yes"}).status_code == 422


def test_api_registers_trusted_sources_and_saves_a_chosen_candidate(tmp_path, monkeypatch):
    from office import public_evidence, source_library
    api = client(tmp_path)
    started = []
    monkeypatch.setattr(public_evidence, "start_library_vectors", lambda root: started.append(root) or False)
    monkeypatch.setattr(external_research, "fetch_public", lambda url, *, maximum, deadline: (CREATOR_FEED.encode(), url, "application/rss+xml"))
    made = api.post("/api/source-library/trusted", json={"url": "https://creator.example/feed.xml", "area": "D", "lane": "example", "name": "내 단골"})
    assert made.status_code == 201 and made.json()["source"]["name"] == "내 단골" and len(api.get("/api/source-library/trusted").json()["sources"]) == 1
    assert api.post("/api/source-library/trusted", json={"url": "https://creator.example/feed.xml", "area": "D", "lane": "rumor"}).status_code == 422
    gone = api.delete(f"/api/source-library/trusted/{made.json()['source']['id']}")
    assert gone.status_code == 200 and gone.json()["sources"] == []
    monkeypatch.setattr(source_library, "fetch_public", lambda url, *, maximum, deadline: (ARTICLE.encode(), url, "text/html"))
    saved = api.post("/api/source-library/links", json={"urls": ["https://creator.example/routine"], "area": "D", "origin": "research",
                                                        "origin_ref": "idea-1", "lane": "example", "use_as_evidence": True})
    body = saved.json()
    assert saved.status_code == 200 and body["results"][0]["item"]["use_as_evidence"] is True and body["results"][0]["item"]["lane"] == "example"
    assert body["stats"]["evidence"] == 1 and started and body["lanes"] == [{"id": "fact", "label": "사실 근거"}, {"id": "example", "label": "사례·참고"}]
    assert api.patch(f"/api/source-library/items/{body['results'][0]['item']['id']}", json={"lane": "fact"}).json()["item"]["lane"] == "fact"


def test_translated_queries_drive_paper_search_while_code_search_keeps_product_names(tmp_path):
    asked = []

    def translate(title):
        asked.append(title)
        return {"queries": ["agent framework comparison", "autonomous agent runtime"], "source": "model", "note": None}
    fetch = routed({"https://api.github.com/": GITHUB, "https://export.arxiv.org/": (ARXIV, "application/atom+xml")})
    result = run_research(tmp_path, "Hermes와 OpenClaw 차이", fetch=fetch, fact_sources=no_library, translate=translate)
    assert asked == ["Hermes와 OpenClaw 차이"] and result["queries"]["english"] == "agent framework comparison"
    assert result["queries"]["alternatives"] == ["autonomous agent runtime"] and result["queries"]["translated"] is True
    assert any("all:agent+AND+all:framework+AND+all:comparison" in url for url in fetch.calls)
    assert any("q=Hermes+in:name" in url for url in fetch.calls) and any("q=OpenClaw+in:name" in url for url in fetch.calls)


def test_translation_is_skipped_for_own_queries_and_falls_back_with_a_note(tmp_path):
    def never(title):
        raise AssertionError("운영자가 검색어를 적었으면 자동으로 만들지 않는다")
    fetch = routed({"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch": ESEARCH,
                    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary": ESUMMARY, "https://api.openalex.org/": OPENALEX})
    own = run_research(tmp_path, "간격 복습이 기억에 미치는 효과", query="spacing effect", fetch=fetch, fact_sources=no_library, translate=never)
    assert own["queries"]["english"] == "spacing effect" and "translated" not in own["queries"]
    assert run_research(tmp_path, "회사를 그만두고 배운 것", area="D", experience_first=True, fetch=offline, fact_sources=no_library, translate=never)["searched"] is False
    note = "이번 달 영어 검색어 자동 만들기 한도(300원)를 다 써서 낱말표로 찾았어요."
    fallback = run_research(tmp_path, "간격 복습이 기억에 미치는 효과", fetch=fetch, fact_sources=no_library,
                            translate=lambda title: {"queries": [], "source": None, "note": note})
    assert fallback["queries"]["english"] == "spaced repetition memory" and note in fallback["notes"] and fallback["candidates"]


def test_paper_search_moves_to_the_next_generated_query_when_the_first_finds_nothing(tmp_path):
    calls = []

    def fetch(url, *, maximum):
        calls.append(url)
        if "esearch" in url:
            return (ESEARCH if "term=spacing+effect" in url else json.dumps({"esearchresult": {"idlist": []}})).encode(), url, "application/json"
        return (ESUMMARY if "esummary" in url else '{"results": []}').encode(), url, "application/json"
    result = run_research(tmp_path, "간격 복습이 기억에 미치는 효과", fetch=fetch, fact_sources=no_library,
                          translate=lambda title: {"queries": ["spaced repetition memory retention benefit", "spacing effect"], "source": "model", "note": None})
    assert [row["url"] for row in result["candidates"]] == ["https://pubmed.ncbi.nlm.nih.gov/111/", "https://pubmed.ncbi.nlm.nih.gov/222/"]
    assert [("benefit" in url, "spacing+effect" in url) for url in calls if "esearch" in url] == [(True, False), (False, True)]


def test_exam_official_page_is_a_candidate_and_store_coupon_needs_separate_confirmation(tmp_path):
    opic = run_research(tmp_path, "오픽 IM2에서 막힌 분을 위한 첫 7일", area="A", query="IM2",
                        fetch=offline, fact_sources=no_library)
    assert any("opic.co.kr/" in candidate["url"] for candidate in opic["candidates"])
    assert opic["library"]["sufficient"] is False
    transfer = run_research(tmp_path, "편입 영어 단어 복습과 50% 쿠폰 캠페인", area="A",
                            fetch=offline, fact_sources=no_library)
    assert any("스토어 확인" in note for note in transfer["notes"])
    assert any("대학 입학처" in note for note in transfer["notes"])
    assert not any("opic.co.kr/" in candidate["url"] for candidate in transfer["candidates"])
