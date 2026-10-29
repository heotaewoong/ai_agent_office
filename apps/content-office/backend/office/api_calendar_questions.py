"""시험 일정·시의성과 독자 질문 수집 API. office/api.py의 create_app에서 register(app, store)로 붙인다.

인증·CSRF는 api.py의 공통 미들웨어가 처리하고, WorkflowError는 공통 핸들러가 409로 돌려준다.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .briefs import DEFAULT_PRESET
from .calendar import calendar_for
from .questions import convert_question, list_questions, receive_question


class QuestionInput(BaseModel):
    source: Literal["homepage", "comment", "dm", "email", "other"]
    text: str = Field(min_length=5, max_length=1000)
    channel_key: str | None = Field(default=None, max_length=100)


class QuestionIdeaInput(BaseModel):
    brief_preset: str | None = Field(default=None, max_length=100)
    title: str | None = Field(default=None, max_length=200)


def register(app, store):
    @app.get("/api/calendar")
    def exam_calendar(preset: str = DEFAULT_PRESET):
        return calendar_for(preset)

    @app.get("/api/questions")
    def questions():
        return list_questions(store)

    @app.post("/api/questions")
    def add_question(body: QuestionInput):
        return {"question": receive_question(store, body.source, body.text, body.channel_key)}

    @app.post("/api/questions/{question_id}/idea")
    def question_to_idea(question_id: str, body: QuestionIdeaInput):
        return {"idea": convert_question(store, question_id, body.brief_preset, body.title, lessons=store.lessons("approved"))}
