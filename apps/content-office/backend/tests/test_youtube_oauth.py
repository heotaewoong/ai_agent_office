"""YouTube 채널 연결(OAuth): 로그인으로 refresh token을 받아 상태 폴더 밖 비밀 파일에만 둔다.

Google 서버는 부르지 않는다. 토큰 교환·채널 조회는 app.state.youtube_oauth_transport 가짜로 대신한다.
"""
import json
import os
import stat
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from office.api import create_app
from office.store import Store

PUBLIC = "https://office.example.com"
REFRESH = "rt-SENTINEL-refresh"
ACCESS = "at-SENTINEL-access"
SECRET = "csecret-SENTINEL"
MAIN_ID = "UCmainko0000000000000000"
ENGLISH_ID = "UCc2CaOrPo-1dezowe7kklZA"
SCOPES = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"


class FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class FakeTransport:
    def __init__(self, *, token=None, token_status=200, channels=None, channels_status=200):
        self.token = token if token is not None else {"access_token": ACCESS, "refresh_token": REFRESH, "scope": SCOPES, "token_type": "Bearer", "expires_in": 3599}
        self.token_status = token_status
        self.channels = channels if channels is not None else {"items": [{"id": MAIN_ID, "snippet": {"title": "허브레인"}}]}
        self.channels_status = channels_status
        self.calls = []

    def post(self, url, data=None, timeout=None, **_):
        self.calls.append(("post", url, dict(data or {})))
        return FakeResponse(self.token_status, self.token)

    def get(self, url, headers=None, params=None, timeout=None, **_):
        self.calls.append(("get", url, {"headers": dict(headers or {}), "params": dict(params or {})}))
        return FakeResponse(self.channels_status, self.channels)


@pytest.fixture
def oauth(tmp_path, monkeypatch, isolated_secrets_file):
    monkeypatch.delenv("YOUTUBE_OAUTH_CLIENT_TYPE", raising=False)
    for key in ("YOUTUBE_REFRESH_TOKEN", "YOUTUBE_MAIN_KO_REFRESH_TOKEN", "YOUTUBE_ENGLISH_REFRESH_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", SECRET)
    monkeypatch.setenv("OFFICE_PUBLIC_ORIGIN", PUBLIC)
    store = Store(tmp_path / "state")
    app = create_app(store)
    transport = FakeTransport()
    app.state.youtube_oauth_transport = transport
    client = TestClient(app, base_url="https://localhost:8510")
    headers = {"Origin": PUBLIC, "X-Office-CSRF": client.get("/api/session").json()["csrf"]}
    return {"store": store, "app": app, "client": client, "headers": headers, "transport": transport, "secrets": isolated_secrets_file}


def start(ctx, key="youtube_main_ko", client=None, headers=None):
    response = (client or ctx["client"]).post("/api/youtube/oauth/start", json={"channel_key": key}, headers=headers or ctx["headers"])
    assert response.status_code == 200, response.text
    url = response.json()["authorize_url"]
    return url, parse_qs(urlsplit(url).query)["state"][0], response


def callback(ctx, state, code="auth-code-1", client=None, **extra):
    params = {"code": code, "state": state, **extra}
    return (client or ctx["client"]).get("/api/youtube/oauth/callback", params=params, follow_redirects=False)


def location(response):
    assert response.status_code == 303, response.text
    parts = urlsplit(response.headers["location"])
    assert parts.path == "/" and not parts.netloc
    return {k: v[0] for k, v in parse_qs(parts.query).items()}


def everything_visible(ctx):
    client = ctx["client"]
    dumps = [json.dumps(ctx["store"].events(limit=500), ensure_ascii=False)]
    for path in ("/api/channels", "/api/youtube/oauth/status", "/api/dashboard", "/api/events"):
        dumps.append(client.get(path).text)
    dumps.append((ctx["store"].root / "office.sqlite3").read_bytes().decode("utf-8", "ignore"))
    return "\n".join(dumps)


def test_start_builds_google_authorize_url_and_binds_browser(oauth):
    url, state, response = start(oauth)
    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == "https://accounts.google.com/o/oauth2/v2/auth"
    query = {k: v[0] for k, v in parse_qs(parts.query).items()}
    assert query["client_id"] == "cid.apps.googleusercontent.com"
    assert query["redirect_uri"] == PUBLIC + "/api/youtube/oauth/callback"
    assert query["response_type"] == "code" and query["access_type"] == "offline"
    assert set(query["scope"].split()) == {"https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"}
    assert "consent" in query["prompt"].split() and query["include_granted_scopes"] == "false"
    assert len(state) >= 32
    assert SECRET not in response.text and SECRET not in url
    cookie = response.headers["set-cookie"].lower()
    assert "hb_youtube_oauth=" in cookie and "httponly" in cookie and "samesite=lax" in cookie and "secure" in cookie and "path=/api/youtube/oauth" in cookie
    # 상태값 원문은 DB에 남기지 않는다(해시만).
    assert state not in (oauth["store"].root / "office.sqlite3").read_bytes().decode("utf-8", "ignore")


def test_start_requires_csrf_youtube_channel_and_client_config(oauth, monkeypatch):
    client, headers = oauth["client"], oauth["headers"]
    assert client.post("/api/youtube/oauth/start", json={"channel_key": "youtube_main_ko"}, headers={"Origin": PUBLIC}).status_code == 403
    for key in ("tistory_main", "nope"):
        blocked = client.post("/api/youtube/oauth/start", json={"channel_key": key}, headers=headers)
        assert blocked.status_code == 409 and "YouTube" in blocked.json()["detail"]
    monkeypatch.delenv("YOUTUBE_CLIENT_SECRET")
    missing = client.post("/api/youtube/oauth/start", json={"channel_key": "youtube_main_ko"}, headers=headers)
    assert missing.status_code == 409 and "YOUTUBE_CLIENT_SECRET" in missing.json()["detail"]
    status = client.get("/api/youtube/oauth/status").json()
    assert status["client_configured"] is False and status["public_origin_configured"] is True


def test_start_requires_public_https_origin(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_OAUTH_CLIENT_TYPE", raising=False)
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "cid")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", SECRET)
    monkeypatch.delenv("OFFICE_PUBLIC_ORIGIN", raising=False)
    client = TestClient(create_app(Store(tmp_path / "state")), base_url="http://localhost:8510")
    headers = {"Origin": "http://localhost:3110", "X-Office-CSRF": client.get("/api/session").json()["csrf"]}
    blocked = client.post("/api/youtube/oauth/start", json={"channel_key": "youtube_main_ko"}, headers=headers)
    assert blocked.status_code == 409 and "OFFICE_PUBLIC_ORIGIN" in blocked.json()["detail"]
    status = client.get("/api/youtube/oauth/status").json()
    assert status == {**status, "client_configured": True, "public_origin_configured": False, "redirect_uri": None}


def test_installed_client_marker_blocks_web_begin_without_disabling_refresh_credentials(oauth, monkeypatch):
    from office import youtube_oauth
    from office.channels import channel, youtube_credentials
    from office.store import WorkflowError

    monkeypatch.setenv("YOUTUBE_OAUTH_CLIENT_TYPE", "installed")
    monkeypatch.setenv("YOUTUBE_MAIN_KO_REFRESH_TOKEN", REFRESH)
    assert youtube_credentials("youtube_main_ko")["refresh_token"] == REFRESH
    assert channel(oauth["store"], "youtube_main_ko")["credentials_configured"] is True
    assert youtube_oauth.client_configured() is False
    with pytest.raises(WorkflowError, match="Desktop.*웹 애플리케이션"):
        youtube_oauth.begin(oauth["store"], "youtube_main_ko", PUBLIC)
    blocked = oauth["client"].post("/api/youtube/oauth/start", json={"channel_key": "youtube_main_ko"}, headers=oauth["headers"])
    assert blocked.status_code == 409 and "Desktop" in blocked.json()["detail"]
    assert oauth["client"].get("/api/youtube/oauth/status").json()["client_configured"] is False
    assert oauth["store"].setting("youtube_oauth_states") is None
    assert oauth["transport"].calls == [] and not oauth["secrets"].exists()
    assert youtube_credentials("youtube_main_ko")["refresh_token"] == REFRESH


@pytest.mark.parametrize("marker", [None, "web"])
def test_unmarked_and_explicit_web_clients_keep_existing_web_flow(oauth, monkeypatch, marker):
    from office import youtube_oauth

    if marker is not None:
        monkeypatch.setenv("YOUTUBE_OAUTH_CLIENT_TYPE", marker)
    assert youtube_oauth.client_configured() is True
    start(oauth)
    assert oauth["transport"].calls == []


def test_secrets_file_inside_state_folder_is_refused(oauth, monkeypatch):
    monkeypatch.setenv("OFFICE_SECRETS_FILE", str(oauth["store"].root / "youtube-tokens.json"))
    blocked = oauth["client"].post("/api/youtube/oauth/start", json={"channel_key": "youtube_main_ko"}, headers=oauth["headers"])
    assert blocked.status_code == 409 and "OFFICE_SECRETS_FILE" in blocked.json()["detail"]


def test_happy_path_stores_token_outside_state_and_binds_channel(oauth):
    from office.channels import channel, youtube_credentials
    _, state, _ = start(oauth)
    result = location(callback(oauth, state))
    assert result == {"youtube": "connected", "channel": "youtube_main_ko"}
    token_call = next(call for call in oauth["transport"].calls if call[0] == "post")
    assert token_call[1] == "https://oauth2.googleapis.com/token"
    assert token_call[2] == {"code": "auth-code-1", "client_id": "cid.apps.googleusercontent.com", "client_secret": SECRET,
                             "redirect_uri": PUBLIC + "/api/youtube/oauth/callback", "grant_type": "authorization_code"}
    lookup = next(call for call in oauth["transport"].calls if call[0] == "get")
    assert lookup[1] == "https://www.googleapis.com/youtube/v3/channels"
    assert lookup[2]["params"] == {"part": "id,snippet", "mine": "true"} and lookup[2]["headers"]["Authorization"] == "Bearer " + ACCESS
    saved = json.loads(oauth["secrets"].read_text(encoding="utf-8"))
    assert saved["youtube_main_ko"]["refresh_token"] == REFRESH and saved["youtube_main_ko"]["channel_id"] == MAIN_ID
    assert ACCESS not in oauth["secrets"].read_text(encoding="utf-8")
    assert not oauth["secrets"].resolve().is_relative_to(oauth["store"].root)
    if os.name != "nt":
        assert stat.S_IMODE(oauth["secrets"].stat().st_mode) == 0o600
    assert youtube_credentials("youtube_main_ko")["refresh_token"] == REFRESH
    row = channel(oauth["store"], "youtube_main_ko")
    assert row["external_account_id"] == MAIN_ID and row["credentials_configured"] is True and row["publication_enabled"] is False
    event = next(e for e in oauth["store"].events(limit=20) if e["kind"] == "youtube_channel_connected")
    assert event["data"]["channel_key"] == "youtube_main_ko" and event["data"]["channel_id"] == MAIN_ID
    visible = everything_visible(oauth)
    assert REFRESH not in visible and ACCESS not in visible and SECRET not in visible and "auth-code-1" not in visible
    status = oauth["client"].get("/api/youtube/oauth/status").json()
    main = next(c for c in status["channels"] if c["key"] == "youtube_main_ko")
    assert main["source"] == "file" and main["channel_id"] == MAIN_ID and main["connected"] is True
    # 연결은 발행이 아니다: 업로드·승인 기록이 생기지 않는다.
    assert not any(e["kind"].startswith("delivery_") or "approv" in e["kind"] for e in oauth["store"].events(limit=50))


def test_state_is_single_use(oauth):
    _, state, _ = start(oauth)
    assert location(callback(oauth, state))["youtube"] == "connected"
    calls = len(oauth["transport"].calls)
    reused = location(callback(oauth, state, code="auth-code-2"))
    assert reused["youtube"] == "error" and reused["reason"] == "state"
    assert len(oauth["transport"].calls) == calls


def test_unknown_missing_and_expired_state_are_rejected(oauth):
    store = oauth["store"]
    assert location(callback(oauth, "not-a-real-state"))["reason"] == "state"
    assert location(oauth["client"].get("/api/youtube/oauth/callback", params={"code": "x"}, follow_redirects=False))["reason"] == "state"
    _, state, _ = start(oauth)
    states = store.setting("youtube_oauth_states")
    store.set_setting("youtube_oauth_states", {key: {**value, "expires_at": 0} for key, value in states.items()})
    assert location(callback(oauth, state))["reason"] == "state"
    assert oauth["transport"].calls == [] and not oauth["secrets"].exists()


def test_callback_from_another_browser_is_rejected(oauth):
    _, state, _ = start(oauth)
    other = TestClient(oauth["app"], base_url="https://localhost:8510")
    result = location(callback(oauth, state, client=other))
    assert result["youtube"] == "error" and result["reason"] == "session"
    assert oauth["transport"].calls == [] and not oauth["secrets"].exists()


def test_user_denied_consent(oauth):
    _, state, _ = start(oauth)
    response = oauth["client"].get("/api/youtube/oauth/callback", params={"error": "access_denied", "state": state}, follow_redirects=False)
    assert location(response) == {"youtube": "error", "reason": "denied", "channel": "youtube_main_ko"}
    assert oauth["transport"].calls == []


def test_channel_id_mismatch_stores_nothing(oauth):
    from office.channels import youtube_credentials
    oauth["transport"].channels = {"items": [{"id": "UCother000000000000000000"[:24], "snippet": {"title": "다른 채널"}}]}
    _, state, _ = start(oauth, "youtube_english")
    result = location(callback(oauth, state))
    assert result == {"youtube": "error", "reason": "channel_mismatch", "channel": "youtube_english", "actual_channel": "UCother000000000000000000"[:24], "expected_channel": ENGLISH_ID}
    assert not oauth["secrets"].exists() and youtube_credentials("youtube_english") is None
    failed = next(e for e in oauth["store"].events(limit=20) if e["kind"] == "youtube_channel_connect_failed")
    assert failed["data"]["reason"] == "channel_mismatch" and REFRESH not in json.dumps(failed)
    assert failed["data"]["actual_channel"] == result["actual_channel"]
    assert failed["data"]["expected_channel"] == ENGLISH_ID
    assert ACCESS not in json.dumps(failed) and SECRET not in json.dumps(failed)


def test_channel_registered_to_another_key_is_rejected(oauth):
    from office.channels import channel
    oauth["transport"].channels = {"items": [{"id": ENGLISH_ID, "snippet": {"title": "영어 채널"}}]}
    _, state, _ = start(oauth, "youtube_main_ko")
    assert location(callback(oauth, state))["reason"] == "channel_in_use"
    assert not oauth["secrets"].exists() and channel(oauth["store"], "youtube_main_ko")["external_account_id"] is None


@pytest.mark.parametrize("transport, reason", [
    (FakeTransport(token_status=400, token={"error": "invalid_grant"}), "token_exchange"),
    (FakeTransport(token={"access_token": ACCESS, "scope": SCOPES}), "no_refresh_token"),
    (FakeTransport(token={"access_token": ACCESS, "refresh_token": REFRESH, "scope": "https://www.googleapis.com/auth/youtube.readonly"}), "scope_missing"),
    (FakeTransport(token={"access_token": ACCESS, "refresh_token": REFRESH, "scope": SCOPES + " https://www.googleapis.com/auth/gmail.send"}), "scope_unexpected"),
    (FakeTransport(channels_status=403, channels={"error": {}}), "channel_lookup"),
    (FakeTransport(channels={"items": []}), "no_channel"),
    (FakeTransport(channels={"items": [{"id": MAIN_ID}, {"id": "UCsecond0000000000000000"}]}), "channel_ambiguous"),
])
def test_google_failures_store_nothing(oauth, transport, reason):
    oauth["app"].state.youtube_oauth_transport = transport
    _, state, _ = start(oauth)
    assert location(callback(oauth, state))["reason"] == reason
    assert not oauth["secrets"].exists()
    assert REFRESH not in everything_visible(oauth)
    if reason == "scope_unexpected":
        assert [call[:2] for call in transport.calls] == [("post", "https://oauth2.googleapis.com/token")]


def test_old_pending_request_cannot_exchange_or_replace_existing_token(oauth):
    from office.youtube_oauth import STATE_SETTING
    from office.youtube_tokens import save_token
    save_token("youtube_main_ko", {"refresh_token": "existing-office-token", "channel_id": MAIN_ID})
    original = oauth["secrets"].read_bytes()
    _, state, _ = start(oauth)
    with oauth["store"].connection(transaction=True) as db:
        pending = json.loads(db.execute("SELECT value FROM settings WHERE key=?", (STATE_SETTING,)).fetchone()[0])
        for record in pending.values():
            record.pop("scope_policy", None)
        db.execute("UPDATE settings SET value=? WHERE key=?", (json.dumps(pending), STATE_SETTING))
    assert location(callback(oauth, state))["reason"] == "scope_changed"
    assert oauth["transport"].calls == []
    assert oauth["secrets"].read_bytes() == original
    assert location(callback(oauth, state))["reason"] == "state"


def test_disconnect_removes_only_the_stored_token(oauth, monkeypatch):
    from office.channels import youtube_credentials
    client, headers = oauth["client"], oauth["headers"]
    _, state, _ = start(oauth)
    location(callback(oauth, state))
    assert client.post("/api/youtube/oauth/disconnect", json={"channel_key": "youtube_main_ko"}).status_code == 403
    removed = client.post("/api/youtube/oauth/disconnect", json={"channel_key": "youtube_main_ko"}, headers=headers)
    assert removed.status_code == 200 and REFRESH not in removed.text
    assert "youtube_main_ko" not in json.loads(oauth["secrets"].read_text(encoding="utf-8"))
    assert youtube_credentials("youtube_main_ko") is None
    assert any(e["kind"] == "youtube_channel_disconnected" and e["data"]["channel_key"] == "youtube_main_ko" for e in oauth["store"].events(limit=20))
    again = client.post("/api/youtube/oauth/disconnect", json={"channel_key": "youtube_main_ko"}, headers=headers)
    assert again.status_code == 409
    monkeypatch.setenv("YOUTUBE_MAIN_KO_REFRESH_TOKEN", "env-token")
    env_only = client.post("/api/youtube/oauth/disconnect", json={"channel_key": "youtube_main_ko"}, headers=headers)
    assert env_only.status_code == 409 and "환경" in env_only.json()["detail"]
    assert youtube_credentials("youtube_main_ko")["refresh_token"] == "env-token"


def test_env_token_takes_precedence_over_file(oauth, monkeypatch):
    from office.channels import youtube_credentials
    _, state, _ = start(oauth)
    location(callback(oauth, state))
    monkeypatch.setenv("YOUTUBE_MAIN_KO_REFRESH_TOKEN", "env-token")
    assert youtube_credentials("youtube_main_ko")["refresh_token"] == "env-token"
    main = next(c for c in oauth["client"].get("/api/youtube/oauth/status").json()["channels"] if c["key"] == "youtube_main_ko")
    assert main["source"] == "env" and main["file_stored"] is True


def test_token_file_helpers(tmp_path, monkeypatch):
    from office import youtube_tokens
    path = tmp_path / "nested" / "tokens.json"
    monkeypatch.setenv("OFFICE_SECRETS_FILE", str(path))
    assert youtube_tokens.secrets_path() == path.resolve()
    assert youtube_tokens.stored_refresh_token("youtube_main_ko") is None
    youtube_tokens.save_token("youtube_main_ko", {"refresh_token": "abc", "channel_id": MAIN_ID, "connected_at": "now", "scopes": ["s"]})
    youtube_tokens.save_token("youtube_english", {"refresh_token": "def", "channel_id": ENGLISH_ID, "connected_at": "now", "scopes": ["s"]})
    assert youtube_tokens.stored_refresh_token("youtube_main_ko") == "abc"
    assert youtube_tokens.public_record("youtube_main_ko") == {"channel_id": MAIN_ID, "connected_at": "now", "scopes": ["s"]}
    assert youtube_tokens.remove_token("youtube_main_ko") is True and youtube_tokens.remove_token("youtube_main_ko") is False
    assert youtube_tokens.stored_refresh_token("youtube_english") == "def"
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    path.write_text("{broken", encoding="utf-8")
    assert youtube_tokens.stored_refresh_token("youtube_english") is None
    assert not list(path.parent.glob("*.tmp"))
