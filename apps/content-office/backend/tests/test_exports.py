from pathlib import Path


def packet():
    return {
        "title": "승인한 한국어 원고",
        "body": "## 핵심 설명\n\n세 가지 근거를 먼저 확인합니다.\n\n1. 첫 번째 단계\n2. 다음 단계\n\n<script>evil()</script>",
        "evidence": [{"id": "E1", "url": "https://example.com/research", "claim": "공식 자료의 범위"}],
        "quality": {"status": "passed", "critical": []},
        "video": {"title": "핵심을 이해하는 법", "description": "근거를 설명합니다.", "tags": ["AI"], "scenes": [{"narration": "근거를 먼저 확인합니다.", "caption": "근거 먼저", "visual": "flow"}]},
    }


def test_blog_exports_escape_html_and_make_paste_safe_numbered_lists(tmp_path):
    from office.exports import write_blog_exports
    files = write_blog_exports(packet(), tmp_path)
    assert {p.name for p in files} == {"tistory.md", "tistory.html", "naver.txt"}
    html = (tmp_path / "tistory.html").read_text()
    assert "<h1" not in html
    assert '<h2' in html and '<script>' not in html
    assert 'hb-number-badge' in html and 'color:inherit' in html
    assert 'overflow-wrap:anywhere' in html
    assert "핵심 설명" in (tmp_path / "naver.txt").read_text()
    assert "## " not in (tmp_path / "naver.txt").read_text()


def test_video_handoff_has_narration_scenes_and_direct_evidence(tmp_path):
    from office.exports import write_video_exports
    files = write_video_exports(packet(), tmp_path)
    assert {p.name for p in files} == {"youtube-script.md", "youtube-plan.json", "description.txt"}
    assert "근거를 먼저 확인합니다." in (tmp_path / "youtube-script.md").read_text()
    assert "https://example.com/research" in (tmp_path / "description.txt").read_text()
    assert "합성 음성" in (tmp_path / "description.txt").read_text()


def test_reference_pdf_and_asset_rights_are_real_files(tmp_path):
    from office.exports import write_reference_pdf, write_rights_manifest
    pdf = write_reference_pdf(packet(), tmp_path)
    rights = write_rights_manifest(packet(), tmp_path)
    assert pdf.read_bytes().startswith(b"%PDF-") and pdf.stat().st_size > 3000
    assert "not_commercially_cleared" in rights.read_text()
    assert "https://example.com/research" in rights.read_text()


def test_blog_html_keeps_citations_clickable_without_activating_untrusted_markup(tmp_path):
    from office.exports import write_blog_exports
    source = packet()
    source['body'] += '\n\n**확인한 근거**는 [공식 원문](https://example.com/report?a=1&b=2)입니다. `print(1)`\n\n[실행](javascript:alert(1))'
    write_blog_exports(source, tmp_path)
    html = (tmp_path / 'tistory.html').read_text()
    assert '<a href="https://example.com/report?a=1&amp;b=2"' in html
    assert '<a href="https://example.com/research"' in html
    assert '<strong>확인한 근거</strong>' in html
    assert '<code>print(1)</code>' in html
    assert 'href="javascript:' not in html and '<script>' not in html


def test_blog_comparison_table_is_readable_cells_with_escaped_content(tmp_path):
    from html.parser import HTMLParser
    from office.exports import write_blog_exports

    source = packet()
    source['body'] = '## 완료 기준\n\n| 확인 항목 | 기대 상태 |\n|---|---|\n| 결제 서비스 | **환불 완료** |\n| 내부 장부 | <img src=x onerror=alert(1)> 30,000원 |'
    write_blog_exports(source, tmp_path)
    html = (tmp_path / 'tistory.html').read_text()
    class Cells(HTMLParser):
        def __init__(self):
            super().__init__(); self.tags = []; self.text = []
        def handle_starttag(self, tag, attrs):
            self.tags.append(tag)
        def handle_data(self, text):
            self.text.append(text)
    parsed = Cells(); parsed.feed(html)
    assert parsed.tags.count('table') == 1
    assert parsed.tags.count('th') == 2 and parsed.tags.count('td') == 4
    assert '환불 완료' in parsed.text
    assert not any('|---|' in text for text in parsed.text)
    assert 'img' not in parsed.tags and '<img src=x' not in html
    assert '&lt;img src=x onerror=alert(1)&gt;' in html
