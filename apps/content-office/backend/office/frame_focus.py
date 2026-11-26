"""내 영상에서 선명한 장면을 고르고, 얼굴을 자르지 않고 카드·썸네일 크기로 맞춘다(0원, 모델 호출 없음).

방식 출처: github.com/wonseokjung/connect-ai-writer 커밋 9057798 lib/frames.mjs(선명도 = 라플라시안 분산, 너무 어둡거나
밝은 장면 제외, 요청 시각 앞뒤 몇 장 중 가장 선명한 것)와 lib/focus.mjs cropBox(넓으면 높이를 지키고, 좁으면 머리 위 여백을
지킨다). 맥 전용 face.swift(애플 Vision) 대신, 서버(EC2)에서도 돌도록 바꿨다:
  1. 사람이 준 위치(x=0~1)가 있으면 그것을 쓴다.
  2. OpenCV가 깔려 있으면 정면 얼굴을 찾는다(선택 사항, 없어도 동작).
  3. 둘 다 없으면 가운데를 지킨다(말하는 사람이 보통 가운데에 있다).
얼굴 위치는 사진을 밖으로 보내지 않고 이 컴퓨터 안에서만 계산한다.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps, ImageStat

from .media import command, executable
from .store import WorkflowError

DARK, BRIGHT = 22, 235  # 이 밝기 밖은 페이드·암전으로 보고 점수를 깎는다


def crop_box(sw, sh, tw, th, faces=(), people=(), x=None, anchor=None):
    """원본(sw x sh)에서 목표 비율(tw:th)로 자를 상자 (left, top, width, height). faces·people은 0~1 비율 상자 {x,y,w,h}.
    anchor(0~1)를 주면 얼굴 가운데를 자른 그림의 그 가로 위치에 둔다(썸네일: 왼쪽 제목, 오른쪽 얼굴)."""
    if min(sw, sh, tw, th) <= 0:
        raise WorkflowError("자를 그림과 목표 크기가 올바르지 않습니다")
    want = tw / th
    face = max(faces, key=lambda b: b["w"] * b["h"], default=None)
    body = max(people, key=lambda b: b["w"] * b["h"], default=None)
    focus = face or body
    if sw / sh > want:
        # 목표보다 넓다: 높이를 다 쓰고(머리가 잘리지 않는다) 왼쪽 끝을 고른다
        cw = round(sh * want)
        if x is not None:
            cx = float(x) * sw
        elif not focus:
            cx = sw / 2
        else:
            fx = focus["x"] + focus["w"] / 2
            # 가운데 가까우면 가운데에, 가장자리면 옆 풍경이 남도록 조금 비켜서 둔다
            at = anchor if anchor is not None else (0.5 if abs(fx - 0.5) < 0.15 else (0.66 if fx > 0.5 else 0.34))
            cx = fx * sw + (0.5 - at) * cw
        left = round(cx - cw / 2)
        if face and x is None:
            pad = face["w"] * sw * 0.25
            left = min(left, round(face["x"] * sw - pad))
            left = max(left, round((face["x"] + face["w"]) * sw + pad - cw))
        left = max(0, min(sw - cw, left))
        return left, 0, cw, sh
    # 목표보다 좁다(세로가 길다): 너비를 다 쓰고 머리 위 여백을 남긴다
    ch = round(sw / want)
    if focus:
        top = round((focus["y"] - (face["h"] * 0.6 if face else 0.02)) * sh)
    else:
        top = round((sh - ch) * 0.25)
    top = max(0, min(sh - ch, top))
    return 0, top, sw, ch


def measure(image):
    """(선명도, 밝기). 선명도는 회색 축소본에 라플라시안을 건 결과의 분산이다."""
    grey = ImageOps.grayscale(image)
    grey.thumbnail((480, 480))
    edges = grey.filter(ImageFilter.Kernel((3, 3), (0, 1, 0, 1, -4, 1, 0, 1, 0), scale=1, offset=128))
    return ImageStat.Stat(edges).var[0], ImageStat.Stat(grey).mean[0]


def frame_score(sharpness, brightness, distance, spread):
    usable = DARK < brightness < BRIGHT
    return (1.0 if usable else 0.15) * sharpness * (1 - abs(distance) / (spread * 6))


def detect_faces(image):
    """OpenCV가 있으면 정면 얼굴 상자(0~1 비율)를, 없으면 빈 목록을 돌려준다. 바깥으로 아무것도 보내지 않는다."""
    try:
        import cv2  # type: ignore
        import numpy  # type: ignore
    except ImportError:
        return []
    grey = numpy.array(ImageOps.grayscale(image))
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    found = cascade.detectMultiScale(grey, scaleFactor=1.1, minNeighbors=5, minSize=(max(24, grey.shape[1] // 30),) * 2)
    w, h = image.size
    return [{"x": fx / w, "y": fy / h, "w": fw / w, "h": fh / h} for fx, fy, fw, fh in found]


def fill_crop(source, width, height, out, *, x=None, faces=None, anchor=None):
    """source를 width x height로 꽉 채워 자른다. 얼굴 상자를 주지 않으면 찾아보고, 쓴 방법(by)을 함께 돌려준다."""
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        if x is not None:
            boxes, by = [], "operator"
        elif faces is not None:
            boxes, by = list(faces), "given"
        else:
            boxes = detect_faces(image)
            by = "opencv" if boxes else "center"
        left, top, cw, ch = crop_box(image.width, image.height, width, height, faces=boxes, x=x, anchor=anchor)
        image.crop((left, top, left + cw, top + ch)).resize((width, height), Image.LANCZOS).save(out)
    return {"path": Path(out), "box": [left, top, cw, ch], "by": by, "faces": len(boxes)}


def _duration(video):
    from .media import probe
    info = probe(video)
    try:
        return float(info.get("format", {}).get("duration", 0))
    except (TypeError, ValueError):
        return 0.0


def best_frame(video, at, out, *, spread=1.2, tries=7):
    """at초 앞뒤 spread초 안에서 tries장을 뽑아 가장 선명하고 너무 어둡거나 밝지 않은 장면을 out에 저장한다."""
    duration = _duration(video)
    if duration <= 0:
        raise WorkflowError("영상 길이를 읽지 못했습니다")
    t0 = max(0.0, min(float(at), max(0.0, duration - 0.2)))
    ffmpeg = executable("ffmpeg")
    picks = []
    work = Path(tempfile.mkdtemp(prefix="frames-"))
    try:
        for i in range(tries):
            t = max(0.0, min(duration - 0.05, t0 - spread + 2 * spread * i / max(1, tries - 1)))
            path = work / f"c{i}.jpg"
            try:
                command([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "3", path], 60)
            except WorkflowError:
                continue
            if not path.is_file():
                continue
            with Image.open(path) as image:
                sharpness, brightness = measure(image)
            picks.append({"t": t, "sharpness": sharpness, "brightness": brightness, "score": frame_score(sharpness, brightness, t - t0, spread)})
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if not picks:
        raise WorkflowError(f"{at}초 근처에서 장면을 뽑지 못했습니다")
    best = max(picks, key=lambda item: item["score"])
    command([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{best['t']:.3f}", "-i", video, "-frames:v", "1", "-q:v", "2", out], 60)
    if not Path(out).is_file():
        raise WorkflowError("고른 장면을 저장하지 못했습니다")
    return {"path": Path(out), "t": round(best["t"], 3), "sharpness": round(best["sharpness"], 1),
            "brightness": round(best["brightness"], 1), "tried": len(picks)}
