"""내 영상의 선명한 장면 고르기와 얼굴을 자르지 않는 자르기. 모델 호출 없음."""
import shutil
import subprocess

import pytest
from PIL import Image, ImageDraw, ImageFilter

from office.frame_focus import best_frame, crop_box, fill_crop, frame_score, measure


def inside(face, box, sw, sh):
    left, top, width, height = box
    return (left <= face["x"] * sw and (face["x"] + face["w"]) * sw <= left + width
            and top <= face["y"] * sh and (face["y"] + face["h"]) * sh <= top + height)


def test_wide_video_to_portrait_card_keeps_the_face_whole():
    assert crop_box(1920, 1080, 1080, 1440) == (555, 0, 810, 1080)  # 얼굴을 모르면 가운데
    face = {"x": 0.80, "y": 0.20, "w": 0.10, "h": 0.25}
    box = crop_box(1920, 1080, 1080, 1440, faces=[face])
    assert box[2:] == (810, 1080) and inside(face, box, 1920, 1080)
    edge = {"x": 0.93, "y": 0.2, "w": 0.07, "h": 0.2}
    assert inside(edge, crop_box(1920, 1080, 1080, 1440, faces=[edge]), 1920, 1080)


def test_operator_position_wins_and_tall_frames_keep_headroom():
    assert crop_box(1920, 1080, 1080, 1440, faces=[{"x": 0.8, "y": 0.2, "w": 0.1, "h": 0.2}], x=0.1)[0] == 0
    face = {"x": 0.4, "y": 0.10, "w": 0.2, "h": 0.12}
    left, top, width, height = crop_box(1080, 1920, 1080, 1080, faces=[face])
    assert (left, width, height) == (0, 1080, 1080) and top <= face["y"] * 1920 and inside(face, (left, top, width, height), 1080, 1920)
    assert crop_box(1080, 1920, 1080, 1080)[1] == round((1920 - 1080) * 0.25)


def test_sharpness_prefers_crisp_frames_and_brightness_penalizes_fades():
    crisp = Image.new("RGB", (320, 240), "white")
    draw = ImageDraw.Draw(crisp)
    for x in range(0, 320, 16):
        draw.rectangle((x, 0, x + 7, 240), fill="black")
    blurred = crisp.filter(ImageFilter.GaussianBlur(6))
    assert measure(crisp)[0] > measure(blurred)[0] * 3
    assert frame_score(500, 120, 0, 1.2) > frame_score(500, 10, 0, 1.2) * 5  # 암전 장면은 크게 깎는다
    assert frame_score(500, 120, 0, 1.2) > frame_score(500, 120, 1.2, 1.2)  # 요청 시각에서 멀수록 조금 깎는다


def test_fill_crop_reports_which_method_found_the_subject(tmp_path):
    source = tmp_path / "frame.png"
    Image.new("RGB", (1920, 1080), "#88aacc").save(source)
    plain = fill_crop(source, 1080, 1440, tmp_path / "a.png")
    assert plain["by"] in ("center", "opencv") and Image.open(plain["path"]).size == (1080, 1440)
    manual = fill_crop(source, 1080, 1080, tmp_path / "b.png", x=0.2)
    assert manual["by"] == "operator" and manual["box"][0] == 0
    given = fill_crop(source, 1080, 1440, tmp_path / "c.png", faces=[{"x": 0.8, "y": 0.2, "w": 0.1, "h": 0.2}])
    assert given["by"] == "given" and given["box"][0] > 555


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg가 있는 서버에서만 확인")
def test_best_frame_skips_a_black_fade(tmp_path):
    video = tmp_path / "talk.mp4"
    # 0~1초는 검은 화면, 1~3초는 무늬가 있는 화면
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
                    "-f", "lavfi", "-i", "testsrc=s=320x240:d=2", "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]", "-map", "[v]",
                    "-pix_fmt", "yuv420p", str(video)], check=True)
    result = best_frame(str(video), 0.8, tmp_path / "pick.jpg", spread=0.6, tries=5)
    assert result["t"] >= 1.0 and result["brightness"] > 22 and result["path"].is_file()


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg가 있는 서버에서만 확인")
def test_owner_video_frame_becomes_a_free_thumbnail_candidate(tmp_path):
    from fastapi.testclient import TestClient

    from office.api import create_app
    from office.media import artifact_record
    from office.store import Store
    store = Store(tmp_path / "state")
    job = store.create_job({"id": "frame-test", "title": "내 영상"})
    job = store.save_source(job["id"], {"title": "내 영상", "body": "편입 시험 한 달 전 공부 순서를 바꿨어요.",
                                        "quality": {"status": "passed", "critical": []}, "video": {"scenes": [{"narration": "내 영상", "caption": "내 영상"}]}})
    folder = store.artifacts / job["id"] / job["source_hash"] / "video"
    folder.mkdir(parents=True)
    video = folder / "talk.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=s=640x360:d=3", "-pix_fmt", "yuv420p", str(video)], check=True)
    record = artifact_record(store.artifacts, video)
    store.update_job(job["id"], manifest={"hash": "m", "files": [record]})
    client = TestClient(create_app(store), base_url="http://localhost:8510")
    headers = {"Origin": "http://localhost:3110", "X-Office-CSRF": client.get("/api/session").json()["csrf"]}
    url = f"/api/jobs/{job['id']}/thumbnail-studio"
    state = client.get(url).json()
    body = {"source_hash": job["source_hash"], "revision": state["revision"], "video_id": record["id"], "at": 1.5}
    assert client.post(url + "/frame", json=body).status_code == 403  # 검토 화면 세션 없이 못 바꾼다
    wrong = client.post(url + "/frame", headers=headers, json={**body, "video_id": "asset_missing"})
    assert wrong.status_code == 409
    done = client.post(url + "/frame", headers=headers, json=body)
    assert done.status_code == 200, done.text
    candidate = done.json()["candidates"][0]
    assert candidate["angle"] == "내 영상 장면" and candidate["provenance"]["kind"] == "owner_video_frame"
    assert candidate["provenance"]["cost_krw"] == 0 and 0.0 <= candidate["provenance"]["t"] <= 3.0
    assert client.get(candidate["url"]).status_code == 200 and store.tasks(job["id"]) == []  # 유료 생성 작업을 넣지 않는다
    stale = client.post(url + "/frame", headers=headers, json=body)  # 옛 판본 번호로는 다시 못 넣는다
    assert stale.status_code == 409
