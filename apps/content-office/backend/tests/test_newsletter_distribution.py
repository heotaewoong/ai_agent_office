"""승인③에 결속된 다중 원고 패키지와 전달 준비. 외부 발송은 실행하지 않는다."""
import hashlib
import json

import pytest

from office import newsletter
from office.store import WorkflowError
from tests.test_youtube_delivery import released_fixture


@pytest.fixture(autouse=True)
def clean_connector_environment(monkeypatch):
    for key in ('NEWSLETTER_FROM', 'NEWSLETTER_UNSUBSCRIBE_URL', 'RESEND_API_KEY', 'SLACK_BOT_TOKEN',
                'NEWSLETTER_SLACK_CHANNEL', 'HEOBRAIN_NEWSLETTER_DRAFT_URL', 'HEOBRAIN_NEWSLETTER_TOKEN'):
        monkeypatch.delenv(key, raising=False)


def add_released_blog(store):
    job = store.create_job({'id': 'second-research', 'title': '다른 기관의 AI 연구', 'url': 'https://research.example.org/ai'})
    job = store.save_source(job['id'], {'title': '다른 기관의 AI 연구', 'body': '별도 근거를 확인한 연구 설명입니다.',
                                      'synthetic_fixture': True, 'quality': {'status': 'passed', 'critical': []}})
    choices = {'blog': True, 'video': False, 'cards': False, 'pdf': False}
    store.review_source(job['id'], job['source_hash'], 'approved', 'fixture-operator', choices)
    folder = store.artifacts / job['id']
    folder.mkdir()
    file = folder / 'blog.md'
    file.write_text('검토한 별도 원고', encoding='utf-8')
    manifest = {'source_hash': job['source_hash'], 'hash': 'b' * 64, 'completed_outputs': ['blog'],
                'output_status': {'blog': {'state': 'completed'}}, 'files': [{'name': file.name,
                'path': file.relative_to(store.artifacts).as_posix(), 'sha256': hashlib.sha256(file.read_bytes()).hexdigest(),
                'bytes': file.stat().st_size, 'outputs': ['blog']}]}
    store.save_manifest_if_current(job['id'], job['source_hash'], choices, manifest)
    store.review_release(job['id'], manifest['hash'], 'approved', 'fixture-operator', outputs=['blog'], media_reviewed=True)
    return job['id']


def build(store, job_id, **changes):
    editorial = {'kind': 'briefing', 'related_job_ids': [], 'destinations': ['email', 'slack', 'website']}
    editorial.update(changes)
    return newsletter.build_issue(store, job_id, issue_key='multi-issue', subject='여러 출처로 읽는 AI 소식',
                                  actor='fixture-operator', editorial=editorial)


def test_multiple_released_sources_are_bound_to_all_formats(tmp_path):
    store, job_id = released_fixture(tmp_path, outputs=('blog', 'video'))
    other = add_released_blog(store)
    issue = build(store, job_id, related_job_ids=[other])
    assert issue['state'] == 'draft' and issue['approval'] is None
    assert '다른 기관의 AI 연구' in issue['markdown']
    package = issue['package']
    assert set(package['outputs']) == {'email', 'slack', 'website'}
    assert package['article_count'] == 2
    assert '<html' in package['outputs']['email']['html']
    assert '다른 기관의 AI 연구' in package['outputs']['slack']['text']
    assert package['outputs']['website']['state'] == 'draft'
    assert package['sources'][1]['job_id'] == other


def test_preparation_requires_human_approval_and_is_idempotent(tmp_path):
    from office.newsletter_distribution import prepare_delivery
    store, job_id = released_fixture(tmp_path, outputs=('blog', 'video'))
    issue = build(store, job_id)
    with pytest.raises(WorkflowError, match='승인③'):
        prepare_delivery(store, issue['id'], expected_hash=issue['review_hash'], actor='fixture-operator')
    issue = newsletter.review_issue(store, issue['id'], 'approve', expected_hash=issue['review_hash'], actor='fixture-operator')
    first = prepare_delivery(store, issue['id'], expected_hash=issue['review_hash'], actor='fixture-operator')
    second = prepare_delivery(store, issue['id'], expected_hash=issue['review_hash'], actor='fixture-operator')
    assert first == second and first['external_requests'] == 0
    assert first['state'] == 'connection_required'
    assert all(item['external_sent'] is False for item in first['destinations'])
    assert len([event for event in store.events(job_id) if event['kind'] == 'newsletter_delivery_prepared']) == 1


def test_related_source_change_blocks_prepare_without_touching_approvals(tmp_path):
    from office.newsletter_distribution import prepare_delivery
    store, job_id = released_fixture(tmp_path, outputs=('blog', 'video'))
    other = add_released_blog(store)
    issue = build(store, job_id, related_job_ids=[other])
    newsletter.review_issue(store, issue['id'], 'approve', expected_hash=issue['review_hash'], actor='fixture-operator')
    store.update_job(other, release_approval=None)
    with pytest.raises(WorkflowError):
        prepare_delivery(store, issue['id'], expected_hash=issue['review_hash'], actor='fixture-operator')
    assert newsletter.issue(store, issue['id'])['approval']['decision'] == 'approved'


def test_target_change_after_approval_blocks_preparation(tmp_path, monkeypatch):
    from office.newsletter_distribution import prepare_delivery
    store, job_id = released_fixture(tmp_path, outputs=('blog', 'video'))
    issue = build(store, job_id)
    newsletter.review_issue(store, issue['id'], 'approve', expected_hash=issue['review_hash'], actor='fixture-operator')
    monkeypatch.setenv('NEWSLETTER_SLACK_CHANNEL', 'C123456789')
    with pytest.raises(WorkflowError):
        prepare_delivery(store, issue['id'], expected_hash=issue['review_hash'], actor='fixture-operator')


def test_connection_status_never_returns_secrets_or_claims_verified(monkeypatch):
    from office.newsletter_distribution import connection_status
    monkeypatch.setenv('RESEND_API_KEY', 'private-fixture-value')
    monkeypatch.setenv('SLACK_BOT_TOKEN', 'private-slack-token')
    status = connection_status()
    assert 'private-fixture' not in json.dumps(status)
    assert 'private-slack' not in json.dumps(status)
    assert all(row['verified'] is False for row in status['destinations'])


@pytest.mark.parametrize('field,value', [('kind', 'unknown'), ('destinations', []), ('destinations', ['public']),
                                        ('related_job_ids', ['missing-job']), ('related_job_ids', ['a'] * 9)])
def test_invalid_editorial_inputs_fail_before_issue_creation(tmp_path, field, value):
    store, job_id = released_fixture(tmp_path, outputs=('blog', 'video'))
    count = len(newsletter.issues(store))
    with pytest.raises(WorkflowError):
        build(store, job_id, **{field: value})
    assert len(newsletter.issues(store)) == count


def test_newsletter_api_prepares_selected_targets_without_external_requests(tmp_path, monkeypatch):
    from tests.test_newsletter import api, lead
    import requests
    def forbidden(*args, **kwargs):
        pytest.fail('전달 준비 API는 외부 네트워크를 호출하면 안 됩니다')
    monkeypatch.setattr(requests, 'post', forbidden)
    store, job_id = released_fixture(tmp_path, outputs=('blog', 'video'))
    client, headers = api(store)
    lead(client, headers, 'synthetic@example.com')
    connections = client.get('/api/newsletter-connections').json()
    assert connections['mode'] == 'prepare-only' and len(connections['destinations']) == 3
    inputs = client.get('/api/newsletter-inputs').json()
    assert any(row['id'] == job_id for row in inputs['released_jobs'])
    assert len(inputs['sources']) >= 2
    issue = client.post(f'/api/jobs/{job_id}/newsletter', headers=headers, json={
        'issue_key': 'api-multi', 'subject': '출처를 확인한 뉴스레터',
        'editorial': {'kind': 'analysis', 'related_job_ids': [], 'destinations': ['email', 'website']}}).json()
    assert issue['editorial']['kind'] == 'analysis'
    url = f"/api/newsletters/{issue['id']}/prepare"
    assert client.post(url, headers=headers, json={'expected_hash': issue['review_hash']}).status_code == 409
    approved = client.post(f"/api/newsletters/{issue['id']}/review", headers=headers,
        json={'decision': 'approve', 'expected_hash': issue['review_hash']}).json()
    assert approved['state'] == 'approved'
    prepared = client.post(url, headers=headers, json={'expected_hash': issue['review_hash']}).json()
    assert {row['key'] for row in prepared['destinations']} == {'email', 'website'}
    assert prepared['external_requests'] == 0 and 'synthetic@example.com' not in json.dumps(prepared)
    assert client.get(f"/api/newsletters/{issue['id']}/prepared").json()['prepared']['id'] == prepared['id']
    record = client.get('/api/leads').json()['leads'][0]
    client.post(f"/api/leads/{record['id']}/withdraw", headers=headers, json={})
    assert client.post(url, headers=headers, json={'expected_hash': issue['review_hash']}).status_code == 409


def test_unsafe_article_html_is_escaped_in_email(tmp_path):
    store, job_id = released_fixture(tmp_path, outputs=('blog', 'video'))
    # Approved fixtures can contain literal code examples; rendering must remain inert.
    job = store.job(job_id)
    job['source_packet']['body'] = '<script>alert(1)</script> 안전한 코드 설명'
    from office.newsletter_formats import package_content
    with store.connection() as db:
        content = package_content(store, db, job, job['release_approval'], '<img src=x onerror=alert(1)>',
                                  {'kind': 'briefing', 'related_job_ids': [], 'destinations': ['email']})
    html = content['package']['outputs']['email']['html']
    assert '<script>' not in html and '<img src=x' not in html
    assert '&lt;script&gt;' in html and '&lt;img' in html


def test_email_subject_rejects_header_newlines(tmp_path):
    store, job_id = released_fixture(tmp_path, outputs=('blog', 'video'))
    with pytest.raises(WorkflowError):
        newsletter.build_issue(store, job_id, issue_key='header-test', subject='뉴스\r\nBcc: other@example.com', actor='fixture-operator')


def test_slack_draft_escapes_mentions_from_article_text(tmp_path):
    store, job_id = released_fixture(tmp_path, outputs=('blog', 'video'))
    job = store.job(job_id)
    job['source_packet']['body'] = '<!channel> <@U12345678> 설명용 문법'
    from office.newsletter_formats import package_content
    with store.connection() as db:
        content = package_content(store, db, job, job['release_approval'], '검토 소식',
                                  {'kind': 'briefing', 'related_job_ids': [], 'destinations': ['slack']})
    text = content['package']['outputs']['slack']['text']
    assert '<!channel>' not in text and '<@U12345678>' not in text


def test_credentials_becoming_available_refreshes_same_prepared_record(tmp_path, monkeypatch):
    from office.newsletter_distribution import prepare_delivery
    monkeypatch.setenv('NEWSLETTER_FROM', 'sender@example.com')
    monkeypatch.setenv('NEWSLETTER_UNSUBSCRIBE_URL', 'https://example.com/unsubscribe')
    store, job_id = released_fixture(tmp_path, outputs=('blog', 'video'))
    issue = build(store, job_id, destinations=['email'])
    newsletter.review_issue(store, issue['id'], 'approve', expected_hash=issue['review_hash'], actor='fixture-operator')
    first = prepare_delivery(store, issue['id'], expected_hash=issue['review_hash'], actor='fixture-operator')
    assert first['state'] == 'connection_required'
    monkeypatch.setenv('RESEND_API_KEY', 'synthetic-key')
    second = prepare_delivery(store, issue['id'], expected_hash=issue['review_hash'], actor='fixture-operator')
    assert second['id'] == first['id'] and second['state'] == 'prepared'
    assert second['external_requests'] == 0


def test_prepared_get_reflects_lost_credentials_without_writing_history(tmp_path, monkeypatch):
    from office.newsletter_distribution import prepare_delivery, prepared_delivery
    for key, value in {'RESEND_API_KEY': 'synthetic-key', 'NEWSLETTER_FROM': 'sender@example.com',
                       'NEWSLETTER_UNSUBSCRIBE_URL': 'https://example.com/unsubscribe'}.items():
        monkeypatch.setenv(key, value)
    store, job_id = released_fixture(tmp_path, outputs=('blog', 'video'))
    issue = build(store, job_id, destinations=['email'])
    newsletter.review_issue(store, issue['id'], 'approve', expected_hash=issue['review_hash'], actor='fixture-operator')
    first = prepare_delivery(store, issue['id'], expected_hash=issue['review_hash'], actor='fixture-operator')
    assert first['state'] == 'prepared'
    with store.connection() as db:
        before = db.execute("SELECT value FROM settings WHERE key LIKE 'newsletter_prepared:%'").fetchone()[0]
    monkeypatch.delenv('RESEND_API_KEY')
    shown = prepared_delivery(store, issue['id'])
    assert shown['id'] == first['id'] and shown['state'] == 'connection_required'
    assert shown['destinations'][0]['configured'] is False
    with store.connection() as db:
        assert db.execute("SELECT value FROM settings WHERE key LIKE 'newsletter_prepared:%'").fetchone()[0] == before
