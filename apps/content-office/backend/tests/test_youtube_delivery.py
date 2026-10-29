"""YouTube private upload adapter: release gate, ledger states, idempotency, reconciliation. No network here."""
import hashlib
import json

import pytest
import requests

from office.store import Store, WorkflowError

MP4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isomiso2mp41" + b"\x01" * 3000


def released_fixture(tmp_path, *, approve_release=True, outputs=('video',), article_id='yt-test'):
    store = Store(tmp_path / 'state')
    job = store.create_job({'id': article_id, 'title': '업로드 시험'})
    packet = {'title': '업로드 시험', 'body': '합성 기능 시험입니다.', 'synthetic_fixture': True,
              'quality': {'status': 'passed', 'critical': []},
              'video': {'title': '승인된 영상 제목', 'description': '승인된 설명', 'tags': ['AI', '자동화'],
                        'scenes': [{'narration': '근거를 확인합니다.', 'caption': '근거'}]}}
    job = store.save_source(job['id'], packet)
    selections = {'blog': True, 'video': True, 'pdf': False, 'cards': False}
    store.review_source(job['id'], job['source_hash'], 'approved', 'op', selections)
    folder = store.artifacts / job['id'] / job['source_hash'] / 'production-fixture'
    folder.mkdir(parents=True)
    (folder / 'short.mp4').write_bytes(MP4)
    (folder / 'description.txt').write_text('승인된 설명\n\n이 영상의 내레이션은 합성 음성입니다.\n', encoding='utf-8')
    (folder / 'blog.md').write_text('# 블로그', encoding='utf-8')

    def record(name, kinds):
        path = folder / name
        return {'name': name, 'path': path.relative_to(store.artifacts).as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size, 'outputs': kinds}
    manifest = {'source_hash': job['source_hash'], 'output_status': {'blog': {'state': 'completed'}, 'video': {'state': 'completed'}},
                'completed_outputs': ['blog', 'video'], 'files': [record('short.mp4', ['video']), record('description.txt', ['video']), record('blog.md', ['blog'])],
                'media': {'duration': 12.0, 'voice_disclosure': '합성 음성'}, 'thumbnail_candidates': [{'id': 'thumb-1', 'name': 'thumb-1.png', 'scores': {}}],
                'production_contract': {'hash': 'c' * 64}, 'hash': 'm' * 64}
    store.save_manifest_if_current(job['id'], job['source_hash'], selections, manifest)
    job = store.select_thumbnail(job['id'], 'thumb-1', 'm' * 64, 'op')
    if approve_release:
        store.review_release(job['id'], job['manifest']['hash'], 'approved', 'op', media_reviewed=True, outputs=list(outputs))
    return store, job['id']


def env(monkeypatch, present=True):
    for key in ('YOUTUBE_CLIENT_ID', 'YOUTUBE_CLIENT_SECRET', 'YOUTUBE_REFRESH_TOKEN'):
        if present:
            monkeypatch.setenv(key, 'test-' + key.lower())
        else:
            monkeypatch.delenv(key, raising=False)


class Response:
    def __init__(self, status, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body, headers or {}

    def json(self):
        if self._body is None:
            raise ValueError('no json')
        return self._body


class FakeYouTube:
    def __init__(self, *, put_status=201, start_status=200, privacy='private', resume_range=None):
        self.put_status, self.start_status, self.privacy, self.resume_range = put_status, start_status, privacy, resume_range
        self.posts, self.puts, self.gets = [], [], []
        self.video = {'id': 'vid_ABC123', 'status': {'uploadStatus': 'uploaded', 'privacyStatus': privacy}}

    def post(self, url, **kwargs):
        self.posts.append({'url': url, **kwargs})
        if url == 'https://oauth2.googleapis.com/token':
            return Response(200, {'access_token': 'ya29.test-access', 'expires_in': 3599, 'token_type': 'Bearer'})
        if self.start_status != 200:
            return Response(self.start_status, {'error': {'message': 'quota'}})
        return Response(200, {}, headers={'Location': 'https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id=UP1'})

    def put(self, url, **kwargs):
        self.puts.append({'url': url, **kwargs})
        if kwargs.get('headers', {}).get('Content-Range', '').startswith('bytes */'):
            if self.resume_range is not None:
                return Response(308, None, headers={'Range': self.resume_range})
            return Response(self.put_status, self.video if self.put_status in (200, 201) else {'error': 'x'})
        return Response(self.put_status, self.video if self.put_status in (200, 201) else {'error': 'x'})

    def get(self, url, **kwargs):
        self.gets.append({'url': url, **kwargs})
        return Response(200, {'items': [{'id': 'vid_ABC123', 'status': {'uploadStatus': 'processed', 'privacyStatus': self.privacy}, 'processingDetails': {'processingStatus': 'succeeded'}}]})


def test_release_approval_for_video_is_required_before_any_request(tmp_path, monkeypatch):
    from office.youtube_delivery import deliver_youtube
    env(monkeypatch)
    store, job_id = released_fixture(tmp_path, approve_release=False)
    session = FakeYouTube()
    with pytest.raises(WorkflowError, match='출고 승인②'):
        deliver_youtube(store, job_id, actor='op', session=session)
    assert session.posts == []
    store2, job2 = released_fixture(tmp_path / 'blog-only', outputs=('blog',))
    with pytest.raises(WorkflowError, match='출고 승인②'):
        deliver_youtube(store2, job2, actor='op', session=session)
    assert session.posts == []


def test_missing_oauth_env_rejects_without_ledger_change(tmp_path, monkeypatch):
    from office.youtube_delivery import deliver_youtube, deliveries
    env(monkeypatch, present=False)
    store, job_id = released_fixture(tmp_path)
    with pytest.raises(WorkflowError, match='YOUTUBE_'):
        deliver_youtube(store, job_id, actor='op', session=FakeYouTube())
    assert deliveries(store, job_id) == []


def test_private_upload_records_external_id_and_is_idempotent(tmp_path, monkeypatch):
    from office.youtube_delivery import deliver_youtube, deliveries
    env(monkeypatch)
    store, job_id = released_fixture(tmp_path)
    session = FakeYouTube()
    record = deliver_youtube(store, job_id, actor='op', session=session)
    assert record['state'] == 'private' and record['external_id'] == 'vid_ABC123' and record['channel'] == 'youtube'
    token_call, start_call = session.posts
    assert token_call['url'] == 'https://oauth2.googleapis.com/token' and token_call['data']['grant_type'] == 'refresh_token'
    assert start_call['url'].startswith('https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable')
    assert start_call['headers']['Authorization'] == 'Bearer ya29.test-access'
    assert start_call['headers']['X-Upload-Content-Length'] == str(len(MP4)) and start_call['headers']['X-Upload-Content-Type'] == 'video/mp4'
    body = start_call['json']
    assert body['status'] == {'privacyStatus': 'private', 'selfDeclaredMadeForKids': False}
    assert body['snippet']['title'] == '승인된 영상 제목' and body['snippet']['tags'] == ['AI', '자동화']
    assert '합성 음성' in body['snippet']['description']
    upload = session.puts[0]
    assert upload['url'].endswith('upload_id=UP1') and upload['data'] == MP4 and upload['headers']['Content-Length'] == str(len(MP4))
    ledger = deliveries(store, job_id)
    assert len(ledger) == 1 and ledger[0]['visibility'] == 'private' and ledger[0]['asset_sha256'] == hashlib.sha256(MP4).hexdigest()
    assert 'ya29' not in json.dumps(ledger) and 'test-youtube' not in json.dumps(ledger)
    kinds = [e['kind'] for e in store.events(job_id)]
    assert 'delivery_private' in kinds
    again = deliver_youtube(store, job_id, actor='op', session=session)
    assert again['external_id'] == 'vid_ABC123' and len(session.puts) == 1 and len(deliveries(store, job_id)) == 1


def test_server_error_during_upload_is_unknown_and_blocks_resend(tmp_path, monkeypatch):
    from office.youtube_delivery import deliver_youtube, deliveries
    env(monkeypatch)
    store, job_id = released_fixture(tmp_path)
    session = FakeYouTube(put_status=503)
    with pytest.raises(WorkflowError, match='불명'):
        deliver_youtube(store, job_id, actor='op', session=session)
    record = deliveries(store, job_id)[0]
    assert record['state'] == 'unknown' and record.get('session_uri', '').endswith('upload_id=UP1')
    with pytest.raises(WorkflowError, match='불명|대사'):
        deliver_youtube(store, job_id, actor='op', session=session)
    assert len(session.puts) == 1


def test_network_failure_at_start_is_unknown_and_quota_error_is_failed(tmp_path, monkeypatch):
    from office.youtube_delivery import deliver_youtube, deliveries
    env(monkeypatch)

    class Offline(FakeYouTube):
        def post(self, url, **kwargs):
            if url == 'https://oauth2.googleapis.com/token':
                return super().post(url, **kwargs)
            raise requests.ConnectionError('offline')
    store, job_id = released_fixture(tmp_path)
    with pytest.raises(WorkflowError, match='불명'):
        deliver_youtube(store, job_id, actor='op', session=Offline())
    assert deliveries(store, job_id)[0]['state'] == 'unknown'
    store2, job2 = released_fixture(tmp_path / 'quota')
    with pytest.raises(WorkflowError, match='403'):
        deliver_youtube(store2, job2, actor='op', session=FakeYouTube(start_status=403))
    record = deliveries(store2, job2)[0]
    assert record['state'] == 'failed'
    retry = deliver_youtube(store2, job2, actor='op', session=FakeYouTube())
    assert retry['state'] == 'private'


def test_reconcile_resumes_incomplete_session_then_confirms_private(tmp_path, monkeypatch):
    from office.youtube_delivery import deliver_youtube, deliveries, reconcile_youtube
    env(monkeypatch)
    store, job_id = released_fixture(tmp_path)
    session = FakeYouTube(put_status=503)
    with pytest.raises(WorkflowError):
        deliver_youtube(store, job_id, actor='op', session=session)
    delivery_id = deliveries(store, job_id)[0]['id']
    resume = FakeYouTube(resume_range='bytes=0-1023')
    record = reconcile_youtube(store, job_id, delivery_id, session=resume)
    status_put, resume_put = resume.puts
    assert status_put['headers']['Content-Range'] == f'bytes */{len(MP4)}' and status_put['headers']['Content-Length'] == '0'
    assert resume_put['headers']['Content-Range'] == f'bytes 1024-{len(MP4) - 1}/{len(MP4)}' and resume_put['data'] == MP4[1024:]
    assert record['state'] == 'private' and record['external_id'] == 'vid_ABC123'
    confirmed = reconcile_youtube(store, job_id, delivery_id, session=resume)
    assert confirmed['upload_status'] == 'processed' and confirmed['processing_status'] == 'succeeded'
    assert resume.gets[0]['params']['id'] == 'vid_ABC123'


def test_unexpected_public_visibility_is_flagged_for_review(tmp_path, monkeypatch):
    from office.youtube_delivery import deliver_youtube, deliveries
    env(monkeypatch)
    store, job_id = released_fixture(tmp_path)
    with pytest.raises(WorkflowError, match='공개 범위'):
        deliver_youtube(store, job_id, actor='op', session=FakeYouTube(privacy='public'))
    record = deliveries(store, job_id)[0]
    assert record['state'] == 'needs_review' and record['external_id'] == 'vid_ABC123'
    assert 'delivery_visibility_mismatch' in [e['kind'] for e in store.events(job_id)]


def test_changed_asset_after_release_is_rejected(tmp_path, monkeypatch):
    from office.youtube_delivery import deliver_youtube
    env(monkeypatch)
    store, job_id = released_fixture(tmp_path)
    job = store.job(job_id)
    path = store.artifacts / next(f['path'] for f in job['manifest']['files'] if f['name'] == 'short.mp4')
    path.write_bytes(MP4 + b'tampered')
    session = FakeYouTube()
    with pytest.raises(WorkflowError, match='변경|검증'):
        deliver_youtube(store, job_id, actor='op', session=session)
    assert session.puts == []


def test_channel_key_selects_credentials_and_is_part_of_idempotency(tmp_path, monkeypatch):
    from office.youtube_delivery import deliver_youtube, deliveries
    env(monkeypatch)
    monkeypatch.setenv('YOUTUBE_ENGLISH_REFRESH_TOKEN', 'en-token')
    store, job_id = released_fixture(tmp_path)
    session = FakeYouTube()
    with pytest.raises(WorkflowError, match='언어'):
        deliver_youtube(store, job_id, actor='op', session=session, channel_key='youtube_english')
    assert session.puts == []
    from office.briefs import build_brief
    store.set_brief(job_id, build_brief('productivity-automation', {'language': 'en'}), 'op')
    # The brief now says English, so the Korean channel is a mismatch too: blocked before any request.
    with pytest.raises(WorkflowError, match='언어'):
        deliver_youtube(store, job_id, actor='op', session=session, channel_key='youtube_main_ko')
    assert session.puts == []
    en = deliver_youtube(store, job_id, actor='op', session=session, channel_key='youtube_english')
    assert en['channel_key'] == 'youtube_english' and en['locale'] == 'en' and en['state'] == 'private'
    assert session.posts[0]['data']['refresh_token'] == 'en-token' and len(session.puts) == 1
    assert en['idempotency_key'] == hashlib.sha256(json.dumps({'asset_sha256': hashlib.sha256(MP4).hexdigest(), 'channel': 'youtube', 'channel_key': 'youtube_english', 'job_id': job_id, 'manifest_hash': store.job(job_id)['manifest']['hash']}, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    assert [r['channel_key'] for r in deliveries(store, job_id)] == ['youtube_english']


def test_language_mismatch_blocks_before_request_and_english_channel_uses_its_token(tmp_path, monkeypatch):
    from office.youtube_delivery import deliver_youtube, deliveries
    from office.briefs import build_brief
    env(monkeypatch)
    monkeypatch.setenv('YOUTUBE_ENGLISH_REFRESH_TOKEN', 'en-token')
    store, job_id = released_fixture(tmp_path)
    store.set_brief(job_id, build_brief('productivity-automation', {'language': 'en'}), 'op')
    session = FakeYouTube()
    with pytest.raises(WorkflowError, match='언어'):
        deliver_youtube(store, job_id, actor='op', session=session, channel_key='youtube_main_ko')
    assert session.posts == []
    record = deliver_youtube(store, job_id, actor='op', session=session, channel_key='youtube_english')
    assert record['channel_key'] == 'youtube_english' and record['locale'] == 'en' and record['state'] == 'private'
    assert session.posts[0]['data']['refresh_token'] == 'en-token'
    again = deliver_youtube(store, job_id, actor='op', session=session, channel_key='youtube_english')
    assert again['id'] == record['id'] and len(session.puts) == 1
    assert len(deliveries(store, job_id)) == 1


def test_unknown_channel_or_missing_channel_token_is_rejected(tmp_path, monkeypatch):
    from office.youtube_delivery import deliver_youtube
    env(monkeypatch)
    monkeypatch.delenv('YOUTUBE_ENGLISH_REFRESH_TOKEN', raising=False)
    store, job_id = released_fixture(tmp_path)
    with pytest.raises(WorkflowError, match='채널'):
        deliver_youtube(store, job_id, actor='op', session=FakeYouTube(), channel_key='tistory_main')
    from office.briefs import build_brief
    store.set_brief(job_id, build_brief('productivity-automation', {'language': 'en'}), 'op')
    with pytest.raises(WorkflowError, match='YOUTUBE_ENGLISH_REFRESH_TOKEN'):
        deliver_youtube(store, job_id, actor='op', session=FakeYouTube(), channel_key='youtube_english')


def test_response_channel_id_mismatch_marks_needs_review(tmp_path, monkeypatch):
    from office.youtube_delivery import deliver_youtube
    from office.channels import update_channel
    env(monkeypatch)
    store, job_id = released_fixture(tmp_path)
    update_channel(store, 'youtube_main_ko', {'external_account_id': 'UCexpected00000000000000'}, actor='op')
    session = FakeYouTube()
    session.video['snippet'] = {'channelId': 'UCother000000000000000000'}
    with pytest.raises(WorkflowError, match='채널'):
        deliver_youtube(store, job_id, actor='op', session=session)
    from office.youtube_delivery import deliveries
    record = deliveries(store, job_id)[0]
    assert record['state'] == 'needs_review' and record['reason'] == 'channel_mismatch'
    assert 'delivery_channel_mismatch' in [e['kind'] for e in store.events(job_id)]
    good = FakeYouTube()
    good.video['snippet'] = {'channelId': 'UCexpected00000000000000'}
    store2, job2 = released_fixture(tmp_path / 'ok')
    update_channel(store2, 'youtube_main_ko', {'external_account_id': 'UCexpected00000000000000'}, actor='op')
    assert deliver_youtube(store2, job2, actor='op', session=good)['state'] == 'private'


def test_concurrent_same_video_starts_only_one_upload(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from office import youtube_delivery as delivery

    env(monkeypatch)
    store, job_id = released_fixture(tmp_path)
    ready = Barrier(2, timeout=10)
    original_metadata = delivery.video_metadata

    def metadata(*args):
        result = original_metadata(*args)
        ready.wait()  # 두 요청 모두 같은 최신 파일을 검증한 뒤 동시에 예약하도록 한다.
        return result

    monkeypatch.setattr(delivery, 'video_metadata', metadata)
    sessions = [FakeYouTube(), FakeYouTube()]
    for index, session in enumerate(sessions):
        session.video['id'] = f'vid_concurrent_{index}'

    def run(session):
        try:
            return delivery.deliver_youtube(store, job_id, actor='op', session=session)
        except WorkflowError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(run, sessions))

    starts = [call for session in sessions for call in session.posts if call['url'] == delivery.UPLOAD_URL]
    uploads = [call for session in sessions for call in session.puts]
    assert len(starts) == 1 and len(uploads) == 1
    completed = [result for result in results if isinstance(result, dict)]
    assert completed and all(result['state'] == 'private' for result in completed)
    records = delivery.deliveries(store, job_id)
    assert len(records) == 1 and records[0]['external_id'] == completed[0]['external_id']


def test_concurrent_distinct_deliveries_preserve_both_external_ids(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, local
    from office import youtube_delivery as delivery

    env(monkeypatch)
    store, first_job = released_fixture(tmp_path, article_id='first')
    _, second_job = released_fixture(tmp_path, article_id='second')
    ready, snapshots = Barrier(2, timeout=10), Barrier(2, timeout=10)
    state = local()
    original_setting, original_save = Store.setting, delivery._save

    def setting(self, key, default=None):
        result = original_setting(self, key, default)
        if key == delivery.LEDGER_KEY and getattr(state, 'finalizing', False):
            snapshots.wait()  # 기존 read-modify-write에서 두 요청이 같은 스냅샷을 읽도록 한다.
        return result

    def save(store, record, **kwargs):
        if record['state'] != 'private':
            return original_save(store, record, **kwargs)
        ready.wait()
        state.finalizing = True
        try:
            return original_save(store, record, **kwargs)
        finally:
            state.finalizing = False

    monkeypatch.setattr(Store, 'setting', setting)
    monkeypatch.setattr(delivery, '_save', save)
    sessions = [FakeYouTube(), FakeYouTube()]
    for index, session in enumerate(sessions):
        session.video['id'] = f'vid_distinct_{index}'

    def run(item):
        job_id, session = item
        return delivery.deliver_youtube(store, job_id, actor='op', session=session)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(run, zip((first_job, second_job), sessions)))

    assert {result['external_id'] for result in results} == {'vid_distinct_0', 'vid_distinct_1'}
    records = delivery.deliveries(store)
    assert {record.get('external_id') for record in records} == {'vid_distinct_0', 'vid_distinct_1'}
    assert len(records) == 2 and all(record['state'] == 'private' for record in records)


def test_active_upload_blocks_reconcile_but_not_other_delivery_or_database(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from office import youtube_delivery as delivery

    env(monkeypatch)
    store, job_id = released_fixture(tmp_path, article_id='first')
    _, other_job = released_fixture(tmp_path, article_id='second')
    started, complete = Event(), Event()

    class PendingUpload(FakeYouTube):
        def put(self, url, **kwargs):
            started.set()
            assert complete.wait(10)
            return super().put(url, **kwargs)

    session, observer = PendingUpload(), FakeYouTube()
    with ThreadPoolExecutor(max_workers=3) as executor:
        active = executor.submit(delivery.deliver_youtube, store, job_id, actor='op', session=session)
        try:
            assert started.wait(10)
            record = delivery.deliveries(store, job_id)[0]
            assert record['state'] == 'accepted'
            with pytest.raises(WorkflowError, match='진행 중'):
                delivery.reconcile_youtube(store, job_id, record['id'], session=observer)
            assert observer.posts == [] and observer.puts == [] and observer.gets == []
            executor.submit(store.set_setting, 'concurrent-write-test', True).result(timeout=5)
            other = executor.submit(delivery.deliver_youtube, store, other_job, actor='op', session=FakeYouTube()).result(timeout=5)
            assert other['state'] == 'private'
        finally:
            complete.set()
        assert active.result(timeout=5)['state'] == 'private'
    assert store.setting('concurrent-write-test') is True
    assert len(delivery.deliveries(store)) == 2


def test_only_one_reconcile_can_resume_an_unknown_session(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from office import youtube_delivery as delivery

    env(monkeypatch)
    store, job_id = released_fixture(tmp_path)
    with pytest.raises(WorkflowError, match='불명'):
        delivery.deliver_youtube(store, job_id, actor='op', session=FakeYouTube(put_status=503))
    record = delivery.deliveries(store, job_id)[0]
    started, complete = Event(), Event()

    class PendingReconcile(FakeYouTube):
        def put(self, url, **kwargs):
            if kwargs.get('headers', {}).get('Content-Range', '').startswith('bytes */'):
                started.set()
                assert complete.wait(10)
            return super().put(url, **kwargs)

    session, duplicate = PendingReconcile(resume_range='bytes=0-1023'), FakeYouTube()
    with ThreadPoolExecutor(max_workers=1) as executor:
        active = executor.submit(delivery.reconcile_youtube, store, job_id, record['id'], session=session)
        try:
            assert started.wait(10)
            with pytest.raises(WorkflowError, match='진행 중'):
                delivery.reconcile_youtube(store, job_id, record['id'], session=duplicate)
            assert duplicate.posts == [] and duplicate.puts == []
        finally:
            complete.set()
        assert active.result(timeout=5)['state'] == 'private'
    assert len(session.puts) == 2


def test_oauth_failure_releases_reservation_for_explicit_retry(tmp_path, monkeypatch):
    from office import youtube_delivery as delivery

    env(monkeypatch)
    store, job_id = released_fixture(tmp_path)

    class InvalidToken(FakeYouTube):
        def post(self, url, **kwargs):
            self.posts.append({'url': url, **kwargs})
            return Response(401, {'error': 'invalid_grant'})

    session = InvalidToken()
    with pytest.raises(WorkflowError, match='인증'):
        delivery.deliver_youtube(store, job_id, actor='op', session=session)
    record = delivery.deliveries(store, job_id)[0]
    assert record['state'] == 'failed' and record['reason'] == 'oauth_before_upload_failed'
    assert len(session.posts) == 1 and session.posts[0]['url'] == delivery.TOKEN_URL and session.puts == []
    assert delivery.deliver_youtube(store, job_id, actor='op', session=FakeYouTube())['state'] == 'private'
    assert len(delivery.deliveries(store, job_id)) == 1


@pytest.mark.parametrize('change', ['reject', 'outputs', 'manifest'])
def test_release_change_during_oauth_stops_before_upload_and_allows_explicit_retry(tmp_path, monkeypatch, change):
    from office import youtube_delivery as delivery
    from office.store import digest

    env(monkeypatch)
    store, job_id = released_fixture(tmp_path)

    class ChangedRelease(FakeYouTube):
        def post(self, url, **kwargs):
            if url == delivery.TOKEN_URL:
                job = store.job(job_id)
                if change == 'manifest':
                    manifest = {**job['manifest'], 'test_revision': 'new-auth-time-version'}
                    manifest['hash'] = digest({key: value for key, value in manifest.items() if key != 'hash'})
                    store.save_manifest_if_current(job_id, job['source_hash'], job['selections'], manifest)
                    store.review_release(job_id, manifest['hash'], 'approved', 'reviewer', media_reviewed=True, outputs=['video'])
                else:
                    store.review_release(job_id, job['manifest']['hash'], 'rejected' if change == 'reject' else 'approved', 'reviewer', outputs=['video'] if change == 'reject' else ['blog'])
            return super().post(url, **kwargs)

    session = ChangedRelease()
    with pytest.raises(WorkflowError, match='출고'):
        delivery.deliver_youtube(store, job_id, actor='op', session=session)
    assert len(session.posts) == 1 and session.posts[0]['url'] == delivery.TOKEN_URL
    assert session.puts == []
    record = delivery.deliveries(store, job_id)[0]
    assert record['state'] == 'failed' and record['reason'] == 'release_changed_before_upload'
    assert not record.get('session_uri') and not record.get('external_id')
    current = store.job(job_id)
    store.review_release(job_id, current['manifest']['hash'], 'approved', 'reviewer', media_reviewed=True, outputs=['video'])
    retry = FakeYouTube()
    assert delivery.deliver_youtube(store, job_id, actor='op', session=retry)['state'] == 'private'
    assert len([call for call in retry.posts if call['url'] == delivery.UPLOAD_URL]) == 1 and len(retry.puts) == 1


def test_process_exit_releases_delivery_lock_and_created_requires_reconciliation(tmp_path, monkeypatch):
    import subprocess
    import sys
    from office import youtube_delivery as delivery

    env(monkeypatch)
    store, job_id = released_fixture(tmp_path)
    record = delivery.deliver_youtube(store, job_id, actor='op', session=FakeYouTube())
    record.update(state='created', external_id=None)
    record.pop('session_uri', None)
    delivery._save(store, record)
    # __exit__ 없이 종료한 프로세스가 잡고 있던 OS lock도 해제되는지 확인한다.
    child = subprocess.run([sys.executable, '-c',
        'import os,sys\nfrom office.store import Store\nfrom office.youtube_delivery import _delivery_lock\n'
        'with _delivery_lock(Store(sys.argv[1]), sys.argv[2]):\n    os._exit(0)\n',
        str(store.root), record['key']], capture_output=True, timeout=15)
    assert child.returncode == 0, child.stderr.decode(errors='replace')
    session = FakeYouTube()
    with pytest.raises(WorkflowError, match='대사'):
        delivery.deliver_youtube(store, job_id, actor='op', session=session)
    with pytest.raises(WorkflowError, match='YouTube Studio'):
        delivery.reconcile_youtube(store, job_id, record['id'], session=session)
    current = delivery.deliveries(store, job_id)[0]
    assert current['state'] == 'unknown' and current['reason'] == 'interrupted_before_session_saved'
    with pytest.raises(WorkflowError, match='대사'):
        delivery.deliver_youtube(store, job_id, actor='op', session=session)
    assert session.posts == [] and session.puts == []


def test_failed_reconcile_releases_lock_and_keeps_unknown_until_explicit_retry(tmp_path, monkeypatch):
    from office import youtube_delivery as delivery

    env(monkeypatch)
    store, job_id = released_fixture(tmp_path)
    with pytest.raises(WorkflowError, match='불명'):
        delivery.deliver_youtube(store, job_id, actor='op', session=FakeYouTube(put_status=503))
    record = delivery.deliveries(store, job_id)[0]

    class Offline(FakeYouTube):
        def put(self, url, **kwargs):
            raise requests.ConnectionError('offline')

    with pytest.raises(WorkflowError, match='불명'):
        delivery.reconcile_youtube(store, job_id, record['id'], session=Offline())
    current = delivery.deliveries(store, job_id)[0]
    assert current['state'] == 'unknown' and current['session_uri'] == record['session_uri']
    duplicate = FakeYouTube()
    with pytest.raises(WorkflowError, match='대사'):
        delivery.deliver_youtube(store, job_id, actor='op', session=duplicate)
    assert duplicate.posts == [] and duplicate.puts == []
    assert delivery.reconcile_youtube(store, job_id, record['id'], session=FakeYouTube())['state'] == 'private'
