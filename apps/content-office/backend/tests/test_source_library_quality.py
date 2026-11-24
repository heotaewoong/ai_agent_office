"""자료 창고 전처리 품질: 빈 근거 막기, 저장 금지 주소, 구조 추출과 원문 대조, 날짜, PDF 쪽 번호, docx 표, 구조 단위 조각."""
import io
import sqlite3
import zipfile
from contextlib import closing

import pytest

from office import source_library as sl
from office.source_library import add_file, add_links, fill_text, import_inbox, item_detail, library_overview, library_path, update_item
from office.store import WorkflowError

PROSE = "간격을 두고 다시 꺼내 보는 복습은 한 번에 몰아서 하는 공부보다 오래 남습니다. 시험 직전 벼락치기는 금방 잊힙니다. "
ARTICLE = f"""<html><head><title>복습 간격 정리</title>
<script type="application/ld+json">{{"@context": "https://schema.org", "@type": "Article", "datePublished": "2026-10-03T09:00:00+09:00",
"dateModified": "2026-11-01"}}</script></head><body><nav>메뉴 홈 로그인</nav><article>
<h1>복습 간격 정리</h1><p>{PROSE * 3}</p>
<h2>간격별 기억 유지율</h2><p>{PROSE * 2}</p>
<table><tr><th>간격</th><th>1주 뒤 기억</th></tr><tr><td>하루</td><td>62%</td></tr><tr><td>사흘</td><td>71%</td></tr><tr><td>일주일</td><td>78%</td></tr></table>
<h2>따라 해 보는 코드</h2><p>{PROSE * 2}</p>
<pre><code>def next_review(days):
    return days * 2
</code></pre>
<h2>정리</h2><p>{PROSE * 3}</p>
<figure><img src="/a.png" alt="간격 반복 곡선 그림"><figcaption>그림 1. 간격을 늘릴수록 기억이 오래 남는다</figcaption></figure>
</article><footer>회사 소개</footer></body></html>"""


def page(markup, final_url=None, kind="text/html; charset=utf-8"):
    calls = []

    def fetch(url, *, maximum):
        calls.append(url)
        return markup.encode("utf-8"), final_url or url, kind
    fetch.calls = calls
    return fetch


def test_web_page_keeps_tables_headings_code_and_dates(tmp_path):
    [result] = add_links(tmp_path, ["https://example.org/spacing"], area="C", fetch=page(ARTICLE))
    item = result["item"]
    assert item["status"] == "done" and item["extractor"] == "trafilatura-2.4.0" and item["note"] == ""
    assert item["published_at"] == "2026-10-03" and item["modified_at"] == "2026-11-01" and item["date_source"] == "json-ld"
    assert item["collected_at"]
    detail = item_detail(tmp_path, item["id"])
    text = "\n".join(detail["passage_texts"])
    assert "| 하루 | 62% |" in text and "1주 뒤 기억" in text
    assert "def next_review(days):\n    return days * 2" in text
    assert "[그림 설명] 그림 1. 간격을 늘릴수록" in text and "[그림] 간격 반복 곡선 그림" in text and "\\[" not in text
    assert "메뉴 홈" not in text and "회사 소개" not in text
    table = next(i for i, t in enumerate(detail["passage_texts"]) if "| 하루 |" in t)
    assert detail["passage_places"][table]["heading"].endswith("간격별 기억 유지율")
    assert all(len(t) <= 1800 for t in detail["passage_texts"])


def test_structure_that_fails_the_source_check_falls_back_with_a_reason(tmp_path, monkeypatch):
    def flat(markup, url):
        return [sl._Block(PROSE * 12)], None
    monkeypatch.setattr(sl, "_trafilatura_doc", flat)
    [result] = add_links(tmp_path, ["https://example.org/spacing"], area="C", fetch=page(ARTICLE))
    item = result["item"]
    assert item["status"] == "done" and item["extractor"] == "html-parser"
    assert "예전 방식으로 저장" in item["note"] and "원문은 3개" in item["note"]
    assert "복습은 한 번에" in "\n".join(item_detail(tmp_path, item["id"])["passage_texts"])


def test_gate_rules():
    source = {"headings": 15, "tables": 1, "code": 1}
    good = [sl._Block("소제목", "heading", 2), sl._Block(PROSE * 8), sl._Block("| a | b |\n| --- | --- |\n| 1 | 2 |", "table"),
            sl._Block("```\nx = 1\n```", "code")]
    assert sl._gate(source, good, 800, 10) is None
    assert "절반" in sl._gate(source, good, 5000, 10)
    assert "소제목 0개" in sl._gate(source, good[1:], 600, 10)
    assert "표 행 0개" in sl._gate(source, [good[0], good[1], good[3]], 600, 10)
    assert "코드 블록 0개" in sl._gate(source, good[:3], 600, 10)
    assert "숫자" in sl._gate({"headings": 0, "tables": 0, "code": 0}, [sl._Block(PROSE * 5)], 500, 60)
    assert "비어" in sl._gate(source, None, 800, 10)


def test_short_link_body_is_not_saved_as_done(tmp_path, monkeypatch):
    monkeypatch.setattr(sl, "_trafilatura_doc", lambda markup, url: (None, None))
    short = "<html><head><title>짧은 글</title></head><body>" + "".join(f"<p>{'짧은 문장입니다. ' * 3}{n}</p>" for n in range(12)) + "</body></html>"
    [result] = add_links(tmp_path, ["https://example.org/short"], area="B", fetch=page(short))
    assert result["item"]["status"] == "done"  # 예전 파서 기준 300자를 넘는다
    noisy = "<html><head><title>짧은 글</title></head><body><p>" + "복습 안내입니다. " * 4 + "</p></body></html>"
    [result] = add_links(tmp_path, ["https://example.org/tiny"], area="B", fetch=page(noisy))
    assert result["item"]["status"] == "needs_check" and result["item"]["passages"] == 0


@pytest.mark.parametrize("url", ["https://m.blog.naver.com/someone/224480782785", "https://blog.naver.com/someone/1",
                                 "https://n.news.naver.com/article/001/0001", "https://v.daum.net/v/2026"])
def test_robots_blocked_hosts_are_never_read(tmp_path, url):
    fetch = page(ARTICLE)
    [result] = add_links(tmp_path, [url], area="B", fetch=fetch)
    item = result["item"]
    assert item["status"] == "needs_check" and "robots.txt" in item["note"] and item["passages"] == 0 and fetch.calls == []
    with pytest.raises(WorkflowError, match="본문이 저장된 자료만"):
        update_item(tmp_path, item["id"], {"use_as_evidence": True})


def test_blocked_host_accepts_pasted_text_only_when_marked_as_mine(tmp_path):
    [result] = add_links(tmp_path, ["https://m.blog.naver.com/me/1"], area="D", fetch=page(ARTICLE))
    item_id = result["item"]["id"]
    with pytest.raises(WorkflowError, match="내 자료"):
        fill_text(tmp_path, item_id, PROSE * 3)
    update_item(tmp_path, item_id, {"mine": True})
    assert fill_text(tmp_path, item_id, PROSE * 3)["status"] == "done"


def test_redirect_into_a_blocked_host_stops_before_parsing(tmp_path):
    fetch = page(ARTICLE, final_url="https://m.blog.naver.com/x/1")
    [result] = add_links(tmp_path, ["https://naver.me/abc"], area="B", fetch=fetch)
    assert result["item"]["status"] == "needs_check" and "네이버 블로그" in result["item"]["note"]


def test_import_skips_blocked_hosts_and_short_link_bodies(tmp_path):
    rows = [
        {"id": "a" * 20, "kind": "link", "title": "네이버", "url": "https://m.blog.naver.com/n_cloudplatform/1", "status": "done", "chunks": [PROSE * 5]},
        {"id": "b" * 20, "kind": "link", "title": "짧음", "url": "https://openai.com/x", "status": "done", "chunks": ["GPT 소개 " * 5]},
        {"id": "c" * 20, "kind": "link", "title": "정상", "url": "https://example.org/ok", "status": "done", "chunks": [PROSE * 5]},
    ]
    assert [r["result"] for r in import_inbox(tmp_path, rows)] == ["skipped", "skipped", "imported"]


def old_library(tmp_path):
    """2026-11-24 운영 판과 같은 칸만 있는 창고를 만든다."""
    path = library_path(tmp_path)
    path.parent.mkdir(parents=True)
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript("""
        CREATE TABLE items(id TEXT PRIMARY KEY, kind TEXT NOT NULL, area TEXT NOT NULL, mine INTEGER NOT NULL DEFAULT 0,
          title TEXT NOT NULL, url TEXT, url_norm TEXT, status TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
          passages INTEGER NOT NULL DEFAULT 0, content_hash TEXT, file_name TEXT, body TEXT, pasted TEXT,
          origin TEXT NOT NULL DEFAULT 'manual', origin_ref TEXT, use_as_evidence INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL, role TEXT, lane TEXT NOT NULL DEFAULT 'fact');
        CREATE TABLE passages(item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE, seq INTEGER NOT NULL, text TEXT NOT NULL,
          PRIMARY KEY(item_id, seq));
        CREATE TABLE passage_vectors(item_id TEXT NOT NULL, seq INTEGER NOT NULL, part INTEGER NOT NULL, start_char INTEGER NOT NULL,
          end_char INTEGER NOT NULL, model TEXT NOT NULL, vector BLOB NOT NULL, PRIMARY KEY(item_id, seq, part),
          FOREIGN KEY(item_id, seq) REFERENCES passages(item_id, seq) ON DELETE CASCADE);""")
        for item_id, url, texts, mine in (("short", "https://www.youtube.com/@channel", ["장동선의 궁금한 뇌 " * 4], 0),
                                          ("naver", "https://m.blog.naver.com/n_cloudplatform/224480782785", [PROSE * 3, PROSE * 3], 0),
                                          ("mynaver", "https://blog.naver.com/me/1", [PROSE * 6], 1),
                                          ("good", "https://example.org/ok", [PROSE * 6], 0)):
            db.execute("INSERT INTO items(id, kind, area, mine, title, url, url_norm, status, passages, use_as_evidence, origin, created_at, updated_at) "
                       "VALUES (?, 'link', 'B', ?, ?, ?, ?, 'done', ?, 1, 'import', '2026-11-20T00:00:00+00:00', '2026-11-20T00:00:00+00:00')",
                       (item_id, mine, item_id, url, url, len(texts)))
            for seq, text in enumerate(texts, 1):
                db.execute("INSERT INTO passages(item_id, seq, text) VALUES (?,?,?)", (item_id, seq, text))
                db.execute("INSERT INTO passage_vectors VALUES (?,?,0,0,?, 'm', x'00')", (item_id, seq, len(text)))
    return path


def test_migration_takes_down_short_and_blocked_bodies_once(tmp_path):
    path = old_library(tmp_path)
    items = {item["id"]: item for item in library_overview(tmp_path)["items"]}
    assert items["short"]["status"] == "needs_check" and "자뿐이라" in items["short"]["note"] and not items["short"]["use_as_evidence"]
    assert items["naver"]["status"] == "needs_check" and "robots.txt" in items["naver"]["note"] and items["naver"]["passages"] == 0
    assert items["naver"]["url"].startswith("https://m.blog.naver.com") and items["naver"]["title"] == "naver"
    assert items["mynaver"]["status"] == "done" and items["good"]["status"] == "done" and items["good"]["use_as_evidence"]
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT COUNT(*) FROM passages WHERE item_id IN ('short','naver')").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM passage_vectors WHERE item_id IN ('short','naver')").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM passage_vectors WHERE item_id='good'").fetchone()[0] == 1
        assert db.execute("SELECT name FROM library_migrations").fetchall() == [("link-body-gate-20261125",)]
        columns = {row[1] for row in db.execute("PRAGMA table_info(items)")}
        assert {"published_at", "modified_at", "collected_at", "date_source", "extractor"} <= columns
        assert {"locator", "heading"} <= {row[1] for row in db.execute("PRAGMA table_info(passages)")}
        db.execute("UPDATE items SET status='done' WHERE id='short'")
        db.commit()
    library_overview(tmp_path)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT status FROM items WHERE id='short'").fetchone()[0] == "done"  # 한 번만 정리한다


def make_pdf(pages):
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.setTitle("study")
    for number, lines in enumerate(pages, 1):
        pdf.drawString(72, 800, "PRIVATE STUDY ONLY")
        y = 760
        for line in lines:
            pdf.drawString(72, y, line)
            y -= 16
        pdf.drawString(300, 40, str(number))
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def test_pdf_keeps_page_numbers_and_drops_repeated_lines(tmp_path):
    def body(n):
        return [f"Page {n} line {k}: spaced retrieval practice improves long-term retention in study {n * 10 + k}." for k in range(3)]
    data = make_pdf([body(1), body(2) + ["Second page keeps its own number."], [], body(4) + ["Fourth page closes the chapter."]])
    item = add_file(tmp_path, "notes.pdf", __import__("base64").b64encode(data).decode(), area="C")
    assert item["status"] == "done" and item["extractor"] == "pypdf-7.1.1" and "1쪽은 글자층이 없거나" in item["note"]
    assert item["date_source"] == "pdf-metadata" and item["published_at"]
    detail = item_detail(tmp_path, item["id"])
    places = [place["locator"] for place in detail["passage_places"]]
    assert places == ["p.1", "p.2", "p.4"]
    text = "\n".join(detail["passage_texts"])
    assert "PRIVATE STUDY ONLY" not in text and "Second page keeps" in detail["passage_texts"][1]


def make_docx():
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    body = (f'<w:document {w}><w:body>'
            '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>복습 계획</w:t></w:r></w:p>'
            f'<w:p><w:r><w:t>{PROSE * 2}</w:t></w:r></w:p>'
            '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>요일</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>과목</w:t></w:r></w:p></w:tc></w:tr>'
            '<w:tr><w:tc><w:p><w:r><w:t>월</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>영어 | 단어</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
            f'<w:p><w:r><w:t>{PROSE}</w:t></w:r></w:p></w:body></w:document>')
    core = ('<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dcterms="http://purl.org/dc/terms/"><dcterms:created>2026-09-01T00:00:00Z</dcterms:created>'
            '<dcterms:modified>2026-09-02T00:00:00Z</dcterms:modified></cp:coreProperties>')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", body)
        archive.writestr("docProps/core.xml", core)
    return buffer.getvalue()


def test_docx_reads_heading_styles_and_tables(tmp_path):
    item = add_file(tmp_path, "plan.docx", __import__("base64").b64encode(make_docx()).decode(), area="C")
    assert item["status"] == "done" and item["extractor"] == "docx-xml"
    assert item["published_at"] == "2026-09-01" and item["modified_at"] == "2026-09-02"
    detail = item_detail(tmp_path, item["id"])
    text = "\n".join(detail["passage_texts"])
    assert "| 요일 | 과목 |" in text and "| 월 | 영어 / 단어 |" in text
    assert detail["passage_places"][0]["heading"] == "복습 계획" and text.startswith("복습 계획")


def test_chunks_start_at_headings_and_keep_big_tables_with_their_header():
    rows = "\n".join(f"| 항목 {n} | {'값 ' * 30}{n} |" for n in range(40))
    blocks = [sl._Block("첫 소제목", "heading", 2), sl._Block(PROSE * 6), sl._Block("둘째 소제목", "heading", 2), sl._Block(PROSE),
              sl._Block("| 항목 | 값 |\n| --- | --- |\n" + rows, "table"), sl._Block("```\n" + "\n".join(f"line_{n} = {n}" for n in range(300)) + "\n```", "code")]
    passages = sl._chunk_blocks(blocks)
    assert passages[0][0].startswith("첫 소제목") and passages[1][0].startswith("둘째 소제목") and passages[1][2] == "둘째 소제목"
    tables = [text for text, _, _ in passages if "| 항목 " in text]
    assert len(tables) >= 2 and all(text.splitlines()[0] == "| 항목 | 값 |" or "| 항목 | 값 |" in text for text in tables)
    codes = [text for text, _, _ in passages if "line_" in text]
    assert len(codes) >= 2 and all(text.startswith("```") and text.endswith("```") for text in codes)
    assert all(len(text) <= 1800 for text, _, _ in passages)


def test_page_boundaries_are_never_crossed():
    blocks = [sl._Block(PROSE, locator="p.1"), sl._Block(PROSE, locator="p.2")]
    assert [locator for _, locator, _ in sl._chunk_blocks(blocks)] == ["p.1", "p.2"]


def test_dates_follow_the_source_order_and_reject_placeholders():
    meta = '<meta property="article:published_time" content="2026-11-20T08:00:00Z"><time datetime="2025-01-01">x</time>'
    assert sl._page_dates(meta) == {"published_at": "2026-11-20", "modified_at": None, "date_source": "meta"}
    assert sl._page_dates('<time datetime="2026-03-04T10:00">x</time>')["date_source"] == "time"
    assert sl._page_dates("<p>x</p>", "2000-01-01") == {"published_at": None, "modified_at": None, "date_source": None}
    assert sl._page_dates("<p>x</p>", "2026-05-06")["date_source"] == "htmldate"
    assert sl._page_dates("<p>x</p>", "2005-01-01")["published_at"] is None
    assert sl._valid_date("2999-01-01") is None and sl._valid_date("2026년 11월 3일") == "2026-11-03"
