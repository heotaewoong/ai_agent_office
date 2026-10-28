import json
import math
from pathlib import Path
import struct
import wave

import pytest

from office.store import Store, WorkflowError
from platform_support import requires_ffmpeg, symlink_or_skip


def approved_job(tmp_path, *, blog=True, video=True, cards=False, pdf=False):
    store = Store(tmp_path / "state")
    job = store.create_job({"id": "fixture-article", "title": "합성 자료 기능 검증", "url": "https://example.com/research"})
    packet = {
        "title": "합성 자료 기능 검증", "body": "## 핵심 설명\n\n이 자료는 실제 뉴스가 아닌 승인된 기능 검증용 예제입니다.",
        "evidence": [{"id": "E1", "url": "https://example.com/research", "claim": "합성 테스트 근거"}],
        "quality": {"status": "passed", "critical": []},
        "video": {"title": "승인과 제작의 흐름", "description": "합성 자료 기능 검증", "tags": ["기능검증"], "scenes": [
            {"narration": "먼저 근거를 확인합니다.", "caption": "근거를 확인", "visual": "flow"},
            {"narration": "승인한 원고로 제작합니다.", "caption": "승인 후 제작", "visual": "comparison"},
        ]},
    }
    job = store.save_source(job["id"], packet)
    selections = {"blog": blog, "video": video, "pdf": pdf, "cards": cards}
    store.review_source(job["id"], job["source_hash"], "approved", "검증 운영자", selections)
    return store, job["id"]


def tone_renderer(seconds=.65):
    def render(text, out_path):
        with wave.open(str(out_path), "wb") as audio:
            audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(16000)
            audio.writeframes(b"".join(struct.pack("<h", int(6000 * math.sin(2 * math.pi * 440 * i / 16000))) for i in range(int(16000 * seconds))))
        return {"voice": "test-tone-not-speech", "provider": "test", "disclosure": "테스트 톤이며 합성 음성이 아닙니다."}
    render.cache_key = f"test-tone-{seconds}"
    return render


def test_production_refuses_unapproved_before_any_artifact(tmp_path):
    from office.media import produce
    store = Store(tmp_path / "state")
    job = store.create_job({"id": "unapproved", "title": "미승인"})
    with pytest.raises(WorkflowError, match="승인"):
        produce(store, job["id"])
    assert list(store.artifacts.iterdir()) == []


@requires_ffmpeg
def test_real_mp4_subtitles_thumbnails_and_manifest_are_bound_to_source(tmp_path):
    from office.media import produce, probe
    from PIL import Image
    store, job_id = approved_job(tmp_path, cards=True, pdf=True)
    manifest = produce(store, job_id, voice_renderer=tone_renderer())
    files = {x["name"]: store.artifacts / x["path"] for x in manifest["files"]}
    info = probe(files["short.mp4"])
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (video["width"], video["height"]) == (1080, 1920)
    assert any(s["codec_type"] == "audio" for s in info["streams"])
    assert 1.2 < float(info["format"]["duration"]) < 2
    assert "00:00:00,650 --> 00:00:01,300" in files["captions.srt"].read_text(encoding="utf-8")
    assert len(manifest["thumbnail_candidates"]) == 5
    for item in manifest["thumbnail_candidates"]:
        with Image.open(store.artifacts / item["path"]) as image:
            assert image.size == (1280, 720)
    assert manifest["source_hash"] == store.job(job_id)["source_hash"]
    assert store.job(job_id)["manifest"]["hash"] == manifest["hash"]
    assert all(f["url"] == "/api/artifacts/" + f["id"] for f in manifest["files"])


@requires_ffmpeg
def test_failed_scene_retains_successful_voice_for_retry(tmp_path):
    from office.media import produce
    store, job_id = approved_job(tmp_path, blog=False)
    renderer = tone_renderer()
    def broken(text, out_path):
        if "승인한" in text: raise WorkflowError("음성 일시 실패")
        return renderer(text, out_path)
    broken.cache_key = renderer.cache_key
    with pytest.raises(WorkflowError, match="음성"):
        produce(store, job_id, voice_renderer=broken)
    first_audio = list(store.artifacts.rglob("voice-*.wav"))
    assert len(first_audio) == 1
    before = first_audio[0].stat().st_mtime_ns
    result = produce(store, job_id, voice_renderer=renderer)
    assert result["media"]["duration"] > 0
    assert first_audio[0].stat().st_mtime_ns == before


def test_blog_can_be_released_independently_when_selected_video_fails(tmp_path, monkeypatch):
    from office import media
    store, job_id = approved_job(tmp_path)
    def unavailable(*args, **kwargs):
        raise WorkflowError('음성 결과 확인이 필요합니다')
    monkeypatch.setattr(media, 'render_short', unavailable)
    result = media.produce(store, job_id, voice_renderer=tone_renderer())
    assert result['completed_outputs'] == ['blog']
    assert result['output_status']['video']['state'] == 'failed'
    assert {row['name'] for row in result['files']} == {'tistory.md', 'tistory.html', 'naver.txt', 'asset-rights.json'}
    assert all(row.get('outputs') for row in result['files'])
    with pytest.raises(WorkflowError, match='완료.*제작물|미완료'):
        store.review_release(job_id, result['hash'], 'approved', 'fixture-operator')
    job = store.review_release(job_id, result['hash'], 'approved', 'fixture-operator', outputs=['blog'])
    assert job['release_approval']['outputs'] == ['blog']
    assert job['source_approval']['selections']['video'] is True


def test_retry_keeps_verified_successful_blog_when_other_output_is_retried(tmp_path, monkeypatch):
    from office import media
    store, job_id = approved_job(tmp_path, video=False, cards=True)
    first = media.produce(store, job_id)
    def must_reuse(*args):
        raise WorkflowError('성공한 글을 다시 생성하지 않아야 합니다')
    monkeypatch.setattr(media, 'write_blog_exports', must_reuse)
    second = media.produce(store, job_id)
    assert second['completed_outputs'] == first['completed_outputs'] == ['blog', 'cards']
    assert {r['path'] for r in second['files'] if 'blog' in r['outputs']} == {r['path'] for r in first['files'] if 'blog' in r['outputs']}


def test_missing_font_blocks_visual_output_but_keeps_independent_blog(tmp_path, monkeypatch):
    from office import media
    store, job_id = approved_job(tmp_path, video=False, cards=True)
    def unavailable():
        raise WorkflowError('한국어 폰트가 없습니다')
    monkeypatch.setattr(media, 'korean_font', unavailable)
    result = media.produce(store, job_id)
    assert result['completed_outputs'] == ['blog']
    assert result['output_status']['cards']['state'] == 'failed'



@requires_ffmpeg
def test_voice_over_sixty_seconds_blocks_without_cutting_or_losing_cache(tmp_path):
    from office.media import produce
    store, job_id = approved_job(tmp_path, blog=False)
    with pytest.raises(WorkflowError, match="60초"):
        produce(store, job_id, voice_renderer=tone_renderer(31))
    assert len(list(store.artifacts.rglob("voice-*.wav"))) == 2
    assert not list(store.artifacts.rglob("short.mp4"))
    assert store.job(job_id)["manifest"] is None


def test_source_change_during_voice_cannot_save_old_manifest(tmp_path):
    from office.media import produce
    store, job_id = approved_job(tmp_path)
    renderer = tone_renderer()
    def changing(text, out_path):
        meta = renderer(text, out_path)
        packet = store.job(job_id)["source_packet"]
        packet["body"] += "\n\n새 근거가 추가되었습니다."
        store.save_source(job_id, packet)
        return meta
    changing.cache_key = "changed-source-test"
    with pytest.raises(WorkflowError, match="변경|승인"):
        produce(store, job_id, voice_renderer=changing)
    assert store.job(job_id)["manifest"] is None


def test_unchanged_source_produces_same_manifest_on_rerun(tmp_path):
    from office.media import produce
    store, job_id = approved_job(tmp_path, video=False, pdf=True)
    first = produce(store, job_id)
    second = produce(store, job_id)
    assert first["hash"] == second["hash"]


def test_new_renderer_preserves_old_artifacts_and_reuses_successful_voice(tmp_path, monkeypatch):
    from office import media
    store, job_id = approved_job(tmp_path)
    renderer = tone_renderer()
    first = media.produce(store, job_id, voice_renderer=renderer)
    old_files = [(store.artifacts / row["path"], row["sha256"]) for row in first["files"]]
    voices = {path: path.stat().st_mtime_ns for path, _ in old_files if path.suffix == ".wav"}
    monkeypatch.setattr(media, "RENDER_VERSION", "test-new-render-contract")
    second = media.produce(store, job_id, voice_renderer=renderer)
    assert second["production_contract"] != first["production_contract"]
    assert second["hash"] != first["hash"]
    assert all(path.is_file() and media.file_hash(path) == sha for path, sha in old_files)
    assert all(path.stat().st_mtime_ns == written for path, written in voices.items())
    assert {row["path"] for row in first["files"] if row["name"] == "short.mp4"}.isdisjoint(
        row["path"] for row in second["files"] if row["name"] == "short.mp4")


def test_font_bytes_and_explicit_voice_configuration_change_production_contract(tmp_path, monkeypatch):
    from office import media
    font = tmp_path / "font.ttf"
    font.write_bytes(b"test-font-first")
    monkeypatch.setattr(media, "korean_font", lambda: font)
    first = media.production_contract(tone_renderer(.65), {"blog": True, "video": True})
    font.write_bytes(b"test-font-second")
    second = media.production_contract(tone_renderer(.65), {"blog": True, "video": True})
    third = media.production_contract(tone_renderer(.8), {"blog": True, "video": True})
    assert first["hash"] != second["hash"] != third["hash"]


@requires_ffmpeg
def test_reapproved_source_reuses_same_speech_input_without_repeating_renderer(tmp_path):
    from office import media
    store, job_id = approved_job(tmp_path)
    first_renderer = tone_renderer()
    first_renderer.cache_key = 'full-authority-version-one'
    first_renderer.asset_cache_key = 'actual-speech-config-unchanged'
    first = media.produce(store, job_id, voice_renderer=first_renderer)
    speech = {row['path']: (store.artifacts / row['path']).stat().st_mtime_ns for row in first['files'] if row['name'].endswith('.wav')}
    packet = store.job(job_id)['source_packet']
    packet['body'] += '\n\n새 출처 설명만 보완했습니다.'
    job = store.save_source(job_id, packet)
    store.review_source(job_id, job['source_hash'], 'approved', 'fixture-operator')
    def no_new_speech(text, path):
        raise AssertionError('동일 음성 입력을 재생성하면 안 됩니다')
    no_new_speech.cache_key = 'full-authority-version-two'
    no_new_speech.asset_cache_key = first_renderer.asset_cache_key
    second = media.produce(store, job_id, voice_renderer=no_new_speech)
    assert second['source_hash'] != first['source_hash']
    assert second['completed_outputs'] == ['blog', 'video']
    assert all((store.artifacts / path).stat().st_mtime_ns == written for path, written in speech.items())


def test_unavailable_korean_voice_does_not_return_fake_success(tmp_path, monkeypatch):
    from office import media
    def unavailable(script):
        raise WorkflowError("ko-KR unavailable")
    monkeypatch.setattr(media, "powershell", unavailable)
    with pytest.raises(WorkflowError, match="한국어 음성"):
        media.local_voice("음성 검증", tmp_path / "speech.wav")
    assert not (tmp_path / "speech.wav").exists()


def test_artifact_folder_symlink_cannot_escape_root(tmp_path):
    from office.media import produce
    store, job_id = approved_job(tmp_path, video=False)
    outside = tmp_path / "outside"; outside.mkdir()
    symlink_or_skip(store.artifacts / job_id, outside, target_is_directory=True)
    with pytest.raises(WorkflowError, match="경로"):
        produce(store, job_id)
    assert list(outside.iterdir()) == []


def test_korean_caption_wrap_keeps_words_together_and_contains_long_tokens():
    from PIL import Image, ImageDraw, ImageFont
    from office.media import wrap_text
    from office.exports import korean_font
    draw = ImageDraw.Draw(Image.new("RGB", (500, 500)))
    font = ImageFont.truetype(str(korean_font()), 40)
    width = draw.textlength("확인한 사실과 추가 질문", font=font) + 1
    assert wrap_text(draw, "확인한 사실과 추가 질문 비교", font, width) == ["확인한 사실과 추가 질문", "비교"]
    long_token = "아주긴하나의단어가화면바깥으로넘치지않아야합니다"
    lines = wrap_text(draw, long_token, font, 160)
    assert "".join(lines) == long_token
    assert all(draw.textlength(line, font=font) <= 160 for line in lines)


def test_interrupted_production_lock_does_not_block_restart(tmp_path):
    from office.media import produce
    store, job_id = approved_job(tmp_path, video=False)
    folder = store.artifacts / job_id / store.job(job_id)["source_hash"]
    folder.mkdir(parents=True)
    (folder / ".production.lock").write_text("999999999", encoding="utf-8")
    result = produce(store, job_id)
    assert any(item["name"] == "tistory.html" for item in result["files"])


def test_concurrent_production_on_same_source_is_rejected(tmp_path):
    from office.media import produce, production_lock
    store, job_id = approved_job(tmp_path, video=False)
    folder = store.artifacts / job_id / store.job(job_id)["source_hash"]
    folder.mkdir(parents=True)
    with production_lock(folder):
        with pytest.raises(WorkflowError, match="제작"):
            produce(store, job_id)
    assert store.job(job_id)["manifest"] is None


@requires_ffmpeg
def test_silent_audio_is_rejected_instead_of_becoming_a_successful_video(tmp_path):
    from office.media import produce
    store, job_id = approved_job(tmp_path, blog=False)
    def silent(text, out_path):
        with wave.open(str(out_path), "wb") as audio:
            audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(16000)
            audio.writeframes(bytes(32000))
        return {"voice": "broken-silent-provider", "provider": "test"}
    silent.cache_key = "silent-fixture"
    with pytest.raises(WorkflowError, match="무음"):
        produce(store, job_id, voice_renderer=silent)
    assert store.job(job_id)["manifest"] is None
    assert not list(store.artifacts.rglob("voice-*.wav"))


def test_scene_uses_explicit_news_steps_and_real_numeric_facts():
    from office.media import scene_content
    flow = scene_content({"caption": "AI 검토 절차", "narration": "자료를 수집해 분석하고 사람이 확인합니다.", "visual": "flow: 자료 수집 → AI 분석 → 사람 확인"}, 4)
    assert flow["kind"] == "flow"
    assert flow["steps"] == ["자료 수집", "AI 분석", "사람 확인"]
    numeric = scene_content({"caption": "검토 시간 30% 감소", "narration": "이 실험에서는 검토 시간이 30% 줄었습니다.", "visual": "number"}, 7)
    assert numeric["numbers"][0]["value"] == "30%"
    assert numeric["kind"] == "number"
    absent = scene_content({"caption": "검증 범위가 중요", "narration": "추가 검증이 필요합니다.", "visual": "큰 숫자 강조"}, 7)
    assert absent["kind"] == "explanation"
    assert absent["numbers"] == []


def test_comparison_uses_actual_pair_and_never_invents_before_after_labels():
    from office.media import scene_content
    content = scene_content({"caption": "수동 입력과 자동 정리 비교", "narration": "수동 입력과 자동 정리를 비교했습니다.", "visual": "comparison: 수동 입력 vs 자동 정리"}, 0)
    assert content["comparison"] == ["수동 입력", "자동 정리"]
    assert content["kind"] == "comparison"
    no_pair = scene_content({"caption": "검증 필요", "narration": "결론을 내리기 전에 실험 조건을 확인해야 합니다.", "visual": "comparison"}, 1)
    assert no_pair["kind"] == "explanation"
    assert no_pair["comparison"] == []


@requires_ffmpeg
def test_thumbnail_concepts_get_distinct_layouts_local_scores_and_recommendation(tmp_path):
    from office.media import produce
    store, job_id = approved_job(tmp_path)
    packet = store.job(job_id)["source_packet"]
    packet["video"]["thumbnails"] = [
        {"title": "근거를 먼저 확인", "subtitle": "승인과 제작의 흐름", "angle": "핵심 설명"},
        {"title": "승인 후 제작", "subtitle": "근거를 확인합니다", "angle": "비교"},
        {"title": "원고로 제작", "subtitle": "승인한 원고로 제작합니다", "angle": "설명"},
        {"title": "제작의 흐름", "subtitle": "근거 확인 후 원고 승인", "angle": "과정"},
        {"title": "근거와 승인", "subtitle": "합성 자료 기능 검증", "angle": "질문"},
    ]
    job = store.save_source(job_id, packet)
    store.review_source(job_id, job["source_hash"], "approved", "검증 운영자")
    manifest = produce(store, job_id, voice_renderer=tone_renderer())
    candidates = manifest["thumbnail_candidates"]
    assert [c["title"] for c in candidates] == [c["title"] for c in packet["video"]["thumbnails"]]
    assert len({c["layout"] for c in candidates}) == 5
    assert all(set(c["scores"]) == {"readability", "contrast", "title_fit", "source_alignment"} for c in candidates)
    assert all(c["assessment_kind"] == "local_layout_heuristic" and c["selection_reason"] for c in candidates)
    assert all(c["contrast_ratio"] >= 4.5 and not c["text_metrics"]["overflow"] for c in candidates)
    assert manifest["best_candidate_id"] in {c["id"] for c in candidates}
    assert any(f["name"] == "thumbnail-review.json" for f in manifest["files"])


def test_unrelated_thumbnail_claims_get_flagged_without_performance_claims(tmp_path):
    from office.media import thumbnail_concepts, assess_thumbnail
    plan = {"title": "근거와 승인", "description": "근거를 검토한 뒤 승인합니다", "scenes": [{"caption": "원고 승인", "narration": "원고 승인 후 제작합니다", "visual": "explanation"}], "thumbnails": [{"title": "매출 300% 보장", "subtitle": "무조건 합격", "angle": "핵심"}] * 5}
    concept = thumbnail_concepts(plan)[0]
    assessment = assess_thumbnail(plan, concept, {"minimum_font_size": 60, "title_lines": 2, "overflow": False, "truncated": False}, "#ffffff", "#0b152d")
    assert assessment["scores"]["source_alignment"] < 3
    assert any("300%" in warning for warning in assessment["warnings"])
    assert assessment["assessment_kind"] == "local_layout_heuristic"


def test_numeric_scene_ignores_layout_box_counts_and_preserves_decimal_units():
    from office.media import scene_content
    layout = scene_content({"caption": "범위 확인", "narration": "범위를 먼저 확인합니다.", "visual": "number: 3개 박스에 큰 숫자를 배치"}, 2)
    assert layout["numbers"] == [] and layout["kind"] == "explanation"
    decimal = scene_content({"caption": "처리량 1.5배", "narration": "시험 조건에서 처리량은 1.5배입니다.", "visual": "number"})
    assert decimal["numbers"] == [{"value": "1.5배", "context": "처리량 1.5배"}]


def test_old_plan_thumbnail_fallback_keeps_approved_title_and_visible_limits(tmp_path):
    from office.media import draw_thumbnails
    plan = {"title": "승인한 원고로 제작", "description": "출처를 확인하고 승인한 원고로 제작합니다", "scenes": [{"caption": "출처 확인", "narration": "출처를 확인합니다.", "visual": "explanation"}]}
    paths = draw_thumbnails(plan, tmp_path)
    review = json.loads((tmp_path / "thumbnail-review.json").read_text(encoding="utf-8"))
    assert len(paths) == 5
    assert all(item["title"] == "승인한 원고로 제작" for item in review["candidates"])
    assert all(item["human_selection"] == "pending" for item in review["candidates"])
    assert all(item["text_metrics"]["title_font_size"] >= 48 for item in review["candidates"])


@pytest.mark.parametrize(("headline", "expected"), [
    ("광고주 10만, 무엇을 센 걸까", "10만"),
    ("20번 해보니 달랐다", "20번"),
    ("검증의 의미를 확인", "핵심"),
])
def test_thumbnail_spotlight_stays_with_its_headline_when_unrelated_scene_number_changes(tmp_path, headline, expected):
    from copy import deepcopy
    from PIL import Image
    from office.media import draw_thumbnails

    plan = {"title": "공식 발표 해설", "scenes": [{"caption": "지원 26개국 확대", "narration": "지원 범위에 대한 수치입니다.", "visual": "number"}],
            "thumbnails": [{"title": headline, "subtitle": "숫자의 의미를 구분", "angle": "수치 해설"}] * 5}
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir(); second.mkdir()
    draw_thumbnails(plan, first)
    changed = deepcopy(plan)
    changed["scenes"][0]["caption"] = "지원 27개국 확대"
    draw_thumbnails(changed, second)
    with Image.open(first / "thumbnail-03.png") as before, Image.open(second / "thumbnail-03.png") as after:
        # The actual visible spotlight must not change with an unrelated metric.
        assert before.crop((875, 245, 1205, 575)).tobytes() == after.crop((875, 245, 1205, 575)).tobytes()
    review = json.loads((first / "thumbnail-review.json").read_text(encoding="utf-8"))
    assert review["candidates"][2]["spotlight_value"] == expected


def test_scene_numeric_sign_ranges_and_korean_comparison_are_not_distorted():
    from office.media import scene_content
    numeric = scene_content({"caption": "오류율 -30%, 개선 범위 10~20%", "narration": "합성 예제의 범위입니다.", "visual": "number"})
    assert [fact["value"] for fact in numeric["numbers"]] == ["-30%", "10~20%"]
    compared = scene_content({"caption": "수동 입력과 자동 정리 비교", "narration": "두 방식을 비교합니다.", "visual": "좌우 비교"})
    assert compared["comparison"] == ["수동 입력", "자동 정리"]


def test_numeric_units_are_preserved_without_relabeling_months_as_item_counts():
    from office.media import scene_content
    months = scene_content({"caption": "검증 기간 3개월", "narration": "기간을 확인합니다.", "visual": "number"})
    assert months["numbers"][0]["value"] == "3개월"
    tokens = scene_content({"caption": "문맥 범위 100만 토큰", "narration": "합성 예제입니다.", "visual": "number"})
    assert tokens["numbers"][0]["value"] == "100만토큰"


def test_long_video_title_uses_first_approved_short_concept_not_vague_shortest():
    from office.media import approved_display_title
    plan = {"title": "아주 긴 뉴스 제목입니다. " * 5, "thumbnails": [{"title": "한국어 평가의 검증 범위"}, {"title": "무슨 변화?"}]}
    assert approved_display_title(plan) == "한국어 평가의 검증 범위"


def test_approved_three_way_visual_comparison_survives_phonetic_narration():
    from office.media import scene_content
    scene = {"caption": "조건 판단 · 선택지 · 점수",
             "narration": "오픈에이아이의 디시전스 에이피아이는 조건 판단, 선택지, 점수를 반환합니다.",
             "visual": "comparison: 조건에 해당? / 어떤 선택? / 정한 척도는?"}
    content = scene_content(scene)
    assert content["kind"] == "comparison"
    assert content["comparison"] == ["조건에 해당?", "어떤 선택?", "정한 척도는?"]
    assert scene["narration"] not in content["key_phrases"]


def test_explanation_display_uses_approved_visual_not_speech_pronunciation():
    from office.media import scene_content
    content = scene_content({"caption": "오류와 검토 비용 확인", "narration": "디시전스 에이피아이의 오류를 확인합니다.",
                             "visual": "explanation: 회사 발표 / 업무별 정확도 별도 검증"})
    assert content["key_phrases"] == ["회사 발표", "업무별 정확도 별도 검증"]
    fallback = scene_content({"caption": "검증 범위 확인", "narration": "발음 전용 문장", "visual": "explanation"})
    assert fallback["key_phrases"] == ["검증 범위 확인"]


def test_actual_scene_image_does_not_display_phonetic_narration_or_repeat_global_title(tmp_path):
    from office.media import draw_scene
    scene = {"caption": "조건 판단 · 선택지 · 점수", "narration": "디시전스 에이피아이 발음 전용",
             "visual": "comparison: 조건에 해당? / 어떤 선택? / 정한 척도는?"}
    first, second = tmp_path / "first.png", tmp_path / "second.png"
    draw_scene({"title": "모든 장면에 반복되던 긴 전체 제목"}, scene, 1, 5, first)
    draw_scene({"title": "다른 전체 제목"}, {**scene, "narration": "표시하면 안 되는 다른 발음 문장"}, 1, 5, second)
    assert first.read_bytes() == second.read_bytes()
    metadata = json.loads(first.with_suffix('.json').read_text(encoding="utf-8"))
    assert metadata['title_metrics']['displayed_text'] == "조건 판단 · 선택지 · 점수"
    assert len(metadata['comparison_metrics']) == 3
    assert all(not item['truncated'] and not item['overflow'] for item in metadata['comparison_metrics'])


def test_numeric_scene_draws_every_approved_metric_inside_the_frame(tmp_path):
    from office.media import draw_scene
    path = tmp_path / 'numbers.png'
    draw_scene({'title': '실험 결과'}, {'caption': '과제 507개 · 평가 20회 · 학습 50단계',
               'narration': '발음 전용 문장', 'visual': 'number: 507개 / 20회 / 50단계'}, 0, 1, path)
    content = json.loads(path.with_suffix('.json').read_text(encoding="utf-8"))
    assert [item['value'] for item in content['numbers']] == ['507개', '20회', '50단계']
    assert len(content['number_metrics']) == 3
    assert all(not item['truncated'] and not item['overflow'] for item in content['number_metrics'])


def test_numeric_scene_keeps_the_approved_price_with_its_currency():
    from office.media import scene_content
    content = scene_content({'caption': '입력 100만 토큰당 $0.10 · 조건 별도',
                             'narration': '미캐시 입력 100만 토큰에 영 점 일 달러.', 'visual': 'number'})
    assert [item['value'] for item in content['numbers']] == ['100만토큰', '$0.10']


def test_windows_voice_temp_path_is_only_accepted_on_windows():
    from office.media import windows_local_path
    assert windows_local_path("C:\Temp\hb-office-x\speech.wav", platform="nt") == Path("C:\Temp\hb-office-x\speech.wav")
    with pytest.raises(WorkflowError, match="Windows"):
        windows_local_path("C:\Temp\hb-office-x\speech.wav", platform="posix")


def background_renderer(color='#7a2e1e'):
    from PIL import Image
    calls = []

    def render(scene_index, out_path):
        calls.append(scene_index)
        Image.new('RGB', (64, 96), color).save(out_path, 'PNG')
        return {'provider': 'test-background', 'model': 'fake-image', 'disclosure': '테스트 배경'}
    render.cache_key = 'test-background-' + color
    render.asset_cache_key = 'test-background-asset-' + color
    render.calls = calls
    return render


def test_scene_with_background_composites_full_frame_and_records_source(tmp_path):
    from office.media import draw_scene
    from PIL import Image
    scene = {'caption': '배경 합성 확인', 'narration': '발음 전용', 'visual': '설명: 배경 위 글자'}
    plain, backed, background = tmp_path / 'plain.png', tmp_path / 'backed.png', tmp_path / 'bg.png'
    Image.new('RGB', (64, 96), '#7a2e1e').save(background, 'PNG')
    draw_scene({'title': '제목'}, scene, 0, 1, plain)
    draw_scene({'title': '제목'}, scene, 0, 1, backed, background=background)
    assert Image.open(backed).size == (1080, 1920)
    assert plain.read_bytes() != backed.read_bytes()
    # The generated background shows through where no text panel is drawn.
    pixel = Image.open(backed).convert('RGB').getpixel((1040, 1500))
    assert pixel[0] > pixel[2], pixel
    metadata = json.loads(backed.with_suffix('.json').read_text(encoding='utf-8'))
    assert metadata['drawing_source'] == 'generated_background+approved_scene_fields'
    assert len(metadata['background_sha256']) == 64
    plain_meta = json.loads(plain.with_suffix('.json').read_text(encoding='utf-8'))
    assert plain_meta['drawing_source'] == 'approved_scene_fields' and 'background_sha256' not in plain_meta


def test_background_renderer_changes_production_contract_deterministically(tmp_path):
    from office import media
    selections = {'blog': True, 'video': False, 'cards': True, 'pdf': False}
    without = media.production_contract(None, selections)
    with_bg = media.production_contract(None, selections, image_renderer=background_renderer())
    again = media.production_contract(None, selections, image_renderer=background_renderer())
    other = media.production_contract(None, selections, image_renderer=background_renderer('#112233'))
    assert without['hash'] != with_bg['hash'] == again['hash'] != other['hash']
    assert with_bg['background'] == 'test-background-#7a2e1e' and without['background'] is None
    assert media.production_contract(None, {'blog': True})['background'] is None


def test_cards_use_background_renderer_per_scene_and_manifest_discloses_it(tmp_path):
    from office.media import produce
    from PIL import Image
    store, job_id = approved_job(tmp_path, blog=False, video=False, cards=True)
    renderer = background_renderer()
    manifest = produce(store, job_id, background_renderer=renderer)
    assert renderer.calls == [0, 1]
    files = {x['name']: store.artifacts / x['path'] for x in manifest['files']}
    assert Image.open(files['scene-01.png']).size == (1080, 1920)
    scene_meta = json.loads(files['scene-01.json'].read_text(encoding='utf-8'))
    assert scene_meta['background_provider'] == 'test-background'
    assert manifest['production_contract']['background'] == 'test-background-#7a2e1e'
    assert manifest['background'] == {'provider': 'test-background', 'model': 'fake-image', 'disclosure': '테스트 배경', 'scenes': 2}


def test_background_failure_fails_only_visual_output_and_keeps_blog(tmp_path):
    from office.media import produce
    store, job_id = approved_job(tmp_path, blog=True, video=False, cards=True)

    def failing(scene_index, out_path):
        raise WorkflowError('OPENAI_API_KEY가 설정되지 않았습니다')
    failing.cache_key = failing.asset_cache_key = 'failing-background'
    manifest = produce(store, job_id, background_renderer=failing)
    assert manifest['output_status']['blog']['state'] == 'completed'
    assert manifest['output_status']['cards']['state'] == 'failed'
    assert 'OPENAI_API_KEY' in manifest['output_status']['cards']['error']
    assert 'background' not in manifest


def test_overlay_only_scene_is_transparent_outside_text_panels(tmp_path):
    from office.media import draw_scene
    from PIL import Image
    scene = {'caption': '오버레이 확인', 'narration': '발음 전용', 'visual': '설명: 글자만 겹침'}
    path = tmp_path / 'overlay.png'
    draw_scene({'title': '제목'}, scene, 0, 1, path, overlay_only=True)
    image = Image.open(path)
    assert image.mode == 'RGBA' and image.size == (1080, 1920)
    assert image.getpixel((1040, 1500))[3] == 0
    assert image.getpixel((300, 280))[3] > 0
    assert image.getpixel((300, 700))[3] == 255
    meta = json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
    assert meta['drawing_source'] == 'overlay_only+approved_scene_fields'


def test_clip_command_loops_generated_clip_under_overlay_for_voice_duration(tmp_path):
    from office.media import clip_command
    args = [str(a) for a in clip_command(tmp_path / 'gen.mp4', tmp_path / 'overlay.png', tmp_path / 'voice.wav', 3.25, tmp_path / 'clip-02.mp4')]
    assert args[0].endswith('ffmpeg') or args[0].endswith('ffmpeg.exe') or args[0] == 'ffmpeg'
    assert '-stream_loop' in args and args[args.index('-stream_loop') + 1] == '-1'
    assert str(tmp_path / 'gen.mp4') in args and str(tmp_path / 'overlay.png') in args and str(tmp_path / 'voice.wav') in args
    graph = args[args.index('-filter_complex') + 1]
    assert 'scale=1080:1920:force_original_aspect_ratio=increase' in graph and 'crop=1080:1920' in graph and 'overlay=0:0' in graph
    assert args[args.index('-t') + 1] == '3.25'
    assert args[-1] == str(tmp_path / 'clip-02.mp4')


def test_clip_renderer_changes_production_contract_only_for_video(tmp_path):
    from office import media

    def clips(scene_index, image_path, out_path):
        raise AssertionError('must not be called by the contract')
    clips.cache_key = 'runway-clip:test'
    clips.asset_cache_key = 'runway-clip-asset:test'
    video = {'blog': True, 'video': True, 'cards': False, 'pdf': False}
    cards = {'blog': True, 'video': False, 'cards': True, 'pdf': False}
    assert media.production_contract(None, video)['hash'] != media.production_contract(None, video, clip_renderer=clips)['hash']
    assert media.production_contract(None, video, clip_renderer=clips)['clip'] == 'runway-clip:test'
    assert media.production_contract(None, cards, clip_renderer=clips)['hash'] == media.production_contract(None, cards)['hash']
    assert media.production_contract(None, cards, clip_renderer=clips)['clip'] is None


def test_generated_clip_requires_background_before_any_paid_call(tmp_path):
    from office.media import scene_clip

    def clips(scene_index, image_path, out_path):
        raise AssertionError('must not be called without a background')
    clips.generated_scenes = [1]
    with pytest.raises(WorkflowError, match='배경'):
        scene_clip(clips, tmp_path, 1, None)
    assert scene_clip(clips, tmp_path, 0, None) == (None, None)
    assert scene_clip(None, tmp_path, 1, tmp_path / 'bg.png') == (None, None)
