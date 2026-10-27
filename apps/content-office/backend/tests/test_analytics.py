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
