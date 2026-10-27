import pytest
from office.ideas import outlier_band, outlier_ratio, rank_ideas, score_idea
from office.store import Store, WorkflowError


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


def test_outlier_bands_follow_channel_average():
    assert outlier_band(outlier_ratio(12000, 1000)) == "10x+"
    assert outlier_band(outlier_ratio(3000, 1000)) == "2-5x"
    assert outlier_band(outlier_ratio(None, 1000)) == "unknown"


def test_idea_without_primary_source_is_blocked_and_sinks():
    good = {"title": "A", "views": 9000, "channel_avg_views": 1000, "demand": 60, "primary_sources": 2, "fit": 0.8}
    weak = {**good, "title": "B", "primary_sources": 0}
    ranked = rank_ideas([weak, good])
    assert ranked[0]["title"] == "A"
    assert ranked[1]["blocked"] == ["1차 출처 없음"]
    assert ranked[1]["score"] == 0.0


def test_ymyl_ai_persona_flag_blocks():
    assert score_idea({"title": "C", "primary_sources": 3, "policy_flags": ["ai_persona_real_person_ymyl"]})["blocked"]


def test_only_approved_lessons_change_weights():
    card = {"title": "D", "demand": 100, "primary_sources": 3, "fit": 1}
    base = score_idea(card)["score"]
    proposed = {"state": "proposed", "weight_change": {"factor": "demand", "delta": 30}}
    assert score_idea(card, lessons=[proposed])["score"] == base
    assert score_idea(card, lessons=[{**proposed, "state": "approved"}])["score"] > base
