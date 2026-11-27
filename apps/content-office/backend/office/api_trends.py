"""트렌드 신호 API: 설정 읽기와 저장, 모으기 요청(작업자가 작업 시간 안에서만 실행)."""
from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

from . import trend_signals


class TrendSettingsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    seeds: list[str] = Field(min_length=1, max_length=trend_signals.MAX_SEEDS)
    sources: list[str] = Field(min_length=1, max_length=len(trend_signals.SOURCES))


def register(app: FastAPI, store):
    @app.get("/api/trend-signals")
    def read_trend_signals():
        return trend_signals.trend_status(store)

    @app.put("/api/trend-signals")
    def save_trend_signals(body: TrendSettingsInput):
        trend_signals.update_trend_settings(store, body.model_dump(), actor="local-operator")
        return trend_signals.trend_status(store)

    @app.post("/api/trend-signals/refresh", status_code=202)
    def refresh_trend_signals():
        # 줄만 세운다. 밖으로 나가는 요청은 작업자가 운영자가 연 작업 시간 안에서만 한다.
        return trend_signals.queue_trends(store)
