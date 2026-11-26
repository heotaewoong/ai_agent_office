"""승인① 원고 → 그림 기억 이야기(뇌리가 주인공인 4~6장 + 표지·떠올려 보기·정답, 1080x1440 PNG).

글은 모델이 쓰고, 그림은 코드가 그린다(story_scenes, 0원). 기억할 것 하나를 장면 하나에 묶는 이중 부호화,
마지막의 떠올려 보기(인출 연습)가 뇌과학 학습 브랜드에 맞는 모양이다. 승인①②를 만들거나 바꾸지 않는다.

방식 출처: github.com/wonseokjung/connect-ai-writer 커밋 9057798 lib/story.mjs(MIT + Commons Clause). 가져온 생각은
'한 장에 행동 하나', '글이 말한 물건은 그 장 그림에 있어야 한다(그림 계약)', '교훈으로 끝내지 않는다',
'주인공이 처음과 끝에 같다', '나이별 글자 수 상한'이다. 동화 대신 학습 기억용으로 바꿨고 코드는 새로 썼다.
"""
from __future__ import annotations

import re

from PIL import Image, ImageDraw, ImageFont

from .brand import brand_system_prompt, load_brand
from .briefs import brief_for_job
from .editorial import BASE
from .exports import korean_font
from .mascot import MOODS, draw_noeri
from .media import artifact_record, text_box, write_json
from .providers import Provider
from .quiz import output_folder, packet_context, save_job_output, text_issues
from .story_scenes import BACKDROPS, NEEDS, PLACES, PROPS, render_scene, scene_words
from .store import Store, canonical, now
from .writer_checks import numbers_in

MIN_PAGES, MAX_PAGES = 4, 6
PAGE_LETTERS, SENTENCE_LETTERS = 80, 40  # 공백 뺀 한글 글자 수. 인스타 한 장에서 한 번에 읽히는 양
PAGE_W, PAGE_H, SCENE_H = 1080, 1440, 900
PAPER, TEXT_INK, GREEN = "#fbf6ec", "#3b2f24", "#2f5e4a"
PREACH = re.compile(r"교훈|명심|해야\s?해요|해야\s?합니다|해야\s?한답니다|잊지\s?마세요|알게\s?되었답니다")
EMOJI = re.compile(r"[\U0001F300-\U0001FAFF☀-➿]")

SCENE_SCHEMA = {
    "type": "object",
    "properties": {
        "backdrop": {"type": "string", "enum": list(BACKDROPS)},
        "props": {"type": "array", "maxItems": 4, "items": {
            "type": "object", "properties": {"name": {"type": "string", "enum": list(PROPS)}, "place": {"type": "string", "enum": list(PLACES)}},
            "required": ["name", "place"], "additionalProperties": False}},
        "hero": {"type": "object", "properties": {"mood": {"type": "string", "enum": list(MOODS)}, "place": {"type": "string", "enum": list(PLACES)}},
                 "required": ["mood", "place"], "additionalProperties": False},
    },
    "required": ["backdrop", "props", "hero"],
    "additionalProperties": False,
}
STORY_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "pages": {"type": "array", "minItems": MIN_PAGES, "maxItems": MAX_PAGES, "items": {
            "type": "object",
            "properties": {"anchor": {"type": "string"}, "text": {"type": "string"}, "scene": SCENE_SCHEMA,
                           "evidence": {"type": "array", "items": {"type": "string"}}},
            "required": ["anchor", "text", "scene", "evidence"], "additionalProperties": False}},
        "recall": {"type": "array", "minItems": 2, "maxItems": 3, "items": {
            "type": "object", "properties": {"question": {"type": "string"}, "answer": {"type": "string"}},
            "required": ["question", "answer"], "additionalProperties": False}},
    },
    "required": ["title", "pages", "recall"],
    "additionalProperties": False,
}

INSTRUCTIONS = (
    "승인된 원고만 근거로 HeoBrain의 '그림 기억 이야기'를 만든다. 주인공은 HeoBrain 캐릭터 '뇌리'(초록색 뇌 모양) 하나뿐이고 사람은 나오지 않는다. "
    f"원고에서 독자가 기억할 핵심 {MIN_PAGES}~{MAX_PAGES}개를 골라 한 장에 하나씩(anchor, 짧은 낱말이나 구) 담는다. "
    "각 장은 뇌리가 하는 행동 하나와 장면 하나로 그 핵심을 보여 준다. 설명보다 장면이다. "
    f"글(text)은 해요체 1~3문장, 공백 빼고 {PAGE_LETTERS}자 이내, 한 문장 {SENTENCE_LETTERS}자 이내이고 anchor를 글에 그대로 넣는다. "
    "장면(scene)은 정해진 배경(backdrop), 소품(props, 0~4개), 뇌리 표정(hero.mood)과 자리(hero.place)에서만 고른다. "
    "글이 말한 물건(책, 노트, 시계, 러닝머신 같은 것)은 그 장의 소품에 반드시 넣는다. "
    "마지막 장도 교훈을 말하지 않고 뇌리가 새로 익힌 행동을 보여 준다. "
    "recall에는 앞 장을 떠올리게 하는 질문 2~3개를 넣고, 정답(answer)은 해당 장의 anchor를 그대로 쓴다. "
    "원고에 없는 숫자, 사실, 개인 경험을 만들지 않고 이모지, 줄표, 꺾쇠괄호, 과장 표현을 쓰지 않는다. "
    "evidence에는 그 장이 기대는 원고 근거 ID만 넣는다."
)


def _letters(text):
    return len(re.sub(r"\s", "", text or ""))


def _norm(text):
    return re.sub(r"[\s\W_]+", "", (text or "").lower())


def story_texts(story):
    texts = [story.get("title", "")]
    for page in story.get("pages") or []:
        texts.append(page.get("text", ""))
    for item in story.get("recall") or []:
        texts += [item.get("question", ""), item.get("answer", "")]
    return [str(text or "") for text in texts]


def story_checks(story, packet, brand=None):
    """결정적 검사. 통과하지 못해도 결과는 저장하고 화면에서 문제점을 보여 준다(퀴즈와 같은 방식)."""
    brand = brand if brand is not None else load_brand()
    pages = [page for page in story.get("pages") or [] if isinstance(page, dict)]
    issues = []
    if not str(story.get("title", "")).strip():
        issues.append("제목이 비어 있어요")
    if not MIN_PAGES <= len(pages) <= MAX_PAGES:
        issues.append(f"장 수는 {MIN_PAGES}~{MAX_PAGES}장이어야 해요 (현재 {len(pages)}장)")
    known = {item.get("id") for item in packet.get("evidence", []) if isinstance(item, dict) and item.get("id")}
    allowed_numbers = numbers_in(" ".join([packet.get("body", ""), *[str(item.get("claim", "")) for item in packet.get("evidence", []) if isinstance(item, dict)]]))
    anchors = []
    for number, page in enumerate(pages, 1):
        text, anchor = str(page.get("text", "")), str(page.get("anchor", "")).strip()
        scene = page.get("scene") or {}
        if not anchor:
            issues.append(f"{number}장: 기억할 것(anchor)이 비어 있어요")
        elif _norm(anchor) not in _norm(text):
            issues.append(f"{number}장: 기억할 것 '{anchor}'이(가) 글에 그대로 없어요")
        anchors.append(anchor)
        if _letters(text) > PAGE_LETTERS:
            issues.append(f"{number}장: 글이 {_letters(text)}자예요. 공백 빼고 {PAGE_LETTERS}자 안으로 줄이세요")
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
            if _letters(sentence) > SENTENCE_LETTERS:
                issues.append(f"{number}장: 긴 문장({_letters(sentence)}자) '{sentence[:20]}…'을 둘로 나누세요")
        if EMOJI.search(text) or re.search(r"[「」『』<>]", text):
            issues.append(f"{number}장: 이모지나 꺾쇠괄호는 쓰지 않아요")
        if scene.get("backdrop") not in BACKDROPS:
            issues.append(f"{number}장: 모르는 배경 '{scene.get('backdrop')}'")
        unknown = [str(prop.get("name")) for prop in scene.get("props") or [] if isinstance(prop, dict) and prop.get("name") not in PROPS]
        if unknown:
            issues.append(f"{number}장: 그릴 수 없는 소품 {', '.join(unknown)}")
        hero = scene.get("hero") or {}
        if hero.get("mood") not in MOODS or hero.get("place") not in PLACES:
            issues.append(f"{number}장: 뇌리의 표정이나 자리가 정해진 값이 아니에요")
        have = scene_words(scene)
        for pattern, thing in NEEDS:
            if pattern.search(text) and thing not in have:
                issues.append(f"{number}장: 글에 '{PROPS[thing]}'이(가) 나오는데 그림에 없어요. 소품에 넣거나 글을 바꾸세요")
        new_numbers = sorted(numbers_in(text) - allowed_numbers)
        if new_numbers:
            issues.append(f"{number}장: 원고에 없는 숫자 {', '.join(new_numbers)}")
        cited = [str(item) for item in page.get("evidence") or []]
        strange = [item for item in cited if item not in known]
        if strange:
            issues.append(f"{number}장: 원고에 없는 근거 ID {', '.join(strange)}")
    clean = [_norm(anchor) for anchor in anchors if anchor]
    if len(set(clean)) != len(clean):
        issues.append("기억할 것(anchor)이 겹쳐요. 장마다 다른 것 하나씩 담으세요")
    if pages and PREACH.search(str(pages[-1].get("text", ""))):
        issues.append("마지막 장이 교훈을 말해요. 뇌리가 새로 익힌 행동을 보여 주는 장면으로 바꾸세요")
    recall = [item for item in story.get("recall") or [] if isinstance(item, dict)]
    if not 2 <= len(recall) <= 3:
        issues.append(f"떠올려 보기 질문은 2~3개여야 해요 (현재 {len(recall)}개)")
    for number, item in enumerate(recall, 1):
        answer = _norm(str(item.get("answer", "")))
        if not str(item.get("question", "")).strip():
            issues.append(f"떠올려 보기 {number}: 질문이 비어 있어요")
        if not answer or not any(answer == anchor or answer in anchor or anchor in answer for anchor in clean if anchor):
            issues.append(f"떠올려 보기 {number}: 정답이 어느 장의 기억할 것과도 맞지 않아요")
    issues.extend(text_issues(story_texts(story), brand))
    return {"passed": not issues, "issues": list(dict.fromkeys(issues))}


# ---------- 그리기 ----------
def _font(size, bold=False):
    return ImageFont.truetype(str(korean_font("bold" if bold else "regular")), size)


def _footer(draw, label, page_no=None, total=None):
    font = _font(26)
    draw.text((70, PAGE_H - 70), "HeoBrain 그림 기억 이야기", font=font, fill="#a08a6a")
    if page_no and total:
        mark = f"{page_no} / {total}"
        width = draw.textlength(mark, font=font)
        draw.text((PAGE_W - 70 - width, PAGE_H - 70), mark, font=font, fill="#a08a6a")
    if label:  # 넘김 안내는 바닥 줄 위에 따로 둔다
        big = _font(34, bold=True)
        width = draw.textlength(label, font=big)
        draw.rounded_rectangle(((PAGE_W - width) / 2 - 30, PAGE_H - 170, (PAGE_W + width) / 2 + 30, PAGE_H - 110), radius=30, fill="#f2e6cf")
        draw.text(((PAGE_W - width) / 2, PAGE_H - 160), label, font=big, fill="#8a5410")


def _centered(draw, text, top, width, size, minimum, *, bold=False, fill="#2e241b", max_lines=3):
    """가운데 정렬 글. 넘치면 글씨를 줄이고, 그래도 넘치면 말줄임표로 보이고 truncated를 돌려준다."""
    from .media import wrap_text
    for font_size in range(size, minimum - 1, -2):
        font = _font(font_size, bold)
        lines = wrap_text(draw, text, font, width)
        if len(lines) <= max_lines:
            break
    truncated = len(lines) > max_lines
    lines = lines[:max_lines]
    if truncated:
        lines[-1] = lines[-1][:-1] + "…"
    gap = font_size + max(8, font_size // 4)
    for index, line in enumerate(lines):
        draw.text(((PAGE_W - draw.textlength(line, font=font)) / 2, top + index * gap), line, font=font, fill=fill)
    return {"font_size": font_size, "lines": len(lines), "truncated": truncated}


def _chip(draw, text, x, y):
    font = _font(30, bold=True)
    width = draw.textlength(text, font=font)
    draw.rounded_rectangle((x, y, x + width + 48, y + 56), radius=28, fill=GREEN)
    draw.text((x + 24, y + 9), text, font=font, fill="#ffffff")


def render_page(page, index, total):
    image = Image.new("RGB", (PAGE_W, PAGE_H), PAPER)
    image.paste(render_scene(page.get("scene") or {}), (0, 0))
    draw = ImageDraw.Draw(image)
    _chip(draw, "기억할 것  " + str(page.get("anchor", ""))[:18], 70, SCENE_H + 40)
    metrics = text_box(draw, str(page.get("text", "")), (70, SCENE_H + 130, PAGE_W - 140, 300), size=46, minimum_size=30,
                       fill=TEXT_INK, font_path=korean_font(), truncate=True)
    _footer(draw, "", index, total)
    return image, metrics


def render_cover(title, first_scene):
    scene = {**(first_scene or {}), "props": [], "hero": {"mood": "happy", "place": "center"}}
    image = Image.new("RGB", (PAGE_W, PAGE_H), PAPER)
    image.paste(render_scene(scene), (0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((PAGE_W / 2 - 40, SCENE_H + 60, PAGE_W / 2 + 40, SCENE_H + 66), fill="#d6892a")
    metrics = _centered(draw, title, SCENE_H + 110, PAGE_W - 180, 72, 44, bold=True, max_lines=2)
    font = _font(30)
    sub = "그림으로 기억하기 · 뇌리와 함께"
    draw.text(((PAGE_W - draw.textlength(sub, font=font)) / 2, SCENE_H + 360), sub, font=font, fill="#8a5410")
    _footer(draw, "")
    return image, metrics


def _list_page(heading, lines, mood, footnote):
    image = Image.new("RGB", (PAGE_W, PAGE_H), PAPER)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, PAGE_W, 300), fill="#e8f3ec")
    draw_noeri(image, PAGE_W - 330, 40, 1.25, mood)
    draw = ImageDraw.Draw(image)
    draw.text((80, 110), heading, font=_font(76, bold=True), fill="#193f32")
    y = 360
    for number, line in enumerate(lines, 1):
        draw.ellipse((80, y + 4, 136, y + 60), fill=GREEN)
        mark = str(number)
        font = _font(32, bold=True)
        draw.text((108 - draw.textlength(mark, font=font) / 2, y + 12), mark, font=font, fill="#ffffff")
        metrics = text_box(draw, line, (170, y, PAGE_W - 250, 230), size=48, minimum_size=30, fill=TEXT_INK, font_path=korean_font(), truncate=True)
        y += 60 + metrics["lines"] * (metrics["font_size"] + max(8, metrics["font_size"] // 4)) + 40
    _footer(draw, footnote)
    return image


def render_recall(recall):
    return _list_page("떠올려 보기", [str(item.get("question", "")) for item in recall], "thinking", "소리 내서 답해 보고 다음 장으로")


def render_answers(recall):
    lines = [f"{item.get('question', '')}  →  {item.get('answer', '')}" for item in recall]
    return _list_page("정답", lines, "proud", "내일 한 번 더 떠올려 보세요")


def contact_sheet(images):
    cols, tw, th, gap = 4, 270, 360, 16
    rows = (len(images) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (tw + gap) + gap, rows * (th + gap) + gap), "#14110d")
    for i, image in enumerate(images):
        sheet.paste(image.resize((tw, th), Image.LANCZOS), (gap + (i % cols) * (tw + gap), gap + (i // cols) * (th + gap)))
    return sheet


def render_story(story, folder, version):
    """모든 장을 그려 PNG로 저장하고 (파일 경로, 그림 메타) 목록을 돌려준다. 순서: 표지, 본문, 떠올려 보기, 정답."""
    pages = story.get("pages") or []
    outputs = []
    cover, metrics = render_cover(str(story.get("title", "")), (pages[0].get("scene") if pages else {}))
    outputs.append(("cover", None, cover, metrics))
    for index, page in enumerate(pages, 1):
        image, metrics = render_page(page, index, len(pages))
        outputs.append(("page", index, image, metrics))
    outputs.append(("recall", None, render_recall(story.get("recall") or []), None))
    outputs.append(("answers", None, render_answers(story.get("recall") or []), None))
    saved = []
    for number, (kind, index, image, metrics) in enumerate(outputs, 1):
        path = folder / f"story-v{version}-{number:02d}-{kind}.png"
        image.save(path, format="PNG", optimize=True)
        saved.append({"kind": kind, "index": index, "path": path, "metrics": metrics})
    sheet = folder / f"story-v{version}-sheet.jpg"
    contact_sheet([item[2] for item in outputs]).save(sheet, format="JPEG", quality=86)
    return saved, sheet


def clean_story(story):
    """모델 응답에서 정해진 칸만 남긴다(저장·화면용)."""
    pages = []
    for page in story.get("pages") or []:
        scene = page.get("scene") or {}
        pages.append({"anchor": str(page.get("anchor", "")).strip(), "text": str(page.get("text", "")).strip(),
                      "evidence": [str(item) for item in page.get("evidence") or []],
                      "scene": {"backdrop": scene.get("backdrop"),
                                "props": [{"name": p.get("name"), "place": p.get("place")} for p in scene.get("props") or [] if isinstance(p, dict)],
                                "hero": {"mood": (scene.get("hero") or {}).get("mood"), "place": (scene.get("hero") or {}).get("place")}}})
    recall = [{"question": str(item.get("question", "")).strip(), "answer": str(item.get("answer", "")).strip()}
              for item in story.get("recall") or [] if isinstance(item, dict)]
    return {"title": str(story.get("title", "")).strip(), "pages": pages, "recall": recall}


def build_record(store, job, story, checks, refined):
    """검사한 이야기를 그려 저장하고 job['story']에 넣을 기록을 만든다."""
    version = int((job.get("story") or {}).get("version", 0)) + 1
    root, folder = output_folder(store, job, "story")
    saved, sheet = render_story(story, folder, version)
    files = []
    for item in saved:
        record = artifact_record(root, item["path"])
        files.append({"kind": item["kind"], "index": item["index"], "artifact_id": record["id"], "artifact": record,
                      "truncated": bool((item["metrics"] or {}).get("truncated"))})
    if any(file["truncated"] for file in files):
        checks = {**checks, "passed": False, "issues": [*checks["issues"], "그림에 다 들어가지 않아 줄여 보인 글이 있어요. 글을 줄여 다시 만드세요"]}
    spec = folder / f"story-v{version}.json"
    data = {"version": version, "generated_at": now(), "source_hash": job["source_hash"], **story, "checks": checks, "refined": refined,
            "note": "글은 모델이, 그림은 코드가 그렸습니다(이미지 생성 비용 0원). 게시는 출고 승인② 뒤 사람이 합니다"}
    write_json(spec, data)
    spec_record = artifact_record(root, spec)
    sheet_record = artifact_record(root, sheet)
    return {**data, "files": files, "artifact_id": spec_record["id"], "artifact": spec_record,
            "sheet": {"artifact_id": sheet_record["id"], "artifact": sheet_record}}


def generate_story(store: Store, job_id, provider=None):
    job = store.require_source_approval(job_id)
    packet = job["source_packet"] or {}
    brand = load_brand()
    provider = provider or Provider(store, job_id=job_id)
    system = brand_system_prompt(BASE, brand)
    context = {"packet": packet_context(packet), "audience": brief_for_job(job), "instructions": INSTRUCTIONS,
               "vocabulary": {"backdrops": BACKDROPS, "props": PROPS, "moods": list(MOODS), "places": list(PLACES)}}
    story = clean_story(provider.generate("story", [{"role": "system", "content": system}, {"role": "user", "content": canonical(context)}],
                                          STORY_SCHEMA, {"max_tokens": 6000, "temperature": 0.5}))
    checks = story_checks(story, packet, brand)
    refined = False
    if not checks["passed"]:
        # 한 번만 고친다. 그래도 걸리면 문제점을 그대로 저장해 사람이 본다(퀴즈와 같은 규칙).
        refine = {**context, "previous": story, "issues": checks["issues"], "instructions": INSTRUCTIONS + " 아래 issues를 모두 해결한 완전한 이야기를 다시 작성한다."}
        story = clean_story(provider.generate("story", [{"role": "system", "content": system}, {"role": "user", "content": canonical(refine)}],
                                              STORY_SCHEMA, {"max_tokens": 6000, "temperature": 0.3}))
        checks = story_checks(story, packet, brand)
        refined = True
    record = build_record(store, job, story, checks, refined)
    save_job_output(store, job_id, job["source_hash"], "story", record, "story_generated",
                    {"role": "편집", "version": record["version"], "source_hash": job["source_hash"], "pages": len(story["pages"]),
                     "passed": record["checks"]["passed"], "issues": len(record["checks"]["issues"]), "artifact_id": record["artifact_id"],
                     "next_action": "장면과 글을 확인하고 출고 승인② 때 함께 검토합니다"})
    return record


STORY_KEYS = ("version", "generated_at", "source_hash", "title", "pages", "recall", "checks", "refined", "note", "artifact_id")


def story_payload(job):
    story = job.get("story")
    if not story:
        return None
    payload = {key: story.get(key) for key in STORY_KEYS}
    payload["files"] = [{key: file.get(key) for key in ("kind", "index", "artifact_id", "truncated")} | {"url": (file.get("artifact") or {}).get("url")}
                        for file in story.get("files") or []]
    payload["sheet_url"] = ((story.get("sheet") or {}).get("artifact") or {}).get("url")
    payload["current"] = story.get("source_hash") == job.get("source_hash")
    return payload


def story_artifacts(job, *, include_stale=False):
    story = job.get("story") or {}
    if not story or (story.get("source_hash") != job.get("source_hash") and not include_stale):
        return
    if story.get("artifact"):
        yield story["artifact"]
    if (story.get("sheet") or {}).get("artifact"):
        yield story["sheet"]["artifact"]
    for file in story.get("files") or []:
        if file.get("artifact"):
            yield file["artifact"]
