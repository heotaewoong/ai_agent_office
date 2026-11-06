from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

from . import benchmarks


class StrictInput(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Source(StrictInput):
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')
    creator_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')
    name: str = Field(min_length=1, max_length=80)
    platform: str = Field(min_length=1, max_length=30)
    url: str = Field(min_length=1, max_length=2000)
    fields: list[str] = Field(min_length=1, max_length=6)
    channel_id: str | None = Field(default=None, max_length=24)


class RegistryInput(StrictInput):
    sources: list[Source] = Field(max_length=64)
    expected_hash: str = Field(pattern=r'^[0-9a-f]{64}$')


class ExpectedInput(StrictInput):
    expected_hash: str = Field(pattern=r'^[0-9a-f]{64}$')


class IdeaInput(ExpectedInput):
    title: str = Field(min_length=1, max_length=200)
    source_url: str = Field(min_length=1, max_length=2000)
    source_id: str = Field(max_length=64)
    fields: list[str] = Field(min_length=1, max_length=6)
    target_platforms: list[str] = Field(min_length=1, max_length=len(benchmarks.PLATFORMS))
    angle: str = Field(min_length=1, max_length=1000)


class ResearchInput(ExpectedInput):
    source_ids: list[str] = Field(min_length=1, max_length=64)
    fields: list[str] = Field(max_length=6)
    platforms: list[str] = Field(max_length=len(benchmarks.PLATFORMS))


def register(app: FastAPI, store):
    @app.get('/api/benchmarks')
    def read_benchmarks():
        return benchmarks.status(store)

    @app.put('/api/benchmarks')
    def save_benchmarks(body: RegistryInput):
        return benchmarks.save(store, {'sources': [row.model_dump(exclude_none=True) for row in body.sources]}, body.expected_hash)

    @app.post('/api/benchmarks/refresh', status_code=202)
    def refresh_benchmarks(body: ExpectedInput):
        return benchmarks.queue(store, body.expected_hash)

    @app.post('/api/benchmarks/ideas')
    def save_benchmark_idea(body: IdeaInput):
        return benchmarks.save_idea(store, body.model_dump())

    @app.post('/api/benchmarks/research-packet')
    def prepare_research(body: ResearchInput):
        return benchmarks.research_packet(store, body.model_dump())
