"""OpenAI background image provider: budget, receipts, caching. No network request is made here."""
import base64
import io
import json

import pytest
import requests
from PIL import Image

from office.store import Store, WorkflowError


SCENES = [{'narration': '근거를 확인합니다.', 'caption': '근거를 먼저 확인', 'visual': '설명: 공식 문서와 발표'},
          {'narration': '원고를 승인합니다.', 'caption': '원고 승인①', 'visual': '흐름: 초안 → 검토 → 승인'},
          {'narration': '선택한 결과를 제작합니다.', 'caption': '출력별 제작', 'visual': '비교: 블로그 vs 영상'}]


def approved_fixture(tmp_path, *, approve=True):
    store = Store(tmp_path / 'state')
    job = store.create_job({'id': 'image-test', 'title': '배경 이미지 시험'})
    packet = {'title': '배경 이미지 시험', 'body': '합성 기능 시험입니다.', 'synthetic_fixture': True,
              'quality': {'status': 'passed', 'critical': []}, 'video': {'scenes': SCENES}}
    job = store.save_source(job['id'], packet)
    if approve:
        store.review_source(job['id'], job['source_hash'], 'approved', '합성 기능 시험 승인', {'video': True, 'cards': True})
    return store, job['id']


def png_bytes(size=(64, 96), color='#336699'):
    out = io.BytesIO()
    Image.new('RGB', size, color).save(out, 'PNG')
    return out.getvalue()


class ImageResponse:
    status_code = 200

    def __init__(self, *, usage=True, output_tokens=1600, png=None):
        self._usage, self._output, self._png = usage, output_tokens, png or png_bytes()

    def json(self):
        data = {'created': 1761600000, 'data': [{'b64_json': base64.b64encode(self._png).decode()}],
                'output_format': 'png', 'quality': 'medium', 'size': '1024x1536'}
        if self._usage:
            data['usage'] = {'input_tokens': 120, 'output_tokens': self._output, 'total_tokens': 120 + self._output,
                             'input_tokens_details': {'text_tokens': 120, 'image_tokens': 0}}
        return data


class HttpError:
    status_code = 429

    def json(self):
        return {'error': {'message': 'rate limited'}}


def recording_transport(response):
    calls = []

    def transport(url, **kwargs):
        calls.append({'url': url, **kwargs})
        return response
    transport.calls = calls
    return transport


def test_unapproved_source_is_rejected_before_any_cost(tmp_path, monkeypatch):
    from office.image_provider import make_openai_background_renderer
    monkeypatch.setenv('OPENAI_API_KEY', 'test-placeholder')
    store, job_id = approved_fixture(tmp_path, approve=False)
    with pytest.raises(WorkflowError, match='승인'):
        make_openai_background_renderer(store, job_id=job_id, allow_paid=True, transport=recording_transport(ImageResponse()))
    assert store.budget()['reserved_krw'] == store.budget()['spent_krw'] == 0


def test_missing_key_rejects_without_reservation_or_asset(tmp_path, monkeypatch):
    from office.image_provider import make_openai_background_renderer
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    store, job_id = approved_fixture(tmp_path)
    transport = recording_transport(ImageResponse())
    renderer = make_openai_background_renderer(store, job_id=job_id, allow_paid=True, transport=transport)
    with pytest.raises(WorkflowError, match='OPENAI_API_KEY'):
        renderer(0, store.root / 'bg.png')
    assert transport.calls == []
    assert store.budget()['reserved_krw'] == 0
    assert not (store.root / 'bg.png').exists()


def test_paid_not_allowed_rejects(tmp_path, monkeypatch):
    from office.image_provider import make_openai_background_renderer
    monkeypatch.setenv('OPENAI_API_KEY', 'test-placeholder')
    store, job_id = approved_fixture(tmp_path)
    renderer = make_openai_background_renderer(store, job_id=job_id, allow_paid=False, transport=recording_transport(ImageResponse()))
    with pytest.raises(WorkflowError, match='명시|유료'):
        renderer(0, store.root / 'bg.png')
    assert store.budget()['reserved_krw'] == 0


def test_success_saves_png_receipt_settles_usage_and_reuses_without_new_call(tmp_path, monkeypatch):
    from office.image_provider import make_openai_background_renderer
    monkeypatch.setenv('OPENAI_API_KEY', 'test-placeholder')
    store, job_id = approved_fixture(tmp_path)
    transport = recording_transport(ImageResponse(output_tokens=1600))
    renderer = make_openai_background_renderer(store, job_id=job_id, allow_paid=True, transport=transport)
    target = store.root / 'out' / 'bg.png'
    meta = renderer(1, target)
    assert target.is_file() and Image.open(target).size == (64, 96)
    assert meta['provider'] == 'openai' and meta['model'].startswith('gpt-image-2.5')
    assert len(transport.calls) == 1
    sent = transport.calls[0]
    assert sent['url'] == 'https://api.openai.com/v1/images/generations'
    assert sent['headers']['Authorization'] == 'Bearer test-placeholder'
    body = sent['json']
    assert body['model'].startswith('gpt-image-2.5') and body['size'] == '1024x1536' and body['n'] == 1
    assert '원고 승인①' in body['prompt'] and '초안' in body['prompt']
    assert '글자' in body['prompt'] or 'text' in body['prompt'].lower()
    budget = store.budget()
    # 120 text tokens x $5/M + 1600 image tokens x $30/M = $0.0486 -> x2000 = 97.2 -> 98 KRW
    assert budget['reserved_krw'] == 0 and budget['spent_krw'] == 98
    receipts = list((store.root / 'image-assets').glob('*.json'))
    assert len(receipts) == 1
    receipt = json.loads(receipts[0].read_text(encoding='utf-8'))
    assert receipt['status'] == 'complete' and receipt['usage']['output_tokens'] == 1600
    assert 'test-placeholder' not in receipts[0].read_text(encoding='utf-8')
    again = store.root / 'out' / 'again.png'
    assert renderer(1, again) == meta
    assert again.read_bytes() == target.read_bytes()
    assert len(transport.calls) == 1 and store.budget()['spent_krw'] == 98


def test_http_error_keeps_reservation_unknown_and_blocks_retry(tmp_path, monkeypatch):
    from office.image_provider import make_openai_background_renderer
    monkeypatch.setenv('OPENAI_API_KEY', 'test-placeholder')
    store, job_id = approved_fixture(tmp_path)
    renderer = make_openai_background_renderer(store, job_id=job_id, allow_paid=True, transport=recording_transport(HttpError()))
    with pytest.raises(WorkflowError, match='429'):
        renderer(0, store.root / 'bg.png')
    assert store.budget()['reserved_krw'] == 200 and store.budget()['spent_krw'] == 0
    assert not (store.root / 'bg.png').exists()
    with pytest.raises(WorkflowError, match='불명|진행'):
        renderer(0, store.root / 'bg.png')


def test_network_failure_is_unknown_not_retried(tmp_path, monkeypatch):
    from office.image_provider import make_openai_background_renderer
    monkeypatch.setenv('OPENAI_API_KEY', 'test-placeholder')
    store, job_id = approved_fixture(tmp_path)

    def transport(url, **kwargs):
        raise requests.ConnectionError('offline')
    renderer = make_openai_background_renderer(store, job_id=job_id, allow_paid=True, transport=transport)
    with pytest.raises(WorkflowError, match='불명'):
        renderer(0, store.root / 'bg.png')
    assert store.budget()['reserved_krw'] == 200
    events = [e['kind'] for e in store.events(limit=20)]
    assert 'cost_unknown' in events


def test_missing_usage_keeps_asset_but_marks_unknown(tmp_path, monkeypatch):
    from office.image_provider import make_openai_background_renderer
    monkeypatch.setenv('OPENAI_API_KEY', 'test-placeholder')
    store, job_id = approved_fixture(tmp_path)
    renderer = make_openai_background_renderer(store, job_id=job_id, allow_paid=True, transport=recording_transport(ImageResponse(usage=False)))
    with pytest.raises(WorkflowError, match='사용량'):
        renderer(0, store.root / 'bg.png')
    assert store.budget()['reserved_krw'] == 200
    assets = list((store.root / 'image-assets').glob('*.png'))
    assert len(assets) == 1
    assert not (store.root / 'bg.png').exists()


def test_usage_over_reservation_is_recorded_and_blocks_further_calls(tmp_path, monkeypatch):
    from office.image_provider import make_openai_background_renderer
    monkeypatch.setenv('OPENAI_API_KEY', 'test-placeholder')
    store, job_id = approved_fixture(tmp_path)
    renderer = make_openai_background_renderer(store, job_id=job_id, allow_paid=True, transport=recording_transport(ImageResponse(output_tokens=9000)))
    with pytest.raises(WorkflowError, match='초과'):
        renderer(0, store.root / 'bg.png')
    assert store.budget()['spent_krw'] > 200
    with pytest.raises(WorkflowError, match='초과'):
        renderer(1, store.root / 'bg2.png')


def test_job_subcap_blocks_before_total_budget(tmp_path, monkeypatch):
    from office.image_provider import make_openai_background_renderer, JOB_CAP_KRW
    monkeypatch.setenv('OPENAI_API_KEY', 'test-placeholder')
    store, job_id = approved_fixture(tmp_path)
    assert JOB_CAP_KRW == 2000
    for index in range(10):
        store.reserve_cost('image', 200, {'job_id': job_id, 'request_kind': 'image', 'cache_key': f'other-{index}'})
    renderer = make_openai_background_renderer(store, job_id=job_id, allow_paid=True, transport=recording_transport(ImageResponse()))
    with pytest.raises(WorkflowError, match='2,000원'):
        renderer(0, store.root / 'bg.png')


def test_scene_index_outside_approved_scenes_is_rejected(tmp_path, monkeypatch):
    from office.image_provider import make_openai_background_renderer
    monkeypatch.setenv('OPENAI_API_KEY', 'test-placeholder')
    store, job_id = approved_fixture(tmp_path)
    transport = recording_transport(ImageResponse())
    renderer = make_openai_background_renderer(store, job_id=job_id, allow_paid=True, transport=transport)
    with pytest.raises(WorkflowError, match='승인된 장면'):
        renderer(7, store.root / 'bg.png')
    assert transport.calls == []


def test_output_path_outside_state_root_is_rejected(tmp_path, monkeypatch):
    from office.image_provider import make_openai_background_renderer
    monkeypatch.setenv('OPENAI_API_KEY', 'test-placeholder')
    store, job_id = approved_fixture(tmp_path)
    renderer = make_openai_background_renderer(store, job_id=job_id, allow_paid=True, transport=recording_transport(ImageResponse()))
    with pytest.raises(WorkflowError, match='경로'):
        renderer(0, tmp_path / 'elsewhere.png')


def test_source_change_after_renderer_creation_invalidates(tmp_path, monkeypatch):
    from office.image_provider import make_openai_background_renderer
    monkeypatch.setenv('OPENAI_API_KEY', 'test-placeholder')
    store, job_id = approved_fixture(tmp_path)
    transport = recording_transport(ImageResponse())
    renderer = make_openai_background_renderer(store, job_id=job_id, allow_paid=True, transport=transport)
    job = store.job(job_id)
    store.save_source(job_id, {**job['source_packet'], 'body': '수정된 본문'})
    with pytest.raises(WorkflowError, match='승인|변경'):
        renderer(0, store.root / 'bg.png')
    assert transport.calls == []
