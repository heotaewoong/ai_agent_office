"""Synthetic credentials and loopback callbacks only; never Google, a browser, or EC2."""
import base64
import hashlib
import http.client
import json
import os
from pathlib import Path
import stat
import threading
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from office import youtube_oauth_desktop as oauth

CHANNEL_ID = "UC" + "a" * 22
CLIENT = {"client_id": "synthetic.apps.googleusercontent.com", "client_secret": "synthetic-client-secret"}
ACCESS = "ya29.synthetic-access-token"
REFRESH = "1//synthetic-refresh-token"
CODE = "4/synthetic-authorization-code"


@pytest.fixture
def flow(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_CLIENT_ID", raising=False)
    client_file = tmp_path / "desktop-client.json"
    client_file.write_text(json.dumps({"installed": {**CLIENT, "auth_uri": "https://attacker.invalid", "token_uri": "https://attacker.invalid"}}), encoding="utf-8")
    output = tmp_path / "new-youtube.env"
    calls = []
    responses = {"tokens": {"access_token": ACCESS, "refresh_token": REFRESH, "token_type": "Bearer", "scope": " ".join(oauth.SCOPES)}, "channels": {"items": [{"id": CHANNEL_ID}]}, "handle": {"items": [{"id": CHANNEL_ID}]}}
    monkeypatch.setattr(oauth, "_callback_code", lambda client, timeout, **kwargs: (CODE, "v" * 86, "http://127.0.0.1:12345/oauth2callback"))

    def request(url, **kwargs):
        calls.append((url, kwargs))
        return responses["tokens"] if url == oauth.TOKEN_URL else responses["handle"] if "forHandle=" in url else responses["channels"]

    monkeypatch.setattr(oauth, "_json_request", request)
    return client_file, output, calls, responses


def test_synthetic_flow_only_saves_existing_env_contract_after_channel_confirmation(flow, monkeypatch, capsys):
    client_file, output, calls, _ = flow
    monkeypatch.setattr("builtins.input", lambda prompt: CHANNEL_ID)
    assert oauth.run(client_file, output, "youtube_main_ko") == CHANNEL_ID
    text = output.read_text(encoding="utf-8")
    rows = dict(line.split("=", 1) for line in text.splitlines() if not line.startswith("#"))
    assert rows == {"YOUTUBE_OAUTH_CLIENT_TYPE": "installed", "YOUTUBE_CLIENT_ID": CLIENT["client_id"], "YOUTUBE_CLIENT_SECRET": CLIENT["client_secret"], "YOUTUBE_MAIN_KO_REFRESH_TOKEN": REFRESH}
    assert ACCESS not in text and CODE not in text and f"channel_id={CHANNEL_ID}" in text
    assert calls[0][0] == oauth.TOKEN_URL and calls[0][1]["form"]["code_verifier"] == "v" * 86
    assert calls[0][1]["form"]["grant_type"] == "authorization_code"
    assert calls[1][0].startswith(oauth.CHANNELS_URL) and calls[1][1]["access_token"] == ACCESS
    assert parse_qs(urlsplit(calls[1][0]).query) == {"part": ["id"], "mine": ["true"], "maxResults": ["2"]}
    assert parse_qs(urlsplit(calls[2][0]).query)["forHandle"] == ["heo-brain"]
    assert "YOUTUBE_CLIENT_ID" not in os.environ
    printed = capsys.readouterr()
    assert all(secret not in printed.out + printed.err for secret in (CLIENT["client_secret"], ACCESS, REFRESH, CODE))
    if os.name != "nt":
        assert stat.S_IMODE(output.stat().st_mode) == 0o600


@pytest.mark.parametrize("patch", [{"scope": oauth.SCOPES[0]}, {"scope": " ".join(oauth.SCOPES) + " https://www.googleapis.com/auth/gmail.readonly"}, {"scope": None}, {"refresh_token": None}, {"access_token": "unsafe\nTOKEN"}, {"token_type": "DPoP"}])
def test_partial_or_invalid_token_response_cannot_create_file(flow, patch):
    client_file, output, _, responses = flow
    responses["tokens"].update(patch)
    with pytest.raises(oauth.OAuthSetupError):
        oauth.run(client_file, output, "youtube_main_ko", expected_channel_id=CHANNEL_ID)
    assert not output.exists()


@pytest.mark.parametrize("listing", [{"items": []}, {"items": [{"id": CHANNEL_ID}, {"id": "UC" + "b" * 22}]}, {"items": [{"id": "not-a-channel"}]}, {"items": [{"id": CHANNEL_ID}], "nextPageToken": "ambiguous"}])
def test_ambiguous_or_missing_owned_channel_cannot_save_credentials(flow, listing):
    client_file, output, _, responses = flow
    responses["channels"] = listing
    with pytest.raises(oauth.OAuthSetupError):
        oauth.run(client_file, output, "youtube_main_ko", expected_channel_id=CHANNEL_ID)
    assert not output.exists()


def test_wrong_expected_channel_and_operator_denial_do_not_write(flow, monkeypatch):
    client_file, output, _, _ = flow
    with pytest.raises(oauth.OAuthSetupError, match="예상 채널"):
        oauth.run(client_file, output, "youtube_main_ko", expected_channel_id="UC" + "b" * 22)
    monkeypatch.setitem(oauth.CHANNELS, "youtube_main_ko", {**oauth.CHANNELS["youtube_main_ko"], "public_url": None})
    monkeypatch.setattr("builtins.input", lambda prompt: "no")
    with pytest.raises(oauth.OAuthSetupError, match="취소"):
        oauth.run(client_file, output, "youtube_main_ko")
    assert not output.exists()


@pytest.mark.parametrize("target", [{"items": [{"id": "UC" + "b" * 22}]}, {"items": []}, {"items": [{"id": CHANNEL_ID}, {"id": "UC" + "b" * 22}]}])
def test_registered_handle_must_identify_the_same_single_owned_channel(flow, target):
    client_file, output, _, responses = flow
    responses["handle"] = target
    with pytest.raises(oauth.OAuthSetupError):
        oauth.run(client_file, output, "youtube_main_ko")
    assert not output.exists()


def test_existing_english_channel_identity_is_default_expected_value(flow):
    client_file, output, _, _ = flow
    with pytest.raises(oauth.OAuthSetupError, match="예상 채널"):
        oauth.run(client_file, output, "youtube_english")
    assert not output.exists()


def test_existing_output_and_other_shared_client_are_blocked_before_auth(flow, monkeypatch):
    client_file, output, _, _ = flow
    monkeypatch.setattr(oauth, "_callback_code", lambda *args: pytest.fail("Preflight failed but started OAuth"))
    output.write_text("EXISTING_OPERATOR_DATA", encoding="utf-8")
    with pytest.raises(oauth.OAuthSetupError, match="이미"):
        oauth.run(client_file, output, "youtube_main_ko")
    assert output.read_text(encoding="utf-8") == "EXISTING_OPERATOR_DATA"
    output.unlink()
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "other.apps.googleusercontent.com")
    with pytest.raises(oauth.OAuthSetupError, match="공용 OAuth"):
        oauth.run(client_file, output, "youtube_main_ko")
    assert not output.exists()


def test_output_race_does_not_overwrite_another_operators_file(flow, monkeypatch):
    client_file, output, calls, responses = flow
    original = oauth._json_request

    def racing(url, **kwargs):
        response = original(url, **kwargs)
        if url.startswith(oauth.CHANNELS_URL):
            output.write_text("CONCURRENT_OPERATOR_DATA", encoding="utf-8")
        return response

    monkeypatch.setattr(oauth, "_json_request", racing)
    with pytest.raises(FileExistsError):
        oauth.run(client_file, output, "youtube_main_ko", expected_channel_id=CHANNEL_ID)
    assert output.read_text(encoding="utf-8") == "CONCURRENT_OPERATOR_DATA"


def test_only_desktop_client_and_non_repository_output_are_allowed(tmp_path):
    client_file = tmp_path / "wrong-client.json"
    client_file.write_text(json.dumps({"web": CLIENT}), encoding="utf-8")
    with pytest.raises(oauth.OAuthSetupError, match="Desktop"):
        oauth.load_client(client_file)
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / ".git").mkdir()
    with pytest.raises(oauth.OAuthSetupError, match="저장소 밖"):
        oauth._output_path(repository / "credentials.env")


def test_secret_environment_characters_never_enter_shell_file(tmp_path):
    with pytest.raises(oauth.OAuthSetupError):
        oauth._save_env(tmp_path / "unsafe.env", CLIENT, "token\nOTHER=INJECTION", "youtube_main_ko", CHANNEL_ID)
    assert not list(tmp_path.iterdir())


def test_cli_suppresses_network_exception_secrets_and_tracebacks(flow, monkeypatch, capsys):
    client_file, output, _, _ = flow
    def forbidden(*args, **kwargs):
        raise RuntimeError(f"RAW_PROVIDER_BODY {CODE} {REFRESH} {CLIENT['client_secret']}")
    monkeypatch.setattr(oauth, "run", forbidden)
    assert oauth.main(["--client-file", str(client_file), "--output-env", str(output), "--channel-key", "youtube_main_ko"]) == 1
    printed = capsys.readouterr()
    assert all(secret not in printed.out + printed.err for secret in ("RAW_PROVIDER_BODY", "Traceback", CODE, REFRESH, CLIENT["client_secret"]))


def test_json_request_does_not_echo_remote_error_body_or_follow_redirects(monkeypatch):
    class Failed:
        def open(self, *args, **kwargs):
            assert kwargs["timeout"] == 15
            raise RuntimeError(f"{CODE} {REFRESH}")
    monkeypatch.setattr(oauth, "build_opener", lambda *args: Failed())
    with pytest.raises(oauth.OAuthSetupError) as error:
        oauth._json_request(oauth.TOKEN_URL, form={"code": CODE})
    assert CODE not in str(error.value) and REFRESH not in str(error.value)
    with pytest.raises(oauth.OAuthSetupError):
        oauth._NoRedirects().redirect_request(None, None, None, None, None, "https://attacker.invalid")


def callback_browser(monkeypatch, actions):
    import builtins
    original_print = builtins.print
    monkeypatch.setattr(oauth.secrets, "token_urlsafe", lambda length: "s" * 43 if length == 32 else "v" * 86)
    completed, failures, threads = [], [], []
    def printed_start(value, *args, **kwargs):
        original_print(value, *args, **kwargs)
        if not str(value).startswith("http://127.0.0.1:"):
            return
        start = urlsplit(value)
        def request_callbacks():
            try:
                client = http.client.HTTPConnection(start.hostname, start.port, timeout=3)
                client.request("GET", start.path)
                response = client.getresponse()
                assert response.status == 302
                location = response.getheader("Location")
                response.read(); client.close()
                query = parse_qs(urlsplit(location).query)
                assert set(query["scope"][0].split()) == set(oauth.SCOPES)
                assert query["code_challenge_method"] == ["S256"] and query["access_type"] == ["offline"]
                assert query["code_challenge"] == [base64.urlsafe_b64encode(hashlib.sha256(("v" * 86).encode("ascii")).digest()).rstrip(b"=").decode("ascii")]
                redirect = urlsplit(query["redirect_uri"][0])
                assert redirect.hostname == "127.0.0.1" and redirect.path == oauth.CALLBACK_PATH
                for action in actions:
                    params = {"code": CODE, "state": query["state"][0]}
                    params.update(action.get("params", {}))
                    client = http.client.HTTPConnection("127.0.0.1", redirect.port, timeout=3)
                    path = action.get("path", redirect.path)
                    if not action.get("bare"):
                        path += "?" + urlencode(params, doseq=True)
                    headers = action.get("headers", {})
                    if headers.get("Host") == "localhost":
                        headers = {"Host": f"localhost:{redirect.port}"}
                    client.request("GET", path, headers=headers)
                    response = client.getresponse()
                    body = response.read().decode("utf-8")
                    assert all(secret not in body for secret in (CODE, query["state"][0], CLIENT["client_id"], CLIENT["client_secret"], oauth.AUTH_URL))
                    assert response.getheader("Cache-Control") == "no-store"
                    if action.get("bare") and path in ("/", "/health") and headers.get("Host") != "attacker.invalid":
                        assert json.loads(body) == {"status": "ready", "service": "heobrain-youtube-oauth-desktop"}
                    completed.append(response.status)
                    client.close()
            except BaseException as error:
                failures.append(error)
        thread = threading.Thread(target=request_callbacks, daemon=True)
        threads.append(thread)
        thread.start()
    monkeypatch.setattr(builtins, "print", printed_start)
    monkeypatch.setattr("webbrowser.open_new_tab", lambda url: pytest.fail("Desktop OAuth must never launch a browser"))
    return completed, failures, threads


def test_real_loopback_rejects_bad_state_host_path_and_duplicates_before_accepting_code(monkeypatch, capsys):
    completed, failures, threads = callback_browser(monkeypatch, [
        {"params": {"state": "wrong-state"}}, {"path": "/wrong-path"}, {"headers": {"Host": "attacker.invalid"}},
        {"params": {"state": ["duplicate-one", "duplicate-two"]}}, {},
    ])
    code, verifier, redirect = oauth._callback_code(CLIENT, 5)
    for thread in threads:
        thread.join(timeout=5)
    assert not failures and all(not thread.is_alive() for thread in threads)
    assert completed == [400, 400, 400, 400, 200] and code == CODE
    assert 43 <= len(verifier) <= 128 and redirect.startswith("http://127.0.0.1:")
    printed = capsys.readouterr()
    assert CODE not in printed.out + printed.err and "wrong-state" not in printed.out + printed.err


def test_loopback_denial_and_timeout_create_no_tokens(monkeypatch):
    completed, failures, threads = callback_browser(monkeypatch, [{"params": {"code": [], "error": "access_denied"}}])
    with pytest.raises(oauth.OAuthSetupError, match="취소"):
        oauth._callback_code(CLIENT, 5)
    for thread in threads:
        thread.join(timeout=5)
    assert completed == [200] and not failures
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: None)
    with pytest.raises(oauth.OAuthSetupError, match="대기 시간"):
        oauth._callback_code(CLIENT, 0.05)


def test_manual_browser_only_exposes_loopback_start_and_checks_redirect_host_query(monkeypatch, capsys):
    import builtins
    original_print = builtins.print
    threads, failures, locations, statuses = [], [], [], []
    monkeypatch.setattr("webbrowser.open_new_tab", lambda url: pytest.fail("Desktop OAuth must never launch a browser"))
    def intercept_print(value, *args, **kwargs):
        original_print(value, *args, **kwargs)
        if not str(value).startswith("http://127.0.0.1:"):
            return
        start = urlsplit(value)
        def callbacks():
            try:
                for path, headers in (("/start?code=DO_NOT_ECHO", {}), ("/start", {"Host": "attacker.invalid"}), ("/start", {})):
                    connection = http.client.HTTPConnection(start.hostname, start.port, timeout=3)
                    connection.request("GET", path, headers=headers)
                    response = connection.getresponse()
                    statuses.append(response.status)
                    location = response.getheader("Location")
                    response.read()
                    assert response.getheader("Cache-Control") == "no-store"
                    connection.close()
                    if location:
                        locations.append(location)
                assert len(locations) == 1 and locations[0].startswith(oauth.AUTH_URL + "?")
                authorization = parse_qs(urlsplit(locations[0]).query)
                redirect = urlsplit(authorization["redirect_uri"][0])
                connection = http.client.HTTPConnection(redirect.hostname, redirect.port, timeout=3)
                connection.request("GET", redirect.path + "?" + urlencode({"state": authorization["state"][0], "code": CODE}))
                response = connection.getresponse()
                assert response.status == 200 and CODE not in response.read().decode("utf-8")
                connection.close()
            except BaseException as error:
                failures.append(error)
        thread = threading.Thread(target=callbacks, daemon=True)
        threads.append(thread)
        thread.start()
    monkeypatch.setattr(builtins, "print", intercept_print)
    assert oauth._callback_code(CLIENT, 5)[0] == CODE
    for thread in threads:
        thread.join(timeout=5)
    assert not failures and statuses == [400, 400, 302]
    printed = capsys.readouterr()
    state = parse_qs(urlsplit(locations[0]).query)["state"][0]
    assert all(value not in printed.out + printed.err for value in (oauth.AUTH_URL, CODE, state, CLIENT["client_secret"]))


def test_root_and_health_are_ready_without_authentication_data_and_reject_bad_hosts_or_queries(monkeypatch):
    completed, failures, threads = callback_browser(monkeypatch, [
        {"path": "/", "bare": True}, {"path": "/health", "bare": True},
        {"path": "/health", "bare": True, "headers": {"Host": "localhost"}},
        {"path": "/health", "bare": True, "headers": {"Host": "attacker.invalid"}},
        {"path": "/health"}, {},
    ])
    assert oauth._callback_code(CLIENT, 5)[0] == CODE
    for thread in threads:
        thread.join(timeout=5)
    assert not failures and completed == [200, 200, 200, 400, 400, 200]


@pytest.mark.parametrize("timeout", [59, 1801, True, 60.5, float("nan")])
def test_timeout_preflight_rejects_invalid_bounds_without_starting_oauth(flow, monkeypatch, timeout):
    client_file, output, calls, _ = flow
    monkeypatch.setattr(oauth, "_callback_code", lambda *args: pytest.fail("Invalid timeout started OAuth"))
    with pytest.raises(oauth.OAuthSetupError, match="60~1800"):
        oauth.run(client_file, output, "youtube_main_ko", timeout=timeout)
    assert calls == [] and not output.exists()


@pytest.mark.parametrize("timeout", [60, 1800])
def test_timeout_bounds_are_passed_to_manual_callback(flow, monkeypatch, timeout):
    client_file, output, _, _ = flow
    waits = []
    monkeypatch.setattr(oauth, "_callback_code", lambda client, wait: (waits.append(wait) or CODE, "v" * 86, "http://127.0.0.1:12345/oauth2callback"))
    assert oauth.run(client_file, output, "youtube_main_ko", expected_channel_id=CHANNEL_ID, timeout=timeout) == CHANNEL_ID
    assert waits == [timeout]


def test_cli_defaults_to_thirty_minutes_and_has_no_automatic_browser_option(flow, monkeypatch):
    client_file, output, _, _ = flow
    calls = []
    monkeypatch.setattr(oauth, "run", lambda *args: calls.append(args))
    arguments = ["--client-file", str(client_file), "--output-env", str(output), "--channel-key", "youtube_main_ko"]
    assert oauth.main(arguments) == 0
    assert calls[0][-1] == 1800
    assert not hasattr(oauth, "webbrowser")
    with pytest.raises(SystemExit):
        oauth.main(arguments + ["--manual-browser"])
