from office.bootstrap import korean_cards
from office.editorial import review_until_ready
from office.gates import run_gates
from office.korean import card_source_hash, check_texts, clean_feed_summary, korean_card, sentence_issues
from office.store import Store, WorkflowError


def test_particles_follow_final_consonant_and_skip_real_words():
    assert sentence_issues("에이전트를 만들고 모델을 비교해요. 책을 읽고 마을로 가요. 서울로 이동해요. 효과와 결과를 봐요. 돈을 모을 수 있어요.") == []
    issues = "\n".join(sentence_issues("에이전트을 만들고 모델를 비교해요. 서울으로 가요. 회사으로 가요. 책와 연필."))
    assert "'에이전트를'" in issues and "'모델을'" in issues and "'서울로'" in issues and "'회사로'" in issues and "'책과'" in issues


def test_latin_or_number_before_particle_is_not_judged():
    assert sentence_issues("AI를 쓰고 GPT을 비교해요. 3을 더해요.") == []


def test_translationese_double_passive_repeat_and_long_sentence():
    joined = "\n".join(check_texts([
        "이 모델은 좋은 성능을 가지고 있어요. 개발에 있어서 중요해요. 자동화하는 것이 가능해요. 데이터가 처리되어지는 방식이에요.",
        "같은 같은 말을 반복해요.",
        "이번 발표에서 회사는 새로운 에이전트 도구를 공개했고 이 도구는 고객 문의를 자동으로 분류하고 적절한 담당자에게 넘기며 처리 결과를 대시보드에 기록하고 주간 보고서까지 만들어 주는데 아직 한국어 지원은 제한적이라고 밝혔어요.",
    ]))
    for expected in ("가지고 있다", "에 있어서", "것이 가능", "이중 피동", "반복", "나누세요"):
        assert expected in joined, expected


def test_markdown_tables_and_links_are_not_checked():
    assert check_texts(["| 모델를 | 값 |\n|---|---|\nhttps://example.com/모델를"]) == []


def test_arxiv_boilerplate_is_removed():
    assert clean_feed_summary("arXiv:2610.35817v2 Announce Type: replace-cross Abstract: A robot policy needs") == "A robot policy needs"
    assert clean_feed_summary("Fast, focused decisions.") == "Fast, focused decisions."


class ReviewProvider:
    def __init__(self, korean_passes=True):
        self.calls = []
        self.korean_passes = korean_passes

    def generate(self, role, messages, schema, options=None):
        self.calls.append(role)
        if role == "refine":
            return {"title": "수정", "body": "수정 본문", "video": {"scenes": []}}
        if role == "korean":
            assert "corrections" in schema["required"]
            fix = {"field": "body", "original": "이 기능의 목적은 비용을 줄인다", "revised": "이 기능의 목적은 비용을 줄이는 것이다", "reason": "주어와 서술어 호응"}
            return {"role": role, "score": 92 if self.korean_passes else 55, "passed": self.korean_passes, "critical_issues": [] if self.korean_passes else ["주어와 서술어가 호응하지 않음"], "minor_issues": [], "summary": "국어", "corrections": [] if self.korean_passes else [fix]}
        return {"role": role, "score": 90, "passed": True, "critical_issues": [], "minor_issues": [], "summary": "검토"}


def test_korean_review_failure_sends_corrections_to_refine_and_blocks():
    provider = ReviewProvider(korean_passes=False)
    result = review_until_ready({"title": "원고", "body": "본문", "evidence": []}, provider)
    assert provider.calls.count("korean") == 3 and provider.calls.count("refine") == 2
    korean = result["quality"]["korean"]
    assert result["quality"]["status"] == "blocked" and korean["passed"] is False
    assert korean["corrections"][0]["revised"].endswith("줄이는 것이다")


def test_korean_review_pass_is_recorded():
    result = review_until_ready({"title": "원고", "body": "본문", "evidence": []}, ReviewProvider())
    assert result["quality"]["status"] == "passed"
    assert result["quality"]["korean"]["passed"] is True and result["quality"]["korean"]["score"] == 92


def test_gates_warn_on_korean_rules_after_human_edit_without_blocking():
    packet = {"title": "에이전트을 비교", "body": "서울으로 가요.", "evidence": [], "quality": {"korean": {"passed": False, "corrections": [{"x": 1}]}}}
    report = run_gates(packet)
    rules = {item["rule"] for item in report["items"]}
    assert {"korean_grammar", "korean_review"} <= rules
    assert all(item["level"] == "warn" for item in report["items"] if item["rule"].startswith("korean"))


class CardProvider:
    def __init__(self, first=None, second=None, fail=False):
        self.calls = []
        self.first = first or {"headline": "구글이 빠른 판단용 Decisions API를 공개했다", "summary": "구글이 짧은 판단을 빠르게 내리는 API를 공개했어요. 분류처럼 경계가 분명한 일에 맞춰 비용을 낮췄어요.", "why": "고객 문의 분류를 자동화하려는 팀이 볼 만해요."}
        self.second = second
        self.fail = fail

    def generate(self, role, messages, schema, options=None):
        if self.fail:
            raise WorkflowError("기존 Gemini 연결이 없습니다")
        self.calls.append((role, messages))
        return self.second if role == "card_ko_fix" else self.first


def article(**extra):
    return {"id": "a1", "title": "Build more responsive apps with the Decisions API", "summary": "Fast, focused, low-cost decisions for any application.", "feed_name": "Google", "score": 80, "published_at": "2026-10-29T00:00:00+00:00", **extra}


def test_card_is_generated_and_checked():
    provider = CardProvider()
    card = korean_card(article(), provider)
    assert [c[0] for c in provider.calls] == ["card_ko"]
    assert card["check"]["passed"] is True and card["check"]["fixed_once"] is False
    assert card["source_hash"] == card_source_hash(article())


def test_card_with_grammar_error_is_fixed_once_with_issue_list():
    bad = {"headline": "구글이 API을 공개했어요", "summary": "구글이 모델를 공개했어요. 서울으로 확대해요.", "why": "볼 만해요."}
    good = {"headline": "구글이 판단용 API를 공개했다", "summary": "구글이 새 모델을 공개했어요. 서울로 확대해요.", "why": "자동화 팀이 볼 만해요."}
    provider = CardProvider(first=bad, second=good)
    card = korean_card(article(), provider)
    assert [c[0] for c in provider.calls] == ["card_ko", "card_ko_fix"]
    assert "모델을" in provider.calls[1][1][-1]["content"]
    assert card["check"]["passed"] is True and card["check"]["fixed_once"] is True and card["headline"] == good["headline"]


def test_english_card_fails_check():
    card = korean_card(article(), CardProvider(first={"headline": "Google ships API", "summary": "Fast decisions.", "why": "Useful."}, second={"headline": "Google ships API", "summary": "Fast decisions.", "why": "Useful."}))
    assert card["check"]["passed"] is False and any("한국어" in issue for issue in card["check"]["issues"])


def test_refresh_cards_reuse_same_source_and_stop_without_provider(tmp_path):
    store = Store(tmp_path)
    provider = CardProvider()
    first = korean_cards(store, [article()], provider=provider, limit=5)
    assert first[0]["card_ko"]["headline"] and len(provider.calls) == 1
    store.save_articles(first)
    again = korean_cards(store, [article()], provider=provider, limit=5)
    assert len(provider.calls) == 1 and again[0]["card_ko"] == first[0]["card_ko"]
    changed = korean_cards(store, [article(summary="New description")], provider=CardProvider(fail=True), limit=5)
    assert "card_ko" not in changed[0]
    event = [e for e in store.events(limit=5) if e["kind"] == "korean_cards"][0]
    assert "Gemini" in (event["data"]["stopped"] or "")


class BlockedFirstProvider(CardProvider):
    def generate(self, role, messages, schema, options=None):
        if '"title": "blocked"' in messages[-1]["content"]:
            raise WorkflowError("같은 모델 호출이 진행 중이거나 결과 불명입니다. 먼저 비용·결과 대사가 필요합니다")
        return super().generate(role, messages, schema, options)


def test_unknown_result_article_is_skipped_and_spare_fills_the_slot(tmp_path):
    store = Store(tmp_path)
    articles = [article(id="b", title="blocked", score=90), article(id="c", title="second", score=80), article(id="d", title="spare", score=70)]
    result = {a["id"]: a for a in korean_cards(store, articles, provider=BlockedFirstProvider(), limit=2)}
    assert "card_ko" not in result["b"] and result["c"]["card_ko"] and result["d"]["card_ko"]
    event = [e for e in store.events(limit=5) if e["kind"] == "korean_cards"][0]
    assert event["data"]["skipped_unknown"] == ["b"] and event["data"]["stopped"] is None and event["data"]["made"] == 2


def test_card_style_mixed_endings_and_template_reason_are_flagged():
    from office.korean import card_style_issues
    bad = {"headline": "연구진이 벤치마크를 공개했어요.", "summary": "연구진이 시험을 만들었다. 에이전트가 직접 구현해야 해요.", "why": "능력을 확인할 수 있기 때문이에요."}
    joined = " / ".join(card_style_issues(bad))
    assert "마침표 없이" in joined and "해요체" in joined and "때문이에요" in joined
    fragment = {"headline": "연구진이 시험을 만들었다", "summary": "연구진이 시험을 만들었어요. 직접 구현해야 해요.", "why": "보안성을 파악할 수 있어서."}
    assert any("완결 문장" in issue for issue in card_style_issues(fragment))
    good = {"headline": "연구진이 시험을 만들었다", "summary": "연구진이 시험을 만들었어요. 직접 구현해야 해요.", "why": "맡겨도 될지 가늠할 기준이 생겨요."}
    assert card_style_issues(good) == []


def test_card_prompt_separates_feed_from_actor_and_handles_empty_description():
    from office.korean import CARD_PROMPT
    assert "발표 주체는 url로 정한다" in CARD_PROMPT and "feed 이름만 보고 주어를 정하지 않는다" in CARD_PROMPT
    assert "제목만 보고 정리했어요" in CARD_PROMPT


class BusyProvider(CardProvider):
    def __init__(self, fail_titles):
        super().__init__()
        self.fail_titles = fail_titles

    def generate(self, role, messages, schema, options=None):
        if any(f'"title": "{t}"' in messages[-1]["content"] for t in self.fail_titles):
            raise WorkflowError("모델 제공자가 HTTP 503를 반환했습니다. 자동 재시도 없이 확인이 필요합니다")
        return super().generate(role, messages, schema, options)


def test_busy_provider_skips_article_and_stops_after_three_in_a_row(tmp_path):
    store = Store(tmp_path)
    arts = [article(id=f"a{i}", title=f"t{i}", score=100 - i) for i in range(6)]
    result = {a["id"]: a for a in korean_cards(store, arts, provider=BusyProvider({"t0", "t2"}), limit=4)}
    assert "card_ko" not in result["a0"] and result["a1"]["card_ko"] and "card_ko" not in result["a2"] and result["a3"]["card_ko"] and result["a4"]["card_ko"]
    event = [e for e in store.events(limit=5) if e["kind"] == "korean_cards"][0]
    assert event["data"]["skipped_unknown"] == ["a0", "a2"] and event["data"]["stopped"] is None
    store2 = Store(tmp_path / "b")
    fresh = [article(id=f"a{i}", title=f"t{i}", score=100 - i) for i in range(6)]
    result2 = {a["id"]: a for a in korean_cards(store2, fresh, provider=BusyProvider({"t0", "t1", "t2", "t3"}), limit=4)}
    assert not any(result2[f"a{i}"].get("card_ko") for i in range(4))
    event2 = [e for e in store2.events(limit=5) if e["kind"] == "korean_cards"][0]
    assert "503" in event2["data"]["stopped"] and event2["data"]["skipped_unknown"] == ["a0", "a1", "a2"]


def test_seed_headlines_pass_korean_rules():
    import json
    from pathlib import Path
    seed = json.loads((Path(__file__).resolve().parents[1] / "config/editorial-seed.json").read_text(encoding="utf-8"))
    for item in seed["selected"]:
        assert check_texts([item["headline_ko"], item["hook_ko"], item["reader_value_ko"], item["blog_angle_ko"]]) == [], item["headline_ko"]
        assert ":" not in item["headline_ko"] and not item["headline_ko"].endswith(".")
