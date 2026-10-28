"""Darwin identity contract with mocked OS data; real Mac execution is a separate gate."""
from contextlib import nullcontext
import sys
from types import SimpleNamespace

from office import runtime


def test_darwin_identity_preserves_args_and_detects_reused_pid(monkeypatch):
    class ProcessError(Exception):
        pass

    created = [1000.125]
    process = SimpleNamespace(
        pid=123,
        oneshot=nullcontext,
        create_time=lambda: created[0],
        cmdline=lambda: ["/usr/bin/python3", "-m", "office.worker", "space in argument"],
        exe=lambda: "/usr/bin/python3",
    )
    monkeypatch.setitem(sys.modules, "psutil", SimpleNamespace(Process=lambda pid: process, Error=ProcessError))
    monkeypatch.setattr(runtime.sys, "platform", "darwin")
    first = runtime.process_identity(123)
    assert first == {"pid": 123, "start_ticks": "darwin:1000.125", "args": process.cmdline(), "executable": "/usr/bin/python3"}
    created[0] = 2000.5
    assert runtime.process_identity(123)["start_ticks"] != first["start_ticks"]


def test_darwin_unreadable_process_fails_closed(monkeypatch):
    class ProcessError(Exception):
        pass

    def denied(pid):
        raise ProcessError("access denied")

    monkeypatch.setitem(sys.modules, "psutil", SimpleNamespace(Process=denied, Error=ProcessError))
    monkeypatch.setattr(runtime.sys, "platform", "darwin")
    assert runtime.process_identity(123) is None
    assert runtime.process_identity(-1) is None
