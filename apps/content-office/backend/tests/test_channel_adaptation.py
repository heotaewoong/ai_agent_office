import copy
import json

import pytest

from office.channel_adaptation import adaptation_issues, source_link, copy_schema
from office.channel_handoff import write_channel_handoffs
from office.gates import metadata_fact_check
from office.output_specs import output_issues
from office.store import WorkflowError
from test_editorial import OriginalPreservingProvider, original_markdown, preservation_job


def copies():
    return {'threads_main': '기기와 폴더의 일시정지 상태부터 확인해요.',
            'linkedin_personal': '도구를 고를 때 비용뿐 아니라 기기 구성과 운영 조건을 함께 확인해요. 개인 사례를 모든 장애의 원인으로 일반화하지 않아요.',
            'instagram_main': '노트가 안 오면 기기와 폴더를 확인해요. 충돌본은 백업 후 비교해요.',
            'x_main': '동기화 완료 표시와 원격 기기 연결 상태를 따로 확인해요.'}


class AdaptedProvider(OriginalPreservingProvider):
    def generate(self, role, messages, schema, options=None):
        result = super().generate(role, messages, schema, options)
        if role in ('gen', 'refine'):
            assert 'channel_posts' in schema['required']
            result['channel_posts'] = copies()
        else:
            assert json.loads(messages[-1]['content'])['packet']['channel_posts'] == copies()
        return result


def test_automatic_generation_review_refine_and_outbox_preserve_detailed_blog(tmp_path, monkeypatch):
    from office.editorial import prepare_source
    from office.media import produce
    original = original_markdown()
    store, job = preservation_job(tmp_path, monkeypatch, original)
    provider = AdaptedProvider(original, refine_once=True)
    saved = prepare_source(store, job['id'], provider=provider)
    assert saved['source_packet']['body'] == original
    assert saved['source_packet']['channel_posts'] == copies()
    assert saved['source_packet']['quality']['status'] == 'passed'
    assert saved['source_approval'] is None
    assert saved['manifest'] is None
    with pytest.raises(WorkflowError, match='승인'):
        produce(store, job['id'])
    # Synthetic operator approval only; no real user job or platform is touched by this test.
    store.review_source(job['id'], saved['source_hash'], 'approved', 'fixture-operator', {'blog': True, 'video': False, 'cards': False, 'pdf': False})
    manifest = produce(store, job['id'])
    files = {r['name']: store.artifacts / r['path'] for r in manifest['files']}
    assert manifest['completed_outputs'] == ['blog']
    assert files['tistory.md'].read_bytes().decode('utf-8').startswith(original)
    assert original.replace('\r\n', '\n').strip() in files['tistory.md'].read_text(encoding='utf-8').replace('\r\n', '\n')
    assert '14절 저자 원문' in files['naver.txt'].read_text(encoding='utf-8')
    assert files['tistory.html'].read_text(encoding='utf-8').count('<table ') == 7
    handoff = json.loads(files['channel-handoff.json'].read_text(encoding='utf-8'))
    for key, value in copies().items():
        row = next(r for r in handoff['channels'] if r['channel_key'] == key)
        text = files[row['file']].read_text(encoding='utf-8')
        assert value in text and '14절 저자 원문' not in text
        assert row['copy_mode'] == 'channel_adapted' and row['source_hash'] == saved['source_hash']
        assert len(text.rstrip()) <= row['review_budget_characters']
    assert store.job(job['id'])['release_approval'] is None
    assert handoff['external_draft_created'] is handoff['external_published'] is False


@pytest.mark.parametrize('kind', ['missing', 'duplicated', 'too_long', 'full_blog', 'malformed'])
def test_invalid_channel_copy_returns_to_review_without_truncation(kind):
    packet = {'body': '상세 원문', 'channel_posts': copies(), 'source_article_url': 'https://example.com/source'}
    if kind == 'missing': del packet['channel_posts']['threads_main']
    if kind == 'duplicated': packet['channel_posts']['threads_main'] = packet['channel_posts']['x_main']
    if kind == 'too_long': packet['channel_posts']['threads_main'] = '가' * 500
    if kind == 'full_blog': packet['channel_posts']['threads_main'] = packet['body']
    if kind == 'malformed': packet['channel_posts'] = ['wrong shape']
    before = copy.deepcopy(packet)
    assert output_issues(packet) and packet == before


def test_utf8_permalink_is_readable_without_decoding_reserved_url_syntax():
    assert source_link({'source_article_url': 'https://example.com/%EC%9B%90%EB%AC%B8#part'}) == 'https://example.com/원문'
    assert source_link({'source_article_url': 'https://example.com/a%2Fb'}) == 'https://example.com/a%2Fb'
    assert not source_link({'source_article_url': 'https://example.com:bad/a'})


def test_unsupported_language_does_not_become_ready_from_korean_copy(tmp_path):
    packet = {'title': '제목', 'body': '상세 본문', 'channel_posts': copies()}
    write_channel_handoffs(packet, tmp_path, source_hash='a' * 64, language='ko')
    rows = json.loads((tmp_path / 'channel-handoff.json').read_text(encoding='utf-8'))['channels']
    english = next(r for r in rows if r['channel_key'] == 'instagram_english')
    assert english['state'] == 'needs_review' and english['copy_mode'] == 'legacy_excerpt'


def test_url_encoding_numbers_are_not_claims_but_social_claim_numbers_still_checked():
    packet = {'title': '근거', 'body': '본문', 'evidence': [],
              'video': {'description': '원문 https://example.com/%EC%9B%90%EB%AC%B8'},
              'channel_posts': {'threads_main': 'https://example.com/2026/1'}}
    assert metadata_fact_check(packet) == []
    packet['channel_posts']['threads_main'] = '효과가 99배예요.'
    assert any(r['level'] == 'block' and '99' in r['message'] for r in metadata_fact_check(packet))


def test_english_source_has_only_its_matching_channel_schema_and_export(tmp_path):
    assert copy_schema('en')['required'] == ['instagram_english']
    assert 'instagram_english' not in copy_schema('ko')['required']
    packet = {'title': 'Keep a local vault', 'body': 'Detailed source remains intact.',
              'audience': {'language': 'en'}, 'channel_posts': {'instagram_english': 'Check the device and folder pause states before changing the setup.'}}
    assert adaptation_issues(packet) == []
    write_channel_handoffs(packet, tmp_path, source_hash='a' * 64, language='en')
    rows = json.loads((tmp_path / 'channel-handoff.json').read_text(encoding='utf-8'))['channels']
    english = next(r for r in rows if r['channel_key'] == 'instagram_english')
    assert english['copy_mode'] == 'channel_adapted'
    assert (tmp_path / english['file']).read_text(encoding='utf-8').startswith(packet['channel_posts']['instagram_english'])
    assert next(r for r in rows if r['channel_key'] == 'threads_main')['state'] == 'needs_review'


def test_user_selected_blog_and_short_titles_survive_model_refine_and_are_reviewed(tmp_path, monkeypatch):
    from office.editorial import prepare_source
    original = original_markdown()
    store, job = preservation_job(tmp_path, monkeypatch, original)
    titles = {'blog': '상세 설정을 보존한 블로그 제목', 'shorts': '동기화 꿀팁'}
    store.update_job(job['id'], channel_titles=titles)
    reviewed = []
    class RenamingProvider(AdaptedProvider):
        def generate(self, role, messages, schema, options=None):
            if role not in ('gen', 'refine'):
                p = json.loads(messages[-1]['content'])['packet']
                reviewed.append((p['title'], p['video']['title']))
            return super().generate(role, messages, schema, options)
    result = prepare_source(store, job['id'], provider=RenamingProvider(original, refine_once=True))
    assert len(reviewed) == 6 and all(pair == (titles['blog'], titles['shorts']) for pair in reviewed)
    assert result['source_packet']['title'] == titles['blog']
    assert result['source_packet']['video']['title'] == titles['shorts']
    assert result['source_packet']['body'] == original and result['source_approval'] is None
