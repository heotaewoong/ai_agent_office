"""The existing operator CSRF middleware protects all lifecycle writes."""
from typing import Literal
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ConfigDict
from . import artifact_library as library


class Selection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ids: list[str] = Field(min_length=1, max_length=100)
    action: Literal['trash', 'restore', 'purge']


class Change(Selection):
    quote: str = Field(min_length=66, max_length=90)
    request_id: str = Field(min_length=1, max_length=80)


def register(app, store):
    @app.get('/api/library')
    def inventory():
        return library.inventory(store)

    @app.post('/api/library/quote')
    def quote(body: Selection):
        return library.quote(store, body.ids, body.action)

    @app.post('/api/library/change')
    def change(body: Change):
        return library.change(store, body.ids, body.action, body.quote, body.request_id)

    @app.get('/api/library/items/{identity}/files/{index}')
    def preview(identity: str, index: int):
        path, media_type = library.preview_file(store, identity, index)
        # Generated HTML must not execute script with operator privileges.
        return FileResponse(path, media_type=media_type, headers={'Cache-Control': 'no-store',
            'X-Content-Type-Options': 'nosniff', 'Content-Security-Policy': "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:"})
