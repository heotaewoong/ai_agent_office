"""HeoBrain 캐릭터 '뇌리'를 코드로 그린다(Pillow). 그림 기억 이야기의 주인공이고, 화면의 진행 표시와 같은 모양이다.

'뇌리에 남다'에서 따온 이름이다. 다른 브랜드의 캐릭터를 옮기지 않고 HeoBrain 색(초록, 크림, 호박색)으로 새로 만들었다.
방식 출처: github.com/wonseokjung/connect-ai-writer 커밋 9057798의 '단계마다 표정이 바뀌는 캐릭터' 아이디어만 가져왔고,
그림과 코드는 새로 썼다. 화면용 SVG는 frontend/app/noeri.tsx가 같은 비율로 그린다.

그리는 좌표는 200x200 상자 기준이고 scale로 키운다. 돈이 드는 호출이나 바깥 파일은 쓰지 않는다.
"""
from __future__ import annotations

from PIL import ImageDraw

MOODS = ("happy", "curious", "thinking", "tired", "proud", "surprised", "calm")
MOOD_LABELS = {"happy": "신남", "curious": "궁금", "thinking": "생각 중", "tired": "지침", "proud": "뿌듯",
               "surprised": "놀람", "calm": "차분"}
PALETTE = {"body": "#cfeedd", "shade": "#a9dcc1", "line": "#2f5e4a", "groove": "#8fc4a8", "cheek": "#f6b9a6",
           "eye": "#223c31", "spark": "#ff8a3d", "white": "#ffffff", "drop": "#8cc8f0"}
# 몸통은 둥근 혹 여러 개를 겹친 뇌 모양이다: (중심 x, 중심 y, 반지름)
LOBES = ((100, 112, 70), (62, 70, 34), (100, 56, 38), (138, 70, 34), (40, 106, 32), (160, 106, 32), (60, 146, 30), (140, 146, 30))


def _circle(draw, cx, cy, r, fill=None, outline=None, width=1):
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill, outline=outline, width=width)


def draw_noeri(image, x, y, scale=1.0, mood="happy", *, facing=0.0):
    """image의 (x, y)를 왼쪽 위로 하는 200*scale 크기 상자에 뇌리를 그린다. facing은 -1(왼쪽)~1(오른쪽) 눈동자 방향."""
    if mood not in MOODS:
        mood = "happy"
    draw = ImageDraw.Draw(image)
    s = scale
    P = lambda px, py: (x + px * s, y + py * s)  # noqa: E731

    def circle(cx, cy, r, **kw):
        (px, py), radius = P(cx, cy), r * s
        _circle(draw, px, py, radius, **kw)

    line_w = max(2, round(5 * s))
    # 발과 팔은 몸통 뒤에 먼저 그린다
    for fx in (78, 122):
        px, py = P(fx, 182)
        draw.ellipse((px - 17 * s - line_w, py - 9 * s - line_w, px + 17 * s + line_w, py + 9 * s + line_w), fill=PALETTE["line"])
        draw.ellipse((px - 17 * s, py - 9 * s, px + 17 * s, py + 9 * s), fill=PALETTE["shade"])
    arm_y = 128 if mood not in ("proud", "surprised") else 104
    for ax in (22, 178):
        circle(ax, arm_y, 15 + line_w / s, fill=PALETTE["line"])
        circle(ax, arm_y, 15, fill=PALETTE["shade"])
    # 몸통 외곽선: 같은 모양을 조금 크게 먼저 그린다
    for cx, cy, r in LOBES:
        circle(cx, cy, r + line_w / s, fill=PALETTE["line"])
    for cx, cy, r in LOBES:
        circle(cx, cy, r, fill=PALETTE["body"])
    # 가운데 골과 주름 몇 줄
    groove = [P(100, 30), P(94, 44), P(104, 58), P(96, 72), P(102, 86)]
    draw.line(groove, fill=PALETTE["groove"], width=max(2, round(4 * s)), joint="curve")
    for (x0, y0, x1, y1, start, end) in ((50, 52, 84, 84, 200, 320), (116, 52, 150, 84, 220, 340), (26, 90, 58, 122, 250, 20),
                                         (142, 90, 174, 122, 160, 290)):
        (a, b), (c, d) = P(x0, y0), P(x1, y1)
        draw.arc((a, b, c, d), start, end, fill=PALETTE["groove"], width=max(2, round(3 * s)))
    # 볼
    for cx in (62, 138):
        (px, py) = P(cx, 134)
        draw.ellipse((px - 13 * s, py - 8 * s, px + 13 * s, py + 8 * s), fill=PALETTE["cheek"])
    _face(draw, P, s, mood, facing)
    _extras(draw, P, s, mood)
    return image


def _face(draw, P, s, mood, facing):
    eye = PALETTE["eye"]
    w = max(2, round(5 * s))
    left, right = (78, 112), (122, 112)
    if mood in ("happy", "proud"):
        for ex, ey in (left, right):
            (a, b), (c, d) = P(ex - 11, ey - 9), P(ex + 11, ey + 9)
            draw.arc((a, b, c, d), 200, 340, fill=eye, width=w)
    elif mood == "tired":
        for ex, ey in (left, right):
            draw.line([P(ex - 10, ey + 2), P(ex + 10, ey + 2)], fill=eye, width=w)
            (a, b), (c, d) = P(ex - 10, ey - 4), P(ex + 10, ey + 8)
            draw.arc((a, b, c, d), 20, 160, fill=eye, width=max(2, round(3 * s)))
    elif mood == "calm":
        for ex, ey in (left, right):
            (px, py) = P(ex, ey + 2)
            draw.ellipse((px - 5 * s, py - 5 * s, px + 5 * s, py + 5 * s), fill=eye)
    else:
        big = 12 if mood == "surprised" else 10
        dx = 4 * facing + (4 if mood == "thinking" else 0)
        dy = -4 if mood == "thinking" else 0
        for ex, ey in (left, right):
            (px, py) = P(ex, ey)
            draw.ellipse((px - big * s, py - big * s, px + big * s, py + big * s), fill=PALETTE["white"], outline=eye, width=max(2, round(3 * s)))
            (qx, qy) = P(ex + dx, ey + dy)
            draw.ellipse((qx - 6 * s, qy - 6 * s, qx + 6 * s, qy + 6 * s), fill=eye)
            draw.ellipse((qx - 1 * s, qy - 4 * s, qx + 3 * s, qy), fill=PALETTE["white"])
        if mood == "curious":
            draw.arc((*P(110, 88), *P(134, 104)), 200, 330, fill=eye, width=max(2, round(3 * s)))
    # 입
    if mood in ("happy", "proud"):
        (a, b), (c, d) = P(86, 128), P(114, 150)
        draw.chord((a, b, c, d), 0, 180, fill="#c45a4a", outline=eye, width=max(2, round(3 * s)))
    elif mood == "surprised":
        (px, py) = P(100, 142)
        draw.ellipse((px - 7 * s, py - 9 * s, px + 7 * s, py + 9 * s), fill="#c45a4a", outline=eye, width=max(2, round(3 * s)))
    elif mood == "curious":
        (px, py) = P(104, 140)
        draw.ellipse((px - 5 * s, py - 5 * s, px + 5 * s, py + 5 * s), outline=eye, width=max(2, round(3 * s)))
    elif mood == "thinking":
        draw.line([P(92, 141), P(110, 139)], fill=eye, width=max(2, round(4 * s)))
    elif mood == "tired":
        draw.line([P(88, 142), P(94, 138), P(100, 142), P(106, 138), P(112, 142)], fill=eye, width=max(2, round(3 * s)), joint="curve")
    else:  # calm
        (a, b), (c, d) = P(88, 130), P(112, 146)
        draw.arc((a, b, c, d), 20, 160, fill=eye, width=max(2, round(4 * s)))


def _star(draw, cx, cy, r, fill):
    points = []
    for i in range(10):
        import math
        angle = -math.pi / 2 + i * math.pi / 5
        radius = r if i % 2 == 0 else r * 0.45
        points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    draw.polygon(points, fill=fill)


def _extras(draw, P, s, mood):
    # 머리 위 반짝임: 생각이 '뇌리를 스치는' 표시
    (sx, sy) = P(152, 18)
    _star(draw, sx, sy, 15 * s, PALETTE["spark"])
    if mood == "thinking":
        for i, (dx, dy, r) in enumerate(((170, 44, 4), (180, 32, 5), (192, 18, 6))):
            (px, py) = P(dx, dy)
            draw.ellipse((px - r * s, py - r * s, px + r * s, py + r * s), fill=PALETTE["line"])
    if mood == "tired":
        (px, py) = P(162, 76)
        draw.polygon([P(162, 64), P(154, 80), P(170, 80)], fill=PALETTE["drop"])
        draw.ellipse((px - 8 * s, py - 4 * s, px + 8 * s, py + 12 * s), fill=PALETTE["drop"])
    if mood == "proud":
        for cx, cy, r in ((24, 40, 9), (182, 62, 8), (14, 150, 7)):
            (px, py) = P(cx, cy)
            _star(draw, px, py, r * s, PALETTE["spark"])
    if mood == "surprised":
        for (x0, y0, x1, y1) in ((12, 34, 24, 54), (184, 34, 172, 54)):
            draw.line([P(x0, y0), P(x1, y1)], fill=PALETTE["line"], width=max(2, round(4 * s)))
