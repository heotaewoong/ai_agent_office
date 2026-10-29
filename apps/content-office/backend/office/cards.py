"""승인① 원고 → 카드뉴스 6~8장(1080x1080 PNG). 넘침·오탈자·금지 주장·중복을 결정적으로 검사한다.

이미지는 1차 도형·글자만 쓰고 외부 이미지는 가져오지 않는다. 승인①②를 만들거나 바꾸지 않는다.
"""
from __future__ import annotations

from PIL import Image, ImageDraw

from .brand import brand_system_prompt, load_brand
from .briefs import brief_for_job
from .editorial import BASE
from .media import artifact_record, text_box
from .providers import Provider
from .quiz import output_folder, packet_context, save_job_output, text_issues
from .store import Store, WorkflowError, canonical, now

SLIDE_SCHEMA = {"type": "object", "properties": {"title": {"type": "string"}, "body": {"type": "string"}}, "required": ["title", "body"], "additionalProperties": False}
CARDS_SCHEMA = {"type": "object", "properties": {"slides": {"type": "array", "minItems": 6, "maxItems": 8, "items": SLIDE_SCHEMA}}, "required": ["slides"], "additionalProperties": False}
MIN_SLIDES, MAX_SLIDES = 6, 8
TITLE_LIMIT, BODY_LIMIT = 20, 70
SIZE = (1080, 1080)
# 제목·본문 상자 (x, y, 폭, 높이)와 글자 크기 범위. 최소 크기까지 내려가야 들어가면 '넘침'으로 본다.
TITLE_BOX, TITLE_SIZE, TITLE_MIN = (90, 250, 900, 300), 76, 44
BODY_BOX, BODY_SIZE, BODY_MIN = (90, 600, 900, 360), 46, 30
BRAND_LABEL = "HeoBrain"
ACCENTS = ["#6de8d5", "#9aa7ff", "#ffc684", "#94d9ff"]

INSTRUCTIONS = f"승인된 원고로 인스타그램형 카드뉴스 {MIN_SLIDES}~{MAX_SLIDES}장을 쓴다. 각 장은 title {TITLE_LIMIT}자 이하, body {BODY_LIMIT}자 이하의 해요체 한국어다. 1장은 독자가 겪는 문제를 짚는 후크, 마지막 장은 '오늘 할 일' 하나와 audience.cta 문구다. 중간 장은 원고의 핵심 답·사례·판단 기준을 한 장에 하나씩 담고 제목을 서로 다르게 쓴다. 원고에 없는 수치·사실을 넣지 않고 줄표(—)·과장·훈계 표현을 쓰지 않으며 표기 고정 목록을 따른다."


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
    for name, text, box, size, minimum in (("제목", slide.get("title", ""), TITLE_BOX, TITLE_SIZE, TITLE_MIN), ("본문", slide.get("body", ""), BODY_BOX, BODY_SIZE, BODY_MIN)):
        try:
            metrics = text_box(draw, text, box, size, minimum_size=minimum)
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


def render_slide(slide, index, total, path, brand_label=BRAND_LABEL):
    """단색 배경 + 제목 + 본문 + 쪽수. media.draw_scene과 같은 색·폰트 규칙."""
    image = Image.new("RGB", SIZE, "#0b1327")
    draw = ImageDraw.Draw(image)
    accent = ACCENTS[(index - 1) % len(ACCENTS)]
    for n in range(4):
        draw.arc((760 - n * 35, -170 + n * 50, 1320 + n * 35, 390 + n * 50), 70, 310, fill="#1b2c48", width=3)
    text_box(draw, brand_label, (90, 90, 700, 60), 34, accent)
    text_box(draw, f"{index}/{total}", (820, 90, 170, 60), 34, "#b8c9e4")
    draw.rectangle((90, 215, 230, 223), fill=accent)
    text_box(draw, slide.get("title", ""), TITLE_BOX, TITLE_SIZE, minimum_size=TITLE_MIN)
    draw.rounded_rectangle((60, 570, 1020, 990), 32, fill="#192c45")
    text_box(draw, slide.get("body", ""), BODY_BOX, BODY_SIZE, "#eaf2ff", minimum_size=BODY_MIN)
    text_box(draw, "출처와 한계는 본문 글에서 확인하세요", (90, 1010, 900, 50), 26, "#b8c9e4")
    image.save(path, "PNG")
    return path


def plan_cards(store: Store, job_id, provider=None):
    job = store.require_source_approval(job_id)
    packet = job["source_packet"] or {}
    brand = load_brand()
    brief = brief_for_job(job)
    provider = provider or Provider(store)
    system = brand_system_prompt(BASE, brand)
    context = {"packet": packet_context(packet), "audience": brief, "instructions": INSTRUCTIONS}
    plan = provider.generate("cards", [{"role": "system", "content": system}, {"role": "user", "content": canonical(context)}], CARDS_SCHEMA, {"max_tokens": 4096, "temperature": 0.5})
    checks = card_checks(plan, brand)
    refined = False
    if not checks["passed"]:
        refine_context = {**context, "previous": plan, "issues": checks["issues"], "instructions": INSTRUCTIONS + " 아래 issues를 모두 해결한 전체 카드 목록을 다시 작성한다."}
        plan = provider.generate("cards", [{"role": "system", "content": system}, {"role": "user", "content": canonical(refine_context)}], CARDS_SCHEMA, {"max_tokens": 4096, "temperature": 0.3})
        checks = card_checks(plan, brand)
        refined = True
    version = int((job.get("cards") or {}).get("version", 0)) + 1
    root, folder = output_folder(store, job, f"cards-v{version}")
    raw = [s for s in (plan.get("slides") or []) if isinstance(s, dict)]
    slides = []
    for index, slide in enumerate(raw, 1):
        record = {"index": index, "title": str(slide.get("title", "")), "body": str(slide.get("body", "")), "artifact_id": None, "artifact": None}
        path = folder / f"card-{index:02}.png"
        try:
            render_slide(record, index, len(raw), path, BRAND_LABEL)
            artifact = artifact_record(root, path)
            record.update(artifact_id=artifact["id"], artifact=artifact)
        except Exception as error:
            # 한 장의 렌더 실패가 나머지 장을 막지 않는다. 비밀값이 섞일 수 있는 도구 오류 문구는 그대로 노출하지 않는다.
            reason = str(error) if isinstance(error, WorkflowError) else f"{type(error).__name__}: 렌더 도구 오류"
            checks = {"passed": False, "issues": [*checks["issues"], f"{index}번 카드: 이미지 렌더 실패. {reason}"]}
        slides.append(record)
    rendered = sum(1 for s in slides if s["artifact_id"])
    record = {"version": version, "generated_at": now(), "source_hash": job["source_hash"], "slides": slides, "checks": checks, "refined": refined, "size": list(SIZE), "visual_source": "first_party_programmatic_shapes_and_text"}
    save_job_output(store, job_id, job["source_hash"], "cards", record, "cards_rendered", {"role": "자료 제작", "version": version, "source_hash": job["source_hash"], "slides": len(slides), "rendered": rendered, "passed": checks["passed"], "issues": len(checks["issues"]), "next_action": "카드 이미지와 검사 결과를 확인합니다"})
    return record
