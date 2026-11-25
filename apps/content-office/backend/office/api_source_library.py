"""자료 창고 API. office/api.py의 create_app에서 register(app, store)로 붙인다.

저장·검색만 한다: 작업 시간을 열지 않는다. 유료 호출은 외부 조사에서 한글 주제를 영어 검색어로 바꿀 때 한 번뿐이다(research_query, 월 한도). 근거로 켠 링크 자료의 문단 벡터는
public_evidence의 로컬 작업자가 자료 창고 전용 임베딩 모델로 따로 계산한다(질문 벡터 작업자와 같은 잠금).
인증·CSRF는 api.py의 공통 미들웨어가, WorkflowError는 공통 핸들러가 409로 처리한다.
"""
from __future__ import annotations

from typing import Literal

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field

from .external_research import add_trusted, delete_trusted, list_trusted, research_plan, run_research, run_tavily, tavily_usage
from .research_choices import click_stats, log_click, save_choice
from .research_query import english_queries
from .source_library import (
    add_file, add_links, add_memo, delete_item, fill_text, item_detail, library_overview, retry_item, search_library,
    set_evidence, update_item,
)

Origin = Literal["manual", "idea", "news", "artifact", "import", "research"]
Lane = Literal["fact", "example"]
Kind = Literal["W1", "W2", "W3", "W4", "W5"]


class _Entry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    area: str = Field(max_length=8)
    mine: bool = Field(default=False, strict=True)
    origin: Origin = "manual"
    origin_ref: str | None = Field(default=None, max_length=160)


class LibraryLinks(_Entry):
    urls: list[str] = Field(min_length=1, max_length=10)
    title: str | None = Field(default=None, max_length=300)
    lane: Lane = "fact"
    use_as_evidence: bool = Field(default=False, strict=True)


class LibraryMemo(_Entry):
    title: str = Field(max_length=300)
    text: str = Field(max_length=80_000)
    mine: bool = Field(default=True, strict=True)


class LibraryFile(_Entry):
    name: str = Field(max_length=300)
    content_base64: str = Field(max_length=11_000_000)


class LibraryPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    use_as_evidence: bool | None = Field(default=None, strict=True)
    area: str | None = Field(default=None, max_length=8)
    mine: bool | None = Field(default=None, strict=True)
    title: str | None = Field(default=None, max_length=300)
    lane: Lane | None = None


class LibraryText(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(max_length=80_000)
    title: str | None = Field(default=None, max_length=300)


class LibraryEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[str] = Field(min_length=1, max_length=1000)
    use_as_evidence: bool = Field(strict=True)


class ResearchTopic(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str | None = Field(default=None, max_length=160)
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(default="", max_length=2000)
    area: str | None = Field(default=None, max_length=8)
    kind: Kind | None = None
    experience_first: bool = Field(default=False, strict=True)


class ResearchRun(ResearchTopic):
    query: str | None = Field(default=None, max_length=200)
    force: bool = Field(default=False, strict=True)


class TavilyRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str | None = Field(default=None, max_length=160)
    title: str = Field(min_length=1, max_length=300)
    query: str | None = Field(default=None, max_length=200)


class ResearchPlans(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topics: list[ResearchTopic] = Field(min_length=1, max_length=80)


class ResearchChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Kind
    area: str = Field(max_length=8)


class TrustedSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(max_length=2048)
    area: str = Field(max_length=8)
    lane: Lane
    name: str | None = Field(default=None, max_length=120)


def _prepare_vectors(root) -> None:
    # 근거로 켠 링크 문단을 공개 근거 검색과 같은 모델로 계산한다. 다른 계산이 돌고 있으면 다음 요청 때 이어서 한다.
    from .public_evidence import start_library_vectors
    start_library_vectors(root)


def register(app, store):
    root = store.root

    def tags(entry: _Entry) -> dict:
        return {"area": entry.area, "mine": entry.mine, "origin": entry.origin, "origin_ref": entry.origin_ref}

    @app.get("/api/source-library")
    def library():
        overview = library_overview(root)
        if overview["vectors"]["pending"] and overview["vectors"]["available"]:
            _prepare_vectors(root)
        return overview

    @app.get("/api/source-library/search")
    def library_search(q: str = Query(max_length=300), area: str | None = Query(default=None, max_length=8),
                       evidence_only: bool = False):
        return {"query": q, "results": search_library(root, q, area=area or None, evidence_only=evidence_only)}

    @app.get("/api/source-library/items/{item_id}")
    def library_item(item_id: str):
        return item_detail(root, item_id)

    @app.post("/api/source-library/links")
    def library_links(body: LibraryLinks):
        results = add_links(root, body.urls, title=body.title, lane=body.lane, use_as_evidence=body.use_as_evidence, **tags(body))
        if body.use_as_evidence:
            _prepare_vectors(root)
        return {"results": results, **library_overview(root)}

    @app.post("/api/source-library/research/plans")
    def library_research_plans(body: ResearchPlans):
        # 기준만 계산한다. 밖으로 나가는 요청은 없다.
        return {"plans": [{"id": topic.id, **research_plan(topic.title, topic.summary, area=topic.area, kind=topic.kind,
                                                          experience_first=topic.experience_first)} for topic in body.topics]}

    @app.post("/api/source-library/research")
    def library_research(body: ResearchRun):
        result = run_research(root, body.title, summary=body.summary, area=body.area, kind=body.kind,
                              experience_first=body.experience_first,
                              query=body.query, force=body.force, translate=lambda title: english_queries(store, title))
        if body.id:
            # 사람이 기획 카드에서 누른 조사만 센다. 추천과 실제로 누른 것이 얼마나 맞는지 보려는 기록이다.
            log_click(root, body.id, result.get("plan") or {}, forced=body.force, searched=bool(result.get("searched")),
                      candidates=len(result.get("candidates") or []))
        return result

    @app.get("/api/source-library/research/tavily")
    def library_tavily_usage():
        # 키 자체는 돌려주지 않는다. 있는지와 이번 달 사용 횟수만 보여 준다.
        return tavily_usage(root)

    @app.post("/api/source-library/research/tavily")
    def library_tavily(body: TavilyRun):
        # 사람이 누른 Tavily 1회 검색. 검색어는 기획 제목이나 운영자가 적은 검색어뿐이다.
        result = run_tavily(root, body.title, query=body.query)
        if body.id:
            log_click(root, body.id, {"need": "tavily"}, forced=True, searched=bool(result.get("searched")),
                      candidates=len(result.get("candidates") or []))
        return result

    @app.put("/api/source-library/research/choices/{idea_id}")
    def library_research_choice(idea_id: str, body: ResearchChoice):
        # 사람이 고른 글 유형과 분야만 저장한다. 기획 카드와 승인은 바꾸지 않는다.
        return {"choice": save_choice(root, idea_id, kind=body.kind, area=body.area)}

    @app.get("/api/source-library/research/clicks")
    def library_research_clicks():
        return click_stats(root)

    @app.get("/api/source-library/trusted")
    def library_trusted():
        return {"sources": list_trusted(root)}

    @app.post("/api/source-library/trusted", status_code=201)
    def library_trusted_add(body: TrustedSource):
        return {"source": add_trusted(root, body.url, area=body.area, lane=body.lane, name=body.name), "sources": list_trusted(root)}

    @app.delete("/api/source-library/trusted/{source_id}")
    def library_trusted_delete(source_id: str):
        return {**delete_trusted(root, source_id), "sources": list_trusted(root)}

    @app.post("/api/source-library/memos", status_code=201)
    def library_memo(body: LibraryMemo):
        return {"item": add_memo(root, body.title, body.text, **tags(body)), **library_overview(root)}

    @app.post("/api/source-library/files", status_code=201)
    def library_file(body: LibraryFile):
        return {"item": add_file(root, body.name, body.content_base64, **tags(body)), **library_overview(root)}

    @app.patch("/api/source-library/items/{item_id}")
    def library_update(item_id: str, body: LibraryPatch):
        item = update_item(root, item_id, body.model_dump(exclude_none=True))
        if body.use_as_evidence:
            _prepare_vectors(root)
        return {"item": item, **library_overview(root)}

    @app.post("/api/source-library/evidence")
    def library_evidence(body: LibraryEvidence):
        result = set_evidence(root, body.ids, body.use_as_evidence)
        if body.use_as_evidence and result["changed"]:
            _prepare_vectors(root)
        return {**result, **library_overview(root)}

    @app.post("/api/source-library/items/{item_id}/text")
    def library_text(item_id: str, body: LibraryText):
        return {"item": fill_text(root, item_id, body.text, body.title), **library_overview(root)}

    @app.post("/api/source-library/items/{item_id}/retry")
    def library_retry(item_id: str):
        return {"item": retry_item(root, item_id), **library_overview(root)}

    @app.delete("/api/source-library/items/{item_id}")
    def library_delete(item_id: str):
        return {**delete_item(root, item_id), **library_overview(root)}
