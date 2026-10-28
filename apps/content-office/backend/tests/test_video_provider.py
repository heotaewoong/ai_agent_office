"""Runway generated-clip provider: opt-in scenes, credits ledger, polling, receipts. No network here."""
import json

import pytest
import requests
from PIL import Image

from office.store import Store, WorkflowError

MP4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isomiso2mp41" + b"\x00" * 200


def scenes(generated=(1,)):
    base = [{'narration': '근거를 확인합니다.', 'caption': '근거를 먼저 확인', 'visual': '설명: 공식 문서와 발표'},
            {'narration': '원고를 승인합니다.', 'caption': '원고 승인①', 'visual': '흐름: 초안 → 검토 → 승인'},
            {'narration': '선택한 결과를 제작합니다.', 'caption': '출력별 제작', 'visual': '비교: 블로그 vs 영상'}]
    for index in generated:
        base[index] = {**base[index], 'clip': 'generated', 'motion': '카메라가 천천히 앞으로 이동'}
    return base


def approved_fixture(tmp_path, *, approve=True, generated=(1,), video=True):
    store = Store(tmp_path / 'state')
    job = store.create_job({'id': 'clip-test', 'title': '생성 영상 시험'})
    packet = {'title': '생성 영상 시험', 'body': '합성 기능 시험입니다.', 'synthetic_fixture': True,
              'quality': {'status': 'passed', 'critical': []}, 'video': {'scenes': scenes(generated)}}
    job = store.save_source(job['id'], packet)
    if approve:
        store.review_source(job['id'], job['source_hash'], 'approved', '합성 기능 시험 승인', {'video': video, 'cards': not video})
    return store, job['id']


def plate(store, name='plate.png'):
    path = store.root / name
    Image.new('RGB', (64, 96), '#7a2e1e').save(path, 'PNG')
    return path


class Response:
    def __init__(self, status, body=None, content=b'', headers=None):
        self.status_code, self._body, self.content, self.headers = status, body, content, headers or {}

    def json(self):
        if self._body is None:
            raise ValueError('no json')
        return self._body


class FakeSession:
    """Scripted Runway: POST creates a task, GET /tasks returns the scripted statuses in order, GET output URL returns bytes."""

    def __init__(self, statuses=None, credits=25, output_bytes=MP4, create_status=200):
        self.statuses = list(statuses or [{'status': 'PENDING'}, {'status': 'RUNNING', 'progress': 0.5},
                                          {'status': 'SUCCEEDED', 'output': ['https://cdn.example/out.mp4'], 'cost': {'credits': credits}}])
        self.output_bytes, self.create_status = output_bytes, create_status
        self.posts, self.gets = [], []

    def post(self, url, **kwargs):
        self.posts.append({'url': url, **kwargs})
        if self.create_status != 200:
            return Response(self.create_status, {'error': 'nope'})
        return Response(200, {'id': 'task_123'})

    def get(self, url, **kwargs):
        self.gets.append({'url': url, **kwargs})
        if url.startswith('https://api.dev.runwayml.com/v1/tasks/'):
            body = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            return Response(200, {'id': 'task_123', 'createdAt': '2026-10-28T00:00:00Z', **body})
        return Response(200, None, content=self.output_bytes)


def make(store, job_id, session, **kwargs):
    from office.video_provider import make_runway_clip_renderer
    return make_runway_clip_renderer(store, job_id=job_id, allow_paid=True, session=session, sleep=lambda s: None, **kwargs)


def test_unapproved_and_missing_secret_are_rejected_before_cost(tmp_path, monkeypatch):
    from office.video_provider import make_runway_clip_renderer
    monkeypatch.setenv('RUNWAYML_API_SECRET', 'test-secret')
    store, job_id = approved_fixture(tmp_path, approve=False)
    with pytest.raises(WorkflowError, match='승인'):
        make_runway_clip_renderer(store, job_id=job_id, allow_paid=True, session=FakeSession())
    monkeypatch.delenv('RUNWAYML_API_SECRET')
    store, job_id = approved_fixture(tmp_path / 'b')
    session = FakeSession()
    with pytest.raises(WorkflowError, match='RUNWAYML_API_SECRET'):
        make(store, job_id, session)(1, plate(store), store.root / 'clip.mp4')
    assert session.posts == [] and store.budget()['reserved_krw'] == 0


def test_only_opted_in_scenes_and_at_most_three_clips(tmp_path, monkeypatch):
    from office.video_provider import make_runway_clip_renderer, MAX_CLIPS_PER_JOB
    monkeypatch.setenv('RUNWAYML_API_SECRET', 'test-secret')
    assert MAX_CLIPS_PER_JOB == 3
    store, job_id = approved_fixture(tmp_path)
    session = FakeSession()
    renderer = make(store, job_id, session)
    with pytest.raises(WorkflowError, match='생성 영상으로 지정'):
        renderer(0, plate(store), store.root / 'clip.mp4')
    assert session.posts == []
    store2, job2 = approved_fixture(tmp_path / 'four', generated=(0, 1, 2))
    packet = store2.job(job2)['source_packet']
    packet['video']['scenes'].append({'narration': '네 번째', 'caption': '네 번째', 'clip': 'generated'})
    job = store2.save_source(job2, packet)
    store2.review_source(job2, job['source_hash'], 'approved', 'op', {'video': True})
    with pytest.raises(WorkflowError, match='3개'):
        make_runway_clip_renderer(store2, job_id=job2, allow_paid=True, session=FakeSession())


def test_success_polls_downloads_settles_credits_and_reuses(tmp_path, monkeypatch):
    monkeypatch.setenv('RUNWAYML_API_SECRET', 'test-secret')
    store, job_id = approved_fixture(tmp_path)
    session = FakeSession(credits=25)
    renderer = make(store, job_id, session)
    out = store.root / 'out' / 'clip.mp4'
    meta = renderer(1, plate(store), out)
    assert out.read_bytes() == MP4
    assert meta['provider'] == 'runway' and meta['model'] == 'gen4_turbo' and meta['duration'] == 5
    create = session.posts[0]
    assert create['url'] == 'https://api.dev.runwayml.com/v1/image_to_video'
    assert create['headers']['Authorization'] == 'Bearer test-secret' and create['headers']['X-Runway-Version'] == '2024-11-06'
    body = create['json']
    assert body['model'] == 'gen4_turbo' and body['ratio'] == '720:1280' and body['duration'] == 5
    assert body['promptImage'].startswith('data:image/png;base64,')
    assert '카메라가 천천히' in body['promptText'] and len(body['promptText']) <= 1000
    assert any(g['url'] == 'https://api.dev.runwayml.com/v1/tasks/task_123' for g in session.gets)
    # 25 credits x $0.01 x 2000 KRW = 500 KRW, reserved 500 for gen4_turbo 5s.
    budget = store.budget()
    assert budget['reserved_krw'] == 0 and budget['spent_krw'] == 500
    receipts = list((store.root / 'clip-assets').glob('*.json'))
    assert len(receipts) == 1
    receipt = json.loads(receipts[0].read_text(encoding='utf-8'))
    assert receipt['status'] == 'complete' and receipt['task_id'] == 'task_123' and 'test-secret' not in receipts[0].read_text(encoding='utf-8')
    posts_before = len(session.posts)
    again = store.root / 'out' / 'again.mp4'
    assert renderer(1, plate(store), again) == meta
    assert again.read_bytes() == MP4 and len(session.posts) == posts_before and store.budget()['spent_krw'] == 500


def test_gen45_profile_reserves_more_and_rejects_over_job_cap(tmp_path, monkeypatch):
    from office.video_provider import JOB_CAP_KRW
    monkeypatch.setenv('RUNWAYML_API_SECRET', 'test-secret')
    assert JOB_CAP_KRW == 3000
    store, job_id = approved_fixture(tmp_path, generated=(0, 1, 2))
    session = FakeSession(credits=60)
    renderer = make(store, job_id, session, model='gen4.5')
    renderer(0, plate(store), store.root / 'c0.mp4')
    assert store.budget()['spent_krw'] == 1200
    renderer(1, plate(store), store.root / 'c1.mp4')
    assert store.budget()['spent_krw'] == 2400
    with pytest.raises(WorkflowError, match='3,000원'):
        renderer(2, plate(store), store.root / 'c2.mp4')


def test_failed_task_settles_reported_cost_and_raises_without_asset(tmp_path, monkeypatch):
    monkeypatch.setenv('RUNWAYML_API_SECRET', 'test-secret')
    store, job_id = approved_fixture(tmp_path)
    session = FakeSession(statuses=[{'status': 'RUNNING'}, {'status': 'FAILED', 'failure': 'moderation', 'failureCode': 'SAFETY.INPUT.IMAGE', 'cost': {'credits': 0}}])
    with pytest.raises(WorkflowError, match='실패'):
        make(store, job_id, session)(1, plate(store), store.root / 'clip.mp4')
    assert store.budget()['reserved_krw'] == 0 and store.budget()['spent_krw'] == 0
    assert not (store.root / 'clip.mp4').exists()
    receipt = json.loads(next((store.root / 'clip-assets').glob('*.json')).read_text(encoding='utf-8'))
    assert receipt['status'] == 'failed' and receipt['failure_code'] == 'SAFETY.INPUT.IMAGE'


def test_stuck_task_becomes_unknown_with_task_id_and_blocks_resubmit(tmp_path, monkeypatch):
    monkeypatch.setenv('RUNWAYML_API_SECRET', 'test-secret')
    store, job_id = approved_fixture(tmp_path)
    session = FakeSession(statuses=[{'status': 'THROTTLED'}])
    renderer = make(store, job_id, session, max_polls=3)
    with pytest.raises(WorkflowError, match='불명'):
        renderer(1, plate(store), store.root / 'clip.mp4')
    assert store.budget()['reserved_krw'] == 500
    receipt = json.loads(next((store.root / 'clip-assets').glob('*.json')).read_text(encoding='utf-8'))
    assert receipt['status'] == 'unknown' and receipt['task_id'] == 'task_123'
    with pytest.raises(WorkflowError, match='불명'):
        renderer(1, plate(store), store.root / 'clip.mp4')
    assert len(session.posts) == 1


def test_create_http_error_and_network_error_keep_reservation(tmp_path, monkeypatch):
    monkeypatch.setenv('RUNWAYML_API_SECRET', 'test-secret')
    store, job_id = approved_fixture(tmp_path)
    with pytest.raises(WorkflowError, match='429'):
        make(store, job_id, FakeSession(create_status=429))(1, plate(store), store.root / 'clip.mp4')
    assert store.budget()['reserved_krw'] == 500

    class Offline(FakeSession):
        def post(self, url, **kwargs):
            raise requests.ConnectionError('offline')
    store2, job2 = approved_fixture(tmp_path / 'b')
    with pytest.raises(WorkflowError, match='불명'):
        make(store2, job2, Offline())(1, plate(store2), store2.root / 'clip.mp4')
    assert store2.budget()['reserved_krw'] == 500


def test_non_mp4_output_is_kept_for_review_not_delivered(tmp_path, monkeypatch):
    monkeypatch.setenv('RUNWAYML_API_SECRET', 'test-secret')
    store, job_id = approved_fixture(tmp_path)
    with pytest.raises(WorkflowError, match='검토'):
        make(store, job_id, FakeSession(output_bytes=b'<html>expired</html>'))(1, plate(store), store.root / 'clip.mp4')
    assert store.budget()['spent_krw'] == 500
    assert not (store.root / 'clip.mp4').exists()


def test_input_image_and_output_path_must_be_inside_state(tmp_path, monkeypatch):
    monkeypatch.setenv('RUNWAYML_API_SECRET', 'test-secret')
    store, job_id = approved_fixture(tmp_path)
    renderer = make(store, job_id, FakeSession())
    outside = tmp_path / 'outside.png'
    Image.new('RGB', (8, 8)).save(outside, 'PNG')
    with pytest.raises(WorkflowError, match='경로'):
        renderer(1, outside, store.root / 'clip.mp4')
    with pytest.raises(WorkflowError, match='경로'):
        renderer(1, plate(store), tmp_path / 'clip.mp4')
