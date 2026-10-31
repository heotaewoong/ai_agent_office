import hashlib
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from office.api import create_app
from office.store import Store, WorkflowError
from office.editorial_assets import register_assets
from office import external_media as module


def context(tmp_path, monkeypatch):
    store = Store(tmp_path / 'state')
    job = store.create_job({'id': 'fixture', 'title': '기존 원고', 'url': ''})
    job = store.save_source(job['id'], {'title': '기존 원고', 'body': '이전 본문', 'quality': {'status': 'passed', 'critical': False}})
    values = {'short.mp4': b'synthetic-video', 'source-original.md': '새 원문입니다.\n'.encode(),
              'captions.srt': '1\n00:00:00,000 --> 00:00:01,000\n새 원문입니다.\n'.encode(),
              'thumbnail-01.png': b'synthetic-image', 'description.txt': '비공개 설명'.encode()}
    files = []
    for name, raw in values.items():
        path = tmp_path / name
        path.write_bytes(raw)
        files.append((name, path))
    draft = register_assets(store, job['id'], job['source_hash'], 'v17 연결 검토', '미승인', files)
    monkeypatch.setattr(module, '_probe', lambda path, decode=False: {'seconds': 2, 'width': 1080, 'height': 1920, 'full_decode': decode})
    return store, job, draft


def prepared(tmp_path, monkeypatch):
    store, job, draft = context(tmp_path, monkeypatch)
    current = module.prepare_review(store, job['id'], draft['id'], job['source_hash'])
    return store, current, draft


def test_prepare_creates_review_version_not_quality_pass_or_approval(tmp_path, monkeypatch):
    store, job, draft = context(tmp_path, monkeypatch)
    current = module.prepare_review(store, job['id'], draft['id'], job['source_hash'])
    assert current['source_hash'] != job['source_hash']
    assert current['source_packet']['body'] == '새 원문입니다.\n'
    assert current['source_packet']['quality']['status'] == 'external_review_required'
    assert current['source_approval'] is current['release_approval'] is current['manifest'] is None
    assert store.drafts(job['id'])[0]['id'] == draft['id']


def test_existing_source_approval_api_cannot_silently_approve_external(tmp_path, monkeypatch):
    store, job, _ = prepared(tmp_path, monkeypatch)
    with pytest.raises(WorkflowError):
        store.review_source(job['id'], job['source_hash'], 'approved', 'fixture')
    assert store.job(job['id'])['source_approval'] is None


def test_explicit_manual_review_is_required_and_strict(tmp_path, monkeypatch):
    store, job, _ = prepared(tmp_path, monkeypatch)
    for checked in [False, None, 'true', 1]:
        with pytest.raises(WorkflowError):
            module.adopt_reviewed(store, job['id'], job['source_hash'], checked)
    assert store.job(job['id'])['manifest'] is None


def test_import_preserves_video_bytes_and_requires_separate_release_approval(tmp_path, monkeypatch):
    store, job, draft = prepared(tmp_path, monkeypatch)
    result = module.adopt_reviewed(store, job['id'], job['source_hash'], True)
    assert result['source_approval']['review_method'] == 'operator_external_media'
    assert result['source_packet']['quality']['status'] == 'external_review_required'
    assert result['release_approval'] is None
    manifest = result['manifest']
    assert manifest['production_method'] == 'imported_edited_media'
    video = next(a for a in manifest['files'] if a['name'] == 'short.mp4')
    assert video['sha256'] == hashlib.sha256(b'synthetic-video').hexdigest()
    assert manifest['selected_thumbnail_id'] is None
    with pytest.raises(WorkflowError):
        store.review_release(job['id'], manifest['hash'], 'approved', 'fixture', True, ['video'])
    candidate = manifest['thumbnail_candidates'][0]
    result = store.select_thumbnail(job['id'], candidate['id'], manifest['hash'], 'fixture')
    result = store.review_release(job['id'], result['manifest']['hash'], 'approved', 'fixture', True, ['video', 'blog'])
    assert result['release_approval']['decision'] == 'approved'
    assert result['release_approval']['external_published'] is False


@pytest.mark.parametrize('name', module.REQUIRED)
def test_modified_import_asset_never_creates_approval_or_manifest(tmp_path, monkeypatch, name):
    store, job, draft = prepared(tmp_path, monkeypatch)
    asset = next(a for a in draft['assets'] if a['name'] == name)
    (store.artifacts / asset['path']).write_bytes(b'changed')
    with pytest.raises(WorkflowError):
        module.adopt_reviewed(store, job['id'], job['source_hash'], True)
    assert store.job(job['id'])['source_approval'] is None
    assert store.job(job['id'])['manifest'] is None


def test_stale_source_or_foreign_draft_never_imports(tmp_path, monkeypatch):
    store, job, draft = context(tmp_path, monkeypatch)
    for version, draft_id in [('f' * 64, draft['id']), (job['source_hash'], 'draft_foreign')]:
        with pytest.raises(WorkflowError):
            module.prepare_review(store, job['id'], draft_id, version)
    assert store.job(job['id']) == job


def test_caption_missing_text_rejected_before_source_update(tmp_path, monkeypatch):
    store, job, draft = context(tmp_path, monkeypatch)
    broken = tmp_path / 'broken.srt'
    broken.write_text('1\n00:00:00,000 --> 00:00:01,000\n다른 원문\n', encoding='utf8')
    files = [(a['name'], broken if a['name'] == 'captions.srt' else store.artifacts / a['path']) for a in draft['assets']]
    other = register_assets(store, job['id'], job['source_hash'], '불일치', '검토', files)
    with pytest.raises(WorkflowError):
        module.prepare_review(store, job['id'], other['id'], job['source_hash'])
    assert store.job(job['id']) == job


def test_manual_flag_does_not_bypass_ordinary_unverified_quality(tmp_path, monkeypatch):
    store, job, _ = prepared(tmp_path, monkeypatch)
    packet = dict(job['source_packet'])
    packet['quality'] = {'status': 'unverified', 'critical': False}
    job = store.save_source(job['id'], packet, expected_hash=job['source_hash'])
    with pytest.raises(WorkflowError):
        store.review_source(job['id'], job['source_hash'], 'approved', 'fixture', external_media_reviewed=True)


def test_repeated_adoption_is_idempotent_without_extra_approval(tmp_path, monkeypatch):
    store, job, _ = prepared(tmp_path, monkeypatch)
    first = module.adopt_reviewed(store, job['id'], job['source_hash'], True)
    second = module.adopt_reviewed(store, job['id'], job['source_hash'], True)
    assert first['manifest'] == second['manifest']
    assert first['source_approval'] == second['source_approval']


def test_endpoint_requires_csrf_and_strict_human_check(tmp_path, monkeypatch):
    store, job, _ = prepared(tmp_path, monkeypatch)
    client = TestClient(create_app(store), base_url='http://localhost:8510')
    path = f'/api/jobs/{job["id"]}/external-media/adopt'
    payload = {'version': job['source_hash'], 'reviewed': True}
    assert client.post(path, json=payload).status_code == 403
    csrf = client.get('/api/session').json()['csrf']
    assert client.post(path, json={**payload, 'reviewed': 'true'}, headers={'X-Office-CSRF': csrf, 'Origin': 'http://localhost:8510'}).status_code == 422
    assert store.job(job['id'])['source_approval'] is None


@pytest.mark.parametrize('timing', ['00:00:01,000 --> 00:00:00,000', '00:00:00,000 --> 00:00:09,000', 'invalid --> invalid'])
def test_invalid_caption_time_never_updates_source(tmp_path, monkeypatch, timing):
    store, job, draft = context(tmp_path, monkeypatch)
    subtitle = tmp_path / 'time.srt'
    subtitle.write_text('1\n' + timing + '\n새 원문입니다.\n', encoding='utf8')
    files = [(a['name'], subtitle if a['name'] == 'captions.srt' else store.artifacts / a['path']) for a in draft['assets']]
    other = register_assets(store, job['id'], job['source_hash'], '시간 오류', '검토', files)
    with pytest.raises(WorkflowError):
        module.prepare_review(store, job['id'], other['id'], job['source_hash'])
    assert store.job(job['id']) == job


def test_copy_race_does_not_record_completed_manifest(tmp_path, monkeypatch):
    store, job, _ = prepared(tmp_path, monkeypatch)
    monkeypatch.setattr(module.shutil, 'copyfile', lambda source, target: Path(target).write_bytes(b'changed-during-copy'))
    with pytest.raises(WorkflowError):
        module.adopt_reviewed(store, job['id'], job['source_hash'], True)
    assert store.job(job['id'])['manifest'] is None


def pack_context(tmp_path, monkeypatch):
    from PIL import Image
    store, job, draft = context(tmp_path, monkeypatch)
    files = [(a['name'], store.artifacts / a['path']) for a in draft['assets']]
    for name in module.PACK_TEXTS:
        path = tmp_path / name
        path.write_text(name + '\n플랫폼에 맞춘 새 원문입니다.\n', 'utf8')
        files.append((name, path))
    for i, name in enumerate(module.PACK_CARDS):
        path = tmp_path / name
        Image.new('RGB', (1080, 1350), (i*20, 50, 80)).save(path)
        files.append((name, path))
    draft = register_assets(store, job['id'], job['source_hash'], '카드와 채널별 글', '미승인', files)
    return store, job, draft


def test_channel_pack_is_reviewable_and_approval_still_required(tmp_path, monkeypatch):
    store, job, draft = pack_context(tmp_path, monkeypatch)
    current = module.prepare_review(store, job['id'], draft['id'], job['source_hash'])
    assert current['source_approval'] is current['release_approval'] is current['manifest'] is None
    assert len(current['source_packet']['external_media']['channel_pack']['cards']) == 8
    result = module.adopt_reviewed(store, job['id'], current['source_hash'], True)
    assert set(result['manifest']['completed_outputs']) == {'blog', 'video', 'cards'}
    assert result['selections']['cards'] is True
    assert result['release_approval'] is None
    files = {a['name']: a for a in result['manifest']['files']}
    assert len([a for a in files.values() if a['outputs'] == ['cards']]) == 8
    assert (store.artifacts / files['tistory.md']['path']).read_text().startswith('tistory-article.md')
    assert (store.artifacts / files['naver.txt']['path']).read_text().startswith('naver-article.txt')
    assert (store.artifacts / files['threads-main.txt']['path']).read_text().startswith('threads-post.txt')
    assert (store.artifacts / files['linkedin-personal.txt']['path']).read_text().startswith('linkedin-post.txt')
    assert result['source_packet']['quality']['status'] == 'external_review_required'
    again = module.adopt_reviewed(store, job['id'], current['source_hash'], True)
    assert result['manifest'] == again['manifest']


@pytest.mark.parametrize('name', ['card-01.png', 'threads-post.txt'])
def test_pack_tamper_cannot_be_approved(tmp_path, monkeypatch, name):
    store, job, draft = pack_context(tmp_path, monkeypatch)
    current = module.prepare_review(store, job['id'], draft['id'], job['source_hash'])
    record = next(a for a in draft['assets'] if a['name'] == name)
    (store.artifacts / record['path']).write_bytes(b'tampered')
    with pytest.raises(WorkflowError):
        module.adopt_reviewed(store, job['id'], current['source_hash'], True)
    assert store.job(job['id'])['source_approval'] is None


@pytest.mark.parametrize('mode', ['partial', 'duplicate', 'dimensions', 'empty'])
def test_invalid_channel_bundle_does_not_replace_original(tmp_path, monkeypatch, mode):
    from PIL import Image
    store, job, draft = pack_context(tmp_path, monkeypatch)
    files = [(a['name'], store.artifacts / a['path']) for a in draft['assets']]
    if mode == 'partial':
        files = [(name,path) for name,path in files if name != 'threads-post.txt']
    elif mode == 'duplicate':
        first = next(path for name,path in files if name == 'card-01.png')
        files = [(name,first if name == 'card-02.png' else path) for name,path in files]
    elif mode == 'dimensions':
        wrong = tmp_path / 'wrong.png'; Image.new('RGB',(30,30)).save(wrong)
        files = [(name,wrong if name == 'card-01.png' else path) for name,path in files]
    else:
        empty = tmp_path / 'empty.txt';empty.write_text(' ', 'utf8')
        files = [(name,empty if name == 'threads-post.txt' else path) for name,path in files]
    other = register_assets(store, job['id'], job['source_hash'], '잘못된 묶음', '검토', files)
    with pytest.raises(WorkflowError):module.prepare_review(store,job['id'],other['id'],job['source_hash'])
    assert store.job(job['id']) == job
