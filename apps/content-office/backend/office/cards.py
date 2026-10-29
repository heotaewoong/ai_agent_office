"""승인① 원고 → 카드뉴스 6~8장(1080x1080 PNG). 문구는 모델이 쓰고 모델이 다시 읽어 검토하며, 넘침·오탈자·금지 주장·중복은 코드가 검사한다.

이미지: 표지·본문·마무리 세 가지 템플릿. 굵은 한글 글꼴과 그라데이션 배경을 쓰고, 운영자가 제작 설정에서 생성 배경을
켰으면 표지 한 장에만 생성 배경(어둡게 눌러서)을 깐다. 승인①②를 만들거나 바꾸지 않는다.
"""
from __future__ import annotations

from PIL import Image, ImageDraw

from .brand import brand_system_prompt, load_brand
from .briefs import brief_for_job
from .editorial import BASE
from .exports import korean_font
from .media import artifact_record, cover_background, text_box
from .providers import Provider
from .quiz import output_folder, packet_context, save_job_output, text_issues
from .store import Store, WorkflowError, canonical, now

SLIDE_SCHEMA = {"type": "object", "properties": {"title": {"type": "string"}, "body": {"type": "string"}}, "required": ["title", "body"], "additionalProperties": False}
CARDS_SCHEMA = {"type": "object", "properties": {"slides": {"type": "array", "minItems": 6, "maxItems": 8, "items": SLIDE_SCHEMA}}, "required": ["slides"], "additionalProperties": False}
REVIEW_SCHEMA = {"type": "object", "properties": {"cards": {"type": "array", "items": {"type": "object", "properties": {
    "index": {"type": "integer"}, "ok": {"type": "boolean"}, "problems": {"type": "array", "items": {"type": "string"}}},
    "required": ["index", "ok", "problems"], "additionalProperties": False}}}, "required": ["cards"], "additionalProperties": False}
MIN_SLIDES, MAX_SLIDES = 6, 8
TITLE_LIMIT, BODY_LIMIT = 22, 95
SIZE = (1080, 1080)
# 본문 템플릿의 제목·본문 상자 (x, y, 폭, 높이)와 글자 크기 범위. 최소 크기까지 내려가야 들어가면 '넘침'으로 본다.
TITLE_BOX, TITLE_SIZE, TITLE_MIN = (90, 300, 900, 330), 84, 48
BODY_BOX, BODY_SIZE, BODY_MIN = (90, 660, 900, 290), 44, 30
BRAND_LABEL = "HeoBrain"
# (위 색, 아래 색, 강조색) — 장마다 돌아가며 쓴다. 모두 어두운 바탕이라 흰 글자가 읽힌다.
PALETTES = [("#0f1b3d", "#1c3a6e", "#6de8d5"), ("#1a1038", "#3b2a7a", "#c3b5ff"), ("#0b2a2e", "#135b5c", "#ffc684"),
            ("#2a1430", "#6a2f5a", "#ffb3c7"), ("#11213a", "#1f4e79", "#94d9ff"), ("#1f1f1f", "#3a3a3a", "#f3d35b")]
CTA_PALETTE = ("#f6f1e7", "#efe4cf", "#d64541")

INSTRUCTIONS = f"""승인된 원고로 인스타그램 카드뉴스 {MIN_SLIDES}~{MAX_SLIDES}장을 쓴다. 독자 한 명에게 말하듯 해요체로 쓴다.

가장 중요한 규칙: 각 카드는 그 카드만 읽어도 뜻이 통해야 한다. 앞 카드를 봐야 아는 대명사·생략(이것, 그 기능, 비용)을 쓰지 않고
'무엇이 무엇을' 주어와 대상을 매번 적는다. 숫자는 무엇의 값인지 함께 쓴다(예: "입력 100만 토큰당 0.10달러" → "이 API는 입력 글 100만 토큰마다 0.10달러를 받아요").
전문용어·영어 약어는 처음 나올 때 한 줄로 풀어 쓴다. 전보문처럼 조사를 빼거나 명사만 나열하지 않는다.

카드 구성
- 1장: 독자가 지금 겪는 상황을 한 문장으로 짚는 후크. 제목은 독자의 말이나 질문처럼.
- 2장: 그 문제가 왜 생기는지, 또는 이 소식이 왜 독자에게 중요한지.
- 3장: 핵심 개념이나 발표 내용을 한 문장으로 풀어 설명.
- 4~{MAX_SLIDES - 1}장: 어떻게 쓰는지·판단 기준·구체 예시를 한 장에 하나씩. 앞 장과 자연스럽게 이어지되 혼자서도 읽히게.
- 마지막 장: '오늘 할 일' 하나(독자가 10분 안에 할 수 있는 행동)와 audience.cta 문구.

형식: title은 {TITLE_LIMIT}자 이하(마침표 없음), body는 {BODY_LIMIT}자 이하 2문장 이내이며 각 문장은 끝까지 완결한다. 제목은 서로 다르게.
원고에 없는 수치·사실을 넣지 않고 줄표(—)·과장·훈계 표현을 쓰지 않으며 표기 고정 목록을 따른다."""

REVIEW_INSTRUCTIONS = """너는 한국어 카드뉴스 편집자다. 각 카드를 '그 카드만 보는 독자'의 눈으로 읽고 판단한다.
ok=false로 표시할 기준: (1) 이 카드만 읽으면 무슨 말인지 모른다(주어·대상이 빠졌거나 앞 카드를 전제한다), (2) 숫자나 용어가 무엇에 대한 것인지 없다,
(3) 전보문·명사 나열·조사 생략·번역투로 어색하다, (4) 두 문장이 서로 안 이어진다, (5) 앞뒤 카드와 순서가 맞지 않아 흐름이 끊긴다.
problems에는 무엇이 왜 문제인지와 어떻게 고치면 되는지를 한 줄씩 한국어로 적는다. 사실 여부는 판단하지 않는다."""


def glossary_issues(text, brand):
    """glossary.json terms의 비표준 표기(키)가 보이면 고정 표기(값)로 바꾸라고 알린다."""
    hits = [written for written in brand.get("terms", {}) if written and written in (text or "")]
    hits = [written for written in hits if not any(other != written and written in other for other in hits)]
    return [f"표기 통일: '{written}' 대신 '{brand['terms'][written]}'로 적어요" for written in hits]


def measure_overflow(slide):
    """실제 폰트로 1080x1080 캔버스에 그려 보고 최소 글자 크기에 닿거나 잘려야 하면 넘침."""
    image = Image.new("RGB", SIZE, "#0b1327")
    draw = ImageDraw.Draw(image)
    overflow = []
    for name, text, box, size, minimum, face in (("제목", slide.get("title", ""), TITLE_BOX, TITLE_SIZE, TITLE_MIN, korean_font("bold")),
                                                 ("본문", slide.get("body", ""), BODY_BOX, BODY_SIZE, BODY_MIN, korean_font())):
        try:
            metrics = text_box(draw, text, box, size, minimum_size=minimum, font_path=face)
        except WorkflowError:
            overflow.append(name)
            continue
        if metrics["font_size"] <= minimum:
            overflow.append(name)
    return overflow


def card_checks(plan, brand=None):
    brand = brand if brand is not None else load_brand()
    slides = [s for s in (plan.get("slides") or []) if isinstance(s, dict)]
    issues = []
    if not MIN_SLIDES <= len(slides) <= MAX_SLIDES:
        issues.append(f"카드는 {MIN_SLIDES}~{MAX_SLIDES}장이어야 해요 (현재 {len(slides)}장)")
    seen = {}
    for number, slide in enumerate(slides, 1):
        title, body = str(slide.get("title", "")).strip(), str(slide.get("body", "")).strip()
        if not title or not body:
            issues.append(f"{number}번 카드: 제목과 본문이 모두 필요해요")
        if len(title) > TITLE_LIMIT:
            issues.append(f"{number}번 카드: 제목이 {TITLE_LIMIT}자를 넘어요 ({len(title)}자)")
        if len(body) > BODY_LIMIT:
            issues.append(f"{number}번 카드: 본문이 {BODY_LIMIT}자를 넘어요 ({len(body)}자)")
        for name in measure_overflow(slide):
            issues.append(f"{number}번 카드: {name} 넘침. 실제 폰트로 그리면 최소 글자 크기에서도 들어가지 않거나 잘려요")
        key = " ".join(title.split())
        if key and key in seen:
            issues.append(f"{number}번 카드: 제목이 {seen[key]}번 카드와 중복돼요")
        seen.setdefault(key, number)
        issues.extend(f"{number}번 카드: {issue}" for issue in glossary_issues(title + "\n" + body, brand))
    issues.extend(text_issues([f"{s.get('title', '')}\n{s.get('body', '')}" for s in slides], brand))
    return {"passed": not issues, "issues": issues}


def review_issues(review):
    """모델 검토 결과를 결정적 검사와 같은 '{n}번 카드: ...' 문장으로 바꾼다."""
    issues = []
    for card in (review or {}).get("cards", []) or []:
        if isinstance(card, dict) and not card.get("ok", True):
            problems = [str(p) for p in card.get("problems", []) if str(p).strip()] or ["이 카드만 읽으면 뜻이 통하지 않아요"]
            issues.extend(f"{card.get('index', '?')}번 카드: {p}" for p in problems)
    return issues


# --- 그리기 ---------------------------------------------------------------------------------------
def _gradient(top, bottom):
    image = Image.new("RGB", SIZE, top)
    draw = ImageDraw.Draw(image)
    t, b = Image.new("RGB", (1, 1), top).getpixel((0, 0)), Image.new("RGB", (1, 1), bottom).getpixel((0, 0))
    for y in range(SIZE[1]):
        f = y / (SIZE[1] - 1)
        draw.line((0, y, SIZE[0], y), fill=tuple(round(t[i] + (b[i] - t[i]) * f) for i in range(3)))
    return image


def _shade(image, top_alpha=40, bottom_alpha=215):
    """아래로 갈수록 어두워지는 막을 얹어 글자가 읽히게 한다."""
    overlay = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(SIZE[1]):
        f = y / (SIZE[1] - 1)
        draw.line((0, y, SIZE[0], y), fill=(5, 10, 25, round(top_alpha + (bottom_alpha - top_alpha) * f)))
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def _pill(draw, xy, text, fill, color, size=30, font=None):
    x, y = xy
    font_path = font or korean_font("bold")
    from PIL import ImageFont
    face = ImageFont.truetype(str(font_path), size)
    width = draw.textlength(text, font=face)
    draw.rounded_rectangle((x, y, x + width + 56, y + size + 30), radius=(size + 30) // 2, fill=fill)
    draw.text((x + 28, y + 13), text, font=face, fill=color)
    return x + width + 56


def _dots(draw, index, total, accent, y=1012):
    gap, radius = 26, 7
    start = SIZE[0] // 2 - (total - 1) * gap // 2
    for n in range(1, total + 1):
        cx = start + (n - 1) * gap
        draw.ellipse((cx - radius, y - radius, cx + radius, y + radius), fill=accent if n == index else "#4a5a78")


def _watermark_number(image, index, accent):
    overlay = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    from PIL import ImageFont
    face = ImageFont.truetype(str(korean_font("bold")), 260)
    label = f"{index:02}"
    width = draw.textlength(label, font=face)
    rgb = Image.new("RGB", (1, 1), accent).getpixel((0, 0))
    draw.text((SIZE[0] - 70 - width, 40), label, font=face, fill=(*rgb, 46))
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def render_slide(slide, index, total, path, brand_label=BRAND_LABEL, *, cta=None, background=None):
    """표지(1장)·본문·마무리(마지막 장) 템플릿. 반환값은 어떤 템플릿과 배경을 썼는지."""
    bold, regular = korean_font("bold"), korean_font()
    title, body = str(slide.get("title", "")), str(slide.get("body", ""))
    template = "cover" if index == 1 else "cta" if index == total else "body"
    top, bottom, accent = PALETTES[(index - 1) % len(PALETTES)]
    used_background = "gradient"
    if template == "cover":
        if background is not None:
            image = _shade(cover_background(background, SIZE), 60, 230)
            used_background = "generated"
        else:
            image = _shade(_gradient(top, bottom), 0, 150)
        draw = ImageDraw.Draw(image)
        _pill(draw, (90, 90), brand_label, accent, "#0b1327", 30)
        text_box(draw, f"{index}/{total}", (900, 100, 100, 50), 30, "#dbe6f5", font_path=regular)
        draw.rectangle((90, 470, 250, 480), fill=accent)
        text_box(draw, title, (90, 505, 900, 330), 92, "#ffffff", minimum_size=52, font_path=bold, line_gap=14)
        text_box(draw, body, (90, 850, 900, 120), 38, "#dbe6f5", minimum_size=26, font_path=regular)
        text_box(draw, "밀어서 보기 →", (790, 1000, 220, 50), 28, accent, font_path=bold)
        record = {"template": template, "background": used_background, "cta": None}
    elif template == "cta":
        top, bottom, accent = CTA_PALETTE
        image = _gradient(top, bottom)
        draw = ImageDraw.Draw(image)
        _pill(draw, (90, 90), brand_label, accent, "#ffffff", 30)
        text_box(draw, f"{index}/{total}", (900, 100, 100, 50), 30, "#6b5f4e", font_path=regular)
        draw.rectangle((90, 270, 250, 280), fill=accent)
        text_box(draw, title, (90, 310, 900, 240), 84, "#1f1a14", minimum_size=48, font_path=bold, line_gap=12)
        text_box(draw, body, (90, 580, 900, 220), 44, "#3d3528", minimum_size=30, font_path=regular)
        if cta:
            _pill(draw, (90, 830), str(cta), accent, "#ffffff", 36)
        text_box(draw, "출처와 한계는 본문 글에서 확인하세요", (90, 1000, 900, 50), 24, "#8a7d69", font_path=regular)
        record = {"template": template, "background": "solid", "cta": str(cta) if cta else None}
    else:
        # 진행 위치는 아래 점과 큰 번호 워터마크가 보여 주므로 'n/N' 글자는 넣지 않는다(워터마크와 겹침).
        image = _watermark_number(_gradient(top, bottom), index, accent)
        draw = ImageDraw.Draw(image)
        _pill(draw, (90, 90), brand_label, accent, "#0b1327", 30)
        draw.rectangle((90, 258, 250, 268), fill=accent)
        text_box(draw, title, TITLE_BOX, TITLE_SIZE, "#ffffff", minimum_size=TITLE_MIN, font_path=bold, line_gap=12)
        draw.line((90, 630, 990, 630), fill="#ffffff", width=1)
        text_box(draw, body, BODY_BOX, BODY_SIZE, "#e6eefb", minimum_size=BODY_MIN, font_path=regular, line_gap=16)
        _dots(draw, index, total, accent)
        record = {"template": template, "background": used_background, "cta": None}
    image.save(path, "PNG")
    return record


def _cover_background(store, job, folder, background_renderer, notes):
    """운영자가 생성 배경을 켰을 때 표지 한 장용 배경. 실패하면 그라데이션으로 가고 사유만 남긴다."""
    renderer = background_renderer
    if renderer is None:
        from .image_selection import background_renderer_for_job
        try:
            renderer = background_renderer_for_job(store, {**job, "selections": {**(job.get("selections") or {}), "cards": True}})
        except WorkflowError as error:
            notes.append(f"배경 이미지 없이 만들었어요: {error}")
            return None, None
    if renderer is None:
        return None, None
    path = folder / "cover-background.png"
    try:
        meta = renderer(0, path) or {}
    except WorkflowError as error:
        notes.append(f"배경 이미지 없이 만들었어요: {error}")
        return None, None
    if not path.is_file():
        notes.append("배경 이미지 없이 만들었어요: 렌더러가 파일을 만들지 않았어요")
        return None, None
    return path, meta


def plan_cards(store: Store, job_id, provider=None, background_renderer=None):
    job = store.require_source_approval(job_id)
    packet = job["source_packet"] or {}
    brand = load_brand()
    brief = brief_for_job(job)
    provider = provider or Provider(store)
    system = brand_system_prompt(BASE, brand)
    context = {"packet": packet_context(packet), "audience": brief, "instructions": INSTRUCTIONS}
    options = {"max_tokens": 4096, "temperature": 0.5, "reasoning_effort": "medium"}
    plan = provider.generate("cards", [{"role": "system", "content": system}, {"role": "user", "content": canonical(context)}], CARDS_SCHEMA, options)
    checks = card_checks(plan, brand)
    review = provider.generate("cards_review", [{"role": "system", "content": system}, {"role": "user", "content": canonical({"cards": plan.get("slides"), "audience": brief, "instructions": REVIEW_INSTRUCTIONS})}], REVIEW_SCHEMA, {"max_tokens": 2048, "temperature": 0.2, "reasoning_effort": "medium"})
    issues = [*checks["issues"], *review_issues(review)]
    refined = False
    if issues:
        refine_context = {**context, "previous": plan, "issues": issues, "instructions": INSTRUCTIONS + " 아래 issues를 모두 해결한 전체 카드 목록을 다시 작성한다. 지적된 카드만이 아니라 전체 흐름이 자연스럽게 이어지도록 고친다."}
        plan = provider.generate("cards", [{"role": "system", "content": system}, {"role": "user", "content": canonical(refine_context)}], CARDS_SCHEMA, {**options, "temperature": 0.3})
        checks = card_checks(plan, brand)
        refined = True
    version = int((job.get("cards") or {}).get("version", 0)) + 1
    root, folder = output_folder(store, job, f"cards-v{version}")
    notes = []
    background, background_meta = _cover_background(store, job, folder, background_renderer, notes)
    raw = [s for s in (plan.get("slides") or []) if isinstance(s, dict)]
    slides = []
    for index, slide in enumerate(raw, 1):
        record = {"index": index, "title": str(slide.get("title", "")), "body": str(slide.get("body", "")), "artifact_id": None, "artifact": None, "template": None, "background": None, "cta": None}
        path = folder / f"card-{index:02}.png"
        try:
            drawn = render_slide(record, index, len(raw), path, BRAND_LABEL, cta=brief.get("cta") if index == len(raw) else None, background=background if index == 1 else None)
            artifact = artifact_record(root, path)
            record.update(artifact_id=artifact["id"], artifact=artifact, **drawn)
        except Exception as error:
            # 한 장의 렌더 실패가 나머지 장을 막지 않는다. 비밀값이 섞일 수 있는 도구 오류 문구는 그대로 노출하지 않는다.
            reason = str(error) if isinstance(error, WorkflowError) else f"{type(error).__name__}: 렌더 도구 오류"
            checks = {"passed": False, "issues": [*checks["issues"], f"{index}번 카드: 이미지 렌더 실패. {reason}"]}
        slides.append(record)
    rendered = sum(1 for s in slides if s["artifact_id"])
    record = {"version": version, "generated_at": now(), "source_hash": job["source_hash"], "slides": slides, "checks": checks, "refined": refined,
              "review": review, "notes": notes, "size": list(SIZE),
              "visual_source": "generated_cover_background_plus_first_party_text" if background else "first_party_gradient_and_text",
              "background_meta": background_meta}
    save_job_output(store, job_id, job["source_hash"], "cards", record, "cards_rendered", {"role": "자료 제작", "version": version, "source_hash": job["source_hash"], "slides": len(slides), "rendered": rendered, "passed": checks["passed"], "issues": len(checks["issues"]), "next_action": "카드 이미지와 검사 결과를 확인합니다"})
    return record
