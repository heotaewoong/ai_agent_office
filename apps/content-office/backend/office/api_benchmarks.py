from fastapi import FastAPI
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from fastapi.responses import JSONResponse

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
    item_id: str | None = Field(default=None, min_length=1, max_length=96)
    snapshot_hash: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')


class ResearchInput(ExpectedInput):
    source_ids: list[str] = Field(max_length=64)
    fields: list[str] = Field(max_length=6)
    platforms: list[str] = Field(max_length=len(benchmarks.PLATFORMS))
    item_ids: list[str] | None = Field(default=None, max_length=6)
    snapshot_hash: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')


class ObservedMetric(StrictInput):
    value: int | None = Field(strict=True, ge=0, le=9007199254740991)
    availability: Literal['observed', 'not_visible', 'unknown']
    raw_text: str = Field(max_length=80)
    precision: Literal['exact', 'approximate', 'unknown']


class Observation(StrictInput):
    url: str = Field(min_length=1, max_length=2000)
    author_username: str = Field(min_length=1, max_length=30)
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(max_length=700)
    published_at: str | None = Field(max_length=64)
    observed_at: str = Field(min_length=1, max_length=64)
    metrics: dict[Literal['views', 'likes', 'comments', 'reposts'], ObservedMetric] = Field(max_length=4)


class ObservationInput(ExpectedInput):
    source_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')
    snapshot_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    capture_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    collection_scope: str = Field(min_length=1, max_length=300)
    items: list[Observation] = Field(min_length=1, max_length=20)


class ResearchRunInput(ResearchInput):
    request_id: UUID
    item_ids: list[str] = Field(min_length=1, max_length=6)
    snapshot_hash: str = Field(pattern=r'^[0-9a-f]{64}$')


class AnalysisReceipt(StrictInput):
    task_id: str = Field(pattern=r'^t_[A-Za-z0-9_-]{1,80}$')
    run_id: int = Field(strict=True, gt=0, le=9007199254740991)
    event_id: int = Field(strict=True, gt=0, le=9007199254740991)
    report_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    body_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


class ResearchIdeaInput(StrictInput):
    item_id: str = Field(min_length=1, max_length=96)
    title: str = Field(min_length=1, max_length=200)
    angle: str = Field(min_length=1, max_length=1000)
    target_platforms: list[str] = Field(min_length=1, max_length=len(benchmarks.PLATFORMS))
    receipt: AnalysisReceipt


def register(app: FastAPI, store):
    def research_call(operation, *args):
        from . import assistant_requests as bridge, benchmark_research
        native = getattr(app.state, 'assistant_native', None)
        try:
            return getattr(benchmark_research, operation)(store, native if native is not None else bridge.configured_client(), *args)
        except bridge.BridgeError as error:
            return JSONResponse({'code': error.code, 'message': str(error), 'detail': str(error)}, status_code=error.status)

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
        return benchmarks.save_idea(store, body.model_dump(exclude_none=True))

    @app.post('/api/benchmarks/observations')
    def import_observations(body: ObservationInput):
        return benchmarks.import_observations(store, body.model_dump())

    @app.post('/api/benchmarks/research-packet')
    def prepare_research(body: ResearchInput):
        return benchmarks.research_packet(store, body.model_dump(exclude_none=True))

    @app.post('/api/benchmarks/research-runs', status_code=202)
    def submit_research(body: ResearchRunInput):
        return research_call('submit_run', body.model_dump(mode='json'))

    @app.get('/api/benchmarks/research-runs/{request_id}')
    def read_research(request_id: UUID):
        return research_call('read_run', str(request_id))

    @app.post('/api/benchmarks/research-runs/{request_id}/ideas')
    def save_research_idea(request_id: UUID, body: ResearchIdeaInput):
        return research_call('save_run_idea', str(request_id), body.model_dump())
