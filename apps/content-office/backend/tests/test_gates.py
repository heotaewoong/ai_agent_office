from office.gates import disclosure_decision, run_gates


def packet(title="AI 도구 비교", body="세 가지 도구를 비교한다", narration="에이전트 팀이 원고를 나눠 쓰고 검수까지 마치는 과정을 보여 준다"):
    return {"title": title, "body": body, "evidence": [{"claim": "공식 발표에 따르면 사용자는 120만 명", "numbers": ["120만"]}],
            "video": {"title": "사용자 120만 명", "description": "", "tags": [], "scenes": [{"narration": narration}]}}


def test_metadata_number_without_evidence_blocks():
    report = run_gates(packet(title="AI 도구 7가지"))
    assert report["status"] == "block"
    assert any("숫자 7" in item["message"] for item in report["items"])


def test_metadata_number_only_in_body_warns():
    report = run_gates(packet(title="AI 도구 3가지", body="도구 3가지를 비교한다"))
    assert report["status"] == "warn"


def test_repeated_template_blocks_as_inauthentic():
    previous = [packet()]
    assert [i["rule"] for i in run_gates(packet(), previous)["items"]] == ["inauthentic_template"]
    assert run_gates(packet(narration="완전히 다른 주제로 직접 촬영한 화면을 설명한다"), previous)["status"] == "pass"


def test_disclosure_only_for_realistic_synthetic_assets():
    assert disclosure_decision([{"kind": "stylized_broll"}, {"kind": "own_voice_clone"}])["youtube_altered_content"] is False
    assert disclosure_decision([{"kind": "realistic_person", "label": "가상 인물 인터뷰"}])["reasons"] == ["가상 인물 인터뷰"]


def test_ymyl_persona_and_banned_claim_block():
    p = {**packet(), "topic": "finance"}
    assert run_gates(p, assets=[{"kind": "ai_persona_real_person"}])["status"] == "block"
    brand = {"banned": ["수익 보장"], "voice": "", "terms": {}, "pronunciation": {}}
    assert run_gates(packet(body="이 방법은 수익 보장"), brand=brand)["status"] == "block"


def test_thousands_separator_matches_plain_number():
    p = packet(title="사용자 1,200개 사례")
    p["evidence"].append({"claim": "집계", "numbers": ["1200"]})
    assert run_gates(p)["status"] == "pass"
