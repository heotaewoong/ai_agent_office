"""Local, paste-safe exports of the approved source. Never publishes content."""
from __future__ import annotations

from html import escape, unescape
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

from .store import WorkflowError

SOURCE_PHOTO_HOSTS = frozenset({"blog.kakaocdn.net", "t1.daumcdn.net"})
SOURCE_PHOTO_NAME_PATTERN = re.compile(r"source-photo-0[1-8]\.(?:png|jpg|webp)")
SOURCE_PHOTO_MAX_BYTES = 8 * 1024 * 1024
SOURCE_PHOTO_TOTAL_BYTES = 32 * 1024 * 1024
SOURCE_PHOTO_MAX_PIXELS = 25_000_000
MARKDOWN_PHOTO = re.compile(r"!\[([^\]\r\n]*)\]\((https://[^\s)]+)\)")


# TrueType (.ttf) only: reportlab cannot read TTC collections or CFF-based OTF such as Noto Sans CJK.
FONT_CANDIDATES = ("C:/Windows/Fonts/malgun.ttf",
                   "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
                   "/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",
                   "/usr/share/fonts/truetype/noto/NotoSansKR-Regular.ttf")


BOLD_FONT_CANDIDATES = ("C:/Windows/Fonts/malgunbd.ttf",
                        "/usr/share/fonts/truetype/nanum/NanumSquareNeo-cBd.ttf",
                        "/usr/share/fonts/truetype/nanum/NanumSquareB.ttf",
                        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
                        "/usr/share/fonts/truetype/nanum/NanumBarunGothicBold.ttf",
                        "/usr/share/fonts/truetype/noto/NotoSansKR-Bold.ttf")


def korean_font(weight: str = "regular") -> Path:
    """Korean TTF for PDF and image text. weight="bold" prefers a bold face and falls back to the regular one."""
    if weight == "bold":
        explicit = os.environ.get("CONTENT_OFFICE_FONT_BOLD")
        if explicit and Path(explicit).suffix.lower() == ".ttf" and Path(explicit).is_file():
            return Path(explicit)
        for candidate in BOLD_FONT_CANDIDATES:
            if Path(candidate).is_file():
                return Path(candidate)
        return korean_font()
    explicit = os.environ.get("CONTENT_OFFICE_FONT")
    if explicit:
        path = Path(explicit)
        if path.suffix.lower() != ".ttf" or not path.is_file():
            raise WorkflowError("CONTENT_OFFICE_FONT는 존재하는 한글 TTF 파일이어야 합니다. TTC/OTF는 PDF 생성기가 읽지 못합니다 (예: fonts-nanum의 NanumGothic.ttf)")
        return path
    for candidate in FONT_CANDIDATES:
        if Path(candidate).is_file():
            return Path(candidate)
    raise WorkflowError("한글 TTF 폰트가 없습니다. Linux는 fonts-nanum을 설치하거나 CONTENT_OFFICE_FONT에 한글 TTF 경로를 지정하세요")


def write_text(folder: Path, name: str, text: str) -> Path:
    path = folder / name
    path.write_text(text, encoding="utf-8")
    return path


def plain_text(body: str) -> str:
    body = re.sub(r"(?m)^#{1,6}\s+", "", body)
    body = re.sub(r"(?m)^>\s?", "", body)
    body = re.sub(r"\[([^\]]+)\]\((https?://[^\s)]+)\)", r"\1 (\2)", body)
    body = re.sub(r"(\*\*|__)(.*?)\1", r"\2", body)
    return re.sub(r"`([^`]+)`", r"\1", body).strip()


def safe_inline(text: str) -> str:
    """A small paste-safe subset: escaped text, emphasis, inline code and HTTP links."""
    pattern = re.compile(r'\[([^\]\n]+)\]\((https?://[^\s)]+)\)|\*\*([^*\n]+)\*\*|`([^`\n]+)`|https?://[^\s<>]+')
    rendered, cursor = [], 0
    for match in pattern.finditer(text):
        rendered.append(escape(text[cursor:match.start()]))
        if match.group(1):
            rendered.append(f'<a href="{escape(match.group(2), quote=True)}" rel="noopener noreferrer">{escape(match.group(1))}</a>')
        elif match.group(3):
            rendered.append('<strong>' + escape(match.group(3)) + '</strong>')
        elif match.group(4):
            rendered.append('<code>' + escape(match.group(4)) + '</code>')
        else:
            url = match.group().rstrip('.,;!')
            rendered.append(f'<a href="{escape(url, quote=True)}" rel="noopener noreferrer">{escape(url)}</a>' + escape(match.group()[len(url):]))
        cursor = match.end()
    return ''.join(rendered) + escape(text[cursor:])


def _source_image_url(value):
    if SOURCE_PHOTO_NAME_PATTERN.fullmatch(value):
        return value
    # Only the public image hosts used by the owner's source articles; never local paths or arbitrary tracking hosts.
    try:
        url = urlsplit(value)
        if (url.scheme == "https" and url.hostname in SOURCE_PHOTO_HOSTS
                and not url.username and not url.password and url.port in (None, 443)):
            return value
    except ValueError:
        pass
    return None


def _prose_blocks(body: str) -> str:
    blocks = []
    for block in re.split(r"\n\s*\n", body.strip()):
        lines = block.splitlines()
        if len(lines) >= 2 and lines[0].strip().startswith('|') and re.fullmatch(r'\|?[\s:|\-]+\|?', lines[1].strip()):
            cells = lambda row: [safe_inline(value.strip()) for value in row.strip().strip('|').split('|')]
            headers = cells(lines[0])
            row_index, rows = 2, []
            while row_index < len(lines) and lines[row_index].strip().startswith('|'):
                rows.append(cells(lines[row_index]))
                row_index += 1
            head = ''.join('<th scope="col" style="padding:14px 16px;text-align:left;border-bottom:1px solid #cdded8;background:#edf6f2">' + cell + '</th>' for cell in headers)
            table_rows = ''.join('<tr>' + ''.join('<td style="padding:14px 16px;vertical-align:top;border-bottom:1px solid #e2eae7">' + cell + '</td>' for cell in row) + '</tr>' for row in rows)
            blocks.append('<div class="hb-table-wrap" style="max-width:100%;overflow-x:auto;margin:26px 0">'
                          '<table style="border-collapse:collapse;width:100%;min-width:480px;font-size:inherit;line-height:1.8">'
                          '<thead><tr>' + head + '</tr></thead><tbody>' + table_rows + '</tbody></table></div>')
            lines = lines[row_index:]
        for line in lines:
            image = re.fullmatch(r'!\[([^\]\n]*)\]\(([^\s)]+)\)', line.strip())
            heading = re.match(r"^(#{1,6})\s+(.+)$", line)
            numbered = re.match(r"^(\d+)[.)]\s+(.+)$", line)
            bullet = re.match(r"^[-*]\s+(.+)$", line)
            quote = re.match(r"^>\s?(.*)$", line)
            if image and (image_url := _source_image_url(image[2])):
                url = escape(image_url, quote=True)
                alt = escape(image[1], quote=True)
                blocks.append(f'<figure style="margin:24px 0"><a href="{url}" target="_blank" rel="noopener noreferrer"><img src="{url}" alt="{alt}" loading="lazy" decoding="async" referrerpolicy="no-referrer" style="display:block;max-width:100%;height:auto;margin:auto"></a><figcaption style="margin-top:10px;font-size:.9em">{alt}</figcaption></figure>')
            elif quote:
                if quote[1].strip():
                    blocks.append('<blockquote style="margin:20px 0;padding:14px 18px;border-left:4px solid #8cc9bd;background:#f3f9f7">'
                                  f'{safe_inline(quote[1])}</blockquote>')
            elif heading:
                level = min(3, max(2, len(heading[1])))
                blocks.append(f'<h{level}>{safe_inline(heading[2])}</h{level}>')
            elif numbered:
                blocks.append('<div class="hb-number-item" style="display:flex;gap:12px;margin:12px 0">'
                              f'<span class="hb-number-badge" style="flex:none">{numbered[1]}.</span>'
                              f'<span style="min-width:0">{safe_inline(numbered[2])}</span></div>')
            elif bullet:
                blocks.append(f'<p style="padding-left:16px">• {safe_inline(bullet[1])}</p>')
            else:
                blocks.append(f'<p style="margin:12px 0">{safe_inline(line)}</p>')
    return "\n".join(blocks)


def safe_fragment(body: str) -> str:
    """Keep code fences literal; untrusted source markup remains escaped."""
    parts, prose, code = [], [], []
    fence = None

    def flush_prose():
        if prose:
            parts.append(_prose_blocks("\n".join(prose)))
            prose.clear()

    for line in body.splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})([^\r\n]*)$", line)
        if fence is None and marker:
            flush_prose()
            fence = marker[1]
        elif fence is not None:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                parts.append('<pre style="max-width:100%;overflow-x:auto;white-space:pre;background:#17242b;color:#f2f7f8;padding:20px;border-radius:12px"><code>' + escape("\n".join(code)) + '</code></pre>')
                code.clear()
                fence = None
            else:
                code.append(line)
        else:
            prose.append(line)
    if fence is not None:
        parts.append('<pre style="max-width:100%;overflow-x:auto;white-space:pre"><code>' + escape("\n".join(code)) + '</code></pre>')
    flush_prose()
    content = "\n".join(parts)
    if not re.search(r"<h[23]>", content):
        content = "<h2>핵심 내용</h2>\n" + content
    return '<style></style>\n<article class="hb-post" style="max-width:760px;margin:0 auto;color:inherit;line-height:1.9;overflow-wrap:anywhere">\n' + content + "\n</article>\n"


def reference_lines(packet: dict) -> list[str]:
    return [f"[{e.get('id', index)}] {e.get('claim', '')}\n{e['url']}" for index, e in enumerate(packet.get("evidence", []), 1) if isinstance(e, dict) and re.match(r"^https?://", str(e.get("url", "")))]


def offer_line(offer) -> str:
    from .offers import offer_text
    return offer_text(offer)


def write_campaign_exports(offer: dict | None, folder: Path) -> list[Path]:
    if not offer:
        return []
    from .offers import offer_snapshot
    text = offer_line(offer)
    metadata = {"kind": "campaign-delivery-review", "offer": offer_snapshot(offer),
                "free_pdf_selected": bool(offer.get("free_pdf")), "product_selected": bool(offer.get("product")),
                "coupon_selected": bool(offer.get("coupon")), "profile_links_updated": False,
                "automatic_dm_enabled": False, "external_published": False}
    instructions = text + "\n\n플랫폼 전달 확인\nInstagram·YouTube Shorts: 실제 프로필 링크에 위 자료/상품 주소를 등록하고 열리는지 확인하세요.\nYouTube 일반 영상: 설명란에 주소를 넣고 계정의 링크 사용 조건을 확인하세요.\n댓글 자동 DM은 별도 연결입니다. 이 파일 생성으로 프로필 수정·메시지 발송·공개 게시가 실행되지 않습니다.\n"
    return [write_text(folder, "profile-links.txt", instructions), write_text(folder, "campaign-delivery.json", json.dumps(metadata, ensure_ascii=False, indent=2))]


def blog_markdown(packet: dict, offer: dict | None = None) -> str:
    body = packet["body"]
    if packet.get("hashtags"):
        body += "\n\n" + " ".join(packet["hashtags"])
    refs = reference_lines(packet)
    if refs:
        body += "\n\n## 출처와 확인 범위\n\n" + "\n\n".join(refs)
    line = offer_line(offer)
    if line:
        body += "\n\n" + line
    return body


def _photo_lines(body):
    """Yield prose lines only: Markdown image examples inside code fences are not fetched."""
    fence = None
    for index, line in enumerate(body.splitlines(keepends=True)):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})([^\r\n]*)", line)
        if fence is None and marker:
            fence = marker[1]
        elif fence is not None:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
        else:
            yield index, line


def _photo_info(raw):
    from PIL import Image
    if not raw or len(raw) > SOURCE_PHOTO_MAX_BYTES:
        raise WorkflowError("원문 사진은 한 장에 8MB 이하여야 합니다")
    try:
        with Image.open(BytesIO(raw)) as image:
            kind, width, height = image.format, image.width, image.height
            if kind not in ("PNG", "JPEG", "WEBP") or getattr(image, "is_animated", False) or getattr(image, "n_frames", 1) != 1:
                raise ValueError("unsupported image")
            if width <= 0 or height <= 0 or width * height > SOURCE_PHOTO_MAX_PIXELS:
                raise ValueError("pixel limit")
            image.verify()
        with Image.open(BytesIO(raw)) as image:
            image.load()
    except Exception:
        raise WorkflowError("원문 사진은 정상적인 PNG·JPEG·WebP 정지영상이며 2,500만 화소 이하여야 합니다") from None
    return {"format": kind, "width": width, "height": height}


def _save_photo_cache(path, photos):
    partial = path.with_suffix(".json.partial")
    partial.write_text(json.dumps({"version": 1, "photos": photos}, ensure_ascii=False, indent=2), encoding="utf-8", newline="")
    partial.replace(path)


def _source_photo_urls(body):
    return list(dict.fromkeys(match[2] for _, line in _photo_lines(body) for match in MARKDOWN_PHOTO.finditer(line) if _source_image_url(match[2])))


def _localize_source_photos(packet, folder):
    from .feeds import fetch_public
    original = packet["body"]
    urls = _source_photo_urls(original)
    if len(urls) > 8:
        raise WorkflowError("원문 사진은 최대 8장까지 보존할 수 있습니다")
    cache_path = folder / "source-photos.json"
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        cached = {item["url_sha256"]: item for item in cache["photos"] if isinstance(item, dict)}
    except (OSError, ValueError, KeyError, TypeError):
        cached = {}
    records, paths, replacements, total = [], [], {}, 0
    for number, url in enumerate(urls, 1):
        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
        previous = cached.get(url_hash) or {}
        raw = None
        name = previous.get("filename", "")
        if isinstance(name, str) and SOURCE_PHOTO_NAME_PATTERN.fullmatch(name) and name.startswith(f"source-photo-{number:02}."):
            try:
                candidate = folder / name
                if candidate.resolve().parent == folder.resolve() and candidate.stat().st_size <= SOURCE_PHOTO_MAX_BYTES:
                    data = candidate.read_bytes()
                    if hashlib.sha256(data).hexdigest() == previous.get("sha256"):
                        raw = data
            except (OSError, WorkflowError):
                pass
        if raw is None:
            try:
                raw, _, _ = fetch_public(url, maximum=SOURCE_PHOTO_MAX_BYTES, allowed_hosts=SOURCE_PHOTO_HOSTS)
            except Exception:
                raise WorkflowError(f"원문 사진 {number}을 안전하게 가져오지 못했습니다. 사진을 누락하지 않고 블로그 제작을 중단합니다") from None
        info = _photo_info(raw)
        total += len(raw)
        if total > SOURCE_PHOTO_TOTAL_BYTES:
            raise WorkflowError("원문 사진 합계는 32MB 이하여야 합니다")
        extension = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}[info["format"]]
        name = f"source-photo-{number:02}.{extension}"
        path = folder / name
        if path.is_symlink():
            raise WorkflowError("원문 사진 저장 경로를 검증하지 못했습니다")
        path.write_bytes(raw)
        source = urlsplit(url)
        records.append({"filename": name, "url_sha256": url_hash, "source_url": source._replace(query="", fragment="").geturl(),
                        "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), **info,
                        "rights": "owner_supplied_reference", "commercial_status": "not_commercially_cleared"})
        paths.append(path)
        replacements[url] = name
        _save_photo_cache(cache_path, records)
    if not urls:
        _save_photo_cache(cache_path, [])
    # Keep the submitted text separate from the localized publishing copy; no Windows newline conversion.
    original_path = folder / "source-original.md"
    original_path.write_text(original, encoding="utf-8", newline="")
    prose_lines = dict(_photo_lines(original))
    localized = [MARKDOWN_PHOTO.sub(lambda match: f"![{match[1]}]({replacements.get(match[2], match[2])})", line) if index in prose_lines else line for index, line in enumerate(original.splitlines(keepends=True))]
    return "".join(localized), [original_path, cache_path, *paths]


def write_blog_exports(packet: dict, folder: Path, offer: dict | None = None) -> list[Path]:
    extra = []
    if packet.get("preserve_original") is True:
        localized, extra = _localize_source_photos(packet, folder)
        packet = {**packet, "body": localized}
    body = blog_markdown(packet, offer)
    files = [write_text(folder, "tistory.md", body + "\n"),
            write_text(folder, "tistory.html", safe_fragment(body)),
            write_text(folder, "naver.txt", packet["title"] + "\n\n" + plain_text(body) + "\n"), *extra]
    if packet.get("titles"):
        files.append(write_text(folder, "title-options.txt", "\n".join(packet["titles"]) + "\n"))
    return files


def blog_reader_html(title: str, content: str, format: str = 'html') -> str:
    """Readable preview of a verified export; the stored publishing fragment stays intact."""
    labels = {'html': '블로그 읽기', 'markdown': 'Markdown 원문', 'naver': '네이버 텍스트', 'draft': '미승인 초안 · 블로그로 내보낼 때의 모습'}
    if format not in labels:
        raise WorkflowError('지원하지 않는 블로그 형식입니다')
    body = content if format in ('html', 'draft') else '<pre class="source-text">' + escape(content) + '</pre>'
    if format in ('html', 'draft'):
        # The reader supplies its own title; only suppress an identical leading body heading.
        heading = re.search(r'(<article\b[^>]*>\s*)<h([1-3])>(.*?)</h\2>\s*', body, re.S)
        if heading and " ".join(unescape(re.sub(r'<[^>]+>', '', heading[3])).split()) == " ".join(title.split()):
            body = body[:heading.start()] + heading[1] + body[heading.end():]
    return f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)} · HeoBrain</title>
<style>
*{{box-sizing:border-box}}html{{color-scheme:light}}body{{margin:0;background:#fff;color:#17212e;font-family:"Pretendard","Noto Sans KR","Malgun Gothic",system-ui,sans-serif;font-size:19px;line-height:1.95;word-break:keep-all;overflow-wrap:anywhere}}
.reader{{max-width:850px;margin:auto;padding:54px 38px 80px}}.brand{{color:#16746b;font-size:13px;font-weight:750;letter-spacing:.1em}}.reading-status{{float:right;color:#647184;letter-spacing:0;font-weight:500}}header{{padding-bottom:30px;border-bottom:1px solid #e3e8ed;margin-bottom:36px}}h1{{font-size:clamp(29px,4vw,43px);line-height:1.4;letter-spacing:-.04em;margin:22px 0 17px;font-weight:800}}.format-note{{color:#647184;font-size:14px;margin:0}}.hb-post{{max-width:none!important}}.hb-post h2{{font-size:25px;line-height:1.5;margin:46px 0 18px;padding-top:5px;letter-spacing:-.025em}}.hb-post h3{{font-size:21px;margin:30px 0 14px}}.hb-post p{{margin:18px 0!important}}.hb-post>p:first-of-type{{font-size:21px;color:#334155;line-height:1.95}}a{{color:#087d76;text-decoration-thickness:1px;text-underline-offset:4px;word-break:break-word}}code{{font-size:.9em;background:#eef5f4;padding:2px 5px;border-radius:4px}}.source-text{{white-space:pre-wrap;overflow-wrap:anywhere;font-family:ui-monospace,"Malgun Gothic",monospace;font-size:16px;line-height:1.95;word-break:normal}}.hb-number-badge{{font-weight:750;color:#087d76}}
@media(max-width:600px){{body{{font-size:18px}}.reader{{padding:28px 20px 52px}}.brand{{font-size:11px}}.reading-status{{float:none;display:block;margin-top:8px}}h1{{margin-top:18px}}.hb-post h2{{font-size:23px;margin-top:34px}}.hb-post>p:first-of-type{{font-size:19px}}}}
</style></head><body><main class="reader"><header><div class="brand">HeoBrain / AI 뉴스<span class="reading-status">검토용 · 미게시</span></div>
<h1>{escape(title)}</h1><p class="format-note">{labels[format]}</p></header>{body}</main></body></html>'''


def write_video_exports(packet: dict, folder: Path, offer: dict | None = None) -> list[Path]:
    plan = packet["video"]
    script = "# " + plan["title"] + "\n\n"
    for index, scene in enumerate(plan["scenes"], 1):
        script += f"## 장면 {index}\n\n말하기: {scene['narration']}\n\n화면: {scene['caption']}\n\n시각 구성: {scene.get('visual', 'explanation')}\n\n"
    description = plan.get("description", "") + "\n\n" + "\n\n".join(reference_lines(packet))
    line = offer_line(offer)
    if line:
        description += "\n\n" + line
    description += "\n\n이 영상의 내레이션은 합성 음성입니다. 게시 전 원문·음성·자막·대표 이미지를 확인하세요.\n"
    return [write_text(folder, "youtube-script.md", script),
            write_text(folder, "youtube-plan.json", json.dumps(plan, ensure_ascii=False, indent=2)),
            write_text(folder, "description.txt", description)]


PEXELS_LICENSE_URL = "https://www.pexels.com/license/"


def stock_credit_line(attributions) -> str:
    """Pexels asks apps to show Pexels as the source and credit creators when possible."""
    names = []
    for item in attributions or []:
        name = str((item or {}).get("name") or "").strip()[:80]
        if name and name not in names:
            names.append(name)
    return "영상 소스: Pexels" + (f" ({', '.join(names)})" if names else "") + " · https://www.pexels.com"


def write_rights_manifest(packet: dict, folder: Path, stock_footage=None) -> Path:
    manifest = {"status": "not_commercially_cleared", "visual_source": "first_party_programmatic_shapes_and_text", "external_visual_assets": [], "font": "System Korean font used for rendering; font files are not distributed", "evidence": [{"id": e.get("id"), "url": e.get("url"), "claim": e.get("claim")} for e in packet.get("evidence", [])], "limitations": ["자료 출처 링크는 이미지·원문 재배포 허가가 아닙니다", "판매용 PDF 및 외부 상품 권리는 별도 검토가 필요합니다", "실제 서비스 화면·타사 로고·실제 시험 문항을 복제하지 않았습니다"]}
    urls = _source_photo_urls(packet["body"]) if packet.get("preserve_original") is True else []
    if urls:
        try:
            cache = json.loads((folder / "source-photos.json").read_text(encoding="utf-8"))
            if not isinstance(cache, dict) or cache.get("version") != 1 or not isinstance(cache.get("photos"), list):
                raise ValueError("invalid photo cache")
            cached = {item["url_sha256"]: item for item in cache["photos"] if isinstance(item, dict)}
        except (OSError, UnicodeError, ValueError, KeyError, TypeError):
            cached = {}
        references, verified = [], []
        for number, url in enumerate(urls, 1):
            url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
            reference = {"url_sha256": url_hash, "source_url": urlsplit(url)._replace(query="", fragment="").geturl(),
                         "rights": "owner_supplied_reference", "commercial_status": "not_commercially_cleared", "verification": "unverified"}
            record = cached.get(url_hash) or {}
            try:
                name = record.get("filename", "")
                if not isinstance(name, str) or not SOURCE_PHOTO_NAME_PATTERN.fullmatch(name) or not name.startswith(f"source-photo-{number:02}."):
                    raise ValueError("invalid photo name")
                path = folder / name
                if path.resolve().parent != folder.resolve() or not path.is_file() or path.stat().st_size > SOURCE_PHOTO_MAX_BYTES:
                    raise ValueError("invalid photo path")
                raw = path.read_bytes()
                checksum = hashlib.sha256(raw).hexdigest()
                if checksum != record.get("sha256") or len(raw) != record.get("bytes"):
                    raise ValueError("invalid photo checksum")
                info = _photo_info(raw)
                extension = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}[info["format"]]
                if name != f"source-photo-{number:02}.{extension}":
                    raise ValueError("invalid photo format")
                reference["verification"] = "local_bytes_verified"
                verified.append({**reference, "filename": name, "sha256": checksum, "bytes": len(raw), **info})
            except (OSError, ValueError, KeyError, TypeError, WorkflowError):
                pass
            references.append(reference)
        complete = len(verified) == len(references)
        manifest.update(visual_source="first_party_programmatic_shapes_and_owner_supplied_references", external_visual_assets=verified,
                        external_visual_references=references, source_photo_verification="complete" if complete else "unverified_or_incomplete")
        manifest["limitations"].append("원문 참조 사진의 로컬 바이트 보존을 확인했습니다. 소유권·초상권·상업 이용 허가는 별도 확인이 필요합니다" if complete else "원문 참조 사진의 보존 결과가 미확인이거나 일부만 확인됐습니다. 사진을 포함한 블로그의 완성을 뜻하지 않습니다. 소유권·상업 이용 허가도 미확인입니다")
    stock = [item for item in (stock_footage or []) if isinstance(item, dict)]
    if stock:
        manifest["visual_source"] += "+pexels_stock_footage"
        manifest["external_visual_assets"] = list(manifest["external_visual_assets"]) + [{
            "provider": "pexels", "pexels_video_id": item.get("pexels_video_id"), "page_url": str(item.get("page_url") or "")[:300],
            "creator": str(item.get("name") or "")[:120], "creator_url": str(item.get("user_url") or "")[:300],
            "license_url": PEXELS_LICENSE_URL, "rights": "pexels_license",
            "commercial_status": "pexels_license_free_use_attribution_appreciated"} for item in stock]
        manifest["stock_credit"] = stock_credit_line(stock)
        manifest["limitations"].append("Pexels 라이선스: 무료·상업 이용·편집 가능, 출처 표기 권장. 편집 없이 그대로 재판매·스톡 사이트 재배포 금지, "
                                        "영상 속 인물·상표가 제품을 보증하는 것처럼 쓰지 않습니다. 인물·상표·사유 재산 노출은 출고 전 사람이 확인합니다")
    return write_text(folder, "asset-rights.json", json.dumps(manifest, ensure_ascii=False, indent=2))


def write_reference_pdf(packet: dict, folder: Path, offer: dict | None = None) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    pdfmetrics.registerFont(TTFont("HBKorean", str(korean_font())))
    body = ParagraphStyle("Body", fontName="HBKorean", fontSize=10, leading=17, textColor=colors.HexColor("#16233b"), alignment=TA_LEFT, wordWrap="CJK")
    title = ParagraphStyle("Title", parent=body, fontSize=20, leading=28, spaceAfter=20)
    heading = ParagraphStyle("Heading", parent=body, fontSize=13, leading=20, spaceBefore=16, spaceAfter=8)
    story = [Paragraph(escape(packet["title"]), title), Paragraph("출처 기반 요약 · 확인 체크리스트", heading)]
    for section in re.split(r"\n\s*\n", packet["body"]):
        story.append(Paragraph(escape(plain_text(section)).replace("\n", "<br/>"), body)); story.append(Spacer(1, 9))
    campaign = offer_line(offer)
    if campaign:
        from .offers import offer_url
        story.append(Paragraph("상품·쿠폰 안내", heading))
        story.append(Paragraph(escape(campaign), body))
        if offer.get("url"):
            story.append(Paragraph(f'<link href="{escape(offer_url(offer), quote=True)}" color="#245dc1">상품과 쿠폰 적용 조건 확인하기</link>', body))
        if offer.get("free_pdf"):
            story.append(Paragraph(f'<link href="{escape(offer["free_pdf"]["url"], quote=True)}" color="#245dc1">무료 PDF 받기</link>', body))
    story.append(Paragraph("게시 전 확인", heading))
    for item in ["주장과 수치가 출처의 범위에 맞는지 확인", "최신성·한계·개인 경험과 사실 구분", "대표 이미지·음성·자막과 글의 내용 일치 확인"]:
        story.append(Paragraph("□ " + escape(item), body))
    story.append(Paragraph("출처", heading))
    for ref in reference_lines(packet): story.append(Paragraph(escape(ref).replace("\n", "<br/>"), body))
    story.append(Spacer(1, 16)); story.append(Paragraph("검토용 무료 자료입니다. 판매 권리 검수 완료를 의미하지 않습니다.", body))
    path = folder / "summary-checklist.pdf"
    SimpleDocTemplate(str(path), pagesize=A4, invariant=1, rightMargin=44, leftMargin=44, topMargin=44, bottomMargin=44, title=packet["title"], author="HeoBrain Content Office").build(story)
    return path
