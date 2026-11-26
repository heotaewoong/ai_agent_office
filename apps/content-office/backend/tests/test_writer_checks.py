"""글쓰기 0원 검사(writer_checks)를 v2_harness에 붙인 동작.

기본 off는 예전과 같고, warn은 기록만 하고, enforce는 규칙 점수에 넣어 고치게 하고 사실을 잃은 고친 판은 되돌린다.
"""
import pytest

from office.editorial import prepare_source
from office.harness_rules import validate_packet
from office.store import Store, WorkflowError
from office.writer_checks import RULES, copy_runs, fact_keep, quote_match, resolve_writer_checks, writer_findings
from test_agent_editorial import FullProvider, evidence_job
from test_harness import EVIDENCE, Stub, good_body, packet, run, verdict

BASE = {"passed": True, "issues": [], "blocking": [], "warnings": []}
PUBLIC = {"id": "E2", "claim": "기획 승인⓪에서 선택한 공개 원문 발췌", "url": "https://example.com/b", "numbers": [],
          "source_quote": "관계자는 실제 사업 현장에서 활용되는 웹서비스로 이어지고 있다고 말했다. 이용자는 15% 늘었다."}
ENGLISH = {"id": "E3", "claim": "기획 승인⓪에서 선택한 공개 원문 발췌", "url": "https://example.com/c", "numbers": [],
           "source_quote": "Tool timeouts can leave AI agents facing ambiguous tool outcomes. The plan certified 28 completions."}
EVIDENCE_PLUS = [*EVIDENCE, PUBLIC, ENGLISH]
DROPPED = good_body().replace("도구 3가지를", "도구들을")


def with_evidence(body):
    return {**packet(body), "evidence": EVIDENCE_PLUS}


def test_mode_defaults_off_and_unknown_values_are_refused(monkeypatch, tmp_path):
    monkeypatch.delenv("HEOBRAIN_WRITER_CHECKS", raising=False)
    store = Store(tmp_path)
    assert resolve_writer_checks(store) == "off" and resolve_writer_checks() == "off"
    store.set_setting("writer_checks", "warn")
    assert resolve_writer_checks(store) == "warn"
    monkeypatch.setenv("HEOBRAIN_WRITER_CHECKS", "strict")
    with pytest.raises(WorkflowError, match="글쓰기 0원 검사"):
        resolve_writer_checks()
    with pytest.raises(WorkflowError, match="글쓰기 0원 검사"):
        run(Stub(), packet(), writer_checks="strict")


def test_off_leaves_validation_exactly_as_before():
    current = with_evidence(good_body() + "\n\n이용자는 15% 줄었어요 [E2]. 결론적으로 좋아요.")
    plain = validate_packet(current, base_checks=BASE, w_type="W3")
    assert plain == validate_packet(current, base_checks=BASE, w_type="W3", writer={"mode": "off"})
    assert "writer_checks" not in plain and not set(RULES) & set(plain["rule_scores"])


def test_warn_records_without_touching_scores_or_issues():
    current = with_evidence(good_body() + "\n\n이용자는 15% 줄었어요 [E2].")
    plain = validate_packet(current, base_checks=BASE)
    warned = validate_packet(current, base_checks=BASE, writer={"mode": "warn"})
    assert {key: warned[key] for key in plain} == plain
    assert warned["writer_checks"]["mode"] == "warn" and warned["writer_checks"]["issues"]["direction_cited"]


def test_enforce_scores_quotes_directions_and_ai_tells():
    bad = with_evidence(good_body() + '\n\n관계자는 "실제 사업 현장에서 쓰이는 앱으로 바뀌고 있다"라고 했어요 [E2]. 이용자는 15% 줄었어요 [E2].'
                        "\n\n결론적으로 이 순서가 좋아요.")
    result = validate_packet(bad, base_checks=BASE, writer={"mode": "enforce"})
    scores = result["rule_scores"]
    assert scores["quote_exact"] is False and scores["direction_cited"] is False and scores["ai_tells"] is False
    assert scores["fact_keep"] is True and result["passed"] is False
    assert any("근거에 없는 인용" in issue for issue in result["issues"])
    good = with_evidence(good_body() + '\n\n관계자는 "실제 사업 현장에서 활용되는 웹서비스로 이어지고 있다"라고 했어요 [E2]. 이용자는 15% 늘었어요 [E2].'
                         '\n\n연구진은 "도구 시간 초과가 모호한 결과를 남긴다"라고 적었어요 [E3].')
    clean = validate_packet(good, base_checks=BASE, writer={"mode": "enforce"})
    assert all(clean["rule_scores"][name] for name in RULES) and clean["writer_checks"]["quotes_translated"] == 1


def test_overclaims_already_checked_by_style_rules_are_not_repeated():
    found = writer_findings(packet(good_body() + "\n\n무조건 합격하는 방법이에요."))
    assert not found["issues"]["ai_tells"]


def test_enforce_rolls_back_a_fix_that_drops_a_supported_number():
    first = good_body()
    stub = Stub(judges=[verdict(completeness="비교축이 빠짐")], refines=[DROPPED])
    result = run(stub, packet(first), writer_checks="enforce")
    harness = result["quality"]["harness"]
    assert stub.calls == ["judge", "refine"] and result["body"] == first
    assert harness["rolled_back"] is True and "fact_keep" in harness["deterioration"]["regressed_rules"]
    assert harness["writer_checks"]["mode"] == "enforce"


def test_off_and_warn_keep_the_same_fix():
    for mode in ("off", "warn"):
        stub = Stub(judges=[verdict(completeness="비교축이 빠짐"), verdict()], refines=[DROPPED])
        result = run(stub, packet(good_body()), writer_checks=mode)
        harness = result["quality"]["harness"]
        assert stub.calls == ["judge", "refine", "judge"] and result["body"] == DROPPED and harness["rolled_back"] is False
        if mode == "off":
            assert "writer_checks" not in harness
        else:
            assert harness["writer_checks"]["issues"]["fact_keep"]


def test_numbers_in_sentences_the_judge_flagged_may_be_dropped():
    flagged = verdict(groundedness="E1이 받치지 않는 문장")
    flagged["ungrounded_sentences"] = ["도구 3가지를 실제 화면으로 비교해요 [E1]."]
    stub = Stub(judges=[flagged, verdict()], refines=[DROPPED])
    result = run(stub, packet(good_body()), writer_checks="enforce")
    assert result["quality"]["harness"]["rolled_back"] is False and result["body"] == DROPPED


def test_fact_keep_and_quote_match_basics():
    sources = {"E3": ("The plan certified 28 completions.", True), "E2": ("홈페이지는 2.6배 증가했다.", True)}
    before = "계획은 28개 완료를 인증했어요 [E3].\n\n홈페이지는 2.6배 늘었어요 [E2]. GPT5 기준이에요."
    assert fact_keep(before, before, sources) == []
    assert ("숫자", "28") in fact_keep(before, "홈페이지는 2.6배 늘었어요 [E2]. GPT5 기준이에요.", sources)
    lost = fact_keep(before, "계획은 28개 완료를 인증했어요 [E3].\n\n홈페이지는 2.6배 줄었어요 [E2].", sources)
    assert ("이름", "GPT5") in lost and any(kind == "방향" for kind, _ in lost)
    assert fact_keep(before + "\n\n완료는 99개였어요 [E3].", before, sources) == []
    assert quote_match("실제 사업 현장", "관계자는 실제 사업, 현장에서") == 1.0 and quote_match("전혀 다른 말", "관계자는 실제") < 0.8


def test_copy_overlap_flags_five_words_copied_outside_quotes():
    copied = with_evidence(good_body() + "\n\n관계자는 실제 사업 현장에서 활용되는 웹서비스로 이어지고 있다고 해요 [E2].")
    found = writer_findings(copied)
    assert len(found["issues"]["copy_overlap"]) == 1 and "E2" in found["issues"]["copy_overlap"][0]
    enforced = validate_packet(copied, base_checks=BASE, writer={"mode": "enforce"})
    assert enforced["rule_scores"]["copy_overlap"] is False and enforced["passed"] is False
    # 따옴표로 인용하면 베끼기가 아니라 인용 대조(quote_exact) 몫이다
    quoted = with_evidence(good_body() + '\n\n관계자는 "실제 사업 현장에서 활용되는 웹서비스로 이어지고 있다"라고 했어요 [E2].')
    assert not writer_findings(quoted)["issues"]["copy_overlap"]
    # 내 말로 풀어 쓰면 통과한다
    own = with_evidence(good_body() + "\n\n현장에서 실제로 쓰는 서비스가 늘고 있대요 [E2].")
    assert not writer_findings(own)["issues"]["copy_overlap"]


def test_copy_runs_ignores_short_and_number_heavy_runs():
    source = "시험은 2026년 3월 7일 1차 필기 접수 시작이며 합격 기준은 과목당 40점 이상이다"
    assert copy_runs("필기 접수 시작이며 합격 기준은 과목당 40점 이상이에요", source) == ["필기 접수 시작이며 합격 기준은 과목당 40점"]
    assert copy_runs("합격 기준은 과목당 40점", source) == []  # 네 낱말은 베끼기로 세지 않는다
    assert copy_runs("2026년 3월 7일 1차 필기", source) == []  # 날짜와 번호뿐인 구간
    # 한글 없는 영어 구간은 용어·제목이 많아 여덟 낱말부터 센다. 붙임표 용어는 한 낱말이다
    assert copy_runs("The plan certified 28 completions today", "The plan certified 28 completions.") == []
    assert copy_runs("우리는 route-to-sink enforcement cut 방식을 봐요", "route-to-sink enforcement cut the leak") == []
    long_en = "agents facing ambiguous tool outcomes can recover by checking public evidence first"
    assert copy_runs("연구는 " + long_en + " 라고 정리해요", long_en) == [long_en]


def test_copy_overlap_ignores_the_owners_own_text():
    owned = {"id": "E9", "claim": "오너가 쓴 합격 후기", "source_kind": "owner_supplied",
             "source_quote": "편입 시험 한 달 전, 김영편입 모의고사 성적이 상위 70%였습니다"}
    body = good_body() + "\n\n편입 시험 한 달 전, 김영편입 모의고사 성적이 상위 70%였어요 [E9]."
    assert not writer_findings({**packet(body), "evidence": [*EVIDENCE_PLUS, owned]})["issues"]["copy_overlap"]
    stranger = {**owned, "source_kind": "http_article_body"}
    assert writer_findings({**packet(body), "evidence": [*EVIDENCE_PLUS, stranger]})["issues"]["copy_overlap"]


def test_prepare_source_threads_the_setting(tmp_path, monkeypatch):
    monkeypatch.delenv("HEOBRAIN_EDITORIAL_ENGINE", raising=False)
    monkeypatch.delenv("HEOBRAIN_WRITER_CHECKS", raising=False)
    store = Store(tmp_path)
    store.set_setting("editorial_engine", "v2_harness")
    store.set_setting("writer_checks", "warn")
    job = evidence_job(store)

    class Routed(FullProvider):
        model = "gemini-3.8-flash"
        judge_model = "gpt-5.4-mini"

        def generate(self, role, messages, schema, options=None):
            if role == "judge":
                self.roles.append(role)
                return verdict()
            return super().generate(role, messages, schema, options)
    result = prepare_source(store, job["id"], provider=Routed("AI 도구 비교"))
    harness = result["source_packet"]["quality"]["harness"]
    assert harness["engine"] == "v2_harness" and harness["writer_checks"]["mode"] == "warn"
    assert not result["source_approval"]
