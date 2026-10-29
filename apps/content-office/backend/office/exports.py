"""Local, paste-safe exports of the approved source. Never publishes content."""
from __future__ import annotations

from html import escape
import json
import os
from pathlib import Path
import re

from .store import WorkflowError


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


def safe_fragment(body: str) -> str:
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
            heading = re.match(r"^(#{1,6})\s+(.+)$", line)
            numbered = re.match(r"^(\d+)[.)]\s+(.+)$", line)
            bullet = re.match(r"^[-*]\s+(.+)$", line)
            quote = re.match(r"^>\s?(.*)$", line)
            if quote:
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
    if not re.search(r"<h[23]>", "".join(blocks)):
        blocks.insert(0, "<h2>핵심 내용</h2>")
    return '<style></style>\n<article class="hb-post" style="max-width:760px;margin:0 auto;color:inherit;line-height:1.9;overflow-wrap:anywhere">\n' + "\n".join(blocks) + "\n</article>\n"


def reference_lines(packet: dict) -> list[str]:
    return [f"[{e.get('id', index)}] {e.get('claim', '')}\n{e['url']}" for index, e in enumerate(packet.get("evidence", []), 1) if isinstance(e, dict) and re.match(r"^https?://", str(e.get("url", "")))]


def offer_line(offer) -> str:
    from .offers import offer_text
    return offer_text(offer)


def blog_markdown(packet: dict, offer: dict | None = None) -> str:
    body = packet["body"]
    refs = reference_lines(packet)
    if refs:
        body += "\n\n## 출처와 확인 범위\n\n" + "\n\n".join(refs)
    line = offer_line(offer)
    if line:
        body += "\n\n" + line
    return body


def write_blog_exports(packet: dict, folder: Path, offer: dict | None = None) -> list[Path]:
    body = blog_markdown(packet, offer)
    return [write_text(folder, "tistory.md", body + "\n"),
            write_text(folder, "tistory.html", safe_fragment(body)),
            write_text(folder, "naver.txt", packet["title"] + "\n\n" + plain_text(body) + "\n")]


def blog_reader_html(title: str, content: str, format: str = 'html') -> str:
    """Readable preview of a verified export; the stored publishing fragment stays intact."""
    labels = {'html': '블로그 읽기', 'markdown': 'Markdown 원문', 'naver': '네이버 텍스트', 'draft': '미승인 초안 · 블로그로 내보낼 때의 모습'}
    if format not in labels:
        raise WorkflowError('지원하지 않는 블로그 형식입니다')
    body = content if format in ('html', 'draft') else '<pre class="source-text">' + escape(content) + '</pre>'
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


def write_rights_manifest(packet: dict, folder: Path) -> Path:
    manifest = {"status": "not_commercially_cleared", "visual_source": "first_party_programmatic_shapes_and_text", "external_visual_assets": [], "font": "System Korean font used for rendering; font files are not distributed", "evidence": [{"id": e.get("id"), "url": e.get("url"), "claim": e.get("claim")} for e in packet.get("evidence", [])], "limitations": ["자료 출처 링크는 이미지·원문 재배포 허가가 아닙니다", "판매용 PDF 및 외부 상품 권리는 별도 검토가 필요합니다", "실제 서비스 화면·타사 로고·실제 시험 문항을 복제하지 않았습니다"]}
    return write_text(folder, "asset-rights.json", json.dumps(manifest, ensure_ascii=False, indent=2))


def write_reference_pdf(packet: dict, folder: Path) -> Path:
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
    story.append(Paragraph("게시 전 확인", heading))
    for item in ["주장과 수치가 출처의 범위에 맞는지 확인", "최신성·한계·개인 경험과 사실 구분", "대표 이미지·음성·자막과 글의 내용 일치 확인"]:
        story.append(Paragraph("□ " + escape(item), body))
    story.append(Paragraph("출처", heading))
    for ref in reference_lines(packet): story.append(Paragraph(escape(ref).replace("\n", "<br/>"), body))
    story.append(Spacer(1, 16)); story.append(Paragraph("검토용 무료 자료입니다. 판매 권리 검수 완료를 의미하지 않습니다.", body))
    path = folder / "summary-checklist.pdf"
    SimpleDocTemplate(str(path), pagesize=A4, invariant=1, rightMargin=44, leftMargin=44, topMargin=44, bottomMargin=44, title=packet["title"], author="HeoBrain Content Office").build(story)
    return path
