"""결재 기억: 승인① 반려가 교훈 후보가 되고, 사람이 승인한 교훈만 다음 원고 요청에 들어간다."""
from office.improvements import rejection_lessons
from office.store import Store


def rejected_job(tmp_path, *, reasons=("style",), note="문장이 너무 길어요"):
    store = Store(tmp_path)
    job = store.create_job({"id": "a1", "title": "기억 시험", "url": "https://example.com/a"})
    job = store.save_source(job["id"], {"title": "글", "body": "본문", "quality": {"status": "passed", "critical": False}, "w_type": "W3"})
    store.review_source(job["id"], job["source_hash"], "rejected", "owner", reasons=list(reasons), note=note)
    return store


def test_rejection_with_reason_becomes_a_proposed_lesson_only(tmp_path):
    store = rejected_job(tmp_path)
    [lesson] = store.lessons()
    assert lesson["state"] == "proposed" and lesson["kind"] == "draft_rejection"
    assert lesson["hypothesis"] == "문체 문제로 반려: 문장이 너무 길어요" and lesson["evidence"]["w_type"] == "W3"
    assert rejection_lessons(store) == []  # 사람이 승인하기 전에는 원고 요청에 넣지 않는다
    store.review_lesson(lesson["id"], "approved", "owner")
    assert rejection_lessons(store) == ["문체 문제로 반려: 문장이 너무 길어요"]


def test_rejection_without_reason_or_note_leaves_no_lesson(tmp_path):
    store = rejected_job(tmp_path, reasons=(), note="")
    assert store.lessons() == []
