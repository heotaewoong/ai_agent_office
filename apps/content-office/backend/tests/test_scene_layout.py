"""Video scene drawing: picture instructions are not headline numbers."""
from office.media import draw_scene, scene_content


def test_numbers_in_picture_instructions_do_not_become_a_number_box():
    scene = {"caption": "긴 답변보다 먼저 분류", "narration": "문의가 쌓일 때 먼저 필요한 건 긴 답변이 아니에요.", "visual": "문의 1건, 분류 우선 흐름"}
    content = scene_content(scene)
    assert content["kind"] != "number" and content["numbers"] == []
    asked = scene_content({"caption": "요금", "narration": "x", "visual": "숫자 강조: 0.10달러"})
    assert asked["kind"] == "number"
