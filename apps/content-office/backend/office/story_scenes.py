"""그림 기억 이야기의 장면을 코드로 그린다(Pillow, 0원). 사람은 그리지 않고 주인공은 늘 '뇌리'다.

방식 출처: github.com/wonseokjung/connect-ai-writer 커밋 9057798 lib/scenes.mjs의 '정해진 배경·소품 목록에서 골라
코드로 그린다'는 생각만 가져왔다. 목록(공부·시험·기억·AI 자동화 소품)과 그림 코드는 HeoBrain에 맞게 새로 썼다.

장면 사양(JSON): {"backdrop": "desk", "props": [{"name": "book", "place": "right"}], "hero": {"mood": "thinking", "place": "left"}}
place: left | center | right. 하늘 소품(해·달·별·구름)과 벽 소품(시계·달력)은 자리를 따로 잡는다.
"""
from __future__ import annotations

import math
import re

from PIL import Image, ImageDraw

from .mascot import MOODS, draw_noeri

BACKDROPS = {
    "desk": "책상", "library": "도서관", "classroom": "교실", "night": "밤", "morning": "아침", "park": "공원",
    "room": "방", "exam": "시험장", "road": "길", "stage": "무대",
}
PROPS = {
    "book": "책", "notebook": "노트", "pencil": "연필", "paper": "종이", "card": "단어 카드", "clock": "시계",
    "calendar": "달력", "lamp": "스탠드", "coffee": "커피", "laptop": "노트북", "phone": "휴대폰", "lightbulb": "전구",
    "trophy": "트로피", "key": "열쇠", "door": "문", "moon": "달", "sun": "해", "star": "별", "cloud": "구름",
    "tree": "나무", "flag": "깃발", "magnifier": "돋보기", "check": "체크 표시", "question": "물음표",
    "treadmill": "러닝머신", "headphones": "헤드폰", "mountain": "산", "robot": "로봇", "bed": "침대", "heart": "하트",
}
PLACES = ("left", "center", "right")
SKY = {"moon", "sun", "star", "cloud"}
WALL = {"clock", "calendar"}
LARGE = {"door", "tree", "treadmill", "bed", "mountain", "robot"}
TABLE_BACKDROPS = {"desk", "library", "classroom", "exam", "room"}
# 글에 이 낱말이 나오면 그 장 그림에 그 소품이 있어야 한다(그림 계약). 배경으로 대신하는 것도 있다.
NEEDS = tuple((re.compile(pattern), thing) for pattern, thing in (
    (r"(?<!공)책(?![상임장])|교재", "book"), (r"노트(?!북)|공책", "notebook"), (r"연필|펜으로|펜을", "pencil"),
    (r"종이|목차|시험지", "paper"), (r"카드", "card"), (r"시계", "clock"), (r"달력", "calendar"), (r"스탠드|전등", "lamp"),
    (r"커피", "coffee"), (r"노트북|컴퓨터", "laptop"), (r"휴대폰|스마트폰|핸드폰", "phone"), (r"전구", "lightbulb"),
    (r"트로피", "trophy"), (r"열쇠", "key"), (r"문을|문이|문 앞", "door"), (r"달빛|달이|달을|보름달", "moon"),
    (r"햇빛|해가 |해를|햇살", "sun"), (r"별이|별을|별빛", "star"), (r"구름", "cloud"), (r"나무", "tree"), (r"깃발", "flag"),
    (r"돋보기", "magnifier"), (r"러닝머신|트레드밀", "treadmill"), (r"헤드폰|이어폰", "headphones"),
    (r"산을|산이|산에|정상에", "mountain"), (r"로봇", "robot"), (r"침대", "bed"), (r"하트", "heart"),
))
NEEDS_BACKDROP = {"night": ("moon", "star"), "morning": ("sun",)}

W, H, S = 1080, 900, 2  # 장면 크기와 슈퍼샘플 배율(계단 현상 줄이기)
INK = "#2f5e4a"


def _grad(draw, box, top, bottom):
    x0, y0, x1, y1 = box
    t = [int(top[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(bottom[i:i + 2], 16) for i in (1, 3, 5)]
    steps = max(1, y1 - y0)
    for i in range(0, steps, 2):
        f = i / steps
        color = tuple(round(t[c] + (b[c] - t[c]) * f) for c in range(3))
        draw.rectangle((x0, y0 + i, x1, y0 + i + 2), fill=color)


def draw_backdrop(img, name):
    d = ImageDraw.Draw(img)
    w, h = img.size
    ground = int(h * 0.74)
    if name == "night":
        _grad(d, (0, 0, w, h), "#1d2a4a", "#3a4f7a")
        d.ellipse((-w * 0.2, ground - 80 * S, w * 1.2, h + 400 * S), fill="#24365a")
    elif name in ("morning", "park", "road"):
        _grad(d, (0, 0, w, ground), "#fde9c8" if name == "morning" else "#d7eef6", "#e9f5ee")
        d.rectangle((0, ground, w, h), fill="#a9d4a0")
        d.ellipse((-w * 0.3, ground - 60 * S, w * 0.7, h + 200 * S), fill="#9ccb93")
        if name == "road":
            d.polygon([(w * 0.42, ground), (w * 0.58, ground), (w * 0.86, h), (w * 0.14, h)], fill="#d9cdb8")
            for i in range(4):
                y = ground + (h - ground) * (i + 0.3) / 4
                d.rectangle((w * 0.495, y, w * 0.505, y + 18 * S), fill="#ffffff")
    elif name == "stage":
        _grad(d, (0, 0, w, h), "#2b2236", "#3d3150")
        d.polygon([(w * 0.42, 0), (w * 0.58, 0), (w * 0.8, ground), (w * 0.2, ground)], fill="#5b4b70")
        d.rectangle((0, ground, w, h), fill="#7a5a3a")
        d.rectangle((0, ground, w, ground + 10 * S), fill="#5c4128")
    else:  # 실내
        wall = {"desk": "#f3efe4", "library": "#efe6d6", "classroom": "#eef1ef", "exam": "#eef1ef", "room": "#e9eef0"}.get(name, "#f3efe4")
        d.rectangle((0, 0, w, h), fill=wall)
        floor_y = int(h * 0.80)
        d.rectangle((0, floor_y, w, h), fill="#d9c3a5")
        if name == "library":
            for side in (0, 1):
                x0 = 30 * S if side == 0 else w - 330 * S
                d.rectangle((x0, 60 * S, x0 + 300 * S, floor_y), fill="#a7744d")
                for row in range(4):
                    y = 90 * S + row * 140 * S
                    d.rectangle((x0 + 14 * S, y + 110 * S, x0 + 286 * S, y + 122 * S), fill="#7f5534")
                    bx = x0 + 18 * S
                    for k in range(9):
                        bw = (18 + (k * 7) % 14) * S
                        color = ("#e3a95c", "#6f9d86", "#d0705a", "#5b7fa8", "#e6d39a")[(k + row) % 5]
                        d.rectangle((bx, y + (16 + (k * 5) % 18) * S, bx + bw, y + 110 * S), fill=color)
                        bx += bw + 4 * S
        if name in ("classroom", "exam"):
            d.rectangle((w * 0.3, 70 * S, w * 0.7, 300 * S), fill="#2f4f45", outline="#a7744d", width=12 * S)
        if name == "room":
            d.rectangle((w * 0.62, 90 * S, w * 0.9, 380 * S), fill="#cfe6f2", outline="#ffffff", width=14 * S)
            d.line([(w * 0.76, 90 * S), (w * 0.76, 380 * S)], fill="#ffffff", width=10 * S)
        if name in TABLE_BACKDROPS:
            d.rectangle((0, int(h * 0.70), w, int(h * 0.74)), fill="#b98a5e")
            d.rectangle((0, int(h * 0.74), w, int(h * 0.77)), fill="#9c7049")
    return int(h * 0.70) if name in TABLE_BACKDROPS else ground


def _poly(d, pts, cx, base, k, **kw):
    d.polygon([(cx + (x - 50) * k, base - (100 - y) * k) for x, y in pts], **kw)


def _rect(d, x0, y0, x1, y1, cx, base, k, **kw):
    d.rounded_rectangle((cx + (x0 - 50) * k, base - (100 - y0) * k, cx + (x1 - 50) * k, base - (100 - y1) * k), radius=max(2, 4 * k), **kw)


def _ell(d, x0, y0, x1, y1, cx, base, k, **kw):
    d.ellipse((cx + (x0 - 50) * k, base - (100 - y0) * k, cx + (x1 - 50) * k, base - (100 - y1) * k), **kw)


def _line(d, pts, cx, base, k, fill=INK, width=3):
    d.line([(cx + (x - 50) * k, base - (100 - y) * k) for x, y in pts], fill=fill, width=max(2, round(width * k)), joint="curve")


def draw_prop(img, name, cx, base, k):
    """100x100 단위 상자의 아래 가운데를 (cx, base)에 맞춰 그린다. k는 단위당 픽셀."""
    d = ImageDraw.Draw(img)
    o = {"outline": INK, "width": max(2, round(3 * k))}
    if name == "book":
        _rect(d, 14, 52, 86, 100, cx, base, k, fill="#d0705a", **o)
        _rect(d, 20, 58, 80, 64, cx, base, k, fill="#f7e7c6")
        _rect(d, 18, 30, 82, 54, cx, base, k, fill="#5b7fa8", **o)
    elif name == "notebook":
        _rect(d, 18, 20, 82, 100, cx, base, k, fill="#f7f3ea", **o)
        for y in (40, 52, 64, 76, 88):
            _line(d, [(28, y), (74, y)], cx, base, k, fill="#9fb8c9", width=2)
        _line(d, [(30, 20), (30, 100)], cx, base, k, fill="#d0705a", width=2)
    elif name == "pencil":
        _poly(d, [(20, 92), (78, 34), (88, 44), (30, 102)], cx, base, k, fill="#f2b33d", **o)
        _poly(d, [(20, 92), (30, 102), (12, 104)], cx, base, k, fill="#f7e7c6", **o)
        _poly(d, [(78, 34), (88, 44), (94, 38), (84, 28)], cx, base, k, fill="#f6b9a6", **o)
    elif name == "paper":
        _poly(d, [(22, 12), (70, 12), (84, 26), (84, 100), (22, 100)], cx, base, k, fill="#ffffff", **o)
        for i, y in enumerate((34, 48, 62, 76)):
            _line(d, [(32, y), (74 - (i % 2) * 12, y)], cx, base, k, fill="#8a9a92", width=2)
    elif name == "card":
        _rect(d, 10, 38, 74, 100, cx, base, k, fill="#fff4dc", **o)
        _rect(d, 28, 26, 92, 88, cx, base, k, fill="#ffffff", **o)
        _line(d, [(46, 70), (60, 44), (74, 70)], cx, base, k, width=4)
        _line(d, [(51, 61), (69, 61)], cx, base, k, width=4)
    elif name == "clock":
        _ell(d, 12, 12, 88, 88, cx, base, k, fill="#ffffff", **o)
        _line(d, [(50, 50), (50, 26)], cx, base, k, width=4)
        _line(d, [(50, 50), (68, 58)], cx, base, k, width=4)
    elif name == "calendar":
        _rect(d, 12, 20, 88, 96, cx, base, k, fill="#ffffff", **o)
        _rect(d, 12, 20, 88, 40, cx, base, k, fill="#d0705a", **o)
        for r in range(3):
            for c in range(4):
                _rect(d, 20 + c * 17, 48 + r * 15, 30 + c * 17, 56 + r * 15, cx, base, k, fill="#cfeedd" if (r, c) != (1, 2) else "#f2b33d")
    elif name == "lamp":
        _poly(d, [(30, 10), (70, 10), (82, 40), (18, 40)], cx, base, k, fill="#f2b33d", **o)
        _line(d, [(50, 40), (50, 92)], cx, base, k, width=5)
        _rect(d, 26, 90, 74, 100, cx, base, k, fill="#2f5e4a")
    elif name == "coffee":
        _rect(d, 22, 40, 72, 100, cx, base, k, fill="#ffffff", **o)
        _ell(d, 64, 54, 88, 82, cx, base, k, outline=INK, width=max(2, round(4 * k)))
        _line(d, [(36, 30), (40, 20), (36, 10)], cx, base, k, fill="#b9c4be", width=3)
        _line(d, [(54, 30), (58, 20), (54, 10)], cx, base, k, fill="#b9c4be", width=3)
    elif name == "laptop":
        _rect(d, 16, 30, 84, 84, cx, base, k, fill="#3c4b46", **o)
        _rect(d, 22, 36, 78, 78, cx, base, k, fill="#9fd3e8")
        _poly(d, [(6, 86), (94, 86), (100, 100), (0, 100)], cx, base, k, fill="#b9c4be", **o)
    elif name == "phone":
        _rect(d, 30, 14, 70, 100, cx, base, k, fill="#3c4b46", **o)
        _rect(d, 35, 22, 65, 88, cx, base, k, fill="#9fd3e8")
    elif name == "lightbulb":
        _ell(d, 22, 6, 78, 66, cx, base, k, fill="#ffe08a", **o)
        _rect(d, 36, 64, 64, 90, cx, base, k, fill="#b9c4be", **o)
        for a in range(-60, 61, 30):
            r0, r1 = 34, 46
            x0 = 50 + r0 * math.sin(math.radians(a)) * 1.3
            y0 = 36 - r0 * math.cos(math.radians(a)) * 1.3
            x1 = 50 + r1 * math.sin(math.radians(a)) * 1.3
            y1 = 36 - r1 * math.cos(math.radians(a)) * 1.3
            _line(d, [(x0, y0), (x1, y1)], cx, base, k, fill="#f2b33d", width=3)
    elif name == "trophy":
        _poly(d, [(26, 10), (74, 10), (68, 50), (32, 50)], cx, base, k, fill="#f2b33d", **o)
        _ell(d, 10, 14, 34, 40, cx, base, k, outline=INK, width=max(2, round(4 * k)))
        _ell(d, 66, 14, 90, 40, cx, base, k, outline=INK, width=max(2, round(4 * k)))
        _rect(d, 44, 50, 56, 78, cx, base, k, fill="#f2b33d", **o)
        _rect(d, 28, 78, 72, 100, cx, base, k, fill="#a7744d", **o)
    elif name == "key":
        _ell(d, 8, 30, 46, 68, cx, base, k, fill="#f2b33d", **o)
        _rect(d, 40, 44, 94, 54, cx, base, k, fill="#f2b33d", **o)
        _rect(d, 76, 54, 84, 68, cx, base, k, fill="#f2b33d", **o)
    elif name == "door":
        _rect(d, 18, 0, 82, 100, cx, base, k, fill="#a7744d", **o)
        _ell(d, 66, 50, 74, 58, cx, base, k, fill="#f2b33d")
    elif name == "moon":
        _ell(d, 14, 14, 86, 86, cx, base, k, fill="#fff1b8")
        _ell(d, 34, 6, 98, 70, cx, base, k, fill="#2b3d63")
    elif name == "sun":
        _ell(d, 22, 22, 78, 78, cx, base, k, fill="#f2b33d")
        for a in range(0, 360, 45):
            x0, y0 = 50 + 34 * math.cos(math.radians(a)), 50 + 34 * math.sin(math.radians(a))
            x1, y1 = 50 + 46 * math.cos(math.radians(a)), 50 + 46 * math.sin(math.radians(a))
            _line(d, [(x0, y0), (x1, y1)], cx, base, k, fill="#f2b33d", width=5)
    elif name == "star":
        pts = []
        for i in range(10):
            ang = -math.pi / 2 + i * math.pi / 5
            r = 44 if i % 2 == 0 else 19
            pts.append((50 + r * math.cos(ang), 52 + r * math.sin(ang)))
        _poly(d, pts, cx, base, k, fill="#fff1b8")
    elif name == "cloud":
        for (x0, y0, x1, y1) in ((10, 44, 50, 84), (30, 26, 74, 70), (54, 40, 92, 80), (20, 56, 84, 88)):
            _ell(d, x0, y0, x1, y1, cx, base, k, fill="#ffffff")
    elif name == "tree":
        _rect(d, 42, 56, 58, 100, cx, base, k, fill="#8b5e3c")
        for (x0, y0, x1, y1) in ((14, 18, 62, 64), (40, 6, 88, 56), (24, 34, 80, 76)):
            _ell(d, x0, y0, x1, y1, cx, base, k, fill="#6fae7a")
    elif name == "flag":
        _line(d, [(30, 100), (30, 8)], cx, base, k, width=5)
        _poly(d, [(30, 10), (86, 24), (30, 40)], cx, base, k, fill="#d0705a", **o)
    elif name == "magnifier":
        _line(d, [(62, 62), (90, 92)], cx, base, k, width=9)
        _ell(d, 10, 10, 70, 70, cx, base, k, fill="#dff1fa", **o)
    elif name == "check":
        _ell(d, 10, 10, 90, 90, cx, base, k, fill="#6fae7a")
        _line(d, [(30, 52), (44, 66), (72, 36)], cx, base, k, fill="#ffffff", width=9)
    elif name == "question":
        _ell(d, 10, 6, 90, 86, cx, base, k, fill="#ffffff", **o)
        _poly(d, [(30, 76), (24, 98), (46, 82)], cx, base, k, fill="#ffffff", **o)
        _line(d, [(38, 34), (44, 24), (58, 22), (64, 32), (52, 44), (50, 54)], cx, base, k, width=7)
        _ell(d, 46, 62, 56, 72, cx, base, k, fill=INK)
    elif name == "treadmill":
        _poly(d, [(4, 86), (84, 74), (92, 84), (10, 98)], cx, base, k, fill="#3c4b46", **o)
        _line(d, [(78, 76), (86, 16)], cx, base, k, width=6)
        _rect(d, 66, 8, 98, 24, cx, base, k, fill="#9fd3e8", **o)
    elif name == "headphones":
        d.arc((cx + (16 - 50) * k, base - (100 - 10) * k, cx + (84 - 50) * k, base - (100 - 78) * k), 180, 360, fill=INK, width=max(2, round(8 * k)))
        _rect(d, 8, 50, 30, 86, cx, base, k, fill="#d0705a", **o)
        _rect(d, 70, 50, 92, 86, cx, base, k, fill="#d0705a", **o)
    elif name == "mountain":
        _poly(d, [(0, 100), (40, 20), (62, 56), (74, 40), (100, 100)], cx, base, k, fill="#8fa9a0", **o)
        _poly(d, [(40, 20), (30, 40), (40, 36), (50, 40)], cx, base, k, fill="#ffffff")
    elif name == "robot":
        _rect(d, 24, 34, 76, 74, cx, base, k, fill="#b9c4be", **o)
        _ell(d, 34, 46, 46, 58, cx, base, k, fill="#2f5e4a")
        _ell(d, 54, 46, 66, 58, cx, base, k, fill="#2f5e4a")
        _line(d, [(50, 34), (50, 18)], cx, base, k, width=4)
        _ell(d, 44, 8, 56, 20, cx, base, k, fill="#f2b33d")
        _rect(d, 30, 74, 70, 100, cx, base, k, fill="#9fb8c9", **o)
    elif name == "bed":
        _rect(d, 4, 60, 96, 90, cx, base, k, fill="#ffffff", **o)
        _rect(d, 4, 40, 14, 100, cx, base, k, fill="#a7744d", **o)
        _rect(d, 14, 52, 38, 66, cx, base, k, fill="#cfeedd", **o)
        _rect(d, 38, 56, 96, 74, cx, base, k, fill="#9fb8c9", **o)
    elif name == "heart":
        _ell(d, 10, 14, 54, 58, cx, base, k, fill="#d0705a")
        _ell(d, 46, 14, 90, 58, cx, base, k, fill="#d0705a")
        _poly(d, [(12, 44), (88, 44), (50, 92)], cx, base, k, fill="#d0705a")


def _slots(hero_place):
    order = [p for p in ("right", "left", "center") if p != hero_place] + [hero_place]
    return order


def render_scene(scene, *, seed=0):
    """장면 사양 하나를 W x H 그림으로 그린다. 모르는 이름은 건너뛰고(검사에서 따로 잡는다) 나머지는 그린다."""
    backdrop = scene.get("backdrop") if scene.get("backdrop") in BACKDROPS else "desk"
    img = Image.new("RGB", (W * S, H * S), "#ffffff")
    ground = draw_backdrop(img, backdrop)
    hero = scene.get("hero") or {}
    hero_place = hero.get("place") if hero.get("place") in PLACES else "left"
    props = [p for p in scene.get("props") or [] if isinstance(p, dict) and p.get("name") in PROPS]
    xs = {"left": 0.22, "center": 0.5, "right": 0.78}
    used = {}
    sky_i = wall_i = 0
    for prop in props:
        name = prop["name"]
        if name in SKY:
            cx = W * S * (0.82 - 0.22 * sky_i) if backdrop in ("night", "morning", "park", "road", "stage") else W * S * (0.85 - 0.2 * sky_i)
            base = (140 + 40 * (sky_i % 2)) * S + 110 * S
            draw_prop(img, name, cx, base, 1.5 * S if name != "star" else 0.8 * S)
            if name == "star":
                for j, (dx, dy, kk) in enumerate(((-260, 60, 0.45), (-120, 150, 0.35), (140, 40, 0.4))):
                    draw_prop(img, "star", cx + dx * S, base + dy * S, kk * S)
            sky_i += 1
            continue
        if name in WALL:
            cx = W * S * (0.14 + 0.72 * (wall_i % 2))
            draw_prop(img, name, cx, 290 * S, 1.6 * S)
            wall_i += 1
            continue
        place = prop.get("place") if prop.get("place") in PLACES else None
        if not place or place == hero_place:
            place = next((p for p in _slots(hero_place) if p not in used), "right")
        count = used.get(place, 0)
        used[place] = count + 1
        size = 2.8 if name in LARGE else 1.75
        if name in LARGE and backdrop in TABLE_BACKDROPS:
            base_y = H * S * 0.80
        else:
            base_y = ground
        cx = W * S * xs[place] + (count * 150 - (75 if count else 0)) * S
        draw_prop(img, name, cx, base_y, size * S)
    present = {p["name"] for p in props}
    if backdrop == "night":  # 밤에는 달과 별이, 아침에는 해가 늘 보인다(scene_words와 같은 약속)
        if "moon" not in present:
            draw_prop(img, "moon", W * S * 0.84, 250 * S, 1.3 * S)
        if "star" not in present:
            for dx, dy, kk in ((0.12, 150, 0.45), (0.3, 90, 0.35), (0.58, 170, 0.4), (0.68, 70, 0.3)):
                draw_prop(img, "star", W * S * dx, dy * S + 60 * S, kk * S)
    if backdrop == "morning" and "sun" not in present:
        draw_prop(img, "sun", W * S * 0.84, 260 * S, 1.4 * S)
    mood = hero.get("mood") if hero.get("mood") in MOODS else "happy"
    if hero is not None and scene.get("hero") is not None:
        scale = 2.0 if hero.get("size") != "small" else 1.4
        hx = W * S * xs[hero_place] - 100 * scale * S
        hy = (H * S * 0.80 if backdrop in TABLE_BACKDROPS else ground + 10 * S) - 196 * scale * S
        facing = {"left": 1.0, "center": 0.0, "right": -1.0}[hero_place]
        draw_noeri(img, hx, hy, scale * S, mood, facing=facing)
    return img.resize((W, H), Image.LANCZOS)


def scene_words(scene):
    """그림에 실제로 있는 것: 소품 이름과 배경이 대신하는 것."""
    have = {p.get("name") for p in scene.get("props") or [] if isinstance(p, dict)}
    have |= set(NEEDS_BACKDROP.get(scene.get("backdrop"), ()))
    return have
