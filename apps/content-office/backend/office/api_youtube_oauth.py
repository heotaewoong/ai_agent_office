"""YouTube 채널 연결(OAuth) API. office/api.py의 create_app에서 register(app, store)로 붙인다.

POST 요청의 세션·CSRF·Origin 검사는 api.py 공통 미들웨어가 하고, WorkflowError는 공통 핸들러가 409로 돌려준다.
콜백은 Google이 브라우저를 보내는 GET이라 결과를 JSON 대신 앱 첫 화면(/?youtube=...)으로 303 리디렉션한다.
토큰 교환·채널 조회 전송은 테스트에서 app.state.youtube_oauth_transport로 바꿀 수 있다.
"""
from __future__ import annotations

from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from .youtube_oauth import BINDING_COOKIE, COOKIE_PATH, STATE_TTL, OAuthFailure, begin, disconnect, finish, status


class OAuthChannel(BaseModel):
    channel_key: str = Field(min_length=1, max_length=64)


def register(app, store):
    def origin():
        from .api import public_origin
        return public_origin()

    @app.get("/api/youtube/oauth/status")
    def youtube_oauth_status():
        return JSONResponse(status(store, origin()), headers={"Cache-Control": "no-store"})

    @app.post("/api/youtube/oauth/start")
    def youtube_oauth_start(body: OAuthChannel):
        url, binding = begin(store, body.channel_key, origin())
        response = JSONResponse({"authorize_url": url, "expires_in": STATE_TTL}, headers={"Cache-Control": "no-store"})
        response.set_cookie(BINDING_COOKIE, binding, max_age=STATE_TTL, path=COOKIE_PATH, httponly=True, samesite="lax", secure=True)
        return response

    @app.get("/api/youtube/oauth/callback")
    def youtube_oauth_callback(request: Request, state: str = "", code: str = "", error: str = ""):
        transport = getattr(app.state, "youtube_oauth_transport", None)
        try:
            key = finish(store, origin=origin(), state=state, code=code, error=error, binding=request.cookies.get(BINDING_COOKIE), transport=transport)
            params = {"youtube": "connected", "channel": key}
        except OAuthFailure as failure:
            params = {"youtube": "error", "reason": failure.reason}
            if failure.channel_key:
                params["channel"] = failure.channel_key
                # 공개 채널 ID만 진단에 남긴다. 토큰·Google 계정 정보는 포함하지 않는다.
                if failure.reason == "channel_mismatch":
                    params.update(actual_channel=failure.actual_channel_id, expected_channel=failure.expected_channel_id)
                store.event("youtube_channel_connect_failed", {"channel_key": failure.channel_key, **{k: v for k, v in params.items() if k not in ("youtube", "channel")}})
        response = RedirectResponse("/?" + urlencode(params), status_code=303, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
        response.delete_cookie(BINDING_COOKIE, path=COOKIE_PATH, secure=True, httponly=True, samesite="lax")
        return response

    @app.post("/api/youtube/oauth/disconnect")
    def youtube_oauth_disconnect(body: OAuthChannel):
        return disconnect(store, body.channel_key)
