import pytest

from office.editorial import deterministic_checks, prepare_source, review_until_ready
from office.store import Store
from tests.test_agent_editorial import FullProvider, evidence_job


def packet_with_markers(markers):
    packet = FullProvider("AI 도구 비교")._packet()
    packet["body"] = packet["body"].replace("[E1]", markers)
    packet["evidence"] = [{"id": id_, "url": "https://example.com/a"} for id_ in ("E1", "E2")]
    return packet


@pytest.mark.parametrize("markers", ["[E1] [E2]", "(E1) (E2)", "(E1, E2)", "[E1, E2]", "( E1 , E2 )"])
def test_bracketed_evidence_groups_link_all_exact_ids(markers):
    assert deterministic_checks(packet_with_markers(markers))["passed"] is True


@pytest.mark.parametrize("markers", ["(E10, E2)", "[E10] [E2]", "E1 E2", "(E1, E2]", "(E1 설명) (E2)"])
def test_prefixes_bare_ids_and_malformed_groups_do_not_link_missing_id(markers):
    issues = deterministic_checks(packet_with_markers(markers))["issues"]
    assert "모든 핵심 근거 ID를 원고에 연결해야 합니다" in issues
    if "E10" in markers:
        assert "존재하지 않는 근거 ID가 인용되었습니다" in issues


def test_unknown_id_inside_group_is_not_hidden_by_known_ids():
    issues = deterministic_checks(packet_with_markers("(E1, E2, E99)"))["issues"]
    assert "존재하지 않는 근거 ID가 인용되었습니다" in issues


def test_generation_and_refinement_receive_same_body_contract(tmp_path):
    class ContractProvider(FullProvider):
        def generate(self, role, messages, schema, options=None):
            if role in ("gen", "refine"):
                text = messages[0]["content"] + messages[-1]["content"]
                assert "1350~1650" in text
                assert "## " in text and "최소 3개" in text
                assert "[E1]" in text
                if role == "refine":
                    assert "이미 통과한" in text and "소제목" in text and "보존" in text
            return super().generate(role, messages, schema, options)

    store = Store(tmp_path)
    job = evidence_job(store)
    provider = ContractProvider("AI 도구 비교", fail_critique_once=True)
    result = prepare_source(store, job["id"], provider=provider)
    assert result["source_packet"]["quality"]["status"] == "passed"
    assert provider.roles.count("refine") == 1
    assert result["source_approval"] is None and result["release_approval"] is None


def test_refinement_structure_issue_remains_visible_as_advisory():
    class LosingStructure(FullProvider):
        def generate(self, role, messages, schema, options=None):
            result = super().generate(role, messages, schema, options)
            if role == "refine":
                result["body"] = result["body"].replace("## ", "")
            return result

    packet = packet_with_markers("[E1] [E2]")
    result = review_until_ready(packet, LosingStructure("AI 도구 비교", fail_critique_once=True), checks_fn=deterministic_checks)
    assert result["quality"]["status"] == "passed"
    assert result["quality"]["refine_count"] >= 1
    assert any("소제목" in issue for issue in result["quality"]["deterministic_checks"]["issues"])
