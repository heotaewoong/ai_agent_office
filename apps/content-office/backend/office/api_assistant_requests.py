"""Operator-authenticated bridge to existing native Hermes Kanban."""
from typing import Literal
from uuid import UUID

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import assistant_requests as bridge


class AssistantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    text: str = Field(min_length=1, max_length=8000)
    assignee: Literal["lumi"] = "lumi"

    @field_validator("text")
    @classmethod
    def nonempty_text(cls, text):
        if not text.strip() or len(text.encode("utf-8")) > 24000:
            raise ValueError("업무 내용을 입력해 주세요")
        return text.strip()


def register(app: FastAPI, store):
    def native():
        client = getattr(app.state, "assistant_native", None)
        return client if client is not None else bridge.configured_client()

    def error_response(error):
        return JSONResponse({"code": error.code, "message": str(error), "detail": str(error)},
                            status_code=error.status)

    @app.post("/api/assistant/requests", status_code=202)
    def submit_request(body: AssistantRequest):
        try:
            return bridge.submit(store, native(), str(body.request_id), body.text)
        except bridge.BridgeError as error:
            return error_response(error)
        except (KeyError, TypeError, ValueError, OSError, AttributeError):
            return error_response(bridge.BridgeError("native_invalid_response", "비서 응답을 확인할 수 없습니다"))

    @app.get("/api/assistant/requests/{request_id}")
    def read_request(request_id: UUID):
        try:
            return bridge.read_request(store, native(), str(request_id))
        except bridge.BridgeError as error:
            return error_response(error)
        except (KeyError, TypeError, ValueError, OSError, AttributeError):
            return error_response(bridge.BridgeError("native_invalid_response", "비서 응답을 확인할 수 없습니다"))
