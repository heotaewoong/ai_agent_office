"""매일 아침 뉴스 자동 수집 설정 API. office/api.py의 create_app에서 register(app, store)로 붙인다.

설정 저장만 한다: 작업 시간을 열거나 수집·요약·작업자를 시작하지 않는다(실행은 cron의 scripts/daily_collect.py).
인증·CSRF는 api.py의 공통 미들웨어가, WorkflowError는 공통 핸들러가 409로 처리한다.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from .daily_collect import daily_collect_status, update_daily_collect_settings


class DailyCollectPatch(BaseModel):
    # 값 검증은 update_daily_collect_settings가 한다(형식 오류도 409로 같은 문장).
    model_config = ConfigDict(extra="allow")
    enabled: Any = None
    time_kst: Any = None
    minutes: Any = None
    max_krw: Any = None


def register(app, store):
    @app.get("/api/settings/daily-collect")
    def daily_collect():
        return daily_collect_status(store)

    @app.put("/api/settings/daily-collect")
    def update_daily_collect(patch: DailyCollectPatch):
        update_daily_collect_settings(store, patch.model_dump(exclude_unset=True), actor="local-operator")
        return daily_collect_status(store)
