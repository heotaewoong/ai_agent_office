"""2026-11-02 operator instruction: rule-based checks must never dead-end the news → draft → approval →
production flow. Format/length/style/number rules become visible advisories; only integrity failures block
(no reviewable HTTPS source, a changed operator original). Human approvals ①② stay human."""
from office.editorial import deterministic_checks, normalize_citations, review_until_ready
from office.gates import run_gates


EVIDENCE = [{"id": f"E{i}", "url": f"https://example.com/{i}", "claim": "사실"} for i in range(1, 4)]


def packet(**overrides):
    base = {"title": "원고", "body": "짧은 본문입니다. " * 20, "evidence": EVIDENCE,
            "titles": ["가", "나", "다"], "hashtags": ["#a", "#b", "#c", "#d", "#e"],
            "video": {"scenes": [{"narration": "말", "caption": "자막"}]}}
    base.update(overrides)
    return base


def test_length_heading_citation_scene_and_style_rules_are_advisories_not_blocks():
    checks = deterministic_checks(packet(body="본문입니다 — 습니다. 됩니다. 입니다. " * 10))
    assert checks["passed"] is True and checks["blocking"] == []
    joined = " ".join(checks["warnings"])
    for expected in ("1,500자", "소제목", "근거 ID", "3~7개", "줄표"):
        assert expected in joined
    assert checks["issues"] == checks["warnings"]


def test_only_integrity_failures_block():
    no_source = deterministic_checks(packet(evidence=[{"id": "E1", "url": "http://insecure.example", "claim": "x"}]))
    assert no_source["passed"] is False and any("HTTPS" in issue for issue in no_source["blocking"])
    changed = deterministic_checks(packet(preserve_original=True, source_input_hash="0" * 64))
    assert changed["passed"] is False and any("원문" in issue for issue in changed["blocking"])


def test_parenthesised_known_evidence_ids_are_normalised_to_brackets():
    known = {"E1", "E2", "E3"}
    assert normalize_citations("설명이에요. (E1, E2, E3)", known) == "설명이에요. [E1][E2][E3]"
    assert normalize_citations("수치예요 (E2) 그리고 [E1, E3]", known) == "수치예요 [E2] 그리고 [E1][E3]"
    assert normalize_citations("（E1）【E2】", known) == "[E1][E2]"
    # Unknown or non-ID parentheses stay untouched: no invented citations.
    assert normalize_citations("(E9) (예: 3개) (GPU)", known) == "(E9) (예: 3개) (GPU)"


class Scripted:
    """Reviews always object; refine returns a short body with parenthesised citations."""

    def __init__(self):
        self.calls = []

    def generate(self, role, messages, schema, options=None):
        self.calls.append(role)
        if role == "refine":
            return {"title": "수정", "body": "수정 본문 (E1, E2, E3)", "video": {"scenes": []}}
        return {"role": role, "score": 70, "passed": False, "critical_issues": ["형식 지적"], "minor_issues": [], "summary": "의견",
                "corrections": []}


def test_review_opinions_never_block_approval_but_are_kept_as_advisories():
    provider = Scripted()
    result = review_until_ready(packet(), provider, checks_fn=deterministic_checks)
    quality = result["quality"]
    assert quality["status"] == "passed" and quality["critical"] is False
    assert provider.calls.count("refine") == 2
    advisories = quality["advisories"]
    assert advisories["model_reviews_passed"] is False
    assert "형식 지적" in " ".join(advisories["review_issues"])
    assert advisories["rule_warnings"]
    # The parenthesised citations from refine were normalised before the final check.
    assert "[E1][E2][E3]" in result["body"]


def test_integrity_block_still_blocks_after_reviews():
    provider = Scripted()
    result = review_until_ready(packet(evidence=[]), provider, checks_fn=deterministic_checks)
    assert result["quality"]["status"] == "blocked" and result["quality"]["critical"] is True


def test_gate_rules_warn_instead_of_block():
    risky = packet(title="합격 보장 99가지", body="본문 " * 50,
                   video={"title": "영상 77", "scenes": [{"narration": "같은 대본 반복 " * 10, "caption": "자막"}]})
    previous = [{"video": {"scenes": [{"narration": "같은 대본 반복 " * 10}]}}]
    report = run_gates(risky, previous, [], {"banned": ["합격 보장"]})
    assert report["status"] == "warn"
    assert {item["rule"] for item in report["items"]} >= {"metadata_numbers", "inauthentic_template", "banned_claim"}
    assert all(item["level"] == "warn" for item in report["items"])


def test_unreadable_news_source_is_a_plain_retryable_failure_not_an_unknown_result(tmp_path, monkeypatch):
    """No paid call is in doubt when the article page cannot be read: fail plainly so the operator can retry
    or pick another article, instead of 'needs_reconciliation'."""
    from office import evidence, worker
    from office.store import Store
    store = Store(tmp_path)
    article = {"id": "unreadable", "title": "읽을 수 없는 기사", "url": "https://example.com/blocked", "evidence": []}
    store.save_articles([article])
    job = store.create_job(article)
    task = store.enqueue("draft", {"job_id": job["id"], "source_hash": None}, key="draft:unreadable")

    def blocked_fetch(*args, **kwargs):
        raise OSError("403 Forbidden")
    monkeypatch.setattr(evidence, "fetch_public", blocked_fetch)

    def run_draft(store, task):
        evidence.collect_article_evidence(store.job(task["payload"]["job_id"])["article"], None, tmp_path)
    monkeypatch.setattr(worker, "process_task", run_draft)
    worker.run_once(store, "worker")
    assert store.task(task["id"])["state"] == "failed"
    assert store.job(job["id"])["state"] == "blocked"
    assert "다른 기사" in store.job(job["id"])["error"]


def test_runtime_inspection_accepts_the_operator_raised_cap_up_to_the_ceiling(tmp_path):
    """2026-11-02: the operator raised the total API cap to 30,000 KRW for the demo; that is not an integrity issue."""
    from office.runtime import BUDGET_CEILING_KRW, inspect_state
    from office.store import Store
    store = Store(tmp_path)
    with store.connection(transaction=True) as db:
        db.execute("UPDATE settings SET value=? WHERE key='budget_cap'", (str(BUDGET_CEILING_KRW),))
    assert BUDGET_CEILING_KRW == 30000
    assert {"code": "budget_exceeded"} not in inspect_state(store, set())["issues"]
    with store.connection(transaction=True) as db:
        db.execute("UPDATE settings SET value=? WHERE key='budget_cap'", (str(BUDGET_CEILING_KRW + 1),))
    assert {"code": "budget_exceeded"} in inspect_state(store, set())["issues"]


def test_all_price_validity_windows_cover_the_interview_period():
    """2026-11-02: text pricing expired at 2026-11-02 00:00 KST and every model call failed. All prices were
    re-checked on the official pages on 2026-11-02 (Gemini's page states the rates hold through 2026-12-31)."""
    from datetime import datetime
    from office import image_provider, openai_speech, speech_provider, video_provider
    from office.providers import DEFAULT_PRICE_VALID_UNTIL, OPENAI_PRICE_CHECKED
    deadline = datetime.fromisoformat("2026-11-30T00:00:00+00:00")
    for value in (DEFAULT_PRICE_VALID_UNTIL, image_provider.PRICE_VALID_UNTIL, openai_speech.PRICE_VALID_UNTIL,
                  speech_provider.PRICE_VALID_UNTIL, video_provider.PRICE_VALID_UNTIL):
        assert datetime.fromisoformat(value) >= deadline, value
    assert OPENAI_PRICE_CHECKED == "2026-11-02"


def test_card_length_and_style_rules_warn_but_unrenderable_cards_still_block():
    """2026-11-02 staging run: one 71-character card body (fits at the drawn size) dropped all card news from
    production. Character limits/duplicates/style are advisories; empty, wrong count or overflowing cards block."""
    from office.cards import card_checks
    slides = [{"title": f"{n}번째 핵심", "body": "카드 본문은 짧게 씁니다."} for n in range(1, 8)]
    slides[5]["body"] = "회사 발표와 현장 성과를 구분해서 읽으면 우리 팀에 맞는 적용점을 훨씬 빠르게 찾을 수 있어요. 오늘 하나만 골라 보세요."
    # An unbreakable run that cannot be drawn at the minimum size is a real overflow and still blocks.
    unbreakable = [dict(s) for s in slides]
    unbreakable[5]["body"] = "가" * 71
    assert card_checks({"slides": unbreakable}, {"terms": {}, "banned": [], "voice": "", "pronunciation": {}})["passed"] is False
    checks = card_checks({"slides": slides}, {"terms": {}, "banned": [], "voice": "", "pronunciation": {}})
    assert checks["passed"] is True and checks["blocking"] == []
    assert any("60자" in issue for issue in checks["warnings"])
    empty = [dict(s) for s in slides]
    empty[0]["body"] = ""
    blocked = card_checks({"slides": empty}, {"terms": {}, "banned": [], "voice": "", "pronunciation": {}})
    assert blocked["passed"] is False and any("필요해요" in issue for issue in blocked["blocking"])
    assert card_checks({"slides": slides[:3]}, {"terms": {}, "banned": [], "voice": "", "pronunciation": {}})["passed"] is False
