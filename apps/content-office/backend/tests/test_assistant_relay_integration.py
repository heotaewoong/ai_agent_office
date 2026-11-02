"""Exercise the actual client wire format against the actual relay handler."""
import json
from types import SimpleNamespace

import pytest

from office import assistant_requests as bridge
from office.store import Store
from test_hermes_board_relay import RID, fixture


def connected_client(monkeypatch, app):
    envelopes = []
    class WireSocket:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def settimeout(self, seconds): assert 0 < seconds <= 15
        def connect(self, path): assert path == "/run/heobrain/real-relay.sock"
        def sendall(self, wire):
            assert wire.endswith(b"\n") and len(wire) <= 32768
            envelope = json.loads(wire)
            envelopes.append(envelope)
            # This is the real reviewed server method, not a protocol-shaped substitute.
            packet = app.handle(envelope, 1000)
            self.reply = json.dumps(packet, ensure_ascii=False).encode() + b"\n"
        def recv(self, size):
            chunk, self.reply = self.reply[:size], self.reply[size:]
            return chunk
    monkeypatch.setattr(bridge, "socket", SimpleNamespace(
        AF_UNIX=1, SOCK_STREAM=1, socket=lambda *_: WireSocket()))
    return bridge.UnixNativeClient("/run/heobrain/real-relay.sock"), envelopes


def test_actual_client_admission_and_all_five_operations_match_real_relay(monkeypatch, tmp_path):
    app, native, sender, _ = fixture(tmp_path)
    native.details.clear()
    client, envelopes = connected_client(monkeypatch, app)
    store = Store(tmp_path / "office")
    ack = bridge.submit(store, client, RID, "공식 https://example.com/docs 와 /home/user/project 근거를 검토해 주세요")
    assert ack["native_task_id"] == "t_new123"
    assert ack["delivery"]["slack"] == "watching"
    assert client.board()["columns"][0]["tasks"][0]["id"] == "t_new123"
    assert client.task("t_new123")["task"]["id"] == "t_new123"
    assert client.subscribe("t_new123", RID)["state"] == "watching"
    assert client.delivery_status("t_new123", RID)["state"] == "watching"
    assert bridge.submit(store, client, RID, "공식 https://example.com/docs 와 /home/user/project 근거를 검토해 주세요")["native_task_id"] == "t_new123"
    create = next(item for item in envelopes if item["op"] == "create")
    assert create["request_id"] == RID
    assert create["payload"]["idempotency_key"] == "office-world:" + create["request_id"]
    assert {item["op"] for item in envelopes} == {"board", "task", "create", "subscribe", "delivery_status"}
    assert len(native.created) == 1
    assert sender.sent == [], "wire integration is local; it must never send Slack or call a model"


def test_native_slack_intake_get_attaches_only_original_daemon_watch(monkeypatch, tmp_path):
    from office import assistant_request_protocol
    from test_slack_office_intake import intake, verified
    monkeypatch.setattr(intake, "protocol_module", lambda: assistant_request_protocol)
    app, native, sender, state = fixture(tmp_path)
    native.details.clear()
    client, envelopes = connected_client(monkeypatch, app)
    store = Store(tmp_path / "office")
    value = verified()
    class Office:
        def lookup(self, rid): return bridge.read_request(store, client, rid)
    result = intake.submit(value, value["text_hash"], intake.NativeCreator(native, state), Office())
    rid = value["request_id"]
    assert result["native_task_id"] == "t_new123"
    assert len(native.created) == 1 and store.setting("assistant_request:" + rid) is None
    assert {item["op"] for item in envelopes} == {"board", "task", "delivery_status", "subscribe"}
    assert all(item["op"] != "create" for item in envelopes)
    assert app.watches[rid]["task_id"] == "t_new123"
    assert json.loads(state.read_text())[rid]["task_id"] == "t_new123"
    # A helper restart reads the shared journal but never overwrites daemon watch state.
    intake.submit(value, value["text_hash"], intake.NativeCreator(native, state), Office())
    assert len(native.created) == 1 and json.loads(state.read_text())[rid]["task_id"] == "t_new123"
    assert sender.sent == []


@pytest.mark.parametrize("key", [None, "wrong-prefix:" + RID, "office-world:not-a-uuid",
                               "office-world:" + RID.upper(), "office-world:" + RID.replace("-", "")])
def test_malformed_create_identity_is_definitely_refused_before_any_socket(monkeypatch, tmp_path, key):
    app, native, _, _ = fixture(tmp_path)
    native.details.clear()
    client, envelopes = connected_client(monkeypatch, app)
    with pytest.raises(bridge.BridgeError) as caught:
        client.create({"idempotency_key": key, "body": "근거 검토"})
    assert caught.value.status == 422
    assert caught.value.code == "native_invalid_request"
    assert envelopes == []
    assert native.created == []
