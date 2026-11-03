import pytest
from office.analytics import baseline, parse_studio_csv, propose_lessons
from office.store import Store

CSV = """Content,Impressions,Impressions click-through rate (%),Views,Average percentage viewed (%),Average view duration
Total,30000,5.0,1500,40,0:02:00
vid-a,10000,2.0,200,55,0:03:25
"""


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


def test_studio_csv_skips_total_and_parses_duration(tmp_path):
    path = tmp_path / "export.csv"
    path.write_text(CSV, encoding="utf-8")
    rows = parse_studio_csv(path)
    assert len(rows) == 1
    assert rows[0]["external_id"] == "vid-a" and rows[0]["avd_seconds"] == 205.0 and rows[0]["ctr"] == 2.0


def test_malformed_cells_become_none_without_aborting_import(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text(
        "Content,Impressions,Impressions click-through rate (%),Views,Average percentage viewed (%),Average view duration\n"
        "vid-x,N/A,5.0%,--,40,1:xx:yy\nvid-y,100,3.0,50,45,0:01:00\n",
        encoding="utf-8",
    )
    rows = parse_studio_csv(path)
    assert [r["external_id"] for r in rows] == ["vid-x", "vid-y"]
    assert rows[0]["impressions"] is None and rows[0]["views"] is None and rows[0]["avd_seconds"] is None
    assert rows[0]["ctr"] == 5.0 and rows[1]["avd_seconds"] == 60.0


def test_low_ctr_high_retention_proposes_packaging_lesson(store):
    for vid, ctr in (("b1", 5.0), ("b2", 6.0), ("b3", 4.0)):
        store.save_snapshot("youtube_long", vid, "7d", {"ctr": ctr, "avp": 40})
    snap = store.save_snapshot("youtube_long", "vid-a", "7d", {"ctr": 2.0, "avp": 55})
    lessons = propose_lessons(snap, baseline(store.snapshots("youtube_long")))
    assert [l["kind"] for l in lessons] == ["packaging"]


def test_snapshot_period_is_upserted(store):
    store.save_snapshot("shorts", "s1", "24h", {"views": 100, "engaged_views": 80})
    store.save_snapshot("shorts", "s1", "24h", {"views": 400, "engaged_views": 120})
    snaps = store.snapshots("shorts")
    assert len(snaps) == 1 and snaps[0]["metrics"]["views"] == 400
    assert [l["kind"] for l in propose_lessons(snaps[0], {"ctr": None, "avp": None})] == ["hook"]


def test_lessons_wait_for_approval(store):
    lesson = store.add_lesson({"kind": "packaging", "weight_change": {"factor": "outlier", "delta": 5}})
    assert store.lessons("approved") == []
    store.review_lesson(lesson["id"], "approved", "local-operator")
    assert store.lessons("approved")[0]["reviewed_by"] == "local-operator"


def test_duplicate_snapshot_lesson_is_not_added_twice(store):
    lesson = {"kind": "packaging", "evidence": {"snapshot_id": "snap-1"}, "weight_change": {"factor": "outlier", "delta": 5}}
    first = store.add_lesson(lesson)
    second = store.add_lesson(dict(lesson))
    assert second["id"] == first["id"]
    assert len(store.lessons()) == 1


def test_non_finite_analytics_number_is_none():
    from office.analytics import _number
    assert _number("nan") is None
    assert _number("inf") is None


def test_parse_studio_text_skips_total_and_blank_rows():
    from office.analytics import parse_studio_text
    text = "\ufeffContent,Views,Impressions click-through rate (%),Average percentage viewed (%)\nabc123,1200,4.5%,38.2%\nTotal,9999,,\n,,,\n"
    rows = parse_studio_text(text)
    assert [r["external_id"] for r in rows] == ["abc123"]
    assert rows[0]["views"] == 1200 and rows[0]["ctr"] == 4.5


def test_baseline_keeps_observed_zero_separate_from_missing_metrics():
    assert baseline([{"metrics": {"ctr": 0, "avp": 0}}, {"metrics": {"ctr": 10, "avp": 80}},
                     {"metrics": {"ctr": None}}]) == {"ctr": 5, "avp": 40}
    assert baseline([{"metrics": {"ctr": 0, "avp": 0}}]) == {"ctr": 0, "avp": 0}


@pytest.mark.parametrize("metrics,expected", [({"ctr": 0, "avp": 55}, "packaging"),
                                              ({"ctr": 8, "avp": 0}, "promise_mismatch")])
def test_zero_observation_can_propose_a_review_against_positive_baselines(metrics, expected):
    snapshot = {"id": "zero-snapshot", "external_id": "zero-video", "period": "7d", "channel": "youtube_long", "metrics": metrics}
    assert [lesson["kind"] for lesson in propose_lessons(snapshot, {"ctr": 5, "avp": 40})] == [expected]


@pytest.mark.parametrize("base", [{"ctr": 0, "avp": 40}, {"ctr": 5, "avp": 0},
                                  {"ctr": None, "avp": 40}])
def test_missing_or_zero_baselines_do_not_make_relative_performance_claims(base):
    snapshot = {"id": "zero-baseline", "external_id": "zero-video", "period": "7d", "channel": "youtube_long", "metrics": {"ctr": 0, "avp": 0}}
    assert propose_lessons(snapshot, base) == []


def test_approved_lesson_keeps_original_observation_when_snapshot_is_replaced(store):
    original = {"ctr": 0, "avp": 55}
    comparison = {"ctr": 5, "avp": 40}
    snapshot = store.save_snapshot("youtube_long", "vid-a", "7d", original)
    lesson = store.add_lesson(propose_lessons(snapshot, comparison)[0])
    reviewed = store.review_lesson(lesson["id"], "approved", "local-operator")
    updated = store.save_snapshot("youtube_long", "vid-a", "7d", {"ctr": 8, "avp": 10})
    assert updated["id"] == snapshot["id"]
    kept = store.lessons("approved")[0]
    assert kept["id"] == reviewed["id"]
    assert kept["reviewed_at"] == reviewed["reviewed_at"]
    assert kept["evidence"]["metrics"] == original
    assert kept["evidence"]["baseline"] == comparison
    assert kept["evidence"]["channel"] == "youtube_long"
    assert kept["state"] == "approved"


def test_lesson_evidence_does_not_alias_caller_metric_or_baseline_objects():
    snapshot = {"id": "snap-source", "external_id": "vid-a", "period": "7d", "channel": "youtube_long",
                "metrics": {"ctr": 0, "avp": 55}}
    comparison = {"ctr": 5, "avp": 40}
    lesson = propose_lessons(snapshot, comparison)[0]
    snapshot["metrics"]["ctr"] = 8
    comparison["avp"] = 99
    assert lesson["evidence"]["metrics"] == {"ctr": 0, "avp": 55}
    assert lesson["evidence"]["baseline"] == {"ctr": 5, "avp": 40}


@pytest.mark.parametrize("metrics", [{"views": 100, "engaged_views": -1}, {"views": -100, "engaged_views": 1},
                                     {"ctr": -1, "avp": 55}, {"ctr": 8, "avp": -1}])
def test_impossible_negative_observations_cannot_generate_lessons(metrics):
    snapshot = {"id": "snap-source", "external_id": "vid-a", "period": "7d", "channel": "shorts", "metrics": metrics}
    assert propose_lessons(snapshot, {"ctr": 5, "avp": 40}) == []


def test_negative_baselines_are_missing_while_observed_zero_remains_valid():
    snapshots = [{"metrics": {"ctr": -1, "avp": -10}}, {"metrics": {"ctr": 5, "avp": 40}},
                 {"metrics": {"ctr": 0, "avp": 0}}]
    assert baseline(snapshots) == {"ctr": 2.5, "avp": 20}


def test_negative_csv_counts_are_missing_without_erasing_zero():
    from office.analytics import parse_studio_text
    rows = parse_studio_text("Content,Views,Engaged views\nvid-a,100,-1\nvid-b,0,0\n")
    assert rows[0]["engaged_views"] is None
    assert rows[1]["views"] == 0 and rows[1]["engaged_views"] == 0
