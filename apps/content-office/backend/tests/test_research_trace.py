"""자료 조사 기록: 바깥 호출 0회인 조사도 종료 기록이 남고, 결과에는 기록용 칸이 새지 않는다."""
from office.external_research import run_research
from office.research_trace import read_research_traces


def offline(url, *, maximum):
    raise OSError("offline")


def no_library(root, query):
    return 0


def test_blocked_and_no_call_research_still_leave_a_trace(tmp_path):
    blocked = run_research(tmp_path, "연예인 열애설 정리", kind="W5", area="E", fetch=offline, fact_sources=no_library)
    quiet = run_research(tmp_path, "회사를 그만두고 배운 것", area="D", experience_first=True, fetch=offline, fact_sources=no_library)
    assert "_trace" not in blocked and "_trace" not in quiet
    rows = read_research_traces(tmp_path)
    assert [row["status"] for row in rows] == ["blocked", "no_outside_call"]
    assert rows[0]["plan"]["blocked"] is True and rows[0]["outside"]["jobs"] == []
    assert rows[1]["plan"]["fact_need"] == "none" and rows[1]["outside"]["fact_lane_called"] is False
    assert all(row["title"] and row["run_id"] and row["elapsed_ms"] >= 0 for row in rows)


def test_searched_research_records_lanes_and_candidates(tmp_path):
    result = run_research(tmp_path, "간격 복습이 기억에 미치는 효과", fetch=offline, fact_sources=no_library)
    assert "_trace" not in result
    row = read_research_traces(tmp_path)[-1]
    assert row["status"] in ("searched", "no_outside_call") and row["plan"]["fact_need"] == "required"
    assert row["outside"]["fact_lane_called"] is True and isinstance(row["candidates"], list)
