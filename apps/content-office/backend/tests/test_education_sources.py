import pytest
from office.education_sources import parse_moe
FEED = {'id':'moe-exam', 'name':'교육부'}

def test_official_notice_has_real_date_url_and_no_inferred_exam_date():
    raw = """<table><tbody><tr><td class='title'><a onclick="goView('294', '123', '0')">수능 부정행위 대응 안내</a></td><td>2026-10-29</td></tr></tbody></table>"""
    article = parse_moe(raw, FEED)[0]
    assert article['segment'] == 'exam'
    assert article['published_at'] == '2026-10-29T00:00:00+09:00'
    assert 'boardSeq=123' in article['url']
    assert '시험일이 아닙니다' in article['date_note']

def test_layout_failure_is_not_an_empty_success():
    with pytest.raises(ValueError): parse_moe('<html>blocked</html>', FEED)
