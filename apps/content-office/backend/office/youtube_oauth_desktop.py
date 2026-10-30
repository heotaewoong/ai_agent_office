"""Desktop-only YouTube OAuth setup; never uploads or changes the running office.

Official protocol reviewed 2026-10-30:
https://developers.google.com/identity/protocols/oauth2/native-app
https://developers.google.com/youtube/data/guides/auth/installed-apps
https://developers.google.com/youtube/data/reference/rest/v3/channels/list

Run on the computer whose external system browser handles Google consent, not a
headless EC2 shell. The output is a NEW operator-owned credential file, never an
automatic merge into office.env. POSIX mode 0600 is enforced; Windows chmod does
not establish a private ACL, so the operator must choose an ACL-protected folder.
Google app verification/testing-token lifetime and revocation remain external.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import sys
import time
from urllib.parse import parse_qs, unquote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .channels import CHANNELS, YOUTUBE_CHANNEL_ID, channel_env_name

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
SCOPES = ("https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly")
CALLBACK_PATH = "/oauth2callback"
MAX_RESPONSE = 128_000
DEFAULT_TIMEOUT = 1800


class OAuthSetupError(ValueError):
    """Only fixed, credential-free messages may be presented to the operator."""


def _credential(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9._~+/-]+={0,2}", value) or len(value) > 16384:
        raise OAuthSetupError("인증 응답 값의 형식이 올바르지 않습니다. 비밀값은 출력하지 않았습니다")
    return value


def load_client(path):
    try:
        with Path(path).open("rb") as source:
            raw = source.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ValueError()
        data = json.loads(raw)
        installed = data.get("installed")
        if not isinstance(installed, dict):
            raise ValueError()
        client = {key: _credential(installed.get(key)) for key in ("client_id", "client_secret")}
        if not client["client_id"].endswith(".apps.googleusercontent.com"):
            raise ValueError()
    except (OSError, ValueError, TypeError, AttributeError):
        raise OAuthSetupError("Google에서 받은 Desktop 앱 client JSON을 확인하세요. 내용은 출력하지 않았습니다") from None
    return client


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise OAuthSetupError("인증 요청의 예기치 않은 이동을 차단했습니다")


def _json_request(url, *, form=None, access_token=None):
    headers = {"Accept": "application/json"}
    data = None
    if form is not None:
        data = urlencode(form).encode("ascii")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if access_token is not None:
        headers["Authorization"] = "Bearer " + _credential(access_token)
    try:
        # Fixed HTTPS endpoints; do not forward credentials via ambient proxy settings or redirects.
        opener = build_opener(ProxyHandler({}), _NoRedirects())
        with opener.open(Request(url, data=data, headers=headers), timeout=15) as response:
            raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ValueError()
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except Exception:
        # HTTP exceptions may contain authorization codes or provider bodies; never echo them.
        raise OAuthSetupError("Google 인증/채널 조회 응답을 확인하지 못했습니다. 비밀 응답은 출력하지 않았습니다") from None


def _callback_code(client, timeout):
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    received = {}

    class Callback(BaseHTTPRequestHandler):
        def setup(self):
            self.request.settimeout(2)
            super().setup()

        def log_message(self, *args):
            pass  # Default access logs include the secret callback query.

        def do_GET(self):
            valid = False
            try:
                parsed = urlsplit(self.path)
                if len(self.path) > 8192 or parsed.scheme or parsed.netloc:
                    raise ValueError()
                hosts = (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}")
                if self.headers.get("Host") not in hosts or self.client_address[0] != "127.0.0.1":
                    raise ValueError()
                if self.path in ("/", "/health"):
                    page = b'{"status":"ready","service":"heobrain-youtube-oauth-desktop"}'
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(page)))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Referrer-Policy", "no-referrer")
                    self.send_header("Content-Security-Policy", "default-src 'none'")
                    self.end_headers()
                    self.wfile.write(page)
                    return
                if self.path == "/start":
                    self.send_response(302)
                    self.send_header("Location", auth_url)
                    self.send_header("Content-Length", "0")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Referrer-Policy", "no-referrer")
                    self.end_headers()
                    return
                if parsed.path != CALLBACK_PATH:
                    raise ValueError()
                query = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=12)
                returned = query.get("state", [])
                if len(returned) != 1 or not secrets.compare_digest(returned[0], state):
                    raise ValueError()
                codes, errors = query.get("code", []), query.get("error", [])
                if len(errors) == 1 and not codes:
                    received["denied"] = True
                    valid = True
                elif len(codes) == 1 and not errors and 0 < len(codes[0]) <= 4096 and not any(ord(char) < 32 for char in codes[0]):
                    received["code"] = codes[0]
                    valid = True
            except (ValueError, TypeError):
                pass
            page = ("요청을 받았습니다. 이 창을 닫고 터미널로 돌아가세요." if valid else "인증 응답을 확인할 수 없습니다. 터미널에서 다시 확인하세요.").encode("utf-8")
            try:
                self.send_response(200 if valid else 400)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(page)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Content-Security-Policy", "default-src 'none'")
                self.end_headers()
                self.wfile.write(page)
            except OSError:
                pass

    class QuietServer(HTTPServer):
        def handle_error(self, *args):
            pass  # Never dump a request traceback containing a callback code.

    with QuietServer(("127.0.0.1", 0), Callback) as server:
        redirect_uri = f"http://127.0.0.1:{server.server_port}{CALLBACK_PATH}"
        auth_url = AUTH_URL + "?" + urlencode({"client_id": client["client_id"], "redirect_uri": redirect_uri,
            "response_type": "code", "scope": " ".join(SCOPES), "state": state,
            "code_challenge": challenge, "code_challenge_method": "S256", "access_type": "offline", "prompt": "consent"})
        print(f"아래 로컬 시작 주소를 이 PC의 브라우저에서 직접 여세요. 대기 시간은 {timeout:g}초입니다. 이 터미널은 인증이 끝날 때까지 열어 두세요.")
        print(f"http://127.0.0.1:{server.server_port}/start", flush=True)
        deadline = time.monotonic() + timeout
        while not received and time.monotonic() < deadline:
            server.timeout = min(0.5, max(0.01, deadline - time.monotonic()))
            server.handle_request()
    if received.get("denied"):
        raise OAuthSetupError("Google 권한 승인이 취소됐습니다. 인증 파일은 만들지 않았습니다")
    if not received.get("code"):
        raise OAuthSetupError("로그인 대기 시간이 끝났습니다. 인증 파일은 만들지 않았습니다")
    return received["code"], verifier, redirect_uri


def _output_path(path):
    path = Path(path).expanduser()
    if path.exists() or path.is_symlink():
        raise OAuthSetupError("출력 파일이 이미 있습니다. 기존 파일을 덮지 않으므로 새 파일명을 지정하세요")
    path = path.parent.resolve(strict=True) / path.name
    if any((parent / ".git").exists() for parent in path.parents):
        raise OAuthSetupError("인증 파일은 Git 저장소 밖의 비공개 폴더에 저장하세요")
    return path


def _save_env(path, client, refresh_token, channel_key, channel_id):
    values = {"YOUTUBE_OAUTH_CLIENT_TYPE": "installed", "YOUTUBE_CLIENT_ID": client["client_id"], "YOUTUBE_CLIENT_SECRET": client["client_secret"], channel_env_name(channel_key): refresh_token}
    text = f"# HeoBrain YouTube OAuth only; channel_key={channel_key}; channel_id={channel_id}\n"
    text += "".join(f"{key}={_credential(value)}\n" for key, value in values.items())
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    identity = os.fstat(fd)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
            if os.name != "nt":
                os.fchmod(output.fileno(), 0o600)
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
    except Exception:
        current = path.stat(follow_symlinks=False)
        if (current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino):
            path.unlink()
        raise OAuthSetupError("새 인증 파일을 안전하게 저장하지 못했습니다. 기존 운영 설정은 바꾸지 않았습니다") from None


def _single_channel_id(listing):
    items = listing.get("items")
    if not isinstance(items, list) or len(items) != 1 or listing.get("nextPageToken") or not isinstance(items[0], dict):
        raise OAuthSetupError("단일 YouTube 채널을 확인하지 못했습니다. Google에서 대상 채널을 선택하고 다시 실행하세요")
    channel_id = items[0].get("id")
    if not isinstance(channel_id, str) or not YOUTUBE_CHANNEL_ID.fullmatch(channel_id):
        raise OAuthSetupError("YouTube 채널 ID를 확인하지 못했습니다")
    return channel_id


def run(client_file, output_env, channel_key, expected_channel_id=None, timeout=DEFAULT_TIMEOUT):
    definition = CHANNELS.get(channel_key)
    if not definition or definition["platform"] != "youtube":
        raise OAuthSetupError("등록된 YouTube 채널 키만 사용할 수 있습니다")
    if type(timeout) is not int or not 60 <= timeout <= DEFAULT_TIMEOUT:
        raise OAuthSetupError("로그인 대기 시간은 60~1800초 정수로 지정하세요")
    expected = expected_channel_id or definition.get("external_account_id")
    if expected and not YOUTUBE_CHANNEL_ID.fullmatch(expected):
        raise OAuthSetupError("예상 YouTube 채널 ID 형식을 확인하세요")
    output = _output_path(output_env)
    client = load_client(client_file)
    if os.environ.get("YOUTUBE_CLIENT_ID") and os.environ["YOUTUBE_CLIENT_ID"] != client["client_id"]:
        raise OAuthSetupError("현재 환경과 다른 공용 OAuth client입니다. 기존 채널 토큰과 합치지 말고 운영자에게 구성을 확인하세요")
    if os.name == "nt":
        print("Windows에서는 chmod만으로 파일 ACL을 보장하지 않습니다. 선택한 폴더의 본인 계정 전용 권한을 직접 확인하세요.")
    code, verifier, redirect_uri = _callback_code(client, timeout)
    tokens = _json_request(TOKEN_URL, form={**client, "code": code, "code_verifier": verifier, "redirect_uri": redirect_uri, "grant_type": "authorization_code"})
    if not isinstance(tokens.get("scope"), str) or set(tokens["scope"].split()) != set(SCOPES) or str(tokens.get("token_type", "")).lower() != "bearer":
        raise OAuthSetupError("필요한 업로드·채널 조회 두 권한만 가진 토큰인지 확인하지 못했습니다. 인증 파일은 만들지 않았습니다")
    access, refresh = _credential(tokens.get("access_token")), _credential(tokens.get("refresh_token"))
    listing = _json_request(CHANNELS_URL + "?" + urlencode({"part": "id", "mine": "true", "maxResults": 2}), access_token=access)
    channel_id = _single_channel_id(listing)
    if expected and not secrets.compare_digest(channel_id, expected):
        raise OAuthSetupError("선택한 Google 채널이 예상 채널과 다릅니다. 인증 파일은 만들지 않았습니다")
    if not expected:
        public = urlsplit(definition.get("public_url") or "")
        handle = unquote(public.path[2:]) if public.scheme == "https" and public.hostname in ("youtube.com", "www.youtube.com") and public.path.startswith("/@") and "/" not in public.path[2:] else ""
        if handle:
            target = _json_request(CHANNELS_URL + "?" + urlencode({"part": "id", "forHandle": handle, "maxResults": 2}), access_token=access)
            if not secrets.compare_digest(channel_id, _single_channel_id(target)):
                raise OAuthSetupError("로그인한 소유 채널과 등록된 YouTube 핸들이 다릅니다. 인증 파일은 만들지 않았습니다")
        elif input(f"확인된 채널 ID는 {channel_id}입니다. 저장하려면 이 ID를 그대로 입력하세요: ").strip() != channel_id:
            raise OAuthSetupError("채널 확인을 취소했습니다. 인증 파일은 만들지 않았습니다")
    _save_env(output, client, refresh, channel_key, channel_id)
    print("새 전용 인증 파일을 저장했습니다. 운영 env 병합·계정 설정·게시 허용·업로드는 실행하지 않았습니다.")
    return channel_id


def main(argv=None):
    parser = argparse.ArgumentParser(description="이 PC의 브라우저에서 시작 주소를 직접 여는 Desktop OAuth. 비밀값을 출력하지 않으며 기존 env를 덮지 않습니다.", epilog="Windows: 본인 전용 ACL 폴더를 사용하세요. EC2 반영/공용 client 병합은 운영자가 별도로 검토합니다.")
    parser.add_argument("--client-file", required=True, type=Path)
    parser.add_argument("--output-env", required=True, type=Path)
    parser.add_argument("--channel-key", required=True, choices=[key for key, row in CHANNELS.items() if row["platform"] == "youtube"])
    parser.add_argument("--expected-channel-id")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="로그인 대기 시간(초): 기본 1800, 허용 60~1800")
    args = parser.parse_args(argv)
    try:
        run(args.client_file, args.output_env, args.channel_key, args.expected_channel_id, args.timeout)
    except (KeyboardInterrupt, EOFError):
        print("인증 설정을 취소했습니다. 운영 설정은 바꾸지 않았습니다.", file=sys.stderr)
        return 1
    except OAuthSetupError as error:
        print(str(error), file=sys.stderr)
        return 1
    except Exception:
        # No exception repr/traceback: even third-party network errors can carry secrets.
        print("인증 설정을 완료하지 못했습니다. Desktop client·대상 채널·권한·새 출력 경로를 확인하세요. 비밀값과 오류 원문은 출력하지 않았습니다.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
