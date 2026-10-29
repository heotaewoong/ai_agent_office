import copy

import pytest
from fastapi.testclient import TestClient

from office.api import create_app
from office.drafts import parse_article, parse_script, register_folder
from office.editorial import deterministic_checks
from office.exports import plain_text, safe_fragment
from office.store import Store, WorkflowError

ARTICLE = """# 반품 메일 한 통의 세 판단

> 개선초안·기존승인과별도·미게시 | 새 원고 검토용

고객 메일에서 시작합니다. [DC1]

> 가상 안내: 주문번호를 알려 주세요.

## 출처와 확인 범위

- [DC1] 공식 가이드: [링크](https://example.com/guide)

편집 메모입니다.
"""

SCRIPT = """# 주문번호 없는 반품 메일

> 개선초안·기존승인과별도·미게시 | 미승인 대본

| 장면 | 시간 제안 | 내레이션 | 화면 자막 | 화면 유형 | 연출 메모 |
|---|---|---|---|---|---|
| 1 | 0~7초 | 메일을 읽어 봅시다. | 가상 메일 | explanation: 가상 메일 | 메일만 보여 준다. |
| 2 | 7~15초 | 질문을 나눕니다. | 질문 세 개 | comparison: 조건 / 선택 / 점수 | 카드 세 장 |

## 설명란

가상 반품 메일을 설명합니다.

## 태그

OpenAI, AI자동화

## 썸네일 문구

| 제목 | 보조 문구 | 관점 |
|---|---|---|
| 메일 한 통, 질문 세 개 | 조건·선택·점수 | 개념 |
"""


@pytest.fixture
def context(tmp_path):
    store = Store(tmp_path / 'state')
    job = store.create_job({'id': 'decisions', 'title': '결정 API', 'url': 'https://example.com/news',
                            'evidence': [{'id': 'DC1', 'url': 'https://example.com/guide', 'claim': '공식 설명'},
                                         {'id': 'DC2', 'url': 'https://example.com/guide', 'claim': '400개'}]})
    store.create_job({'id': 'other', 'title': '다른 뉴스', 'url': 'https://example.com/other',
                      'evidence': [{'id': 'AD1', 'url': 'https://example.com/ads', 'claim': '광고'}]})
    packet = {'title': '승인 원고', 'body': '## 기존\n\n기존 본문 [DC1] [DC2]', 'evidence': job['article']['evidence'],
              'quality': {'status': 'passed', 'critical': False}}
    job = store.save_source(job['id'], packet)
    store.review_source(job['id'], job['source_hash'], 'approved', 'tester', {'blog': True, 'video': True})
    folder = tmp_path / 'draft'
    folder.mkdir()
    (folder / 'article.md').write_text(ARTICLE, encoding='utf-8')
    (folder / 'script.md').write_text(SCRIPT, encoding='utf-8')
    return store, job['id'], folder


def test_article_drops_editor_status_and_duplicate_sources_but_keeps_reader_quotes():
    title, body = parse_article(ARTICLE)
    assert title == '반품 메일 한 통의 세 판단'
    assert '개선초안' not in body and '출처와 확인 범위' not in body and '편집 메모' not in body
    assert '> 가상 안내: 주문번호를 알려 주세요.' in body


def test_script_table_becomes_renderer_scenes_with_metadata():
    video = parse_script(SCRIPT)
    assert video['title'] == '주문번호 없는 반품 메일'
    assert video['scenes'][1] == {'narration': '질문을 나눕니다.', 'caption': '질문 세 개',
                                  'visual': 'comparison: 조건 / 선택 / 점수', 'direction': '카드 세 장'}
    assert video['tags'] == ['OpenAI', 'AI자동화']
    assert video['description'] == '가상 반품 메일을 설명합니다.'
    assert video['thumbnails'] == [{'title': '메일 한 통, 질문 세 개', 'subtitle': '조건·선택·점수', 'angle': '개념'}]


def test_registered_draft_is_visible_without_touching_approval_or_production(context):
    store, job_id, folder = context
    before = copy.deepcopy(store.job(job_id))
    record = register_folder(store, folder)
    assert record['job_id'] == job_id and record['status'] == 'unapproved_draft'
    assert record['evidence_ids_missing'] == ['DC2']
    assert register_folder(store, folder)['id'] == record['id']
    assert len(store.drafts(job_id)) == 1
    assert store.job(job_id) == before
    client = TestClient(create_app(store), base_url='http://localhost:8510')
    detail = client.get(f'/api/jobs/{job_id}').json()
    assert [d['id'] for d in detail['drafts']] == [record['id']]
    assert detail['source_hash'] == before['source_hash']


def test_draft_preview_reads_like_the_exported_blog_and_is_script_free(context):
    store, job_id, folder = context
    record = register_folder(store, folder)
    client = TestClient(create_app(store), base_url='http://localhost:8510')
    response = client.get(f'/api/jobs/{job_id}/drafts/{record["id"]}/preview')
    assert response.status_code == 200
    assert '미승인 초안' in response.text and '<blockquote' in response.text
    assert '출처와 확인 범위' in response.text and 'https://example.com/guide' in response.text
    assert "script-src 'none'" in response.headers['content-security-policy']
    assert client.get(f'/api/jobs/{job_id}/drafts/draft_missing/preview').status_code == 404


def test_unmatched_draft_is_refused(tmp_path, context):
    store, _, folder = context
    (folder / 'article.md').write_text('# 제목\n\n근거 없는 글 [ZZ1]\n', encoding='utf-8')
    with pytest.raises(WorkflowError):
        register_folder(store, folder)


def test_bound_draft_preserves_job_and_deduplicates_within_its_source(context):
    store, job_id, folder = context
    before = copy.deepcopy(store.job(job_id))
    legacy = register_folder(store, folder, job_id)
    record = register_folder(store, folder, job_id, expected_source_hash=before['source_hash'])
    assert record['based_on_source_hash'] == before['source_hash']
    assert record['status'] == 'unapproved_draft' and record['id'] != legacy['id']
    assert register_folder(store, folder, job_id, expected_source_hash=before['source_hash']) == record
    assert register_folder(store, folder, job_id) == legacy
    assert store.job(job_id) == before
    assert len(store.drafts(job_id)) == 2


def test_bound_draft_rejects_old_version_even_if_already_registered(context):
    store, job_id, folder = context
    old_hash = store.job(job_id)['source_hash']
    register_folder(store, folder, job_id, expected_source_hash=old_hash)
    packet = {**store.job(job_id)['source_packet'], 'body': '새로 수정한 원고 [DC1]'}
    current = store.save_source(job_id, packet)
    before_events = store.events(job_id)
    before_drafts = store.drafts(job_id)
    with pytest.raises(WorkflowError, match='원고 판본이 변경'):
        register_folder(store, folder, job_id, expected_source_hash=old_hash)
    assert store.drafts(job_id) == before_drafts
    assert store.events(job_id) == before_events
    assert store.job(job_id) == current
    new = register_folder(store, folder, job_id, expected_source_hash=current['source_hash'])
    assert new['id'] != before_drafts[0]['id']
    assert new['based_on_source_hash'] == current['source_hash']


def test_bound_draft_checks_version_at_write_after_intake_read(context, monkeypatch):
    store, job_id, folder = context
    old_hash = store.job(job_id)['source_hash']
    add_draft = store.add_draft
    after_change = {}

    def change_source_then_insert(*args, **kwargs):
        packet = {**store.job(job_id)['source_packet'], 'body': '초안 읽기 후 바뀐 원고 [DC1]'}
        after_change['job'] = store.save_source(job_id, packet)
        after_change['events'] = store.events(job_id)
        return add_draft(*args, **kwargs)

    monkeypatch.setattr(store, 'add_draft', change_source_then_insert)
    with pytest.raises(WorkflowError, match='원고 판본이 변경'):
        register_folder(store, folder, job_id, expected_source_hash=old_hash)
    assert store.drafts(job_id) == []
    assert store.events(job_id) == after_change['events']
    assert store.job(job_id) == after_change['job']


def test_bound_intake_requires_explicit_job_before_reading_files(context):
    store, job_id, folder = context
    with pytest.raises(WorkflowError, match='--job'):
        register_folder(store, folder / 'missing', expected_source_hash=store.job(job_id)['source_hash'])


def test_bound_intake_cli_refuses_missing_job_before_opening_store(monkeypatch):
    from office.drafts import main
    monkeypatch.setattr('office.bootstrap.default_store', lambda: pytest.fail('운영 작업 장부를 열면 안 됩니다'))
    monkeypatch.setattr('sys.argv', ['office.drafts', 'unused', '--source-hash', 'a' * 64])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2


def test_blog_quote_renders_as_blockquote_without_raw_marker():
    html = safe_fragment('## 예시\n\n> 가상 설명: <b>72mm</b>')
    assert '<blockquote' in html and '&gt; 가상' not in html and '&lt;b&gt;' in html
    assert plain_text('> 가상 설명') == '가상 설명'


@pytest.mark.parametrize('name', ['01_ThinkingBox', '02_Decisions_API', '03_ChatGPT_광고'])
def test_workspace_drafts_pass_the_offices_own_structure_checks(name):
    from pathlib import Path
    from office.bootstrap import WORKSPACE, enrich
    from office.drafts import load_folder
    folder = WORKSPACE / 'output/2026-10-26_AI뉴스_품질개선_초안' / name
    if not folder.is_dir():
        pytest.skip('workspace drafts are not present')
    draft = load_folder(folder)
    prefix = {'01_ThinkingBox': 'TB', '02_Decisions_API': 'DC', '03_ChatGPT_광고': 'AD'}[name]
    import json
    seed = json.loads((Path(__file__).resolve().parents[1] / 'config/editorial-seed.json').read_text(encoding="utf-8"))
    claims = [c for item in seed['selected'] for c in item['claims'] if c['id'].startswith(prefix)]
    evidence = enrich([{'url': next(i['primary_url'] for i in seed['selected'] if any(c['id'].startswith(prefix) for c in i['claims'])), 'title': draft['title']}])[0]['evidence']
    assert {e['id'] for e in evidence} == {c['id'] for c in claims}
    checks = deterministic_checks({**draft, 'evidence': evidence})
    assert checks['passed'], checks['issues']
