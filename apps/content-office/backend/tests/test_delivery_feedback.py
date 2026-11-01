import pytest
from office.store import Store, WorkflowError
from office.delivery_queue import target

def test_expired_pc_status_explains_pc_reconnection_without_server_oauth(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFICE_SOCIAL_AUTH_MODE", "owner_pc")
    monkeypatch.setattr("office.delivery_queue.channel", lambda *args: {"platform":"youtube", "credentials_configured":False})
    store=Store(tmp_path)
    with pytest.raises(WorkflowError, match="PC 인증 실행기"):
        target(store,"youtube_english",{})
    assert store.tasks()==[]
