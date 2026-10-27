import copy
import hashlib

import pytest
from fastapi.testclient import TestClient

from office.api import create_app
from office.exports import write_blog_exports
from office.store import Store, digest


@pytest.fixture
def blog_context(tmp_path):
    store = Store(tmp_path / 'state')
    job = store.create_job({'id': 'reader-example', 'title': '블로그 예시', 'url': 'https://example.com/news'})
    packet = {'title': 'AI 문의 <script>alert(1)</script>', 'body': '## 판단의 기준\n\n검토할 문의와 다음 행동입니다.',
              'evidence': [], 'quality': {'status': 'passed', 'critical': []}}
    job = store.save_source(job['id'], packet)
    store.review_source(job['id'], job['source_hash'], 'approved', 'test-reader', {'blog': True, 'video': False})
    folder = store.artifacts / 'reader-example'
    folder.mkdir()
    files = write_blog_exports(packet, folder)
    records = [{'id': f'asset_reader_{index}', 'name': p.name, 'path': str(p.relative_to(store.artifacts)),
                'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'size': p.stat().st_size, 'outputs': ['blog']}
               for index, p in enumerate(files)]
    manifest = {'source_hash': job['source_hash'], 'files': records, 'completed_outputs': ['blog'],
                'output_status': {'blog': {'state': 'completed'}}}
    manifest['hash'] = digest(manifest)
    store.save_manifest_if_current(job['id'], job['source_hash'], store.job(job['id'])['selections'], manifest)
    return store, TestClient(create_app(store), base_url='http://localhost:8510'), job['id'], files


@pytest.mark.parametrize('format', ['html', 'markdown', 'naver'])
def test_reader_shows_actual_blog_without_release_and_leaves_state_unchanged(blog_context, format):
    store, client, job_id, files = blog_context
    before = copy.deepcopy(store.job(job_id))
    budget = store.budget()
    original = {p.name: p.read_bytes() for p in files}
    response = client.get(f'/api/jobs/{job_id}/blog-preview', params={'format': format})
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/html')
    assert '<html lang="ko">' in response.text
    assert '판단의 기준' in response.text and '검토할 문의와 다음 행동입니다.' in response.text
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in response.text
    assert '<script>' not in response.text
    assert "script-src 'none'" in response.headers['content-security-policy']
    assert store.job(job_id) == before
    assert store.budget() == budget
    assert store.tasks() == []
    assert {p.name: p.read_bytes() for p in files} == original


def test_reader_rejects_changed_export_bytes(blog_context):
    store, client, job_id, files = blog_context
    next(p for p in files if p.suffix == '.html').write_text('changed', encoding="utf-8")
    assert client.get(f'/api/jobs/{job_id}/blog-preview').status_code == 409


def test_reader_rejects_stale_source_and_unfinished_blog(blog_context):
    store, client, job_id, _ = blog_context
    packet = copy.deepcopy(store.job(job_id)['source_packet'])
    packet['body'] = '새 원고입니다.'
    store.save_source(job_id, packet)
    assert client.get(f'/api/jobs/{job_id}/blog-preview').status_code == 409


def test_reader_rejects_unknown_format(blog_context):
    _, client, job_id, _ = blog_context
    assert client.get(f'/api/jobs/{job_id}/blog-preview?format=../../private').status_code == 422
