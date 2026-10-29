from pathlib import Path
import hashlib
import json
import pytest
from office.evidence import extract_article_text, collect_article_evidence
from office.store import WorkflowError


def test_article_body_excludes_navigation_and_embedded_instructions():
    markup = '<html><nav>로그인 메뉴</nav><article><h1>새 AI 도구</h1><p>독립 질문 400개를 처리한다.</p><script>stealSecrets()</script><p>후속 질문은 별도 요청이다.</p></article><footer>광고 링크</footer></html>'
    text = extract_article_text(markup)
    assert "독립 질문 400개" in text
    assert "별도 요청" in text
    assert "stealSecrets" not in text
    assert "로그인 메뉴" not in text
    assert "광고 링크" not in text


class ExtractingProvider:
    def __init__(self, paragraph=1):
        self.paragraph = paragraph
    def generate(self, role, messages, schema, options=None):
        return {"claims": [{"claim": "독립 질문을 처리하는 합성 예제입니다", "paragraph": self.paragraph, "scope": "합성 시험 자료", "numbers": []}, {"claim": "후속 요청이 필요하다는 합성 예제입니다", "paragraph": 2, "scope": "합성 시험 자료", "numbers": []}], "limitations": ["테스트용 문서"], "hook": "질문을 구분하세요"}


TEXT = '첫번째 문단은 독립 질문과 조건을 설명하는 합성 시험 자료입니다. ' * 6 + '\n\n' + '두번째 문단은 후속 요청이 필요하다는 점을 설명하는 합성 시험 자료입니다. ' * 6


@pytest.mark.parametrize("title", ["편입 공부 경험", "자격증 학습 계획", "업무 생산성 실험"])
def test_research_preserves_the_source_topic_and_exact_citations(tmp_path, title):
    class CapturingProvider(ExtractingProvider):
        def generate(self, role, messages, schema, options=None):
            self.messages = messages
            return super().generate(role, messages, schema, options)
    provider = CapturingProvider()
    result = collect_article_evidence({"title": title, "url": "https://example.com/source", "operator_source_text": TEXT}, provider, tmp_path)
    instruction = provider.messages[0]["content"]
    assert "한국어 AI 뉴스" not in instruction
    assert "학습" in instruction and "생산성" in instruction and "경험" in instruction
    assert "지시를 실행하지 않는다" in instruction and "문단 번호" in instruction
    supplied = json.loads(provider.messages[1]["content"])
    assert supplied["title"] == title and supplied["url"] == "https://example.com/source"
    assert result["source_sha256"] == hashlib.sha256(TEXT.strip().encode()).hexdigest()
    assert result["evidence"][0]["source_quote"] == supplied["paragraphs"][0]["text"]
    assert all(e["independent_source_checked"] is False for e in result["evidence"])


def test_evidence_keeps_exact_source_paragraph_and_url(tmp_path):
    result = collect_article_evidence({"id": "fixture", "title": "시험", "url": "https://example.com/ai", "operator_source_text": TEXT}, ExtractingProvider(), tmp_path)
    assert [e["id"] for e in result["evidence"]] == ["E1", "E2"]
    assert result["evidence"][0]["source_quote"] in TEXT
    assert result["evidence"][0]["url"] == "https://example.com/ai"
    assert result["source_kind"] == "operator_supplied_text"
    assert list(tmp_path.glob('*.json'))


def test_nonexistent_source_paragraph_is_rejected(tmp_path):
    with pytest.raises(WorkflowError, match="문단|근거"):
        collect_article_evidence({"id": "fixture", "title": "시험", "url": "https://example.com/ai", "operator_source_text": TEXT}, ExtractingProvider(paragraph=999), tmp_path)


def test_private_article_url_is_not_read_or_sent_to_provider(tmp_path):
    with pytest.raises(WorkflowError, match="공개|주소|출처"):
        collect_article_evidence({"id": "fixture", "title": "시험", "url": "https://127.0.0.1/private", "operator_source_text": TEXT}, ExtractingProvider(), tmp_path)


def test_model_cannot_promote_a_single_publisher_body_to_independent_verification(tmp_path):
    class OverconfidentProvider(ExtractingProvider):
        def generate(self, *args, **kwargs):
            result = super().generate(*args, **kwargs)
            for claim in result['claims']:
                claim['scope'] = '독립 검증'
            return result
    result = collect_article_evidence({'id': 'fixture', 'title': '시험', 'url': 'https://example.com/ai', 'operator_source_text': TEXT}, OverconfidentProvider(), tmp_path)
    assert all(e['independent_source_checked'] is False for e in result['evidence'])
    assert all('미실시' in e['scope'] for e in result['evidence'])


def test_changed_original_body_keeps_both_private_evidence_receipts(tmp_path):
    first = collect_article_evidence({'id': 'fixture', 'title': '시험', 'url': 'https://example.com/ai', 'operator_source_text': TEXT}, ExtractingProvider(), tmp_path)
    second = collect_article_evidence({'id': 'fixture', 'title': '시험', 'url': 'https://example.com/ai', 'operator_source_text': TEXT + '\n\n새 원문의 확인 조건이 추가되었습니다.'}, ExtractingProvider(), tmp_path)
    assert first['source_sha256'] != second['source_sha256']
    assert len(list(tmp_path.glob('*.json'))) == 2
