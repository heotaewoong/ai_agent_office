import json
from types import SimpleNamespace

import pytest

from office import assistant_requests as bridge


def relay(monkeypatch, response):
    sockets = []
    class Connection:
        def __init__(self):
            self.buffer = response
            self.reads = 0
            self.sent = None
            sockets.append(self)
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def settimeout(self, timeout): assert 0 < timeout <= 15
        def connect(self, path): assert path == "/run/heobrain/native.sock"
        def sendall(self, data): self.sent = data
        def recv(self, size):
            self.reads += 1
            data, self.buffer = self.buffer[:size], self.buffer[size:]
            return data
    monkeypatch.setattr(bridge, "socket", SimpleNamespace(AF_UNIX=1, SOCK_STREAM=1,
                                                         socket=lambda *_: Connection()))
    return sockets


@pytest.mark.parametrize("response", [b"{}\n", b'{"ok":true,"result":[]}\n',
                                     b'{"ok":true,"result":{}}', b" " * 2_097_153,
                                     b'{"ok":true,"result":{}}\n{"extra":1}\n',
                                     b'{"ok":false,"error":["bad"]}\n'],
                         ids=["empty", "array", "missing_newline", "oversized", "extra_frame", "error_array"])
def test_unix_relay_rejects_unframed_oversized_or_wrong_schema(monkeypatch, response):
    relay(monkeypatch, response)
    with pytest.raises(bridge.BridgeError):
        bridge.UnixNativeClient("/run/heobrain/native.sock").board()


def test_unix_relay_rejection_never_returns_raw_private_error(monkeypatch):
    relay(monkeypatch, json.dumps({"ok": False, "error": {"code": "bad",
                                 "message": "token=private /home/private"}}).encode() + b"\n")
    with pytest.raises(bridge.BridgeError) as caught:
        bridge.UnixNativeClient("/run/heobrain/native.sock").board()
    assert "private" not in str(caught.value)


def test_unix_relay_has_total_fifteen_second_deadline_not_per_chunk(monkeypatch):
    sockets = relay(monkeypatch, b" " * 2_097_153)
    ticks = iter([0, 16])
    monkeypatch.setattr(bridge, "monotonic", lambda: next(ticks), raising=False)
    with pytest.raises(bridge.BridgeError):
        bridge.UnixNativeClient("/run/heobrain/native.sock").board()
    assert sockets[0].reads == 0


def test_unix_relay_rejects_large_request_before_connecting(monkeypatch):
    sockets = relay(monkeypatch, b'{"ok":true,"result":{}}\n')
    with pytest.raises(bridge.BridgeError) as caught:
        bridge.UnixNativeClient("/run/heobrain/native.sock").create({
            "idempotency_key": "office-world:aa3a151d-72e8-4abf-b09d-10d416279c41", "body": "a" * 32768})
    assert caught.value.code == "native_request_too_large"
    assert sockets == []


@pytest.mark.parametrize("path", ["relative.sock", "http://localhost/socket", "/bad\x00socket", "/" + "a" * 108])
def test_unix_relay_configuration_requires_bounded_absolute_unix_path(path):
    with pytest.raises(bridge.BridgeError) as caught:
        bridge.UnixNativeClient(path)
    assert caught.value.status == 503
