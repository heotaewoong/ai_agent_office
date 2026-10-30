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

    def __init__(self, statuses=None, credits=25, output_bytes=MP4, create_status=200, balance=10_000, organization_status=200):
        self.statuses = list(statuses or [{'status': 'PENDING'}, {'status': 'RUNNING', 'progress': 0.5},
                                          {'status': 'SUCCEEDED', 'output': ['https://cdn.example/out.mp4'], 'cost': {'credits': credits}}])
        self.output_bytes, self.create_status = output_bytes, create_status
        self.balance, self.organization_status = balance, organization_status
        self.posts, self.gets = [], []

    def post(self, url, **kwargs):
        self.posts.append({'url': url, **kwargs})
        if self.create_status != 200:
            return Response(self.create_status, {'error': 'nope'})
        return Response(200, {'id': 'task_123'})

    def get(self, url, **kwargs):
        self.gets.append({'url': url, **kwargs})
        if url == 'https://api.dev.runwayml.com/v1/organization':
            if self.organization_status != 200:
                return Response(self.organization_status, {'error': 'nope'})
            return Response(200, {'creditBalance': self.balance, 'tier': {}, 'usage': {}})
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


def test_every_scene_by_default_marked_scenes_first_and_operator_may_lower(tmp_path, monkeypatch):
    from office.video_provider import make_runway_clip_renderer, MAX_CLIPS_PER_JOB
    monkeypatch.setenv('RUNWAYML_API_SECRET', 'test-secret')
    assert MAX_CLIPS_PER_JOB == 12
    store, job_id = approved_fixture(tmp_path)
    # Default: every scene is a generated clip, so no scene is left as a near-frozen still.
    assert make(store, job_id, FakeSession()).generated_scenes == [0, 1, 2]
    unmarked, unmarked_job = approved_fixture(tmp_path / 'unmarked', generated=())
    assert make(unmarked, unmarked_job, FakeSession()).generated_scenes == [0, 1, 2]
    # A lower operator limit keeps the marked scene first, else the hook.
    store.set_setting('clip_limits', {'max_clips_per_video': 1, 'daily_paid_clips': 3})
    session = FakeSession()
    renderer = make(store, job_id, session)
    assert renderer.generated_scenes == [1]
    with pytest.raises(WorkflowError, match='생성 영상으로 지정'):
        renderer(0, plate(store), store.root / 'clip.mp4')
    assert session.posts == []
    unmarked.set_setting('clip_limits', {'max_clips_per_video': 1, 'daily_paid_clips': 3})
    assert make(unmarked, unmarked_job, FakeSession()).generated_scenes == [0]
    store.set_setting('clip_limits', {'max_clips_per_video': 2, 'daily_paid_clips': 3})
    assert make_runway_clip_renderer(store, job_id=job_id, allow_paid=True, session=FakeSession()).generated_scenes == [0, 1]
    store.set_setting('clip_limits', {'max_clips_per_video': 99})
    assert make_runway_clip_renderer(store, job_id=job_id, allow_paid=True, session=FakeSession()).generated_scenes == [0, 1, 2]


def test_grok_clip_length_follows_the_scene_voice_so_it_never_loops(tmp_path, monkeypatch):
    from office.video_provider import clip_seconds
    monkeypatch.setenv('RUNWAYML_API_SECRET', 'test-secret')
    assert clip_seconds('grok_imagine_1_5_lite', 7.88) == 8 and clip_seconds('grok_imagine_1_5_lite', 9.72) == 10
    assert clip_seconds('grok_imagine_1_5_lite', 0.4) == 1 and clip_seconds('grok_imagine_1_5_lite', 40) == 15
    assert clip_seconds('grok_imagine_1_5_lite', None) == 5 and clip_seconds('gen4_turbo', 7.88) == 5
    store, job_id = approved_fixture(tmp_path)
    session = FakeSession(credits=25)
    renderer = make(store, job_id, session, model='grok_imagine_1_5_lite')
    assert renderer.accepts_seconds is True
    meta = renderer(1, plate(store), store.root / 'clip.mp4', seconds=7.88)
    assert session.posts[0]['json']['duration'] == 8 and meta['duration'] == 8
    # 8s x 3 credits + 1 start frame = 25 credits = 500 KRW reserved and settled without overrun.
    assert store.budget()['spent_krw'] == 500 and store.budget()['reserved_krw'] == 0


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
    assert JOB_CAP_KRW == 5000
    store, job_id = approved_fixture(tmp_path, generated=(0, 1, 2))
    packet = store.job(job_id)['source_packet']
    packet['video']['scenes'] += [{'narration': f'{n}번째 장면입니다.', 'caption': f'{n}번째'} for n in (4, 5)]
    job = store.save_source(job_id, packet)
    store.review_source(job_id, job['source_hash'], 'approved', 'op', {'video': True})
    store.set_setting('clip_limits', {'max_clips_per_video': 5, 'daily_paid_clips': 15})
    session = FakeSession(credits=60)
    renderer = make(store, job_id, session, model='gen4.5')
    for index in range(4):
        renderer(index, plate(store, f'p{index}.png'), store.root / f'c{index}.mp4')
    assert store.budget()['spent_krw'] == 4800
    with pytest.raises(WorkflowError, match='5,000원'):
        renderer(4, plate(store, 'p4.png'), store.root / 'c4.mp4')


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


def test_grok_lite_is_the_cheapest_profile_with_auto_ratio_and_start_frame_credit(tmp_path, monkeypatch):
    from office.video_provider import credits_per_clip
    monkeypatch.setenv('RUNWAYML_API_SECRET', 'test-secret')
    assert credits_per_clip('grok_imagine_1_5_lite') == 16 < credits_per_clip('gen4_turbo') == 25 < credits_per_clip('gen4.5') == 60
    store, job_id = approved_fixture(tmp_path)
    session = FakeSession(credits=16)
    renderer = make(store, job_id, session, model='grok_imagine_1_5_lite')
    assert renderer.clip_provider.config['reservation_krw'] == 320
    renderer(1, plate(store), store.root / 'clip.mp4')
    body = session.posts[0]['json']
    assert body['model'] == 'grok_imagine_1_5_lite' and body['ratio'] == 'auto_720p' and body['duration'] == 5
    assert body['promptImage'].startswith('data:image/png;base64,') and 'photograph' in body['promptText']
    assert store.budget()['spent_krw'] == 320


def test_credit_preflight_refuses_before_any_paid_call(tmp_path, monkeypatch):
    monkeypatch.setenv('RUNWAYML_API_SECRET', 'test-secret')
    store, job_id = approved_fixture(tmp_path)
    poor = FakeSession(balance=10)
    with pytest.raises(WorkflowError, match=r'Runway 크레딧이 부족합니다\(잔액 10, 필요 50\)'):
        make(store, job_id, poor)(1, plate(store), store.root / 'clip.mp4')
    assert poor.posts == [] and store.budget()['reserved_krw'] == 0
    assert poor.gets[0]['headers']['Authorization'] == 'Bearer test-secret' and poor.gets[0]['headers']['X-Runway-Version'] == '2024-11-06'
    broken = FakeSession(organization_status=500)
    with pytest.raises(WorkflowError, match='잔액을 확인하지 못해'):
        make(store, job_id, broken)(1, plate(store), store.root / 'clip.mp4')
    assert broken.posts == [] and store.budget()['reserved_krw'] == 0
    assert [e['data']['ok'] for e in store.events(job_id) if e['kind'] == 'clip_credit_preflight'] == [False, False]


def test_daily_paid_clip_cap_counts_all_jobs_in_kst_day(tmp_path, monkeypatch):
    from office import video_provider
    monkeypatch.setenv('RUNWAYML_API_SECRET', 'test-secret')
    store, job_id = approved_fixture(tmp_path, generated=(0, 1, 2))
    store.set_setting('clip_limits', {'max_clips_per_video': 3, 'daily_paid_clips': 1})
    session = FakeSession(credits=25)
    renderer = make(store, job_id, session)
    renderer(0, plate(store), store.root / 'c0.mp4')
    assert video_provider.paid_clips_today(store) == 1
    with pytest.raises(WorkflowError, match='오늘.*1개'):
        renderer(1, plate(store, 'other.png'), store.root / 'c1.mp4')
    assert len(session.posts) == 1
    # Reservations from another KST day do not count.
    import datetime as dt
    monkeypatch.setattr(video_provider, 'kst_today', lambda: dt.date(2000, 1, 1))
    assert video_provider.paid_clips_today(store) == 0


def test_reproduction_with_unchanged_scene_inputs_makes_zero_new_runway_calls(tmp_path, monkeypatch):
    monkeypatch.setenv('RUNWAYML_API_SECRET', 'test-secret')
    store, job_id = approved_fixture(tmp_path)
    session = FakeSession(credits=25)
    first = make(store, job_id, session)(1, plate(store), store.root / 'a.mp4')
    calls = (len(session.posts), len(session.gets))
    # The operator edits the body (not this scene) and re-approves: a new source version, same scene inputs.
    packet = store.job(job_id)['source_packet']
    packet['body'] = packet['body'] + ' 본문만 고쳤습니다.'
    job = store.save_source(job_id, packet)
    store.review_source(job_id, job['source_hash'], 'approved', 'op', {'video': True})
    again = make(store, job_id, session)(1, plate(store), store.root / 'b.mp4')
    assert again == first and (len(session.posts), len(session.gets)) == calls
    assert store.budget()['spent_krw'] == 500
