from datetime import datetime, timedelta, timezone
import hashlib
import json

import pytest

from office import owner_auth, youtube_tokens
from office.channels import channel, youtube_credentials
from office.store import WorkflowError
from test_youtube_delivery import enabled_fixture


def ready(tmp_path, monkeypatch, approve_release=True):
    store, job_id = enabled_fixture(tmp_path, approve_release=approve_release)
    monkeypatch.setenv('OFFICE_SOCIAL_AUTH_MODE', 'owner_pc')
    monkeypatch.setenv('OFFICE_STATE_DIR', str(store.root))
    folder = store.root / 'runtime'; folder.mkdir(exist_ok=True)
    (folder / 'owner-auth-status.json').write_text(json.dumps({'checked_at': datetime.now(timezone.utc).isoformat(), 'channels': {'youtube_main_ko': True}}))
    return store, job_id


def test_owner_mode_blocks_server_token_storage(tmp_path, monkeypatch):
    ready(tmp_path, monkeypatch)
    secret = tmp_path / 'tokens.json'
    monkeypatch.setenv('OFFICE_SECRETS_FILE', str(secret))
    with pytest.raises(WorkflowError, match='본인 PC'):
        youtube_tokens.save_token('youtube_main_ko', {'refresh_token': 'synthetic', 'channel_id': 'fixture'})
    assert not secret.exists()


def test_server_env_credentials_do_not_override_owner_mode(tmp_path, monkeypatch):
    store, _ = ready(tmp_path, monkeypatch)
    for key in ('YOUTUBE_CLIENT_ID', 'YOUTUBE_CLIENT_SECRET', 'YOUTUBE_REFRESH_TOKEN'):
        monkeypatch.setenv(key, 'synthetic')
    assert youtube_credentials('youtube_main_ko') is None
    assert channel(store, 'youtube_main_ko')['credentials_configured'] is True
    from office.youtube_oauth import client_configured, require_ready
    assert client_configured() is False
    with pytest.raises(WorkflowError, match='본인 PC'): require_ready(store, 'https://example.invalid')


def test_expired_owner_lease_does_not_claim_connection(tmp_path, monkeypatch):
    store, _ = ready(tmp_path, monkeypatch)
    path = store.root / 'runtime/owner-auth-status.json'
    path.write_text(json.dumps({'checked_at': (datetime.now(timezone.utc) - timedelta(minutes=11)).isoformat(), 'channels': {'youtube_main_ko': True}}))
    assert owner_auth.available_keys() == []
    assert not channel(store, 'youtube_main_ko')['credentials_configured']


def test_release_approval_remains_required_without_credentials_on_server(tmp_path, monkeypatch):
    store, job_id = ready(tmp_path, monkeypatch, approve_release=False)
    from office.youtube_delivery import deliver_youtube
    with pytest.raises(WorkflowError, match='출고 승인②'):
        deliver_youtube(store, job_id, actor='fixture')
    assert not store.setting('deliveries', {})


def test_staging_is_idempotent_and_export_does_not_expose_credentials(tmp_path, monkeypatch):
    store, job_id = ready(tmp_path, monkeypatch)
    from office.youtube_delivery import deliver_youtube
    first = deliver_youtube(store, job_id, actor='fixture')
    assert first['state'] == 'pending_owner'
    assert deliver_youtube(store, job_id, actor='fixture') == first
    packet, = owner_auth.export_pending(store)
    assert set(packet) == {'delivery_key', 'channel_key', 'job_id', 'asset_path', 'asset_sha256', 'asset_size', 'title', 'description', 'authorized_end'}
    assert not any('token' in key or 'secret' in key for key in packet)


def test_owner_receipt_validates_media_and_cannot_publish(tmp_path, monkeypatch):
    store, job_id = ready(tmp_path, monkeypatch)
    first = owner_auth.stage_delivery(store, job_id, 'youtube_main_ko', 'fixture')
    packet, = owner_auth.export_pending(store)
    media = (store.artifacts / packet['asset_path']).read_bytes()
    metadata = {'snippet': {k: packet[k] for k in ('title', 'description')}, 'status': {'privacyStatus': 'private', 'selfDeclaredMadeForKids': False}}
    checksum = hashlib.sha256(media + json.dumps(metadata, sort_keys=True).encode()).hexdigest()
    receipt = {'state': 'platform_private', 'external_id': 'fixture_123', 'content_hash': checksum, 'channel_key': 'youtube_main_ko', 'verified_at': datetime.now(timezone.utc).isoformat()}
    with pytest.raises(WorkflowError): owner_auth.accept_receipt(store, first['key'], {**receipt, 'state': 'published'})
    with pytest.raises(WorkflowError): owner_auth.accept_receipt(store, first['key'], {**receipt, 'content_hash': '0' * 64})
    final = owner_auth.accept_receipt(store, first['key'], receipt)
    assert final['state'] == 'private'
    assert owner_auth.accept_receipt(store, first['key'], receipt) == final
    assert owner_auth.export_pending(store) == []


def test_closed_work_window_prevents_new_owner_delivery(tmp_path, monkeypatch):
    store, job_id = ready(tmp_path, monkeypatch)
    store.set_setting('work_window', {'status': 'closed'})
    with pytest.raises(WorkflowError, match='작업 시간'):
        owner_auth.stage_delivery(store, job_id, 'youtube_main_ko', 'fixture')


def test_tampered_asset_is_not_sent_to_owner(tmp_path, monkeypatch):
    store, job_id = ready(tmp_path, monkeypatch)
    owner_auth.stage_delivery(store, job_id, 'youtube_main_ko', 'fixture')
    packet, = owner_auth.export_pending(store)
    (store.artifacts / packet['asset_path']).write_bytes(b'tampered')
    with pytest.raises(WorkflowError): owner_auth.export_pending(store)
