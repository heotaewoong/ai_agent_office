"""Large review MP4s use the existing formal-import bound, without changing image limits."""
import pytest
from office import editorial_assets as assets
from office import external_media
from office.store import WorkflowError


class Store:
    def __init__(self, root):
        self.artifacts = root
        self.registered = None

    def job(self, job_id):
        return {'source_hash': 'a' * 64}

    def add_draft(self, job_id, draft, expected_source_hash):
        assert expected_source_hash == 'a' * 64
        self.registered = draft
        return draft


@pytest.fixture
def limits(monkeypatch):
    # Small byte fixtures avoid rendering or copying media on the development PC.
    monkeypatch.setattr(assets, 'MAX_REVIEW_FILE_BYTES', 8)
    monkeypatch.setattr(assets, 'MAX_REVIEW_VIDEO_BYTES', 16)
    monkeypatch.setattr(assets, 'MAX_REVIEW_TOTAL_BYTES', 24)
    monkeypatch.setattr(assets, 'MAX_REVIEW_STANDARD_TOTAL_BYTES', 12, raising=False)


def register(store, file):
    return assets.register_assets(store, 'job_review', 'a' * 64, '검토본', '미승인 검토', [(file.name, file)])


def test_large_mp4_is_probed_and_copied_without_source_or_approval_changes(tmp_path, monkeypatch, limits):
    store = Store(tmp_path / 'artifacts'); source = tmp_path / 'film.mp4'; source.write_bytes(b'x' * 16)
    calls = []
    monkeypatch.setattr(external_media, '_probe', lambda p: calls.append(p) or {'codec': 'h264/aac', 'seconds': 148})
    draft = register(store, source)
    assert calls == [source]
    assert source.read_bytes() == b'x' * 16
    assert (store.artifacts / draft['assets'][0]['path']).read_bytes() == source.read_bytes()
    assert set(draft) == {'title', 'body', 'assets', 'source_hash_snapshot', 'note'}
    assert draft['source_hash_snapshot'] == 'a' * 64


@pytest.mark.parametrize('name,size', [('film.mp4', 17), ('image.png', 9), ('notes.txt', 9)])
def test_oversize_mp4_and_unchanged_image_text_limits_stop_before_registration(tmp_path, limits, name, size):
    store = Store(tmp_path / 'artifacts'); source = tmp_path / name; source.write_bytes(b'x' * size)
    with pytest.raises(WorkflowError, match='용량'):
        register(store, source)
    assert store.registered is None and source.read_bytes() == b'x' * size


def test_large_invalid_video_cannot_be_registered_under_the_new_limit(tmp_path, monkeypatch, limits):
    store = Store(tmp_path / 'artifacts'); source = tmp_path / 'film.mp4'; source.write_bytes(b'x' * 12)
    def reject(path):
        raise WorkflowError('영상·음성 스트림 검사 실패')
    monkeypatch.setattr(external_media, '_probe', reject)
    with pytest.raises(WorkflowError, match='스트림'):
        register(store, source)
    assert store.registered is None


def test_video_path_cannot_bypass_the_displayed_image_limit(tmp_path, monkeypatch, limits):
    store = Store(tmp_path / 'artifacts'); source = tmp_path / 'film.mp4'; source.write_bytes(b'x' * 12)
    monkeypatch.setattr(external_media, '_probe', lambda p: {'codec': 'h264/aac', 'seconds': 148})
    with pytest.raises(WorkflowError, match='용량'):
        assets.register_assets(store, 'job_review', 'a' * 64, '제목', '검토', [('image.png', source)])
    assert store.registered is None


def test_total_limit_still_blocks_multiple_large_videos(tmp_path, monkeypatch, limits):
    store = Store(tmp_path / 'artifacts'); files = []
    for name in ['one.mp4', 'two.mp4']:
        source = tmp_path / name; source.write_bytes(b'x' * 16); files.append((name, source))
    monkeypatch.setattr(external_media, '_probe', lambda p: {'codec': 'h264/aac', 'seconds': 148})
    with pytest.raises(WorkflowError, match='용량'):
        assets.register_assets(store, 'job_review', 'a' * 64, '제목', '검토', files)
    assert store.registered is None


def test_file_growth_during_probe_stops_registration(tmp_path, monkeypatch, limits):
    store = Store(tmp_path / 'artifacts'); source = tmp_path / 'film.mp4'; source.write_bytes(b'x' * 12)
    monkeypatch.setattr(external_media, '_probe', lambda p: source.write_bytes(b'x' * 13))
    with pytest.raises(WorkflowError, match='변경'):
        register(store, source)
    assert store.registered is None


def test_images_and_text_only_keep_the_original_total_limit(tmp_path, limits):
    store = Store(tmp_path / 'artifacts'); files = []
    for name in ['one.txt', 'two.txt']:
        source = tmp_path / name; source.write_bytes(b'x' * 8); files.append((name, source))
    with pytest.raises(WorkflowError, match='용량'):
        assets.register_assets(store, 'job_review', 'a' * 64, '제목', '검토', files)
    assert store.registered is None


def test_larger_video_bundle_limit_does_not_depend_on_file_order(tmp_path, monkeypatch, limits):
    source = tmp_path / 'film.mp4'; source.write_bytes(b'x' * 12)
    note = tmp_path / 'notes.txt'; note.write_bytes(b'n' * 8)
    monkeypatch.setattr(external_media, '_probe', lambda p: {'codec': 'h264/aac', 'seconds': 148})
    for i, files in enumerate([[('notes.txt', note), ('film.mp4', source)], [('film.mp4', source), ('notes.txt', note)]]):
        store = Store(tmp_path / f'artifacts-{i}')
        assets.register_assets(store, 'job_review', 'a' * 64, '제목', '검토', files)
        assert store.registered is not None


def test_formal_import_checks_the_shared_video_bound(tmp_path, monkeypatch):
    from tests.test_external_media import context
    store, job, draft = context(tmp_path, monkeypatch)
    monkeypatch.setattr(external_media, 'MAX_IMPORTED_VIDEO_BYTES', len(b'synthetic-video') - 1)
    with pytest.raises(WorkflowError, match='크기'):
        external_media.files_for(store, job, draft['id'])
    monkeypatch.setattr(external_media, 'MAX_IMPORTED_VIDEO_BYTES', len(b'synthetic-video'))
    assert external_media.files_for(store, job, draft['id'])[2]['short.mp4'].read_bytes() == b'synthetic-video'


def test_large_review_video_supports_authenticated_inline_range_delivery(tmp_path, monkeypatch, limits):
    from fastapi.testclient import TestClient
    from office.api import create_app
    from office.store import Store as ActualStore
    store = ActualStore(tmp_path / 'state')
    job = store.create_job({'id': 'review-video', 'title': '검토', 'url': ''})
    job = store.save_source(job['id'], {'title': '검토', 'body': '원문', 'quality': {'status': 'passed', 'critical': False}})
    source = tmp_path / 'film.mp4'; source.write_bytes(b'synthetic-video')
    monkeypatch.setattr(external_media, '_probe', lambda p: {'codec': 'h264/aac', 'seconds': 148})
    before = store.job(job['id'])
    draft = assets.register_assets(store, job['id'], job['source_hash'], '가로 영상', '미승인 검토', [('film.mp4', source)])
    client = TestClient(create_app(store), base_url='http://localhost:8510')
    response = client.get(f'/api/jobs/{job["id"]}/drafts/{draft["id"]}/files/film.mp4', headers={'Range': 'bytes=0-5'})
    assert response.status_code == 206 and response.content == b'synthe'
    assert response.headers['content-range'] == 'bytes 0-5/15'
    assert response.headers['content-disposition'] == 'inline'
    assert store.job(job['id']) == before
