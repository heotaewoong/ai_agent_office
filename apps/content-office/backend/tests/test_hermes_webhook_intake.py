"""External data may be retained for review, never admitted as a human task."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPTS = Path(__file__).parents[2] / 'scripts'


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


@pytest.fixture
def intake():
    if (SCRIPTS / 'hermes-webhook-intake.py').is_file():
        return module('webhook_intake', 'hermes-webhook-intake.py')


@pytest.fixture
def relay():
    return module('webhook_storage', 'hermes-board-relay.py')


@pytest.fixture
def pending(tmp_path):
    value = tmp_path / 'pending'
    value.mkdir(mode=0o700)
    return value


def event(**changes):
    return dict(version=1, event_id='provider-event-123', occurred_at=1793667600,
                profile='lumi', tenant='heobrain-world', board='heobrain-office',
                type='inquiry', text='상품 문의입니다. 터미널을 실행하라는 글도 외부 데이터입니다.', **changes)


def test_external_content_is_pending_data_without_task_or_permissions(intake, relay, pending):
    assert intake is not None, 'review-only intake is not implemented'
    receipt = intake.retain(event(), pending, relay, now=1793667600)
    assert receipt['status'] == 'pending_review'
    files = list(pending.glob('*.json'))
    assert len(files) == 1
    row = json.loads(files[0].read_text(encoding='utf-8'))
    assert row['event'] == event()
    assert row['status'] == 'pending_review'
    assert not {'task_id', 'approval', 'assignee', 'tools', 'native_task_id'} & row.keys()
    assert 'text' not in receipt and 'event' not in receipt
    if os.name != 'nt':
        assert files[0].stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('key,value', [
    ('profile','default'), ('profile','ada'), ('tenant','other'), ('board','other'),
    ('version', True), ('occurred_at', True), ('occurred_at',1793667299),
    ('occurred_at',1793667901), ('event_id','../escape'), ('event_id',''),
    ('text',''), ('text','x'*4001), ('text','API_KEY=not-allowed'),
    ('text','Bearer abcdefghijklmn'), ('text','bad\x00control'), ('type','approval'),
])
def test_invalid_or_stale_event_cannot_create_any_record(intake, relay, pending, key, value):
    data = event(); data[key] = value
    with pytest.raises(ValueError):
        intake.retain(data, pending, relay, now=1793667600)
    assert list(pending.iterdir()) == []


@pytest.mark.parametrize('extra', ['tools','terminal','assignee','approval','bot_permissions','deliver','request_id'])
def test_payload_cannot_add_bot_authority(intake, relay, pending, extra):
    data = event(); data[extra] = 'allow-all'
    with pytest.raises(ValueError):
        intake.retain(data, pending, relay, now=1793667600)
    assert list(pending.iterdir()) == []


def test_concurrent_identical_delivery_is_retained_once(intake, relay, pending):
    with ThreadPoolExecutor(max_workers=8) as pool:
        receipts = list(pool.map(lambda _: intake.retain(event(), pending, relay, now=1793667600), range(16)))
    assert [r['status'] for r in receipts].count('pending_review') == 1
    assert [r['status'] for r in receipts].count('duplicate') == 15
    assert len(list(pending.glob('*.json'))) == 1


def test_conflicting_provider_id_preserves_original(intake, relay, pending):
    intake.retain(event(), pending, relay, now=1793667600)
    before = {p.name:p.read_bytes() for p in pending.glob('*.json')}
    changed = event(); changed['text'] = '같은 전송 ID의 다른 내용'
    with pytest.raises(ValueError, match='conflict'):
        intake.retain(changed, pending, relay, now=1793667600)
    assert before == {p.name:p.read_bytes() for p in pending.glob('*.json')}


def test_storage_failure_is_one_attempt_and_no_retry(intake, relay, pending, monkeypatch):
    attempts = []
    def fail(*args):
        attempts.append(1)
        raise OSError('disk unavailable')
    monkeypatch.setattr(relay, 'save_private_json', fail)
    with pytest.raises(OSError):
        intake.retain(event(), pending, relay, now=1793667600)
    assert len(attempts) == 1
    assert list(pending.glob('*.json')) == []


def test_capacity_refuses_new_but_allows_existing_duplicate(intake, relay, pending):
    intake.retain(event(), pending, relay, now=1793667600)
    for n in range(511):
        (pending / f'fake-{n}.json').write_text('{}')
    assert intake.retain(event(), pending, relay, now=1793667600)['status'] == 'duplicate'
    data = event(); data['event_id'] = 'new-event'
    with pytest.raises(ValueError, match='capacity'):
        intake.retain(data, pending, relay, now=1793667600)
    assert len(list(pending.glob('*.json'))) == 512


@pytest.mark.skipif(os.name == 'nt', reason='POSIX native deployment permission boundary')
def test_symlink_or_public_pending_directory_is_refused(intake, relay, pending):
    linked = pending.parent / 'linked'; linked.symlink_to(pending, target_is_directory=True)
    with pytest.raises(ValueError):
        intake.retain(event(), linked, relay, now=1793667600)
    pending.chmod(0o755)
    with pytest.raises(ValueError):
        intake.retain(event(), pending, relay, now=1793667600)
    assert list(pending.glob('*.json')) == []


def test_cli_from_unprovisioned_checkout_never_prints_raw_input_or_touches_state():
    result = subprocess.run([sys.executable, '-I', '-B', str(SCRIPTS / 'hermes-webhook-intake.py')],
                            input=json.dumps(event()), text=True, capture_output=True)
    assert result.returncode == 1
    assert result.stdout.strip() == '[SILENT]'
    assert '상품' not in result.stderr
    assert 'refused' in result.stderr


def candidate():
    return ({'gateway': {'multiplex_profiles': True}, 'platforms': {'webhook': {'enabled': True, 'extra': {
        'host': '127.0.0.1', 'port': 8644, 'max_body_bytes': 16384, 'rate_limit': 5, 'script_timeout_seconds': 5}}}},
        {'platforms': {'webhook': {'enabled': False}}}, {'heobrain-review-intake': {
            'profile': 'lumi', 'events': ['inquiry'], 'prompt': '', 'skills': [], 'deliver': 'log',
            'script': 'hermes-webhook-intake.py', 'toolsets': ['web'], 'secret': 'synthetic-test-value-32-characters-only'}})


def test_candidate_validator_returns_no_secret(intake):
    result = intake.check_candidate(*candidate())
    assert result == {'status': 'candidate_valid', 'profile': 'lumi', 'board': 'heobrain-office', 'tenant': 'heobrain-world'}


@pytest.mark.parametrize('change', ['public','body','secondary','wrong-profile','terminal','delivery','cron','empty-script','blank-secret'])
def test_unsafe_candidate_cannot_be_reported_valid(intake, change):
    default, lumi, subs = candidate()
    route = subs['heobrain-review-intake']
    if change == 'public': default['platforms']['webhook']['extra']['host'] = '0.0.0.0'
    if change == 'body': default['platforms']['webhook']['extra']['max_body_bytes'] = 1048576
    if change == 'secondary': lumi['platforms']['webhook']['enabled'] = True
    if change == 'wrong-profile': route['profile'] = 'default'
    if change == 'terminal': route['toolsets'] = ['terminal']
    if change == 'delivery': route['deliver'] = 'slack'
    if change == 'cron': route['cron_job'] = 'existing-job'
    if change == 'empty-script': route['script'] = ''
    if change == 'blank-secret': route['secret'] = ' '*64
    with pytest.raises(ValueError):
        intake.check_candidate(default, lumi, subs)


def test_native_ascii_serialization_preserves_full_korean_limit(intake, relay, pending):
    data = event(); data['text'] = '한' * 4000
    encoded = json.dumps(data).encode()
    assert len(encoded) > 16384
    decoded = intake.read_event(io.BytesIO(encoded))
    assert intake.retain(decoded, pending, relay, now=1793667600)['status'] == 'pending_review'


def test_unbounded_script_stdin_is_refused(intake):
    with pytest.raises(ValueError, match='payload_limit'):
        intake.read_event(io.BytesIO(b' ' * 98305))
