from hashlib import sha256
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from office import api_world_music

def setup(tmp_path):
    app = FastAPI()
    api_world_music.register(app, SimpleNamespace(root=tmp_path))
    return TestClient(app)

def test_missing_does_not_expose_paths_or_create_files(tmp_path):
    client = setup(tmp_path)
    result = client.get('/api/world/music/status').json()
    assert result['available'] is False
    assert str(tmp_path) not in str(result)
    assert client.get('/api/world/music/audio').status_code == 404
    assert list(tmp_path.iterdir()) == []

def test_verified_audio_and_ranges(tmp_path, monkeypatch):
    path = tmp_path / 'world-media' / 'titan.mp3'
    path.parent.mkdir()
    path.write_bytes(b'licensed-test-audio')
    monkeypatch.setattr(api_world_music, 'EXPECTED_SHA256', sha256(path.read_bytes()).hexdigest())
    client = setup(tmp_path)
    assert client.get('/api/world/music/status').json()['available'] is True
    result = client.get('/api/world/music/audio')
    assert result.content == b'licensed-test-audio'
    assert result.headers['cache-control'] == 'private, no-store'
    assert result.headers['content-type'] == 'audio/mpeg'
    partial = client.get('/api/world/music/audio', headers={'Range': 'bytes=0-7'})
    assert partial.status_code == 206
    assert partial.content == b'licensed'
    path.write_bytes(b'changed')
    assert client.get('/api/world/music/audio').status_code == 404

def test_outside_symlink_is_rejected(tmp_path, monkeypatch):
    outside = tmp_path.parent / (tmp_path.name + '-outside.mp3')
    outside.write_bytes(b'outside')
    folder = tmp_path / 'world-media'
    folder.mkdir()
    try:
        (folder / 'titan.mp3').symlink_to(outside)
    except OSError:
        import pytest
        pytest.skip('symlink privilege unavailable')
    monkeypatch.setattr(api_world_music, 'EXPECTED_SHA256', sha256(b'outside').hexdigest())
    assert setup(tmp_path).get('/api/world/music/audio').status_code == 404
