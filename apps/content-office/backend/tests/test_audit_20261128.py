"""2026-11-28 전체 점검에서 고친 두 가지의 회귀 시험."""
import pytest

from office import harness
from office.private_books import BOOK_SOURCE_KIND, low_information_chunk


def packet():
    return {"title": "t", "body": "본문 [E1][B1]", "evidence": [
        {"id": "E1", "url": "https://example.com", "source_quote": "공개 문단", "source_kind": "approved_public_evidence"},
        {"id": "B1", "url": "book://abc", "source_quote": "책 원문 문장", "source_kind": BOOK_SOURCE_KIND, "book_title": "책"}]}


def test_gemini_judge_gets_no_book_text_unless_paid(monkeypatch):
    monkeypatch.delenv("HEOBRAIN_GEMINI_PAID", raising=False)
    view, masked = harness.judge_view(packet(), "gemini-3.5-flash-lite")
    assert masked == 1
    quotes = {e["id"]: e["source_quote"] for e in view["evidence"]}
    assert quotes["E1"] == "공개 문단" and "책 원문" not in quotes["B1"]
    monkeypatch.setenv("HEOBRAIN_GEMINI_PAID", "1")
    assert harness.judge_view(packet(), "gemini-3.5-flash-lite")[1] == 0


def test_openai_judge_keeps_book_text(monkeypatch):
    monkeypatch.delenv("HEOBRAIN_GEMINI_PAID", raising=False)
    view, masked = harness.judge_view(packet(), "gpt-5.4")
    assert masked == 0 and any(e["source_quote"] == "책 원문 문장" for e in view["evidence"])


def test_masked_judge_call_never_sends_book_text(monkeypatch):
    monkeypatch.delenv("HEOBRAIN_GEMINI_PAID", raising=False)
    sent = {}

    class Fake:
        def generate(self, role, messages, schema, options=None):
            sent["system"], sent["user"] = messages[0]["content"], messages[1]["content"]
            return {"axes": {axis: {"passed": True, "reason": "ok"} for axis in harness.BINARY_AXES}}

    out = harness.run_binary_judge(packet(), Fake(), w_type="W3", gen_model="gpt-5.4-mini", judge_model="gemini-3.5-flash-lite", brief={})
    assert "책 원문 문장" not in sent["user"] and "원문을 보내지 않았다" in sent["system"] and out["masked_book_quotes"] == 1


@pytest.mark.parametrize("text,low", [
    ("CHAPTER\n4\n실전 개발 2:\n콘텐츠 생산 AI 팀 구축", True),
    ("PART IV\n\nLLM 성능 평가\n\nLLM 평가의 중요성 225\n\n17.1 LLM의 예측 불가능성 225\n\n17.2 안정적인 평가 체계 226\n\n17.3 골든 데이터셋 만들기 228", True),
    ("골든 데이터셋은 이러한 선택지를 동일한 조건에서 비교하게 해 준다. 검색 알고리즘을 개선하거나 새로운 청킹 전략을 시도할 때마다 "
     "같은 데이터셋으로 성능을 재면 변경의 효과를 숫자로 확인할 수 있다.", False),
    ("에이전트는 도구를 고르고 결과를 보고 다음 행동을 정한다.", False),
])
def test_low_information_book_chunks(text, low):
    assert low_information_chunk(text) is low
