import pytest
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
    html = (tmp_path / "tistory.html").read_text(encoding="utf-8")
    assert "<h1" not in html
    assert '<h2' in html and '<script>' not in html
    assert 'hb-number-badge' in html and 'color:inherit' in html
    assert 'overflow-wrap:anywhere' in html
    assert "핵심 설명" in (tmp_path / "naver.txt").read_text(encoding="utf-8")
    assert "## " not in (tmp_path / "naver.txt").read_text(encoding="utf-8")


def test_blog_code_fences_preserve_commands_blank_lines_and_escape_markup():
    from html.parser import HTMLParser
    from office.exports import safe_fragment

    class CodeReader(HTMLParser):
        def __init__(self):
            super().__init__()
            self.in_code = False
            self.code = []
        def handle_starttag(self, tag, attrs):
            if tag == 'code':
                self.in_code = True
        def handle_endtag(self, tag):
            if tag == 'code':
                self.in_code = False
        def handle_data(self, data):
            if self.in_code:
                self.code.append(data)

    command = 'Test-NetConnection 192.168.1.5 -Port 22000\n\n<img src=x onerror=alert(1)>\n  <script>never()</script>'
    html = safe_fragment('## 확인\n\n```powershell\n' + command + '\n```\n\n## 다음 단계\n\n연결 결과를 확인해요.')
    reader = CodeReader()
    reader.feed(html)
    assert ''.join(reader.code) == command
    assert '<script>' not in html and '<img ' not in html
    assert '<pre ' in html and '<h2>다음 단계</h2>' in html


def test_unclosed_code_fence_is_literal_and_does_not_parse_markdown():
    from office.exports import safe_fragment
    html = safe_fragment('~~~text\n## 이것은 코드\n| 표 | 아님 |\n|---|---|\n<script>never()</script>')
    assert '<table' not in html and '<script>' not in html
    assert '## 이것은 코드' in html and '&lt;script&gt;' in html


def test_source_photos_allow_only_explicit_public_hosts_and_escape_alt():
    from office.exports import safe_fragment
    html = safe_fragment('## 원문 사진\n\n![기기 "일시정지" 화면](https://blog.kakaocdn.net/example/photo.png?a=1&b=2)\n\n![다른 사진](https://t1.daumcdn.net/photo.png)\n\n![차단](https://attacker.example/pixel.png)\n\n![차단](https://blog.kakaocdn.net@127.0.0.1/photo.png)\n\n![차단](https://blog.kakaocdn.net:444/photo.png)\n\n<img src=x onerror=alert(1)>')
    assert html.count('<img ') == 2
    assert 'alt="기기 &quot;일시정지&quot; 화면"' in html
    assert 'referrerpolicy="no-referrer"' in html
    assert 'src="https://attacker.example' not in html
    assert 'src="https://blog.kakaocdn.net@' not in html
    assert 'src="https://blog.kakaocdn.net:444' not in html
    assert 'onerror=alert(1)>' not in html


def test_photo_inside_code_fence_is_never_loaded():
    from office.exports import safe_fragment
    html = safe_fragment('```markdown\n![사진](https://blog.kakaocdn.net/photo.png)\n```')
    assert '<img ' not in html and '![사진]' in html


def test_video_handoff_has_narration_scenes_and_direct_evidence(tmp_path):
    from office.exports import write_video_exports
    files = write_video_exports(packet(), tmp_path)
    assert {p.name for p in files} == {"youtube-script.md", "youtube-plan.json", "description.txt"}
    assert "근거를 먼저 확인합니다." in (tmp_path / "youtube-script.md").read_text(encoding="utf-8")
    assert "https://example.com/research" in (tmp_path / "description.txt").read_text(encoding="utf-8")
    assert "합성 음성" in (tmp_path / "description.txt").read_text(encoding="utf-8")


def test_reference_pdf_and_asset_rights_are_real_files(tmp_path):
    from office.exports import write_reference_pdf, write_rights_manifest
    pdf = write_reference_pdf(packet(), tmp_path)
    rights = write_rights_manifest(packet(), tmp_path)
    assert pdf.read_bytes().startswith(b"%PDF-") and pdf.stat().st_size > 3000
    assert "not_commercially_cleared" in rights.read_text(encoding="utf-8")
    assert "https://example.com/research" in rights.read_text(encoding="utf-8")


def test_blog_html_keeps_citations_clickable_without_activating_untrusted_markup(tmp_path):
    from office.exports import write_blog_exports
    source = packet()
    source['body'] += '\n\n**확인한 근거**는 [공식 원문](https://example.com/report?a=1&b=2)입니다. `print(1)`\n\n[실행](javascript:alert(1))'
    write_blog_exports(source, tmp_path)
    html = (tmp_path / 'tistory.html').read_text(encoding="utf-8")
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
    html = (tmp_path / 'tistory.html').read_text(encoding="utf-8")
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


def test_korean_font_accepts_only_truetype_and_never_uses_wsl_paths(tmp_path, monkeypatch):
    """reportlab cannot read TTC/OTF collections; the WSL bridge path is gone."""
    from office import exports
    from office.store import WorkflowError
    ttc = tmp_path / 'NotoSansCJK-Regular.ttc'
    ttc.write_bytes(b'ttcf' + b'\0' * 64)
    monkeypatch.setenv('CONTENT_OFFICE_FONT', str(ttc))
    with pytest.raises(WorkflowError, match='TTF'):
        exports.korean_font()
    ttf = tmp_path / 'NanumGothic.ttf'
    ttf.write_bytes(b'\x00\x01\x00\x00' + b'\0' * 64)
    monkeypatch.setenv('CONTENT_OFFICE_FONT', str(ttf))
    assert exports.korean_font() == ttf
    monkeypatch.delenv('CONTENT_OFFICE_FONT')
    assert all(not str(candidate).startswith('/mnt/') and str(candidate).lower().endswith('.ttf') for candidate in exports.FONT_CANDIDATES)
    assert '/usr/share/fonts/truetype/nanum/NanumGothic.ttf' in exports.FONT_CANDIDATES


def photo_bytes(kind="PNG", *, animated=False):
    from io import BytesIO
    from PIL import Image
    buffer = BytesIO()
    image = Image.new("RGB", (3, 2), "red")
    options = {"save_all": True, "append_images": [Image.new("RGB", (3, 2), "blue")], "duration": 100} if animated else {}
    image.save(buffer, format=kind, **options)
    return buffer.getvalue()


def photo_packet(urls):
    source = packet()
    source.update(preserve_original=True, body="## 직접 제공한 글\r\n\r\n" + "\r\n\r\n".join(f"![사진 {index}]({url})" for index, url in enumerate(urls, 1)) + "  \r\n")
    return source


@pytest.mark.parametrize("kind,extension", [("PNG", "png"), ("JPEG", "jpg"), ("WEBP", "webp")])
def test_original_photos_are_local_bytes_and_bind_to_blog_files_without_mutating_source(tmp_path, monkeypatch, kind, extension):
    import hashlib
    import json
    from office import feeds
    from office.exports import write_blog_exports, write_rights_manifest
    raw = photo_bytes(kind)
    url = "https://blog.kakaocdn.net/original/photo?credential=private&expires=123&signature=secret"
    source = photo_packet([url])
    original = source["body"]
    calls = []
    def fetch(value, *, maximum, allowed_hosts):
        calls.append(value)
        assert maximum == 8 * 1024 * 1024 and allowed_hosts == {"blog.kakaocdn.net", "t1.daumcdn.net"}
        return raw, value, "image/incorrect-header"
    monkeypatch.setattr(feeds, "fetch_public", fetch)
    files = write_blog_exports(source, tmp_path)
    photo = tmp_path / f"source-photo-01.{extension}"
    assert photo.read_bytes() == raw and source["body"] == original
    assert (tmp_path / "source-original.md").read_bytes() == original.encode("utf-8")
    assert {p.name for p in files} == {"tistory.md", "tistory.html", "naver.txt", "source-original.md", "source-photos.json", photo.name}
    html = (tmp_path / "tistory.html").read_text(encoding="utf-8")
    assert f'src="{photo.name}"' in html and f'href="{photo.name}"' in html and "signature=secret" not in html
    cached = json.loads((tmp_path / "source-photos.json").read_text(encoding="utf-8"))["photos"][0]
    assert cached["sha256"] == hashlib.sha256(raw).hexdigest() and cached["url_sha256"] == hashlib.sha256(url.encode()).hexdigest()
    assert cached["source_url"] == "https://blog.kakaocdn.net/original/photo" and cached["rights"] == "owner_supplied_reference"
    rights = write_rights_manifest(source, tmp_path).read_text(encoding="utf-8")
    assert "owner_supplied_reference" in rights and "signature=secret" not in rights and "not_commercially_cleared" in rights
    write_blog_exports(source, tmp_path)
    assert calls == [url]
    photo.write_bytes(b"corrupted cache")
    write_blog_exports(source, tmp_path)
    assert calls == [url, url] and photo.read_bytes() == raw


def test_photo_failure_preserves_verified_cache_and_retry_fetches_only_missing_photo(tmp_path, monkeypatch):
    import json
    from office import feeds
    from office.exports import write_blog_exports
    from office.store import WorkflowError
    raw = photo_bytes()
    urls = ["https://blog.kakaocdn.net/one?signature=first", "https://t1.daumcdn.net/two?signature=second"]
    source = photo_packet(urls)
    def partial(url, **kwargs):
        if url == urls[1]:
            raise RuntimeError("failed request with sensitive URL")
        return raw, url, "image/png"
    monkeypatch.setattr(feeds, "fetch_public", partial)
    with pytest.raises(WorkflowError, match="사진 2") as error:
        write_blog_exports(source, tmp_path)
    assert "signature" not in str(error.value) and not (tmp_path / "tistory.html").exists()
    assert len(json.loads((tmp_path / "source-photos.json").read_text(encoding="utf-8"))["photos"]) == 1
    calls = []
    def retry(url, **kwargs):
        calls.append(url)
        return raw, url, "image/png"
    monkeypatch.setattr(feeds, "fetch_public", retry)
    files = write_blog_exports(source, tmp_path)
    assert calls == [urls[1]] and len([p for p in files if p.name.startswith("source-photo-")]) == 2


@pytest.mark.parametrize("raw", [b'<svg xmlns="http://www.w3.org/2000/svg"></svg>', b"not an image", photo_bytes("GIF"), photo_bytes("PNG", animated=True)])
def test_invalid_svg_and_animated_photos_fail_without_silent_omission(tmp_path, monkeypatch, raw):
    from office import feeds
    from office.exports import write_blog_exports
    from office.store import WorkflowError
    monkeypatch.setattr(feeds, "fetch_public", lambda url, **kwargs: (raw, url, "image/png"))
    with pytest.raises(WorkflowError, match="PNG.*JPEG.*WebP"):
        write_blog_exports(photo_packet(["https://blog.kakaocdn.net/photo"]), tmp_path)
    assert not (tmp_path / "tistory.html").exists()


@pytest.mark.parametrize("limit", ["count", "bytes", "total", "pixels"])
def test_source_photo_resource_limits_fail_closed(tmp_path, monkeypatch, limit):
    from office import exports, feeds
    from office.store import WorkflowError
    raw = photo_bytes()
    urls = [f"https://blog.kakaocdn.net/photo-{index}" for index in range(9 if limit == "count" else 2)]
    calls = []
    def fetch(url, **kwargs):
        calls.append(url)
        return raw, url, "image/png"
    monkeypatch.setattr(feeds, "fetch_public", fetch)
    if limit == "bytes":
        monkeypatch.setattr(exports, "SOURCE_PHOTO_MAX_BYTES", len(raw) - 1)
    elif limit == "total":
        monkeypatch.setattr(exports, "SOURCE_PHOTO_TOTAL_BYTES", len(raw) + 1)
    elif limit == "pixels":
        monkeypatch.setattr(exports, "SOURCE_PHOTO_MAX_PIXELS", 5)
    with pytest.raises(WorkflowError):
        exports.write_blog_exports(photo_packet(urls), tmp_path)
    assert not (tmp_path / "tistory.html").exists()
    if limit == "count":
        assert calls == []


def test_photo_examples_in_code_and_summary_mode_never_fetch(tmp_path, monkeypatch):
    from office import feeds
    from office.exports import write_blog_exports
    def forbidden(*args, **kwargs):
        pytest.fail("코드 예제 또는 기본 요약 모드에서 사진을 다운로드하지 않습니다")
    monkeypatch.setattr(feeds, "fetch_public", forbidden)
    source = packet()
    source["body"] = "![사진](https://blog.kakaocdn.net/photo)"
    write_blog_exports(source, tmp_path)
    source.update(preserve_original=True, body="```markdown\n![사진](https://blog.kakaocdn.net/photo)\n```")
    files = write_blog_exports(source, tmp_path)
    html = (tmp_path / "tistory.html").read_text(encoding="utf-8")
    assert "<img " not in html and "![사진]" in html and "source-original.md" in {p.name for p in files}


def test_only_generated_photo_names_can_load_as_local_images():
    from office.exports import safe_fragment
    html = safe_fragment("\n\n".join(f"![사진]({name})" for name in ("source-photo-01.png", "source-photo-08.webp", "../source-photo-01.png", "/source-photo-01.png", "source-photo-09.png", "source-photo-01.svg", "source-photo-01.png?x=1")))
    assert html.count("<img ") == 2


def test_local_source_photos_are_hashed_blog_artifacts_and_in_release_zip(tmp_path, monkeypatch):
    import hashlib
    from io import BytesIO
    import zipfile
    from fastapi.testclient import TestClient
    from office.api import create_app
    from office import feeds, media
    from tests.test_media import approved_job
    store, job_id = approved_job(tmp_path, video=False)
    original = photo_packet(["https://blog.kakaocdn.net/photo?signature=private"])
    saved = store.save_source(job_id, original)
    store.review_source(job_id, saved["source_hash"], "approved", "synthetic-fixture-human", {"blog": True})
    raw = photo_bytes()
    monkeypatch.setattr(feeds, "fetch_public", lambda url, **kwargs: (raw, url, "image/png"))
    manifest = media.produce(store, job_id)
    files = {row["name"]: row for row in manifest["files"]}
    for name in ("source-photo-01.png", "source-photos.json", "source-original.md"):
        assert files[name]["outputs"] == ["blog"]
        assert files[name]["sha256"] == hashlib.sha256((store.artifacts / files[name]["path"]).read_bytes()).hexdigest()
    assert files["source-photo-01.png"]["sha256"] == hashlib.sha256(raw).hexdigest()
    store.review_release(job_id, manifest["hash"], "approved", "synthetic-fixture-human", outputs=["blog"])
    client = TestClient(create_app(store), base_url="http://localhost:8510")
    client.get("/api/session")
    response = client.get(f"/api/jobs/{job_id}/package")
    assert response.status_code == 200
    with zipfile.ZipFile(BytesIO(response.content)) as archive:
        assert archive.read("source-photo-01.png") == raw
        assert archive.read("source-original.md") == original["body"].encode("utf-8")
        assert b"signature=private" not in archive.read("source-photos.json")


@pytest.mark.parametrize("cache", [None, b"{broken", b"[]", b"{}", b'{"version":1,"photos":null}', b'{"version":1,"photos":[{"unexpected":"signature=must-not-leak"}]}'])
def test_source_photo_failure_preserves_independent_completed_video(tmp_path, monkeypatch, cache):
    import json
    from office import feeds, media
    from office.store import WorkflowError
    from tests.test_media import approved_job, tone_renderer
    store, job_id = approved_job(tmp_path)
    saved = store.save_source(job_id, photo_packet(["https://blog.kakaocdn.net/photo"]))
    store.review_source(job_id, saved["source_hash"], "approved", "synthetic-fixture-human", {"blog": True, "video": True})
    def unavailable(*args, **kwargs):
        raise WorkflowError("사진 다운로드 실패")
    def synthetic_video(plan, folder, **kwargs):
        output = folder / "short.mp4"
        output.write_bytes(b"synthetic-video-for-partial-output-contract")
        return {"media": {"duration": 1.0}, "thumbnails": [], "backgrounds": [], "clips": [], "files": [output]}
    original_writer = media.write_blog_exports
    def with_cache(packet, folder, offer):
        if cache is not None:
            (folder / "source-photos.json").write_bytes(cache)
        return original_writer(packet, folder, offer)
    monkeypatch.setattr(feeds, "fetch_public", unavailable)
    monkeypatch.setattr(media, "render_short", synthetic_video)
    monkeypatch.setattr(media, "write_blog_exports", with_cache)
    result = media.produce(store, job_id, voice_renderer=tone_renderer())
    assert result["completed_outputs"] == ["video"] and result["output_status"]["blog"]["state"] == "failed"
    assert "short.mp4" in {row["name"] for row in result["files"]}
    assert "tistory.html" not in {row["name"] for row in result["files"]}
    assert store.job(job_id)["manifest"]["hash"] == result["hash"]
    rights_record = next(row for row in result["files"] if row["name"] == "asset-rights.json")
    rights = json.loads((store.artifacts / rights_record["path"]).read_text(encoding="utf-8"))
    assert rights["source_photo_verification"] == "unverified_or_incomplete"
    assert rights["external_visual_assets"] == [] and rights["external_visual_references"][0]["verification"] == "unverified"
    assert "signature=must-not-leak" not in json.dumps(rights) and "미확인" in " ".join(rights["limitations"])


def test_photo_rights_verify_actual_bytes_and_never_trust_cached_claims(tmp_path, monkeypatch):
    import json
    from office import feeds
    from office.exports import write_blog_exports, write_rights_manifest
    raw = photo_bytes()
    source = photo_packet(["https://blog.kakaocdn.net/photo?signature=not-for-manifest"])
    monkeypatch.setattr(feeds, "fetch_public", lambda url, **kwargs: (raw, url, "image/png"))
    write_blog_exports(source, tmp_path)
    cache_path = tmp_path / "source-photos.json"
    cached = json.loads(cache_path.read_text(encoding="utf-8"))
    cached["photos"][0].update(rights="commercially_cleared", source_url="https://attacker.invalid/?signature=leaked", extra="signature=leaked")
    cache_path.write_text(json.dumps(cached), encoding="utf-8")
    rights = json.loads(write_rights_manifest(source, tmp_path).read_text(encoding="utf-8"))
    assert rights["source_photo_verification"] == "complete"
    assert rights["external_visual_assets"][0]["rights"] == "owner_supplied_reference"
    assert "attacker" not in json.dumps(rights) and "signature=" not in json.dumps(rights)
    (tmp_path / "source-photo-01.png").write_bytes(b"changed after caching")
    rights = json.loads(write_rights_manifest(source, tmp_path).read_text(encoding="utf-8"))
    assert rights["source_photo_verification"] == "unverified_or_incomplete" and rights["external_visual_assets"] == []
