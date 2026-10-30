from typing import Literal
from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field
from . import discovery


class ResearchConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    platforms: list[Literal['youtube', 'naver_blog', 'tistory', 'instagram', 'threads', 'x', 'linkedin']] = Field(min_length=1, max_length=7)
    topic: str = Field(min_length=1, max_length=80)
    region: Literal['KR', 'US', 'GB', 'JP']
    youtube_channels: list[str] = Field(min_length=1, max_length=6)
    expected_hash: str = Field(pattern=r'^[0-9a-f]{64}$')


def register(app: FastAPI, store):
    @app.get('/api/discovery')
    def read_discovery():
        return discovery.status(store)

    @app.put('/api/discovery')
    def save_discovery(body: ResearchConfig):
        task = discovery.save(store, body.model_dump(exclude={'expected_hash'}), body.expected_hash)
        return {**discovery.status(store), 'task': task}

    @app.post('/api/discovery/refresh', status_code=202)
    def refresh_discovery():
        # Enqueue only; the existing worker and operator window gate every external collection.
        return discovery.queue(store)
