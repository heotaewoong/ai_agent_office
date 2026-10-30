import pytest
from datetime import datetime,timedelta,timezone
from office.store import Store,WorkflowError
from office.providers import Provider
from office import codex_text_provider as cp
SCHEMA={"type":"object","properties":{"answer":{"type":"string"}},"required":["answer"],"additionalProperties":False}
def ready(tmp_path):
 s=Store(tmp_path);s.set_setting("model",cp.PROFILE_ID);s.set_setting("work_window",{"status":"active","authorized_end":(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()});return s

def test_choice_cache_zero_cost(tmp_path,monkeypatch):
 s=ready(tmp_path);calls=[]
 monkeypatch.setattr(cp,"subscription_status",lambda:{"configured":True})
 monkeypatch.setattr(cp,"run_codex",lambda *a:calls.append(1) or {"answer":"ok"})
 from office.text_selection import select_profile
 assert select_profile(s,cp.PROFILE_ID,actor="test")["paid"] is False
 for _ in range(2):assert Provider(s).generate("critique",[],SCHEMA)=={"answer":"ok"}
 assert len(calls)==1 and s.budget()["spent_krw"]==0

def test_unknown_blocks_duplicate_without_fallback(tmp_path,monkeypatch):
 s=ready(tmp_path);calls=[]
 def fail(*a):calls.append(1);raise WorkflowError("unknown")
 monkeypatch.setattr(cp,"run_codex",fail)
 for _ in range(2):
  with pytest.raises(WorkflowError):Provider(s).generate("gen",[],SCHEMA)
 assert len(calls)==1

def test_closed_window_and_bad_schema(tmp_path,monkeypatch):
 s=ready(tmp_path);s.set_setting("work_window",{"status":"closed"})
 monkeypatch.setattr(cp,"run_codex",lambda *a:pytest.fail("closed"))
 with pytest.raises(WorkflowError,match="작업 시간"):Provider(s).generate("gen",[],SCHEMA)
 s=ready(tmp_path);monkeypatch.setattr(cp,"run_codex",lambda *a:{"wrong":True})
 with pytest.raises(WorkflowError,match="요청 형식"):Provider(s).generate("gen",[],SCHEMA)

def test_environment_and_auth_type(monkeypatch):
 from types import SimpleNamespace
 monkeypatch.setenv("OPENAI_API_KEY","not-real");monkeypatch.setenv("OFFICE_STATE_DIR","private")
 assert not ({"OPENAI_API_KEY","OFFICE_STATE_DIR"}&cp.cli_environment().keys())
 monkeypatch.setattr(cp.subprocess,"run",lambda *a,**k:SimpleNamespace(returncode=0,stdout="Logged in using API key",stderr=""))
 cp._status.cache_clear();assert cp._status(0,"codex","home") is False


def test_cli_path_includes_node_sibling_for_service_process(monkeypatch,tmp_path):
    binary=tmp_path/"bin"/"codex"
    monkeypatch.setenv("PATH","/usr/bin")
    assert cp.cli_environment(str(binary))["PATH"].split(cp.os.pathsep)[0]==str(binary.parent)
