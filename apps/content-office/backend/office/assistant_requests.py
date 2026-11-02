"""Native Hermes task references; the native board remains the execution ledger."""
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
from time import monotonic
from uuid import UUID
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .store import canonical, digest, now
from .assistant_request_protocol import BOARD, TENANT, task_payload

PROFILES = {"default", "mybots-sage", "lumi", "ada", "ethan", "mia", "noah", "oliver", "sam"}
TASK_ID = re.compile(r"t_[a-zA-Z0-9_-]{1,80}\Z")
UNSAFE_DISPLAY = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u202a-\u202e\u2066-\u2069]"
    r"|(?:/|%2f)(?:home|users|mnt|tmp|etc|root|var)(?:/|%2f)|[a-z]:[\\/]|\.\.[\\/]"
    r"|bearer\s|(?:api[_-]?key|password|secret|token)\s*[:=]|sk-[a-z0-9]{12,}|xox[baprs]-[a-z0-9-]+",
    re.IGNORECASE,
)


class BridgeError(ValueError):
    def __init__(self, code, message, status=502):
        super().__init__(message)
        self.code, self.status = code, status


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class NativeClient:
    def __init__(self, base_url, token_file):
        parsed = urlsplit(base_url)
        if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}
                or parsed.username or parsed.password or parsed.path not in {"", "/"}
                or parsed.query or parsed.fragment):
            raise BridgeError("assistant_not_configured", "비서 연결 주소를 서버에서 확인해 주세요", 503)
        self.base_url = base_url.rstrip("/")
        self.token_file = Path(token_file)
        self.opener = build_opener(ProxyHandler({}), _NoRedirect())
        self._token()

    def _token(self):
        try:
            info = self.token_file.lstat()
            if (not self.token_file.is_absolute() or not stat.S_ISREG(info.st_mode)
                    or (os.name != "nt" and (stat.S_IMODE(info.st_mode) != 0o600
                                              or info.st_uid != os.geteuid()))):
                raise OSError()
            token = self.token_file.read_text(encoding="utf-8").strip()
            if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", token):
                raise ValueError()
            return token
        except (OSError, ValueError):
            raise BridgeError("assistant_not_configured", "비서의 서버 전용 인증 설정을 확인해 주세요", 503) from None

    def _request(self, method, path, payload=None):
        query = urlencode({"profile": "default", "board": BOARD,
                           **({"tenant": TENANT} if path == "board" else {})})
        request = Request(self.base_url + "/api/plugins/kanban/" + path + "?" + query,
                          data=canonical(payload).encode() if payload is not None else None,
                          method=method, headers={"X-Hermes-Session-Token": self._token(),
                                                  "Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=15) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise ValueError()
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise ValueError()
                return data
        except (HTTPError, URLError, OSError, ValueError):
            raise BridgeError("native_unavailable", "기존 비서 서버의 응답을 확인할 수 없습니다") from None

    def board(self):
        return self._request("GET", "board")

    def create(self, payload):
        return self._request("POST", "tasks", payload)

    def task(self, task_id):
        if not TASK_ID.fullmatch(task_id):
            raise BridgeError("native_invalid_response", "비서 업무 참조를 확인할 수 없습니다")
        return self._request("GET", "tasks/" + task_id)


class UnixNativeClient:
    """One bounded request per native-owned socket connection; no owner token crosses it."""
    def __init__(self, path):
        if (not isinstance(path, str) or not path.startswith("/") or "\x00" in path
                or len(os.fsencode(path)) > 107 or not hasattr(socket, "AF_UNIX")):
            raise BridgeError("assistant_not_configured", "서버 전용 비서 연결 경로를 확인해 주세요", 503)
        self.path = path

    def _request(self, op, **fields):
        wire = canonical({"op": op, **fields}).encode() + b"\n"
        if len(wire) > 32768:
            raise BridgeError("native_request_too_large", "비서 요청이 연결 규격보다 큽니다", 413)
        deadline = monotonic() + 15
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(15)
                connection.connect(self.path)
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise TimeoutError()
                connection.settimeout(remaining)
                connection.sendall(wire)
                buffer = bytearray()
                while b"\n" not in buffer:
                    remaining = deadline - monotonic()
                    if remaining <= 0:
                        raise TimeoutError()
                    connection.settimeout(remaining)
                    chunk = connection.recv(min(65536, 2_097_153 - len(buffer)))
                    if not chunk:
                        raise ValueError()
                    buffer.extend(chunk)
                    if len(buffer) > 2_097_152:
                        raise ValueError()
                line, extra = bytes(buffer).split(b"\n", 1)
                if extra.strip():
                    raise ValueError()
                response = json.loads(line)
        except (OSError, ValueError):
            raise BridgeError("native_relay_unavailable", "기존 비서의 서버 연결을 확인할 수 없습니다") from None
        if not isinstance(response, dict):
            raise BridgeError("native_invalid_response", "비서 연결 응답의 형식을 확인할 수 없습니다")
        if response.get("ok") is not True:
            error = response.get("error") or {}
            if isinstance(error, dict) and error.get("code") == "privacy_review_required":
                raise BridgeError("privacy_review_required", "Slack 전달 내용을 먼저 검토해야 합니다", 409)
            if isinstance(error, dict) and error.get("code") == "unsafe_request_body":
                raise BridgeError("unsafe_request_body", "요청에 인증정보나 허용되지 않는 문자가 있어 접수하지 않았습니다", 422)
            raise BridgeError("native_relay_rejected", "비서 연결이 허용 범위를 확인하지 못했습니다")
        if not isinstance(response.get("result"), dict):
            raise BridgeError("native_invalid_response", "비서 연결 응답의 형식을 확인할 수 없습니다")
        return response["result"]

    def board(self):
        return self._request("board")

    def create(self, payload):
        key = payload.get("idempotency_key") if isinstance(payload, dict) else None
        try:
            if not isinstance(key, str) or not key.startswith("office-world:"):
                raise ValueError()
            request_id = key[len("office-world:"):]
            if str(UUID(request_id)) != request_id:
                raise ValueError()
        except ValueError:
            raise BridgeError("native_invalid_request", "비서 요청 번호의 형식을 확인해 주세요", 422) from None
        return self._request("create", request_id=request_id, payload=payload)

    def task(self, task_id):
        if not TASK_ID.fullmatch(str(task_id)):
            raise BridgeError("native_invalid_response", "비서 업무 참조를 확인할 수 없습니다")
        return self._request("task", task_id=task_id)

    def subscribe(self, task_id, request_id):
        return self._request("subscribe", task_id=task_id, request_id=request_id)

    def delivery_status(self, task_id, request_id):
        return self._request("delivery_status", task_id=task_id, request_id=request_id)


def configured_client():
    socket_path = os.environ.get("OFFICE_HERMES_SOCKET", "")
    if socket_path:
        return UnixNativeClient(socket_path)
    base = os.environ.get("OFFICE_HERMES_BASE_URL", "")
    token = os.environ.get("OFFICE_HERMES_TOKEN_FILE", "")
    if not base or not token:
        raise BridgeError("assistant_not_configured", "루미 연결이 아직 준비되지 않았습니다. 서버 연결 설정이 필요합니다", 503)
    return NativeClient(base, token)


def _record(store, request_id):
    return store.setting("assistant_request:" + request_id)


def _save(store, record):
    store.set_setting("assistant_request:" + record["request_id"], record)


def _discard_reservation(store, record):
    # Remove only our unchanged reservation, never another process's reconciled record.
    with store.connection(transaction=True) as db:
        db.execute("DELETE FROM settings WHERE key=? AND value=?",
                   ("assistant_request:" + record["request_id"], canonical(record)))


def _adopt(native, record):
    data = native.board()
    if not isinstance(data.get("columns"), list):
        raise BridgeError("native_invalid_response", "비서 보드의 응답 형식을 확인할 수 없습니다")
    matches = [card for column in data["columns"] for card in column.get("tasks", [])
               if card.get("idempotency_key") == record["native_key"]]
    if len(matches) > 1:
        raise BridgeError("native_duplicate_request", "같은 요청의 업무가 여러 개입니다. 재전송 없이 확인이 필요합니다", 409)
    if not matches:
        return None
    return _card_id(matches[0], record)


def _native_record(native, request_id):
    """Read-only, ephemeral reference for a root created by verified native intake."""
    data = native.board()
    if not isinstance(data.get("columns"), list):
        raise BridgeError("native_invalid_response", "비서 보드의 응답 형식을 확인할 수 없습니다")
    key = "office-world:" + request_id
    matches = [card for column in data["columns"] for card in column.get("tasks", [])
               if card.get("idempotency_key") == key]
    if len(matches) > 1:
        raise BridgeError("native_duplicate_request", "같은 요청의 업무가 여러 개입니다. 확인이 필요합니다", 409)
    if not matches:
        raise BridgeError("request_not_found", "이 화면의 요청을 찾을 수 없습니다", 404)
    card = matches[0]
    body = card.get("body")
    if not isinstance(body, str) or not body.strip() or len(body) > 8000 or len(body.encode()) > 24000:
        raise BridgeError("native_request_conflict", "기존 비서 업무의 범위를 확인할 수 없습니다", 409)
    record = {"request_id": request_id, "native_key": key,
              "body_hash": hashlib.sha256(body.encode()).hexdigest(), "board": BOARD,
              "created_at": card.get("created_at"), "phase": "admitted"}
    record["native_task_id"] = _card_id(card, record)
    return record


def _card_id(card, record):
    body_hash = hashlib.sha256(str(card.get("body") or "").encode()).hexdigest()
    if (body_hash != record["body_hash"] or card.get("idempotency_key") != record["native_key"]
            or card.get("assignee") != "lumi"
            or card.get("tenant") != TENANT or not TASK_ID.fullmatch(str(card.get("id", "")))):
        raise BridgeError("native_request_conflict", "기존 비서 업무와 요청 내용이 일치하지 않습니다", 409)
    return card["id"]


def submit(store, native, request_id, text):
    fingerprint = digest({"text": text, "assignee": "lumi"})
    payload = task_payload(request_id, text)
    body = payload["body"]
    with store.connection(transaction=True) as db:
        key = "assistant_request:" + request_id
        row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        fresh = row is None
        record = json.loads(row[0]) if row else {
            "request_id": request_id, "payload_hash": fingerprint,
            "body_hash": hashlib.sha256(body.encode()).hexdigest(),
            "native_key": "office-world:" + request_id, "native_task_id": None,
            "board": BOARD, "created_at": now(), "phase": "preflight",
        }
        if record["payload_hash"] != fingerprint:
            raise BridgeError("request_conflict", "같은 요청 번호의 내용이 바뀌었습니다", 409)
        if fresh:
            # Reserve before I/O: a concurrent process may reconcile, but must never submit again.
            db.execute("INSERT INTO settings VALUES(?,?)", (key, canonical(record)))
        elif record.get("phase") == "preflight_failed":
            fresh = True
            record["phase"] = "preflight"
            record.pop("rejection_code", None)
            db.execute("UPDATE settings SET value=? WHERE key=?", (canonical(record), key))
    if record["native_task_id"]:
        return {**_ack(record), "delivery": _delivery(native, record)}
    try:
        task_id = _adopt(native, record)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        if fresh and isinstance(error, BridgeError) and error.status == 409:
            # The existing native-only root must remain readable after a conflicting web POST.
            _discard_reservation(store, record)
            raise
        if fresh:
            record["phase"] = "preflight_failed"
            _save(store, record)
        if isinstance(error, BridgeError) and error.status == 409:
            raise
        raise BridgeError("native_preflight_failed", "접수 전 연결 확인에 실패했습니다. 같은 요청 번호로 다시 확인해 주세요") from None
    if not task_id and not fresh:
        raise BridgeError("native_admission_unknown", "접수 결과를 확인 중입니다. 같은 요청 번호를 유지해 주세요")
    if not task_id:
        record["phase"] = "posting"
        _save(store, record)
        try:
            data = native.create(payload)
            task_id = _card_id(data["task"], record)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            if isinstance(error, BridgeError) and error.code in {"unsafe_request_body", "native_request_too_large", "native_invalid_request"}:
                record.update(phase="preflight_failed", rejection_code=error.code)
                _save(store, record)
                raise
            # A native intake may win after our empty preflight. Prove a conflicting
            # root by GET before removing our reservation; absence/timeouts stay unknown.
            try:
                _adopt(native, record)
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as conflict:
                if isinstance(conflict, BridgeError) and conflict.status == 409:
                    _discard_reservation(store, record)
                    raise
            # A timeout can follow successful admission; neither retry nor replace this UUID.
            raise BridgeError("native_admission_unknown", "접수 결과를 확인 중입니다. 같은 요청 번호를 유지해 주세요") from None
    record["native_task_id"] = task_id
    record["phase"] = "admitted"
    _save(store, record)
    return {**_ack(record), "delivery": _delivery(native, record)}


def _ack(record):
    return {"request_id": record["request_id"], "native_task_id": record["native_task_id"],
            "board": BOARD, "status": "queued", "delivery": {"slack": "not_attached"}}


def _delivery(native, record, expected_notice=None):
    if not hasattr(native, "subscribe"):
        return {"slack": "not_attached"}
    try:
        data = (native.delivery_status(record["native_task_id"], record["request_id"])
                if hasattr(native, "delivery_status") else {"state": "not_attached"})
        if data.get("state") in {"not_attached", "failed"}:
            data = native.subscribe(record["native_task_id"], record["request_id"])
        if (data.get("task_id") != record["native_task_id"]
                or data.get("request_id") != record["request_id"]
                or data.get("state") not in {"watching", "pending", "sent_unverified", "confirmed",
                                              "unknown", "failed", "not_attached"}):
            raise ValueError()
        notice = _validated_notice_ref(data.get("notice_ref"), record["request_id"])
        result = {"slack": data["state"], "notice_ref": notice, "external_delivery_verified":
                  data["state"] == "confirmed" and data.get("external_delivery_verified") is True
                  and expected_notice is not None and notice == expected_notice}
        error = data.get("error")
        code = data.get("error_code") or (error.get("code") if isinstance(error, dict) else None)
        if isinstance(code, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,79}", code):
            result["error_code"] = code
        if data.get("cursor_state") in {"pending", "checkpointed", "unobserved"}:
            result["cursor_state"] = data["cursor_state"]
        return result
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        state = "privacy_review_required" if getattr(error, "code", "") == "privacy_review_required" else "failed"
        return {"slack": state, "external_delivery_verified": False}


def _validated_notice_ref(value, request_id):
    if value is None:
        return None
    if (not isinstance(value, dict) or set(value) != {"request_id", "task_id", "run_id", "event_id", "terminal_state"}
            or value["request_id"] != request_id or not isinstance(value["task_id"], str)
            or not TASK_ID.fullmatch(value["task_id"]) or value["terminal_state"] not in {"completed", "blocked"}
            or any(type(value[key]) is not int or not 0 < value[key] <= 9_007_199_254_740_991 for key in ("run_id", "event_id"))):
        raise ValueError("invalid notice reference")
    return dict(value)


def read_request(store, native, request_id):
    record = _record(store, request_id)
    native_only = not record
    if native_only:
        record = _native_record(native, request_id)
    if record.get("rejection_code") and not record["native_task_id"]:
        return {**_ack(record), "status": "failed", "native_status": "not_submitted", "assignee": "lumi",
                "title": "접수 전 검토 필요", "updated_at": record["created_at"], "current_run_id": None,
                "events": [], "report": None, "error": {"code": record["rejection_code"],
                "message": "요청은 접수되지 않았습니다. 인증정보나 허용되지 않는 입력을 검토해 주세요"}}
    if not record["native_task_id"]:
        task_id = _adopt(native, record)
        if not task_id:
            return {**_ack(record), "native_status": "admission_unknown", "assignee": "lumi",
                    "title": "접수 확인 중", "updated_at": record["created_at"], "current_run_id": None,
                    "events": [], "report": None, "error": {"code": "native_admission_unknown",
                    "message": "접수 여부를 대사 중입니다. 새 요청 번호로 다시 보내지 마세요"}}
        record["native_task_id"] = task_id
        record["phase"] = "admitted"
    data = native.task(record["native_task_id"])
    if native_only:
        _card_id(data.get("task", {}), record)
    result = project_collaboration(native, record, data)
    result["delivery"] = _delivery(native, record, result.pop("_notice_ref", None))
    return result


def project_collaboration(native, record, root):
    root_id = record["native_task_id"]
    nodes = {root_id: root}
    pending = [(child, root_id, 1, (root_id,))
               for child in root.get("links", {}).get("children", [])]
    while pending:
        child, parent, depth, ancestors = pending.pop(0)
        if not isinstance(child, str) or not TASK_ID.fullmatch(child) or child in ancestors:
            raise BridgeError("native_graph_invalid", "역할 업무 연결을 확인할 수 없습니다", 409)
        if depth > 3 or (child not in nodes and len(nodes) >= 5):
            raise BridgeError("native_graph_limit", "역할 업무의 확인 범위를 넘었습니다. 사람 검토가 필요합니다", 409)
        data = nodes.get(child) or native.task(child)
        if data.get("task", {}).get("id") != child or parent not in data.get("links", {}).get("parents", []):
            raise BridgeError("native_graph_invalid", "역할 업무의 실제 인계 관계가 일치하지 않습니다", 409)
        if child in nodes:
            continue
        nodes[child] = data
        pending.extend((next_id, child, depth + 1, (*ancestors, child))
                       for next_id in data.get("links", {}).get("children", []))
    _check_complete_graph(nodes, root_id)
    projections = {ident: project({**record, "native_task_id": ident,
                                  "native_key": data["task"].get("idempotency_key")}, data)
                   for ident, data in nodes.items()}
    result = dict(projections[root_id])
    events = [event for projection in projections.values() for event in projection["events"]]
    result["events"] = sorted(events, key=lambda event: (event.get("created_at") or 0, event["id"]))[-100:]
    result["report"] = None
    # Internal current-graph evidence is consumed before the API DTO leaves this module.
    result["_notice_ref"] = None
    if result["events"]:
        result["updated_at"] = result["events"][-1]["created_at"]
    try:
        final_id = _canonical_final(nodes, record)
    except BridgeError as error:
        result.update(status="blocked", error={"code": error.code, "message": str(error)})
        return result
    unsettled = [projections[ident] for ident, data in nodes.items() if data["task"].get("status") != "done"]
    if unsettled:
        rank = {"failed": 0, "blocked": 1, "running": 2, "queued": 3}
        active = min(unsettled, key=lambda projection: rank[projection["status"]])
        for key in ("status", "native_status", "assignee", "current_run_id", "error"):
            result[key] = active[key]
        if active["native_status"] == "blocked":
            result["_notice_ref"] = _blocked_notice_ref(nodes[active["native_task_id"]], record["request_id"])
        return result
    if final_id is None:
        result.update(status="blocked", error={"code": "collaboration_incomplete",
                      "message": "담당 작업·독립 검토·루미 최종 보고의 실제 카드가 모두 필요합니다"})
        return result
    proofs = {ident: _completed_evidence(data["task"], data.get("events", []), data.get("runs", []))
              for ident, data in nodes.items()}
    if any(proof is None for proof in proofs.values()):
        result.update(status="blocked", error={"code": "completion_unverified",
                      "message": "모든 역할의 실제 실행과 완료 영수증을 확인해야 합니다"})
        return result
    if proofs[final_id][1]["id"] != max(proof[1]["id"] for proof in proofs.values()):
        result.update(status="blocked", error={"code": "native_collaboration_invalid",
                      "message": "루미 최종 보고보다 뒤의 역할 완료 기록이 있어 다시 검토해야 합니다"})
        return result
    final = projections[final_id]
    if final["report"] is None:
        result.update(status="blocked", error=final["error"])
        return result
    result.update(status="completed", native_status="done", assignee="lumi", current_run_id=None,
                  report=final["report"], error=None)
    result["_notice_ref"] = {"request_id": record["request_id"], "task_id": final["report"]["task_id"],
                             "run_id": final["report"]["run_id"], "event_id": final["report"]["event_id"],
                             "terminal_state": "completed"}
    return result


def _blocked_notice_ref(data, request_id):
    task = data["task"]
    latest = max((run for run in data.get("runs", []) if run.get("task_id") == task["id"]),
                 key=lambda run: run["id"], default=None)
    events = [event for event in data.get("events", []) if latest and event.get("task_id") == task["id"]
              and event.get("kind") == "blocked" and event.get("run_id") == latest["id"]]
    if (task.get("status") != "blocked" or not latest or latest.get("status") != "blocked"
            or latest.get("outcome") != "blocked" or latest.get("profile") != task.get("assignee")
            or not latest.get("ended_at") or not events):
        return None
    event = max(events, key=lambda item: item["id"])
    return {"request_id": request_id, "task_id": task["id"], "run_id": latest["id"],
            "event_id": event["id"], "terminal_state": "blocked"}


def _check_complete_graph(nodes, root_id):
    incoming = dict.fromkeys(nodes, 0)
    children = {ident: set(data.get("links", {}).get("children", [])) for ident, data in nodes.items()}
    for targets in children.values():
        for target in targets:
            if target not in nodes:
                raise BridgeError("native_graph_invalid", "역할 업무 연결이 완전하지 않습니다", 409)
            incoming[target] += 1
    queue = [ident for ident, count in incoming.items() if count == 0]
    distance, visited = {root_id: 0}, 0
    while queue:
        ident = queue.pop(0)
        visited += 1
        for child in children[ident]:
            distance[child] = max(distance.get(child, 0), distance.get(ident, 0) + 1)
            if distance[child] > 3:
                raise BridgeError("native_graph_limit", "역할 업무의 인계 깊이가 허용 범위를 넘었습니다", 409)
            incoming[child] -= 1
            if incoming[child] == 0:
                queue.append(child)
    if visited != len(nodes):
        raise BridgeError("native_graph_invalid", "역할 업무 연결에 순환이 있습니다", 409)


def _canonical_final(nodes, record):
    key = record["native_key"]
    allowed = {key, key + ":work", key + ":work-a", key + ":work-b", key + ":verify", key + ":final"}
    by_key = {}
    def invalid():
        raise BridgeError("native_collaboration_invalid", "역할·독립 검토·최종 보고의 업무 연결이 약속과 다릅니다", 409)
    for ident, data in nodes.items():
        native_key = data["task"].get("idempotency_key")
        if native_key not in allowed or native_key in by_key:
            invalid()
        by_key[native_key] = ident
    parallel = key + ":work-a" in by_key or key + ":work-b" in by_key
    if parallel and key + ":work" in by_key:
        invalid()
    work_keys = [key + suffix for suffix in ([":work-a", ":work-b"] if parallel else [":work"])]
    if not {key, *work_keys, key + ":verify", key + ":final"} <= by_key.keys():
        return None
    root_id, verify_id, final_id = by_key[key], by_key[key + ":verify"], by_key[key + ":final"]
    work_ids = {by_key[work_key] for work_key in work_keys}
    actors = {ident: data["task"].get("assignee") for ident, data in nodes.items()}
    workers = {actors[ident] for ident in work_ids}
    if (root_id != record["native_task_id"] or actors[root_id] != "lumi" or actors[final_id] != "lumi"
            or not set(actors.values()) <= PROFILES or not 3 <= len(set(actors.values())) <= 4
            or "lumi" in workers or actors[verify_id] in workers | {"lumi"}):
        invalid()
    parents = {root_id: set(), verify_id: work_ids, final_id: work_ids | {verify_id}}
    parents.update({ident: {root_id} for ident in work_ids})
    children = {ident: {child for child, sources in parents.items() if ident in sources} for ident in nodes}
    for ident, data in nodes.items():
        if (set(data.get("links", {}).get("parents", [])) != parents[ident]
                or set(data.get("links", {}).get("children", [])) != children[ident]):
            invalid()
    return final_id


def _completed_evidence(task, events, runs):
    ident = task.get("id")
    latest = max((run for run in runs if run.get("task_id") == ident), key=lambda run: run["id"], default=None)
    completed = [event for event in events if latest and event.get("task_id") == ident
                 and event.get("kind") == "completed" and event.get("run_id") == latest.get("id")]
    if (task.get("status") != "done" or not latest or latest.get("status") != "done"
            or latest.get("outcome") != "completed" or latest.get("profile") != task.get("assignee")
            or not latest.get("ended_at") or not completed):
        return None
    return latest, max(completed, key=lambda event: event["id"])


def project(record, data):
    task = data.get("task", {})
    task_id = record["native_task_id"]
    if task.get("id") != task_id or task.get("idempotency_key") != record["native_key"]:
        raise BridgeError("native_invalid_response", "비서 업무 참조가 일치하지 않습니다")
    events = [e for e in data.get("events", []) if e.get("task_id") == task_id]
    runs = [r for r in data.get("runs", []) if r.get("task_id") == task_id]
    evidence = _completed_evidence(task, events, runs)
    report = None
    unsafe_report = False
    native_status = task.get("status")
    if native_status not in {"triage", "todo", "ready", "running", "review", "done", "blocked", "archived"}:
        raise BridgeError("native_invalid_response", "비서 업무의 현재 상태를 확인할 수 없습니다")
    if evidence and str(evidence[0].get("summary") or "").strip():
        latest, event = evidence
        summary = str(latest["summary"])
        unsafe_report = bool(UNSAFE_DISPLAY.search(summary))
        if not unsafe_report:
            if len(summary) > 6000:
                summary = summary[:5900] + "\n[화면 표시를 줄였습니다. 전체 결과는 기존 비서 업무에서 확인하세요.]"
            report = {"summary": summary, "verified": True, "task_id": task_id,
                      "run_id": latest["id"], "event_id": event["id"]}
    status = {"running": "running", "blocked": "blocked", "review": "blocked",
              "archived": "failed"}.get(native_status, "queued")
    error = None
    if report:
        status = "completed"
    elif unsafe_report:
        status = "blocked"
        error = {"code": "report_redaction_required", "message": "완료 요약에 내부 정보가 있어 화면 전달을 보류했습니다. 기존 비서 업무에서 검토가 필요합니다"}
    elif native_status == "done":
        status = "blocked"
        error = {"code": "completion_unverified", "message": "완료 표시의 실제 실행 영수증을 확인해야 합니다"}
    elif status == "blocked":
        error = {"code": "human_action_required", "message": "사람의 입력·검토·승인이 필요합니다"}
    elif status == "failed":
        error = {"code": "native_task_closed", "message": "기존 비서 업무가 보관되었습니다"}
    return {"request_id": record["request_id"], "native_task_id": task_id, "board": BOARD,
            "delivery": {"slack": "not_attached"},
            "status": status, "native_status": native_status, "assignee": task.get("assignee"),
            "title": "3D 비서 요청 · " + record["request_id"][:8], "updated_at": max([e.get("created_at", 0) for e in events],
                                                          default=task.get("created_at")),
            "current_run_id": task.get("current_run_id"), "events": [
                {**{k: e.get(k) for k in ("id", "task_id", "run_id", "kind", "created_at")},
                 "assignee": next((r.get("profile") for r in runs if r.get("id") == e.get("run_id")),
                                  task.get("assignee"))} for e in events[-100:]],
            "report": report, "error": error}
