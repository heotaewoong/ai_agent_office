"""승인① 원고 → 카드뉴스 6~8장(1080x1440 PNG). 문구는 모델이 쓰고 모델이 다시 읽어 검토하며, 넘침·오탈자·금지 주장·중복은 코드가 검사한다.

이미지: 카드마다 그 카드 내용을 보여 주는 주제 이미지를 화면 전체 배경으로 깔고(OpenAI, 운영자가 켠 경우),
아래쪽에 짙은 그라데이션을 얹어 큰 글자(외곽선 포함)가 어떤 배경에서도 읽히게 한다. 이미지가 없으면 같은 배치의
그라데이션 배경을 쓴다. 마지막 장은 밝은 마무리(오늘 할 일 + CTA) 템플릿. 승인①②를 만들거나 바꾸지 않는다.
"""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from .brand import brand_system_prompt, load_brand
from .briefs import brief_for_job
from .editorial import BASE
from .exports import korean_font
from .media import artifact_record, text_box
from .providers import Provider
from .quiz import output_folder, packet_context, save_job_output, text_issues
from .store import Store, WorkflowError, canonical, now

SLIDE_SCHEMA = {"type": "object", "properties": {"title": {"type": "string"}, "body": {"type": "string"}, "visual": {"type": "string"}},
                "required": ["title", "body", "visual"], "additionalProperties": False}
CARDS_SCHEMA = {"type": "object", "properties": {"slides": {"type": "array", "minItems": 6, "maxItems": 8, "items": SLIDE_SCHEMA}}, "required": ["slides"], "additionalProperties": False}
REVIEW_SCHEMA = {"type": "object", "properties": {"cards": {"type": "array", "items": {"type": "object", "properties": {
    "index": {"type": "integer"}, "ok": {"type": "boolean"}, "problems": {"type": "array", "items": {"type": "string"}}},
    "required": ["index", "ok", "problems"], "additionalProperties": False}}}, "required": ["cards"], "additionalProperties": False}
MIN_SLIDES, MAX_SLIDES = 6, 8
TITLE_LIMIT, BODY_LIMIT = 18, 60
SIZE = (1080, 1080)
# 사진형(표지·본문) 템플릿의 글자 상자 (x, y, 폭, 높이)와 글자 크기 범위. 최소 크기에서도 안 들어가면 '넘침'.
TITLE_BOX, TITLE_SIZE, TITLE_MIN = (72, 560, 936, 250), 100, 72
BODY_BOX, BODY_SIZE, BODY_MIN = (72, 830, 936, 190), 52, 42
BRAND_LABEL = "HeoBrain"
# (위 색, 아래 색, 강조색) — 이미지가 없을 때의 배경과 강조색.
PALETTES = [("#16325c", "#0b1327", "#6de8d5"), ("#3b2a7a", "#140c2e", "#c3b5ff"), ("#135b5c", "#071d20", "#ffc684"),
            ("#6a2f5a", "#1c0b1a", "#ffb3c7"), ("#1f4e79", "#0a1828", "#94d9ff"), ("#4a4a4a", "#141414", "#f3d35b")]
CTA_PALETTE = ("#f6f1e7", "#efe4cf", "#d64541")
STROKE = (8, 12, 24)

INSTRUCTIONS = f"""승인된 원고로 인스타그램 카드뉴스 {MIN_SLIDES}~{MAX_SLIDES}장을 쓴다. 독자 한 명에게 말하듯 해요체로 쓴다.

가장 중요한 규칙: 각 카드는 그 카드만 읽어도 뜻이 통해야 한다. 앞 카드를 봐야 아는 대명사·생략(이것, 그 기능, 비용)을 쓰지 않고
'무엇이 무엇을' 주어와 대상을 매번 적는다. 숫자는 무엇의 값인지 함께 쓴다. 전문용어·영어 약어는 쉬운 말로 바꾸거나 짧게 풀어 쓴다.
전보문처럼 조사를 빼거나 명사만 나열하지 않는다. 카드는 휴대폰에서 큰 글씨로 보이므로 짧고 쉽게 쓴다.

카드 구성
- 1장: 독자가 지금 겪는 상황을 짚는 후크. 제목은 독자의 말이나 질문처럼.
- 2장: 그 문제가 왜 생기는지, 또는 이 소식이 왜 독자에게 중요한지.
- 3장: 핵심 개념이나 발표 내용을 쉬운 말 한 문장으로.
- 4~{MAX_SLIDES - 1}장: 어떻게 쓰는지·판단 기준·구체 예시를 한 장에 하나씩. 앞 장과 자연스럽게 이어지되 혼자서도 읽히게.
- 마지막 장: '오늘 할 일' 하나(독자가 10분 안에 할 수 있는 행동). CTA 문구는 이미지에 따로 들어가므로 body에 쓰지 않는다.

형식: title은 {TITLE_LIMIT}자 이하(마침표 없음), body는 {BODY_LIMIT}자 이하 1~2문장이며 각 문장은 끝까지 완결한다. 제목은 서로 다르게.
visual: 그 카드 내용을 그대로 보여 주는 배경 이미지 장면을 한국어 한 문장으로 구체적으로 쓴다(사물·도구·행동·장소). 화면·종이에 숫자나 글자가 보이는 장면은 쓰지 않는다. 예) "책상 위 노트북 화면에서
서류 더미가 자동으로 분류되어 세 갈래 상자로 들어가는 장면". 글자·숫자·로고·실존 인물 얼굴은 넣지 않는다.
원고에 없는 수치·사실을 넣지 않고 줄표(—)·과장·훈계 표현을 쓰지 않으며 표기 고정 목록을 따른다."""

REVIEW_INSTRUCTIONS = """너는 한국어 카드뉴스 편집자다. 각 카드를 '그 카드만 보는 독자'의 눈으로 읽고 판단한다.
ok=false로 표시할 기준: (1) 이 카드만 읽으면 무슨 말인지 모른다(주어·대상이 빠졌거나 앞 카드를 전제한다), (2) 숫자나 용어가 무엇에 대한 것인지 없다,
(3) 전보문·명사 나열·조사 생략·번역투로 어색하다, (4) 두 문장이 서로 안 이어진다, (5) 앞뒤 카드와 순서가 맞지 않아 흐름이 끊긴다,
(6) visual이 카드 내용과 관계없거나 글자를 넣으라고 한다.
problems에는 무엇이 왜 문제인지와 어떻게 고치면 되는지를 한 줄씩 한국어로 적는다. 사실 여부는 판단하지 않는다."""


def glossary_issues(text, brand):
    """glossary.json terms의 비표준 표기(키)가 보이면 고정 표기(값)로 바꾸라고 알린다."""
    hits = [written for written in brand.get("terms", {}) if written and written in (text or "")]
    hits = [written for written in hits if not any(other != written and written in other for other in hits)]
    return [f"표기 통일: '{written}' 대신 '{brand['terms'][written]}'로 적어요" for written in hits]


def measure_overflow(slide):
    """실제 굵은 폰트로 1080x1080 캔버스에 그려 보고 최소 글자 크기에서도 칸에 안 들어가면 넘침."""
    image = Image.new("RGB", SIZE, "#0b1327")
    draw = ImageDraw.Draw(image)
    overflow = []
    for name, text, box, size, minimum in (("제목", slide.get("title", ""), TITLE_BOX, TITLE_SIZE, TITLE_MIN),
                                           ("본문", slide.get("body", ""), BODY_BOX, BODY_SIZE, BODY_MIN)):
        try:
            text_box(draw, text, box, size, minimum_size=minimum, font_path=korean_font("bold"), line_gap=max(10, size // 6))
        except WorkflowError:
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
            issues.append(f"{number}번 카드: {name} 넘침. 큰 글씨로 그리면 칸에 들어가지 않아요. 더 짧게 써요")
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


def _fill(source):
    """생성 이미지를 1080x1080에 꽉 차게 자른다(어둡게 섞지 않는다. 가독성은 아래 막이 맡는다)."""
    with Image.open(source) as opened:
        picture = opened.convert("RGB")
    scale = max(SIZE[0] / picture.width, SIZE[1] / picture.height)
    resized = picture.resize((max(SIZE[0], round(picture.width * scale)), max(SIZE[1], round(picture.height * scale))), Image.LANCZOS)
    left, top = (resized.width - SIZE[0]) // 2, (resized.height - SIZE[1]) // 2
    return resized.crop((left, top, left + SIZE[0], top + SIZE[1]))


def _legibility(image):
    """위쪽은 살짝, 글자가 놓이는 아래 절반은 짙게 어둡게 해서 흰 글자가 어떤 이미지에서도 읽히게 한다."""
    overlay = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(SIZE[1]):
        if y < 220:
            alpha = round(110 * (1 - y / 220))
        elif y < 420:
            alpha = 0
        else:
            alpha = round(235 * min(1.0, (y - 420) / 260))
        draw.line((0, y, SIZE[0], y), fill=(*STROKE, alpha))
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def _pill(draw, xy, text, fill, color, size=32):
    x, y = xy
    face = ImageFont.truetype(str(korean_font("bold")), size)
    width = draw.textlength(text, font=face)
    draw.rounded_rectangle((x, y, x + width + 56, y + size + 28), radius=(size + 28) // 2, fill=fill)
    draw.text((x + 28, y + 12), text, font=face, fill=color)
    return x + width + 56


def _outlined(draw, text, box, size, minimum, fill, stroke_width):
    """외곽선이 있는 굵은 글자. text_box로 크기·줄바꿈을 정한 뒤 같은 자리에 외곽선을 얹어 그린다."""
    gap = max(10, size // 6)
    box = (box[0], box[1], box[2], box[3] + gap)
    metrics = text_box(ImageDraw.Draw(Image.new("RGB", SIZE)), text, box, size, minimum_size=minimum, font_path=korean_font("bold"), line_gap=gap)
    face = ImageFont.truetype(str(korean_font("bold")), metrics["font_size"])
    line_height = metrics["font_size"] + gap
    for n, line in enumerate(metrics["displayed_text"].split("\n")):
        draw.text((box[0], box[1] + n * line_height), line, font=face, fill=fill, stroke_width=stroke_width, stroke_fill=STROKE)
    return metrics


def _fit(text, box, size, minimum):
    """넘침 검사와 같은 규칙으로 글자 크기·줄 수를 정하고 실제 높이를 돌려준다."""
    gap = max(10, size // 6)
    metrics = text_box(ImageDraw.Draw(Image.new("RGB", SIZE)), text, box, size, minimum_size=minimum, font_path=korean_font("bold"), line_gap=gap)
    line_height = metrics["font_size"] + max(10, metrics["font_size"] // 6)
    return {**metrics, "height": metrics["lines"] * line_height - max(10, metrics["font_size"] // 6)}


def _dots(draw, index, total, accent, y=110):
    gap, radius = 24, 7
    start = SIZE[0] - 90 - (total - 1) * gap
    for n in range(1, total + 1):
        cx = start + (n - 1) * gap
        draw.ellipse((cx - radius, y - radius, cx + radius, y + radius), fill=accent if n == index else "#cfd8e6", outline=STROKE, width=2)


def _save_instagram_portrait(image, path):
    # 기존 검수된 글자 배치를 보존하고 3:4 격자용 여백만 더한다.
    portrait = Image.new("RGB", (1080, 1440), image.getpixel((0, 1079)))
    portrait.paste(image, (0, 180))
    portrait.save(path, "PNG")


def render_slide(slide, index, total, path, brand_label=BRAND_LABEL, *, cta=None, background=None, promotion=None):
    """표지(1장)·본문(사진형)·마무리(마지막 장) 템플릿. 반환값은 어떤 템플릿과 배경을 썼는지."""
    title, body = str(slide.get("title", "")), str(slide.get("body", ""))
    template = "cover" if index == 1 else "cta" if index == total else "body"
    top, bottom, accent = PALETTES[(index - 1) % len(PALETTES)]
    bold = korean_font("bold")
    if template == "cta":
        top, bottom, accent = CTA_PALETTE
        image = _gradient(top, bottom)
        draw = ImageDraw.Draw(image)
        _pill(draw, (72, 80), brand_label, accent, "#ffffff")
        draw.rectangle((72, 250, 232, 262), fill=accent)
        text_box(draw, title, (72, 300, 936, 250), 104, "#1f1a14", minimum_size=72, font_path=bold, line_gap=16)
        text_box(draw, body, (72, 570, 936, 240), 54, "#3d3528", minimum_size=42, font_path=bold, line_gap=14)
        if promotion:
            text_box(draw, promotion, (72, 840, 936, 145), 40, "#b83230", minimum_size=26, font_path=bold)
        elif cta:
            _pill(draw, (72, 850), str(cta), accent, "#ffffff", 44)
        text_box(draw, "자료 안내는 게시물 본문에서 확인하세요", (72, 1000, 936, 50), 26, "#8a7d69", font_path=korean_font())
        _save_instagram_portrait(image, path)
        return {"template": template, "background": "solid", "cta": promotion or (str(cta) if cta else None)}
    if background is not None:
        image, used = _legibility(_fill(background)), "generated"
    else:
        image, used = _legibility(_gradient(top, bottom)), "gradient"
    draw = ImageDraw.Draw(image)
    _pill(draw, (72, 80), brand_label, accent, "#0b1327")
    _dots(draw, index, total, accent)
    # 제목+본문 묶음을 아래쪽에 붙인다(제목이 한 줄이어도 사이가 비지 않게). 크기는 넘침 검사와 같은 상자로 정한다.
    title_m = _fit(title, TITLE_BOX, TITLE_SIZE, TITLE_MIN)
    body_m = _fit(body, BODY_BOX, BODY_SIZE, BODY_MIN)
    bottom = 1000 if template == "cover" else 1020
    body_top = bottom - body_m["height"]
    title_top = body_top - 46 - title_m["height"]
    draw.rectangle((72, title_top - 34, 232, title_top - 22), fill=accent)
    _outlined(draw, title, (TITLE_BOX[0], title_top, TITLE_BOX[2], title_m["height"] + 4), title_m["font_size"], title_m["font_size"], "#ffffff", 5)
    _outlined(draw, body, (BODY_BOX[0], body_top, BODY_BOX[2], body_m["height"] + 4), body_m["font_size"], body_m["font_size"], "#f1f5ff", 4)
    if template == "cover":
        text_box(draw, "넘겨서 보기 →", (800, 1018, 220, 44), 30, accent, font_path=bold)
    _save_instagram_portrait(image, path)
    return {"template": template, "background": used, "cta": None}


def _card_renderer(store, job_id, images, background_renderer, notes):
    """카드 이미지를 만들 함수. 운영자가 고르지 않았으면 None(그라데이션)."""
    if background_renderer is not None:
        return background_renderer
    if images is not False:
        from .image_selection import profile_summary
        profile_id = profile_summary(store)["id"]
        if profile_id == "codex-subscription":
            from .codex_image_provider import make_codex_card_image_renderer
            try:
                return make_codex_card_image_renderer(store, job_id=job_id)
            except WorkflowError as error:
                notes.append(f"주제 이미지 없이 만들었어요: {error}")
                return None
    if images is None:
        # 키가 있어도 이미지 생성을 선택한 것은 아니다. 기본 요청은 제작 프로필을 따른다.
        images = profile_id == "openai-gpt-image"
    if not images:
        return None
    from .image_provider import make_openai_card_image_renderer
    try:
        return make_openai_card_image_renderer(store, job_id=job_id, allow_paid=True)
    except WorkflowError as error:
        notes.append(f"주제 이미지 없이 만들었어요: {error}")
        return None


def plan_cards(store: Store, job_id, provider=None, background_renderer=None, images=None, *, require_passed=False):
    """images: True면 카드마다 주제 이미지를 생성(유료), False면 그라데이션, None이면 제작 설정의 배경 이미지 프로필을 따른다."""
    job = store.require_source_approval(job_id)
    packet = job["source_packet"] or {}
    from .offers import offer_card_cta, offer_snapshot, require_offer_ready
    require_offer_ready(job.get("offer"))
    brand = load_brand()
    brief = brief_for_job(job)
    provider = provider or Provider(store, job_id=job_id)
    system = brand_system_prompt(BASE, brand)
    context = {"packet": packet_context(packet), "audience": brief, "campaign_offer": offer_snapshot(job.get("offer")), "instructions": INSTRUCTIONS}
    if brief.get('axis') == 'A':
        context['instructions'] += ' 학습 카드에는 원고 근거로 구별 기준·구체 예시·틀리지 않은 연상 고리·먼저 풀어 볼 질문을 배치하고 다음 장에서 정답과 이유를 설명한다. 질문 장에 정답을 먼저 노출하지 않는다. 장 수와 글자 한도는 유지한다.'
        quiz = job.get('quiz') or {}
        if quiz.get('source_hash') == job.get('source_hash') and quiz.get('checks', {}).get('passed') is True:
            context['verified_format_quiz_data'] = quiz.get('questions', [])
            context['instructions'] += ' 제공한 퀴즈는 형식 검사를 통과한 참고 데이터이며 독립 사실 검증 증명은 아니다. 해당 원고의 근거로 질문과 정답의 의미를 보존한다.'
    options = {"max_tokens": 12000, "temperature": 0.5, "reasoning_effort": "low"}
    plan = provider.generate("cards", [{"role": "system", "content": system}, {"role": "user", "content": canonical(context)}], CARDS_SCHEMA, options)
    checks = card_checks(plan, brand)
    review = provider.generate("cards_review", [{"role": "system", "content": system}, {"role": "user", "content": canonical({"cards": plan.get("slides"), "audience": brief, "instructions": REVIEW_INSTRUCTIONS})}], REVIEW_SCHEMA, {"max_tokens": 6000, "temperature": 0.2, "reasoning_effort": "low"})
    issues = [*checks["issues"], *review_issues(review)]
    refined = False
    notes = []
    if issues:
        refine_context = {**context, "previous": plan, "issues": issues, "instructions": INSTRUCTIONS + " 아래 issues를 모두 해결한 전체 카드 목록을 다시 작성한다. 지적된 카드만이 아니라 전체 흐름이 자연스럽게 이어지도록 고친다."}
        try:
            revised = provider.generate("cards", [{"role": "system", "content": system}, {"role": "user", "content": canonical(refine_context)}], CARDS_SCHEMA, {**options, "temperature": 0.3})
            plan, checks, refined = revised, card_checks(revised, brand), True
        except WorkflowError as error:
            # 수정 단계가 실패해도 이미 비용을 낸 첫 결과로 카드를 만든다. 검토 지적은 이슈로 남긴다.
            notes.append(f"수정 단계 실패로 첫 결과를 썼어요: {error}")
            checks = {"passed": False, "issues": issues}
    version = int((job.get("cards") or {}).get("version", 0)) + 1
    root, folder = output_folder(store, job, f"cards-v{version}")
    # Production never buys six background images for a text plan that still fails checks.
    renderer = None if require_passed and not checks['passed'] else _card_renderer(store, job_id, images, background_renderer, notes)
    raw = [s for s in (plan.get("slides") or []) if isinstance(s, dict)]
    slides, image_meta = [], []
    for index, slide in enumerate(raw, 1):
        record = {"index": index, "title": str(slide.get("title", "")), "body": str(slide.get("body", "")), "visual": str(slide.get("visual", "")),
                  "artifact_id": None, "artifact": None, "template": None, "background": None, "cta": None}
        path = folder / f"card-{index:02}.png"
        background = None
        if renderer is not None and index < len(raw):
            picture = folder / f"image-{index:02}.png"
            try:
                meta = renderer(index - 1, record, picture) or {}
                if picture.is_file():
                    background = picture
                    image_meta.append({"index": index, **meta})
            except WorkflowError as error:
                # 한 장이라도 실패하면(키 없음·한도·결과 불명) 남은 장은 이미지 없이 만든다. 같은 실패를 비용 들여 반복하지 않는다.
                notes.append(f"{index}번부터 주제 이미지 없이 만들었어요: {error}")
                renderer = None
        try:
            drawn = render_slide(record, index, len(raw), path, BRAND_LABEL, cta=brief.get("cta") if index == len(raw) else None, background=background,
                                 promotion=offer_card_cta(job.get("offer")) if index == len(raw) else None)
            artifact = artifact_record(root, path)
            record.update(artifact_id=artifact["id"], artifact=artifact, **drawn)
        except Exception as error:
            # 한 장의 렌더 실패가 나머지 장을 막지 않는다. 비밀값이 섞일 수 있는 도구 오류 문구는 그대로 노출하지 않는다.
            reason = str(error) if isinstance(error, WorkflowError) else f"{type(error).__name__}: 렌더 도구 오류"
            checks = {"passed": False, "issues": [*checks["issues"], f"{index}번 카드: 이미지 렌더 실패. {reason}"]}
        slides.append(record)
    rendered = sum(1 for s in slides if s["artifact_id"])
    generated = sum(1 for s in slides if s.get("background") == "generated")
    record = {"version": version, "generated_at": now(), "source_hash": job["source_hash"], "slides": slides, "checks": checks, "refined": refined,
              "review": review, "notes": notes, "size": list(SIZE), "images": image_meta,
              "visual_source": "generated_topic_images_plus_first_party_text" if generated else "first_party_gradient_and_text"}
    save_job_output(store, job_id, job["source_hash"], "cards", record, "cards_rendered", {"role": "자료 제작", "version": version, "source_hash": job["source_hash"], "slides": len(slides), "rendered": rendered, "generated_images": generated, "passed": checks["passed"], "issues": len(checks["issues"]), "next_action": "카드 이미지와 검사 결과를 확인합니다"})
    return record
