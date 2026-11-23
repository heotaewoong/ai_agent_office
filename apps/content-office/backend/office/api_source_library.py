"""자료 창고 API. office/api.py의 create_app에서 register(app, store)로 붙인다.

저장·검색만 한다: 작업 시간을 열거나 유료 API를 부르지 않는다. 근거로 켠 링크 자료의 문단 벡터는
public_evidence의 로컬 MiniLM 작업자가 따로 계산한다(공개 근거 검색과 같은 모델, 같은 잠금).
인증·CSRF는 api.py의 공통 미들웨어가, WorkflowError는 공통 핸들러가 409로 처리한다.
"""
from __future__ import annotations

from typing import Literal

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field

from .source_library import (
    add_file, add_links, add_memo, delete_item, fill_text, item_detail, library_overview, retry_item, search_library,
    set_evidence, update_item,
)

Origin = Literal["manual", "idea", "news", "artifact", "import"]


class _Entry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    area: str = Field(max_length=8)
    mine: bool = Field(default=False, strict=True)
    origin: Origin = "manual"
    origin_ref: str | None = Field(default=None, max_length=160)


class LibraryLinks(_Entry):
    urls: list[str] = Field(min_length=1, max_length=10)
    title: str | None = Field(default=None, max_length=300)


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


class LibraryText(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(max_length=80_000)
    title: str | None = Field(default=None, max_length=300)


class LibraryEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[str] = Field(min_length=1, max_length=1000)
    use_as_evidence: bool = Field(strict=True)


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
        return {"results": add_links(root, body.urls, title=body.title, **tags(body)), **library_overview(root)}

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
