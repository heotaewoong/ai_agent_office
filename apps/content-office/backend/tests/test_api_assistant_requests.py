import copy
import uuid

import pytest
from fastapi.testclient import TestClient

from office.api import create_app
from office.store import Store


class NativeFixture:
    def __init__(self):
        self.cards = []
        self.details = {}
        self.posts = []
        self.timeout_after_create = False

    def board(self):
        return {"columns": [{"name": "ready", "tasks": copy.deepcopy(self.cards)}]}

    def create(self, payload):
        self.posts.append(copy.deepcopy(payload))
        card = {**payload, "id": "t_fixture", "status": "ready", "created_at": 10,
                "completed_at": None, "current_run_id": None}
        self.cards.append(card)
        self.details[card["id"]] = {"task": card, "events": [], "runs": []}
        if self.timeout_after_create:
            raise TimeoutError("credential must never appear in an error")
        return {"task": card}

    def task(self, task_id):
        return copy.deepcopy(self.details[task_id])


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    monkeypatch.delenv("OFFICE_HERMES_BASE_URL", raising=False)
    monkeypatch.delenv("OFFICE_HERMES_TOKEN_FILE", raising=False)
    store = Store(tmp_path)
    app = create_app(store)
    native = NativeFixture()
    app.state.assistant_native = native
    client = TestClient(app, base_url="http://localhost:8510")
    csrf = client.get("/api/session").json()["csrf"]
    headers = {"Origin": "http://localhost:3110", "X-Office-CSRF": csrf}
    return store, app, native, client, headers


def submit(bridge, request_id=None, text="팀에서 검토하고 결과를 알려 주세요"):
    _, _, _, client, headers = bridge
    return client.post("/api/assistant/requests", json={
        "request_id": request_id or str(uuid.uuid4()), "text": text, "assignee": "lumi",
    }, headers=headers)


def test_submit_reuses_native_board_and_same_uuid_once(bridge):
    store, _, native, client, _ = bridge
    rid = str(uuid.uuid4())
    first = submit(bridge, rid)
    assert first.status_code == 202
    assert first.json()["native_task_id"] == "t_fixture"
    assert first.json()["board"] == "heobrain-office"
    assert first.json()["delivery"] == {"slack": "not_attached"}
    assert submit(bridge, rid).json() == first.json()
    assert len(native.posts) == 1
    payload = native.posts[0]
    assert payload["assignee"] == "lumi"
    assert payload["idempotency_key"] == "office-world:" + rid
    assert payload["max_runtime_seconds"] == 300
    assert payload["goal_mode"] is False
    assert payload["skills"] == ["heobrain-office-coordinator"]
    assert payload["title"] == "3D 비서 요청 · " + rid[:8]
    assert "model_override" not in payload
    assert store.jobs() == []
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM tasks").fetchone()[0] == 0
        record = db.execute("SELECT value FROM settings WHERE key=?",
                            ("assistant_request:" + rid,)).fetchone()[0]
    assert "팀에서 검토" not in record
    assert client.get("/api/assistant/requests/" + rid).json()["status"] == "queued"


def test_same_uuid_changed_payload_is_conflict_without_native_post(bridge):
    rid = str(uuid.uuid4())
    assert submit(bridge, rid).status_code == 202
    response = submit(bridge, rid, "다른 업무")
    assert response.status_code == 409
    assert response.json()["code"] == "request_conflict"
    assert len(bridge[2].posts) == 1


def test_ack_timeout_reconciles_same_native_key_without_resubmission(bridge):
    _, _, native, client, _ = bridge
    native.timeout_after_create = True
    rid = str(uuid.uuid4())
    response = submit(bridge, rid)
    assert response.status_code == 502
    assert response.json()["code"] == "native_admission_unknown"
    assert "credential" not in response.text
    reconciled = client.get("/api/assistant/requests/" + rid)
    assert reconciled.status_code == 200
    assert reconciled.json()["native_task_id"] == "t_fixture"
    assert submit(bridge, rid).status_code == 202
    assert len(native.posts) == 1


def test_unknown_admission_does_not_retry_post_when_board_has_no_match(bridge):
    _, _, native, client, _ = bridge
    def timeout(_):
        native.posts.append({})
        raise TimeoutError()
    native.create = timeout
    rid = str(uuid.uuid4())
    assert submit(bridge, rid).status_code == 502
    assert submit(bridge, rid).status_code == 502
    state = client.get("/api/assistant/requests/" + rid).json()
    assert state["native_task_id"] is None
    assert state["native_status"] == "admission_unknown"
    assert state["error"]["code"] == "native_admission_unknown"
    assert len(native.posts) == 1


def test_report_requires_matching_completed_native_run_and_event(bridge):
    from office.assistant_requests import project
    store, _, native, client, _ = bridge
    rid = str(uuid.uuid4())
    assert submit(bridge, rid).status_code == 202
    details = native.details["t_fixture"]
    details["task"].update(status="done", result="작업자가 말한 완료", completed_at=20)
    bare = client.get("/api/assistant/requests/" + rid).json()
    assert bare["report"] is None
    assert bare["status"] != "completed"
    details["runs"] = [{"id": 3, "task_id": "t_fixture", "profile": "lumi",
                        "status": "done", "outcome": "completed", "ended_at": 20,
                        "summary": "실제 실행 결과"}]
    details["events"] = [{"id": 8, "task_id": "t_fixture", "run_id": 99,
                          "kind": "completed", "created_at": 20, "payload": "secret body"}]
    assert client.get("/api/assistant/requests/" + rid).json()["report"] is None
    details["events"][0]["run_id"] = 3
    verified = client.get("/api/assistant/requests/" + rid).json()
    assert verified["status"] == "blocked"
    assert verified["error"]["code"] == "collaboration_incomplete"
    assert verified["report"] is None
    individual = project(store.setting("assistant_request:" + rid), details)
    assert individual["report"] == {"summary": "실제 실행 결과", "verified": True,
                                    "task_id": "t_fixture", "run_id": 3, "event_id": 8}
    assert "payload" not in verified["events"][0]
    assert verified["events"][0]["assignee"] == "lumi"


def test_blocked_and_running_are_not_success_reports(bridge):
    _, _, native, client, _ = bridge
    rid = str(uuid.uuid4())
    assert submit(bridge, rid).status_code == 202
    native.details["t_fixture"]["task"].update(status="blocked", block_kind="needs_input")
    state = client.get("/api/assistant/requests/" + rid).json()
    assert state["status"] == "blocked"
    assert state["report"] is None
    assert "승인" in state["error"]["message"]


def test_unconfigured_bridge_is_disabled_and_does_not_create_journal(bridge):
    store, app, _, _, _ = bridge
    del app.state.assistant_native
    response = submit(bridge)
    assert response.status_code == 503
    assert response.json()["code"] == "assistant_not_configured"
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM settings WHERE key GLOB 'assistant_request:*'").fetchone()[0] == 0


def test_requires_existing_operator_session_and_lumi_only(bridge):
    _, _, native, client, headers = bridge
    payload = {"request_id": str(uuid.uuid4()), "text": "검토", "assignee": "lumi"}
    assert client.post("/api/assistant/requests", json=payload).status_code == 403
    payload["assignee"] = "other"
    assert client.post("/api/assistant/requests", json=payload, headers=headers).status_code == 422
    assert native.posts == []


@pytest.mark.parametrize("patch", [{"request_id": "not-uuid"}, {"text": " "},
                                  {"text": "가" * 8001}, {"native_url": "http://evil"}])
def test_invalid_inputs_fail_before_native_access(bridge, patch):
    _, _, native, client, headers = bridge
    payload = {"request_id": str(uuid.uuid4()), "text": "검토", "assignee": "lumi", **patch}
    assert client.post("/api/assistant/requests", json=payload, headers=headers).status_code == 422
    assert native.posts == []


def test_missing_request_is_not_adopted_or_created(bridge):
    response = bridge[3].get("/api/assistant/requests/" + str(uuid.uuid4()))
    assert response.status_code == 404
    assert bridge[2].posts == []


@pytest.mark.parametrize("retry_preflight", [False, True])
def test_concurrent_same_uuid_reserves_only_one_native_creation(bridge, retry_preflight):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from office.assistant_requests import BridgeError, submit as native_submit

    store, _, native, _, _ = bridge
    rid = str(uuid.uuid4())
    if retry_preflight:
        original_board = native.board
        native.board = lambda: (_ for _ in ()).throw(TimeoutError())
        with pytest.raises(BridgeError) as failed:
            native_submit(store, native, rid, "검토")
        assert failed.value.code == "native_preflight_failed"
        native.board = original_board
    entered, finish = Event(), Event()
    original = native.create
    def paused_create(payload):
        entered.set()
        assert finish.wait(5)
        return original(payload)
    native.create = paused_create
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(native_submit, store, native, rid, "검토")
        assert entered.wait(5)
        with pytest.raises(BridgeError, match="접수 결과"):
            native_submit(store, native, rid, "검토")
        finish.set()
        assert first.result()["native_task_id"] == "t_fixture"
    assert len(native.posts) == 1


def test_old_success_does_not_verify_a_later_failed_run(bridge):
    _, _, native, client, _ = bridge
    rid = str(uuid.uuid4())
    assert submit(bridge, rid).status_code == 202
    data = native.details["t_fixture"]
    data["task"].update(status="done")
    data["runs"] = [
        {"id": 1, "task_id": "t_fixture", "profile": "lumi", "status": "done",
         "outcome": "completed", "ended_at": 20, "summary": "옛 성공"},
        {"id": 2, "task_id": "t_fixture", "profile": "lumi", "status": "failed", "outcome": "failed"},
    ]
    data["events"] = [{"id": 8, "task_id": "t_fixture", "run_id": 1,
                       "kind": "completed", "created_at": 20}]
    response = client.get("/api/assistant/requests/" + rid)
    assert response.json()["report"] is None
    assert response.json()["status"] == "blocked"


@pytest.mark.parametrize("base", ["https://example.com", "http://127.0.0.1@evil.test",
                                 "http://127.0.0.1/path", "http://127.0.0.1?token=secret"])
def test_native_configuration_rejects_remote_or_credential_urls(tmp_path, base):
    from office.assistant_requests import BridgeError, NativeClient
    with pytest.raises(BridgeError):
        NativeClient(base, tmp_path / "private-token")


def test_native_transport_pins_profile_board_and_keeps_token_out_of_url(tmp_path):
    from office.assistant_requests import NativeClient
    token = tmp_path / "token"
    token.write_text("a" * 43)
    token.chmod(0o600)
    native = NativeClient("http://127.0.0.1:9119", token)
    captured = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, limit): return b'{"columns": []}'
    class Opener:
        def open(self, request, timeout):
            captured.append(request)
            assert timeout == 15
            return Response()
    native.opener = Opener()
    assert native.board() == {"columns": []}
    request = captured[0]
    assert request.full_url == "http://127.0.0.1:9119/api/plugins/kanban/board?profile=default&board=heobrain-office&tenant=heobrain-world"
    assert "a" * 43 not in request.full_url
    assert request.get_header("X-hermes-session-token") == "a" * 43


def test_preflight_failure_can_retry_same_uuid_without_unknown_post_replay(bridge):
    _, _, native, _, _ = bridge
    original = native.board
    calls = 0
    def board():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError()
        return original()
    native.board = board
    rid = str(uuid.uuid4())
    failed = submit(bridge, rid)
    assert failed.status_code == 502
    assert failed.json()["code"] == "native_preflight_failed"
    assert native.posts == []
    assert submit(bridge, rid).status_code == 202
    assert len(native.posts) == 1


def test_missing_private_token_is_disabled_before_reserving_request(bridge, monkeypatch, tmp_path):
    store, app, _, _, _ = bridge
    del app.state.assistant_native
    monkeypatch.setenv("OFFICE_HERMES_BASE_URL", "http://127.0.0.1:9119")
    monkeypatch.setenv("OFFICE_HERMES_TOKEN_FILE", str(tmp_path / "missing"))
    assert submit(bridge).status_code == 503
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM settings WHERE key GLOB 'assistant_request:*'").fetchone()[0] == 0


def _complete(data, run_id, event_id, profile, summary):
    task = data["task"]
    task.update(status="done", assignee=profile)
    data["runs"] = [{"id": run_id, "task_id": task["id"], "profile": profile,
                     "status": "done", "outcome": "completed", "ended_at": event_id, "summary": summary}]
    data["events"] = [{"id": event_id, "task_id": task["id"], "run_id": run_id,
                       "kind": "completed", "created_at": event_id}]


def test_delegation_requires_actual_child_completion_then_final_lumi_report(bridge):
    from test_assistant_collaboration import collaboration
    _, _, native, client, _ = bridge
    rid = str(uuid.uuid4())
    assert submit(bridge, rid).status_code == 202
    complete_nodes = collaboration(request_id=rid, root_id="t_fixture")
    native.details["t_fixture"] = copy.deepcopy(complete_nodes["t_fixture"])
    child = copy.deepcopy(complete_nodes["t_work"])
    child["task"]["status"] = "running"; child["events"] = []; child["runs"] = []
    child["links"]["children"] = []
    native.details["t_work"] = child
    pending = client.get("/api/assistant/requests/" + rid).json()
    assert pending["status"] == "running"
    assert pending["report"] is None
    _complete(child, 2, 20, "ethan", "역할 검토 완료")
    without_lumi = client.get("/api/assistant/requests/" + rid).json()
    assert without_lumi["status"] == "blocked"
    assert without_lumi["report"] is None
    assert without_lumi["error"]["code"] == "collaboration_incomplete"
    native.details.update(complete_nodes)
    native.details["t_final"]["runs"][0]["summary"] = "검토 반영 최종 보고"
    response = client.get("/api/assistant/requests/" + rid).json()
    assert response["status"] == "completed"
    assert response["report"]["task_id"] == "t_final"
    assert response["report"]["summary"] == "검토 반영 최종 보고"
    assert [e["assignee"] for e in response["events"]] == ["lumi", "ethan", "ada", "lumi"]


def test_dependency_cycle_is_rejected_without_fake_completion(bridge):
    _, _, native, client, _ = bridge
    rid = str(uuid.uuid4())
    assert submit(bridge, rid).status_code == 202
    native.details["t_fixture"]["links"] = {"parents": [], "children": ["t_fixture"]}
    response = client.get("/api/assistant/requests/" + rid)
    assert response.status_code == 409
    assert response.json()["code"] == "native_graph_invalid"


def test_foreign_child_link_cannot_supply_completion_evidence(bridge):
    _, _, native, client, _ = bridge
    rid = str(uuid.uuid4())
    assert submit(bridge, rid).status_code == 202
    native.details["t_fixture"]["links"] = {"parents": [], "children": ["t_foreign"]}
    native.details["t_foreign"] = {"task": {"id": "t_foreign", "status": "done"},
                                     "links": {"parents": ["t_unrelated"], "children": []}}
    response = client.get("/api/assistant/requests/" + rid)
    assert response.status_code == 409
    assert response.json()["code"] == "native_graph_invalid"


def test_native_dependency_reads_have_depth_and_total_caps(bridge):
    _, _, native, client, _ = bridge
    rid = str(uuid.uuid4())
    assert submit(bridge, rid).status_code == 202
    previous = "t_fixture"
    for index in range(5):
        task_id = f"t_depth{index}"
        native.details[previous].setdefault("links", {})["children"] = [task_id]
        native.details[task_id] = {"task": {"id": task_id, "status": "ready"},
                                   "links": {"parents": [previous], "children": []}}
        previous = task_id
    calls = []
    original = native.task
    def task(task_id):
        calls.append(task_id)
        return original(task_id)
    native.task = task
    response = client.get("/api/assistant/requests/" + rid)
    assert response.status_code == 409
    assert response.json()["code"] == "native_graph_limit"
    assert len(calls) == 4
    calls.clear()
    root = native.details["t_fixture"]
    root["links"] = {"parents": [], "children": [f"t_wide{index}" for index in range(12)]}
    for task_id in root["links"]["children"]:
        native.details[task_id] = {"task": {"id": task_id, "status": "ready"},
                                  "links": {"parents": ["t_fixture"], "children": []}}
    response = client.get("/api/assistant/requests/" + rid)
    assert response.status_code == 409
    assert response.json()["code"] == "native_graph_limit"
    assert len(calls) == 5


@pytest.mark.parametrize("unsafe", ["결과 /home/private/result.md", r"결과 C:\private\result.md",
                                    "token=private-value", "Bearer private-credential",
                                    "sk-abcdefghijklmnopqrstuv", "결과\u202e숨김"])
def test_unsafe_report_is_blocked_without_sending_private_summary_to_browser(bridge, unsafe):
    from test_assistant_collaboration import collaboration
    _, _, native, client, _ = bridge
    rid = str(uuid.uuid4())
    assert submit(bridge, rid).status_code == 202
    native.details.update(collaboration(request_id=rid, root_id="t_fixture"))
    native.details["t_final"]["runs"][0]["summary"] = unsafe
    response = client.get("/api/assistant/requests/" + rid)
    assert response.status_code == 200
    assert response.json()["status"] == "blocked"
    assert response.json()["report"] is None
    assert response.json()["error"]["code"] == "report_redaction_required"
    assert unsafe not in response.text


def test_server_unix_relay_needs_no_http_owner_token_and_reports_subscription_separately(bridge, monkeypatch):
    import json
    from types import SimpleNamespace
    from office import assistant_requests
    _, app, native, client, _ = bridge
    del app.state.assistant_native
    monkeypatch.setenv("OFFICE_HERMES_SOCKET", "/run/heobrain/hermes.sock")
    monkeypatch.setenv("OFFICE_HERMES_BASE_URL", "http://evil.test")
    monkeypatch.setenv("OFFICE_HERMES_TOKEN_FILE", "/never-read-token")
    operations = []
    registered = False
    class RelaySocket:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def settimeout(self, seconds): assert 0 < seconds <= 15
        def connect(self, path): assert path == "/run/heobrain/hermes.sock"
        def sendall(self, data):
            nonlocal registered
            assert len(data) <= 32768 and data.endswith(b"\n")
            request = json.loads(data)
            operations.append(request["op"])
            op = request["op"]
            if op == "board": result = native.board()
            elif op == "create": result = native.create(request["payload"])
            elif op == "task": result = native.task(request["task_id"])
            else:
                if op == "subscribe": registered = True
                result = {"task_id": "t_fixture", "request_id": request["request_id"],
                          "state": "watching" if registered else "not_attached", "external_delivery_verified": False}
            self.buffer = json.dumps({"ok": True, "result": result}).encode() + b"\n"
        def recv(self, limit):
            chunk, self.buffer = self.buffer[:limit], self.buffer[limit:]
            return chunk
    monkeypatch.setattr(assistant_requests, "socket", SimpleNamespace(
        AF_UNIX=1, SOCK_STREAM=1, socket=lambda *args: RelaySocket()), raising=False)
    rid = str(uuid.uuid4())
    response = submit(bridge, rid)
    assert response.status_code == 202
    assert response.json()["delivery"]["slack"] == "watching"
    assert response.json()["delivery"]["external_delivery_verified"] is False
    state = client.get("/api/assistant/requests/" + rid)
    assert state.status_code == 200
    assert state.json()["delivery"]["slack"] == "watching"
    assert operations.count("create") == 1
    assert "subscribe" in operations and "delivery_status" in operations
    assert "never-read-token" not in response.text


def test_slack_subscription_failure_does_not_lose_or_resubmit_admitted_task(bridge):
    from office.assistant_requests import BridgeError
    _, _, native, _, _ = bridge
    def subscribe(*_):
        raise BridgeError("privacy_review_required", "private raw error must not leak", 409)
    native.subscribe = subscribe
    rid = str(uuid.uuid4())
    response = submit(bridge, rid)
    assert response.status_code == 202
    assert response.json()["native_task_id"] == "t_fixture"
    assert response.json()["delivery"]["slack"] == "privacy_review_required"
    assert "raw error" not in response.text
    assert submit(bridge, rid).status_code == 202
    assert len(native.posts) == 1


def test_only_matching_confirmed_native_slack_readback_sets_external_verified(bridge):
    from test_assistant_collaboration import collaboration
    _, _, native, client, _ = bridge
    rid = str(uuid.uuid4())
    reference = {"request_id": rid, "task_id": "t_work", "run_id": 2, "event_id": 19, "terminal_state": "blocked"}
    native.subscribe = lambda *_: pytest.fail("Existing watch must not be recreated")
    native.delivery_status = lambda *_: {"task_id": "t_fixture", "request_id": rid,
                                         "state": "confirmed", "external_delivery_verified": True,
                                         "notice_ref": copy.deepcopy(reference)}
    response = submit(bridge, rid)
    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert response.json()["delivery"]["external_delivery_verified"] is False
    native.details.update(collaboration(request_id=rid, root_id="t_fixture"))
    stale = client.get("/api/assistant/requests/" + rid).json()
    assert stale["report"]["task_id"] == "t_final"
    assert stale["delivery"]["external_delivery_verified"] is False
    reference.update(task_id="t_final", run_id=5, event_id=50, terminal_state="completed")
    current = client.get("/api/assistant/requests/" + rid).json()
    assert current["delivery"]["notice_ref"] == reference
    assert current["delivery"]["external_delivery_verified"] is True
    assert "_notice_ref" not in current
    valid = copy.deepcopy(reference)
    for patch in [{"task_id": "t_work"}, {"run_id": 4}, {"event_id": 49}, {"terminal_state": "blocked"}]:
        reference.clear(); reference.update({**valid, **patch})
        assert client.get("/api/assistant/requests/" + rid).json()["delivery"]["external_delivery_verified"] is False
    native.delivery_status = lambda *_: {"task_id": "t_unrelated", "request_id": rid,
                                         "state": "confirmed", "external_delivery_verified": True}
    response = submit(bridge, rid)
    assert response.status_code == 202
    assert response.json()["delivery"] == {"slack": "failed", "external_delivery_verified": False}


def test_confirmed_blocked_notice_matches_only_the_current_actual_blocked_run(bridge):
    from test_assistant_collaboration import collaboration
    _, _, native, client, _ = bridge
    rid = str(uuid.uuid4())
    assert submit(bridge, rid).status_code == 202
    native.details.update(collaboration(request_id=rid, root_id="t_fixture"))
    work = native.details["t_work"]
    work["task"]["status"] = "blocked"
    work["runs"][0].update(status="blocked", outcome="blocked")
    work["events"][0]["kind"] = "blocked"
    reference = {"request_id": rid, "task_id": "t_work", "run_id": 2, "event_id": 20, "terminal_state": "blocked"}
    native.subscribe = lambda *_: pytest.fail("Existing watch must not be recreated")
    native.delivery_status = lambda *_: {"task_id": "t_fixture", "request_id": rid,
                                         "state": "confirmed", "external_delivery_verified": True,
                                         "notice_ref": copy.deepcopy(reference)}
    current = client.get("/api/assistant/requests/" + rid).json()
    assert current["status"] == "blocked"
    assert current["report"] is None
    assert current["delivery"]["external_delivery_verified"] is True
    reference["run_id"] = 1
    assert client.get("/api/assistant/requests/" + rid).json()["delivery"]["external_delivery_verified"] is False


def test_create_receipt_with_wrong_native_key_is_unknown_until_reconciled(bridge):
    _, _, native, client, _ = bridge
    original = native.create
    def create(payload):
        data = copy.deepcopy(original(payload))
        data["task"]["idempotency_key"] = "wrong-key"
        return data
    native.create = create
    rid = str(uuid.uuid4())
    response = submit(bridge, rid)
    assert response.status_code == 502
    assert response.json()["code"] == "native_admission_unknown"
    assert client.get("/api/assistant/requests/" + rid).json()["native_task_id"] == "t_fixture"
    assert len(native.posts) == 1


def test_duplicate_native_keys_are_conflict_and_never_choose_latest(bridge):
    _, _, native, _, _ = bridge
    native.timeout_after_create = True
    rid = str(uuid.uuid4())
    assert submit(bridge, rid).status_code == 502
    native.cards.append({**native.cards[0], "id": "t_duplicate"})
    response = submit(bridge, rid)
    assert response.status_code == 409
    assert response.json()["code"] == "native_duplicate_request"
    assert len(native.posts) == 1


def test_malformed_preflight_is_retryable_and_malformed_delivery_keeps_admission(bridge):
    _, _, native, _, _ = bridge
    original = native.board
    native.board = lambda: {"columns": ["invalid"]}
    rid = str(uuid.uuid4())
    response = submit(bridge, rid)
    assert response.status_code == 502
    assert response.json()["code"] == "native_preflight_failed"
    assert native.posts == []
    native.board = original
    native.delivery_status = lambda *_: ["invalid"]
    native.subscribe = lambda *_: pytest.fail("Malformed status must not create a second watch")
    response = submit(bridge, rid)
    assert response.status_code == 202
    assert response.json()["delivery"] == {"slack": "failed", "external_delivery_verified": False}
    assert len(native.posts) == 1


def test_definite_relay_body_refusal_is_not_an_unknown_native_admission(bridge):
    from office.assistant_requests import BridgeError
    _, _, native, client, _ = bridge
    def reject(_):
        raise BridgeError("unsafe_request_body", "요청 내용을 검토해 주세요", 422)
    native.create = reject
    rid = str(uuid.uuid4())
    response = submit(bridge, rid)
    assert response.status_code == 422
    assert response.json()["code"] == "unsafe_request_body"
    state = client.get("/api/assistant/requests/" + rid).json()
    assert state["status"] == "failed"
    assert state["native_status"] == "not_submitted"
    assert state["native_task_id"] is None
    assert state["error"]["code"] == "unsafe_request_body"
    assert native.posts == []
