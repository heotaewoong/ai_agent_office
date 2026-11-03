from io import BytesIO
from zipfile import ZipFile

import pytest

from office import evidence
from office.store import SourceUnavailable


NOTICE = '''<html><nav>메뉴 글자만 길어도 본문이라고 인정하면 안 됩니다.</nav>
<div class="synapTextWrap">스마트안경 부정행위 대응계획</div>
<section class="attachment"><ul><li><span>대응계획.hwpx</span>
<a href="/boardCnts/fileDown.do?fileSeq=abc">다운로드</a></li></ul></section></html>'''


def hwpx(text):
    out = BytesIO()
    with ZipFile(out, 'w') as archive:
        archive.writestr('Contents/section0.xml', '<root xmlns:h="urn:test"><h:p><h:t>' + text + '</h:t></h:p></root>')
    return out.getvalue()


class Recorder:
    def __init__(self):
        self.calls = []

    def generate(self, role, messages, schema, options):
        import json
        self.calls.append(json.loads(messages[-1]['content']))
        return {'claims': [{'claim': '스마트안경 대응', 'paragraph': 1, 'numbers': [], 'scope': '발표'}] * 2,
                'limitations': [], 'hook': '실제 대응 내용', 'source_sufficient': True, 'source_reason': '첨부의 조치 본문 확인'}


def test_attachment_body_is_researched_instead_of_notice_shell(tmp_path, monkeypatch):
    body = '스마트안경 사용과 단순 소지는 구분하며, 시험장에는 전담 인력을 배치한다. ' * 8
    requested = []
    def fetch(url, **kwargs):
        requested.append(url)
        return (hwpx(body) if 'fileDown' in url else NOTICE.encode()), url, 'application/octet-stream'
    monkeypatch.setattr(evidence, 'fetch_public', fetch)
    provider = Recorder()
    result = evidence.collect_article_evidence({'title': '대응계획', 'url': 'https://www.moe.go.kr/notice',
        'source_kind': 'official_notice'}, provider, tmp_path)
    assert len(requested) == 2
    assert body.strip() == provider.calls[0]['paragraphs'][0]['text']
    assert '메뉴 글자' not in str(provider.calls)
    assert result['source_documents'][0]['url'] == requested[1]
    assert result['evidence'][0]['url'] == requested[1]


@pytest.mark.parametrize('replacement', [b'not a document', b'<html>access denied</html>'])
def test_unreadable_attachment_stops_before_any_model_call(tmp_path, monkeypatch, replacement):
    monkeypatch.setattr(evidence, 'fetch_public', lambda url, **kw:
        (replacement if 'fileDown' in url else NOTICE.encode(), url, 'text/html'))
    provider = Recorder()
    with pytest.raises(SourceUnavailable, match='첨부'):
        evidence.collect_article_evidence({'title': '대응계획', 'url': 'https://www.moe.go.kr/notice'}, provider, tmp_path)
    assert provider.calls == []


def test_cross_origin_attachment_is_not_fetched(tmp_path, monkeypatch):
    markup = NOTICE.replace('/boardCnts/fileDown.do?fileSeq=abc', 'https://other.example/file.hwpx')
    calls = []
    def fetch(url, **kw):
        calls.append(url)
        return markup.encode(), url, 'text/html'
    monkeypatch.setattr(evidence, 'fetch_public', fetch)
    with pytest.raises(SourceUnavailable):
        evidence.collect_article_evidence({'title': '대응계획', 'url': 'https://www.moe.go.kr/notice'}, Recorder(), tmp_path)
    assert len(calls) == 1


def test_high_scores_do_not_override_missing_or_failed_news_content_checks():
    from office.editorial import review_until_ready
    class Reviewer:
        def __init__(self, check): self.check = check
        def generate(self, role, messages, schema, options):
            result = {'role': role, 'score': 99, 'passed': True, 'critical_issues': [], 'minor_issues': [], 'summary': '글은 자연스러움'}
            if self.check is not None: result['content_checks'] = self.check
            return result
    for check in [None, {'source_sufficient': False, 'topic_matches': True, 'reason': '제목만 있음'},
                  {'source_sufficient': True, 'topic_matches': False, 'reason': '공지 읽는 법으로 바꿈'},
                  {'source_sufficient': True, 'topic_matches': True, 'reason': ''}]:
        result = review_until_ready({'title': '대응계획', 'body': '공지 읽는 법', 'news_review_required': True},
            Reviewer(check), refine_limit=0)
        assert result['quality']['status'] == 'blocked'
        assert result['quality']['deterministic_checks']['blocking']


def test_notice_metadata_evidence_is_not_substantive_news_evidence():
    from office.evidence import metadata_only_evidence
    article = {'title': '[보도참고자료] 스마트안경 부정행위 대응계획',
        'evidence': [{'source_quote': '[보도참고자료] 스마트안경 부정행위 대응계획'},
                     {'source_quote': '[교육부 10-29] 스마트안경 부정행위 대응계획.hwpx'}]}
    assert metadata_only_evidence(article)
    assert not metadata_only_evidence({**article, 'evidence': [{'source_quote': '시험장에 전담 인력을 배치한다.'}]})


def test_legacy_passed_notice_cannot_be_approved_using_only_filenames(tmp_path):
    from office.store import Store, WorkflowError
    store = Store(tmp_path)
    article = {'id': 'notice', 'title': '스마트안경 대응계획', 'url': 'https://www.moe.go.kr/notice',
               'evidence': [{'id': 'E1', 'source_quote': '스마트안경 대응계획', 'url': 'https://www.moe.go.kr/notice'}]}
    job = store.create_job(article)
    job = store.save_source(job['id'], {'title': '공지 읽는 법', 'body': '기존 잘못된 원고',
        'quality': {'status': 'passed', 'critical': False}, 'evidence': article['evidence']})
    before = store.job(job['id'])
    with pytest.raises(WorkflowError, match='본문'):
        store.review_source(job['id'], job['source_hash'], 'approved', 'test-human')
    assert store.job(job['id']) == before
    assert store.review_source(job['id'], job['source_hash'], 'rejected', 'test-human')['state'] == 'source_rejected'


def test_news_content_is_rechecked_after_refine_and_style_advice_stays_nonblocking():
    from office.editorial import review_until_ready
    class Reviewer:
        def __init__(self): self.round = 0
        def generate(self, role, messages, schema, options):
            if role == 'refine':
                self.round += 1
                return {'body': '실제 대응계획 설명'}
            return {'role': role, 'score': 70, 'passed': False, 'critical_issues': [],
                    'minor_issues': ['문장이 길다'], 'summary': '문체 보완',
                    'content_checks': {'source_sufficient': True, 'topic_matches': self.round > 0,
                                       'reason': '원문 사건과 비교한 판정'}}
    provider = Reviewer()
    result = review_until_ready({'body': '공지 읽는 법', 'news_review_required': True}, provider, refine_limit=1)
    assert provider.round == 1
    assert result['quality']['history'][0]['deterministic_checks']['blocking']
    assert result['quality']['status'] == 'passed'
    assert result['quality']['advisories']['model_reviews_passed'] is False


def test_content_checks_do_not_erase_an_existing_integrity_failure():
    from office.editorial import content_review_checks
    reviews = [{'role': role, 'content_checks': {'source_sufficient': True, 'topic_matches': True, 'reason': '원문 사건과 일치'}}
               for role in ('critique', 'eval')]
    result = content_review_checks({'passed': False, 'issues': ['source hash changed']},
                                   {'news_review_required': True}, reviews)
    assert result['blocking'] == ['source hash changed']
    assert result['passed'] is False


def test_actual_review_endpoint_blocks_legacy_metadata_without_changing_job_or_queue(tmp_path):
    from fastapi.testclient import TestClient
    from office.api import create_app
    from office.store import Store
    store = Store(tmp_path)
    article = {'id': 'notice-api', 'title': '스마트안경 대응계획', 'url': 'https://www.moe.go.kr/notice',
               'evidence': [{'id': 'E1', 'source_quote': '스마트안경 대응계획', 'url': 'https://www.moe.go.kr/notice'}]}
    job = store.create_job(article)
    job = store.save_source(job['id'], {'title': '공지 읽는 법', 'body': '기존 원고를 보존합니다',
        'quality': {'status': 'passed', 'critical': False}, 'evidence': article['evidence']})
    client = TestClient(create_app(store), base_url='http://localhost:8510')
    csrf = client.get('/api/session').json()['csrf']
    before = store.job(job['id'])
    response = client.post(f"/api/jobs/{job['id']}/reviews/source",
        json={'version': job['source_hash'], 'decision': 'approved', 'auto_produce': False},
        headers={'Origin': 'http://localhost:3110', 'X-Office-CSRF': csrf})
    assert response.status_code == 409
    assert '본문' in response.text
    assert client.get(f"/api/jobs/{job['id']}").json()['source_hash'] == job['source_hash']
    assert store.job(job['id']) == before and store.tasks() == []


def test_research_can_report_insufficient_material_without_inventing_two_claims(tmp_path):
    from office.store import WorkflowError
    class Insufficient:
        def generate(self, role, messages, schema, options):
            assert schema['properties']['claims']['minItems'] == 0
            return {'claims': [], 'source_sufficient': False, 'source_reason': '첨부 안내만 있음',
                    'limitations': ['본문 없음'], 'hook': ''}
    with pytest.raises(WorkflowError, match='본문'):
        evidence.collect_article_evidence({'title': '자료 안내', 'url': 'https://example.com/notice',
            'operator_source_text': '제목과 첨부파일 안내만 보입니다. ' * 20}, Insufficient(), tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_new_article_evidence_does_not_make_old_passed_metadata_packet_approvable(tmp_path):
    from office.store import Store, WorkflowError
    store = Store(tmp_path)
    article = {'id': 'refresh-race', 'title': '스마트안경 대응계획', 'url': 'https://www.moe.go.kr/notice',
               'evidence': [{'id': 'E1', 'source_quote': '스마트안경 대응계획', 'url': 'https://www.moe.go.kr/notice'}]}
    job = store.create_job(article)
    job = store.save_source(job['id'], {'title': '공지 읽는 법', 'body': '옛 원고',
        'quality': {'status': 'passed', 'critical': False}, 'evidence': article['evidence']})
    refreshed = {**article, 'evidence': [{'id': 'E1', 'source_quote': '시험장에 전담 인력을 배치한다.',
                                      'url': 'https://www.moe.go.kr/plan.hwpx'}]}
    store.save_article_evidence_if_current(job['id'], job['source_hash'], refreshed)
    before = store.job(job['id'])
    with pytest.raises(WorkflowError, match='본문'):
        store.review_source(job['id'], job['source_hash'], 'approved', 'test-human')
    assert store.job(job['id']) == before


@pytest.mark.parametrize('previous_attempt_refreshed', [False, True])
def test_recheck_uses_refreshed_body_evidence_not_cached_filename_quotes(tmp_path, monkeypatch, previous_attempt_refreshed):
    import json
    from office import editorial
    from office.store import Store
    store = Store(tmp_path)
    article = {'id': 'recheck', 'title': '스마트안경 대응계획', 'url': 'https://www.moe.go.kr/notice',
               'evidence': [{'id': 'E1', 'source_quote': '스마트안경 대응계획', 'url': 'https://www.moe.go.kr/notice'}]}
    job = store.create_job(article)
    job = store.save_source(job['id'], {'title': '공지 읽는 법', 'body': '기존 본문 보존', 'audience': job['brief'],
        'video': {'scenes': [{'narration': '기존 영상 대본'}]},
        'quality': {'status': 'passed', 'critical': False}, 'evidence': article['evidence']})
    fresh = [{'id': 'E1', 'source_quote': '시험장에 전담 인력을 배치한다.', 'url': 'https://www.moe.go.kr/plan.hwpx'}]
    if previous_attempt_refreshed:
        # A prior attempt saved the researched article, then failed before saving
        # a new reviewed source_packet. Retry must not keep reviewing its old quotes.
        store.save_article_evidence_if_current(job['id'], job['source_hash'], {**article, 'evidence': fresh})
    monkeypatch.setattr(evidence, 'collect_article_evidence', lambda *args:
        {'evidence': fresh, 'limitations': [], 'hook': '실제 대응계획', 'source_kind': 'http_attachment_body', 'retrieved_at': 'fixture', 'source_sha256': 'a'*64})
    class Reviewer:
        def generate(self, role, messages, schema, options):
            assert json.loads(messages[-1]['content'])['packet']['evidence'] == fresh
            return {'role': role, 'score': 90, 'passed': True, 'critical_issues': [], 'minor_issues': [], 'summary': '검토',
                    'content_checks': {'source_sufficient': True, 'topic_matches': False, 'reason': '옛 원고는 공지 읽는 법임'}}
    result = editorial.prepare_source(store, job['id'], provider=Reviewer(), evaluate_only=True)
    assert result['source_packet']['body'] == '기존 본문 보존'
    assert result['source_packet']['quality']['status'] == 'blocked'


def test_inline_notice_keeps_late_measures_as_separate_paragraphs(tmp_path, monkeypatch):
    first = '첫번째 조치를 구체적으로 설명합니다. ' * 60
    second = '두번째 조치와 적용 조건을 설명합니다. ' * 60
    last = '마지막 문단의 전담 인력 배치와 시행 일정도 반드시 보존합니다.'
    page = f'<div class="synapTextWrap"><p>{first}</p><p>{second}</p><p>{last}</p></div>'
    calls = []
    def fetch(url, **kw):
        calls.append(url)
        return page.encode(), url, 'text/html'
    monkeypatch.setattr(evidence, 'fetch_public', fetch)
    provider = Recorder()
    evidence.collect_article_evidence({'title': '새 대응계획', 'url': 'https://www.moe.go.kr/notice'}, provider, tmp_path)
    assert len(calls) == 1
    assert provider.calls[0]['paragraphs'][-1]['text'] == last


def test_attachment_redirect_to_another_host_is_not_used(tmp_path, monkeypatch):
    def fetch(url, **kwargs):
        return (hwpx('가'*300), 'https://other.example/doc.hwpx', 'application/zip') if 'fileDown' in url else (NOTICE.encode(), url, 'text/html')
    monkeypatch.setattr(evidence, 'fetch_public', fetch)
    provider = Recorder()
    with pytest.raises(SourceUnavailable):
        evidence.collect_article_evidence({'title': '계획', 'url': 'https://www.moe.go.kr/notice'}, provider, tmp_path)
    assert provider.calls == []


def test_hwpx_rejects_dtd_and_entities_without_expanding_them():
    from office.source_material import hwpx_text
    out = BytesIO()
    with ZipFile(out, 'w') as archive:
        archive.writestr('Contents/section0.xml', '<!DOCTYPE x [<!ENTITY secret "not allowed">]><root>&secret;</root>')
    with pytest.raises(ValueError):
        hwpx_text(out.getvalue())


@pytest.mark.parametrize('count', [0, 33])
def test_hwpx_requires_a_bounded_number_of_sections(count):
    from office.source_material import hwpx_text
    out = BytesIO()
    with ZipFile(out, 'w') as archive:
        for i in range(count):
            archive.writestr(f'Contents/section{i}.xml', '<root/>')
    with pytest.raises(ValueError):
        hwpx_text(out.getvalue())


def test_hwpx_rejects_large_uncompressed_sections():
    from office.source_material import hwpx_text
    from zipfile import ZIP_DEFLATED
    out = BytesIO()
    with ZipFile(out, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('Contents/section0.xml', b' ' * 4_000_001)
    with pytest.raises(ValueError):
        hwpx_text(out.getvalue())
