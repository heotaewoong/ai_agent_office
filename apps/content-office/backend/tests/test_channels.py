"""Channel registry: owner-provided public addresses, per-channel credentials, no publication by default."""
import pytest

from office.store import Store, WorkflowError


def test_registry_has_owner_channels_with_safe_defaults(tmp_path):
    from office.channels import registry, CHANNELS
    store = Store(tmp_path)
    keys = set(CHANNELS)
    assert {"youtube_main_ko", "youtube_english", "instagram_main", "instagram_english", "threads_main", "linkedin_personal", "tistory_main", "naver_blog_main", "x_main", "slack_internal", "discord_contact"} <= keys
    rows = registry(store)
    by = {r["key"]: r for r in rows}
    assert by["youtube_english"]["platform"] == "youtube" and by["youtube_english"]["locale"] == "en"
    assert by["youtube_english"]["external_account_id"] == "UCc2CaOrPo-1dezowe7kklZA"
    assert by["youtube_main_ko"]["external_account_id"] is None
    assert all(r["publication_enabled"] is False for r in rows)
    assert by["tistory_main"]["delivery"] == "manual" and by["youtube_main_ko"]["delivery"] == "youtube_api"
    assert by["discord_contact"]["delivery"] == "notify"
    assert all(r["public_url"].startswith("https://") for r in rows if r.get("public_url"))


def test_operator_can_bind_external_id_and_enable_without_touching_secrets(tmp_path):
    from office.channels import registry, update_channel
    store = Store(tmp_path)
    row = update_channel(store, "youtube_main_ko", {"external_account_id": "UCmainko0000000000000000", "publication_enabled": True}, actor="local-operator")
    assert row["external_account_id"] == "UCmainko0000000000000000" and row["publication_enabled"] is True
    assert {r["key"]: r for r in registry(store)}["youtube_main_ko"]["publication_enabled"] is True
    with pytest.raises(WorkflowError, match="채널"):
        update_channel(store, "tiktok_main", {"publication_enabled": True}, actor="local-operator")
    with pytest.raises(WorkflowError, match="필드"):
        update_channel(store, "youtube_main_ko", {"refresh_token": "abc"}, actor="local-operator")
    with pytest.raises(WorkflowError, match="channel ID"):
        update_channel(store, "youtube_main_ko", {"external_account_id": "not a channel id"}, actor="local-operator")
    assert any(e["kind"] == "channel_updated" for e in store.events(limit=5))


def test_youtube_credentials_are_per_channel_with_legacy_fallback(monkeypatch):
    from office.channels import youtube_credentials, configured_youtube_channels
    for key in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN", "YOUTUBE_MAIN_KO_REFRESH_TOKEN", "YOUTUBE_ENGLISH_REFRESH_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    assert configured_youtube_channels() == []
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "cid")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "sec")
    monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", "legacy")
    assert youtube_credentials("youtube_main_ko") == {"client_id": "cid", "client_secret": "sec", "refresh_token": "legacy"}
    assert youtube_credentials("youtube_english") is None
    assert configured_youtube_channels() == ["youtube_main_ko"]
    monkeypatch.setenv("YOUTUBE_ENGLISH_REFRESH_TOKEN", "en-token")
    monkeypatch.setenv("YOUTUBE_MAIN_KO_REFRESH_TOKEN", "ko-token")
    assert youtube_credentials("youtube_main_ko")["refresh_token"] == "ko-token"
    assert youtube_credentials("youtube_english")["refresh_token"] == "en-token"
    assert configured_youtube_channels() == ["youtube_main_ko", "youtube_english"]
    with pytest.raises(WorkflowError, match="YouTube 채널"):
        youtube_credentials("tistory_main")


def test_formats_include_manual_social_channels():
    from office.formats import FORMATS
    for key in ("x_post", "threads_post", "linkedin_post", "instagram_card"):
        assert FORMATS[key]["delivery"] in ("manual_paste", "manual_upload"), key
