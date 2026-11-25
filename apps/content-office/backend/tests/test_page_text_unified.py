"""2026-11-25: 자료 창고만 표, 소제목, 코드를 살려 읽고 오늘의 뉴스 근거, 기획 공개 근거, 수집 때 읽기 확인은 예전 파서를 쓰던 문제.
세 경로가 자료 창고와 같은 공용 추출(page_text)을 쓰고, 새 추출이 떨어지면 각자의 예전 파서로 돌아가는지 본다."""
from office.evidence import extract_article_text, extract_page_text
from office.source_access import probe
from office.source_library import page_text

ROWS = "".join(f"<tr><td>{year}년</td><td>{fee:,}원</td><td>{day}월 {day}일</td></tr>" for year, fee, day in
               ((2025, 19400, 3), (2026, 20200, 4), (2027, 21000, 5)))
ARTICLE = ("<html><head><title>정보처리기사 일정 안내</title></head><body><nav>메뉴 로그인 회원가입</nav><article>"
           "<h1>정보처리기사 일정 안내</h1>"
           + "<p>시험 원서 접수는 큐넷에서 받으며, 접수 기간을 넘기면 추가 접수가 따로 열리지 않을 수 있습니다. 응시 자격도 함께 확인해야 합니다.</p>" * 3
           + "<h2>연도별 응시료</h2><table><thead><tr><th>연도</th><th>응시료</th><th>필기 시작</th></tr></thead><tbody>" + ROWS
           + "</tbody></table><h2>설치 명령</h2><pre><code>pip install trafilatura\n\npython -m pytest -q</code></pre>"
           + "<h3>주의할 점</h3>" + "<p>필기 합격 뒤 실기 접수는 별도로 해야 하며 일정이 회차마다 다르니 공지를 다시 확인하세요.</p>" * 3
           + "</article><footer>광고 꼬리말 링크</footer></body></html>")


def test_page_text_keeps_table_and_code_as_single_paragraphs_and_drops_menu():
    found = page_text(ARTICLE, "https://example.com/exam")
    assert found["extractor"] in ("trafilatura-2.4.0", "readability-0.9")
    paragraphs = found["text"].split("\n\n")
    table = [p for p in paragraphs if "20,200원" in p]
    assert len(table) == 1 and "21,000원" in table[0] and "응시료" in table[0]  # 표가 한 문단에 머리행과 같이 남는다
    code = [p for p in paragraphs if "pip install trafilatura" in p]
    assert len(code) == 1 and "python -m pytest -q" in code[0]  # 코드 안의 빈 줄 때문에 둘로 갈라지지 않는다
    assert any("연도별 응시료" in p for p in paragraphs)
    assert "회원가입" not in found["text"] and "광고 꼬리말" not in found["text"]


def test_old_parser_loses_the_table_structure_that_the_shared_extractor_keeps():
    old = extract_article_text(ARTICLE)
    new, extractor = extract_page_text(ARTICLE, "https://example.com/exam")
    old_table = [p for p in old.split("\n\n") if "20,200원" in p]
    new_table = [p for p in new.split("\n\n") if "20,200원" in p]
    assert extractor != "html-parser"
    assert not any("|" in p for p in old_table)  # 예전 파서는 표를 칸 구분 없는 글자로만 남긴다
    assert new_table and "|" in new_table[0]


def test_short_or_unreadable_pages_fall_back_to_the_old_parser():
    tiny = "<html><body><article><p>짧은 안내문입니다. 자세한 내용은 첨부파일을 보세요.</p></article></body></html>"
    assert page_text(tiny, "https://example.com/tiny")["text"] == ""
    text, extractor = extract_page_text(tiny, "https://example.com/tiny")
    assert extractor == "html-parser" and text == extract_article_text(tiny)
    assert extract_page_text("", "")[1] == "html-parser"


def test_collection_probe_uses_the_same_extractor_by_default():
    calls = []

    def fetch(url, maximum=None):
        calls.append(url)
        return ARTICLE.encode(), url, {}

    access = probe([{"id": "a1", "title": "기사", "url": "https://exam.example/notice"}], {}, fetch=fetch)
    assert access["exam.example"]["readable"] is True and calls == ["https://exam.example/notice"]
    # 주입한 한 인자 추출기도 예전처럼 동작한다(기존 시험과 호출 방식 호환)
    seen = []
    probe([{"id": "b1", "title": "기사", "url": "https://other.example/x"}], {}, fetch=fetch,
          extract=lambda markup: (seen.append(len(markup)), "가" * 2000)[1])
    assert seen