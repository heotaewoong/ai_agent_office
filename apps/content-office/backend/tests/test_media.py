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


def cache_social_cards(store, job_id):
    from PIL import Image
    from office.quiz import artifact_record
    root=store.artifacts; job=store.job(job_id); slides=[]
    for n in range(7):
        path=root/f'card-{n+1:02}.png'
        Image.new('RGB',(1080,1350),(n*30,60,90)).save(path)
        slides.append({'artifact':artifact_record(root,path),'index':n+1})
    store.update_job(job_id,cards={'source_hash':job['source_hash'],'slides':slides,'checks':{'passed':True,'issues':[]},'images':[]})


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
    cache_social_cards(store,job_id)
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
    assert {row['name'] for row in result['files']} == {'tistory.md', 'tistory.html', 'naver.txt', 'asset-rights.json', 'channel-handoff.json', 'x-main.txt', 'threads-main.txt', 'linkedin-personal.txt', 'instagram-main-caption.txt', 'instagram-english-caption.txt'}
    assert all('blog' in row['outputs'] for row in result['files'] if row['name'].endswith('-caption.txt') or row['name'] == 'channel-handoff.json')
    assert all(row.get('outputs') for row in result['files'])
    with pytest.raises(WorkflowError, match='완료.*제작물|미완료'):
        store.review_release(job_id, result['hash'], 'approved', 'fixture-operator')
    job = store.review_release(job_id, result['hash'], 'approved', 'fixture-operator', outputs=['blog'])
    assert job['release_approval']['outputs'] == ['blog']
    assert job['source_approval']['selections']['video'] is True


def test_retry_keeps_verified_successful_blog_when_other_output_is_retried(tmp_path, monkeypatch):
    from office import media
    store, job_id = approved_job(tmp_path, video=False, cards=True)
    cache_social_cards(store,job_id)
    first = media.produce(store, job_id)
    def must_reuse(*args):
        raise WorkflowError('성공한 글을 다시 생성하지 않아야 합니다')
    monkeypatch.setattr(media, 'write_blog_exports', must_reuse)
    second = media.produce(store, job_id)
    assert second['completed_outputs'] == first['completed_outputs'] == ['blog', 'cards']
    assert {r['path'] for r in second['files'] if 'blog' in r['outputs']} == {r['path'] for r in first['files'] if 'blog' in r['outputs']}


def test_new_checked_card_revision_changes_manifest_without_overwriting_old_files(tmp_path,monkeypatch):
    from PIL import Image
    from office.quiz import artifact_record
    from office import media
    store,job_id=approved_job(tmp_path,video=False,cards=True)
    cache_social_cards(store,job_id)
    first=media.produce(store,job_id)
    old={r['path']:(store.artifacts/r['path']).read_bytes() for r in first['files'] if 'cards' in r['outputs']}
    folder=store.artifacts/'cards-v2';folder.mkdir();slides=[]
    for i in range(7):
        path=folder/f'card-{i+1:02}.png';Image.new('RGB',(1080,1350),(i*30+1,80,100)).save(path)
        slides.append({'artifact':artifact_record(store.artifacts,path),'index':i+1})
    store.update_job(job_id,cards={'source_hash':first['source_hash'],'slides':slides,'checks':{'passed':True,'issues':[]},'version':2})
    monkeypatch.setattr(media,'write_blog_exports',lambda *a:pytest.fail('성공한 글은 재사용해야 합니다'))
    second=media.produce(store,job_id)
    assert second['hash']!=first['hash'] and second['completed_outputs']==['blog','cards']
    assert all((store.artifacts/path).read_bytes()==data for path,data in old.items())


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
    assert windows_local_path(r"C:\Temp\hb-office-x\speech.wav", platform="nt") == Path(r"C:\Temp\hb-office-x\speech.wav")
    with pytest.raises(WorkflowError, match="Windows"):
        windows_local_path(r"C:\Temp\hb-office-x\speech.wav", platform="posix")


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


def test_production_exports_checked_social_cards_without_regenerating_backgrounds(tmp_path):
    from office.media import produce
    from PIL import Image
    store, job_id = approved_job(tmp_path, blog=False, video=False, cards=True)
    cache_social_cards(store,job_id)
    renderer = background_renderer()
    manifest = produce(store, job_id, background_renderer=renderer)
    assert renderer.calls == []
    files = {x['name']: store.artifacts / x['path'] for x in manifest['files']}
    assert Image.open(files['card-01.png']).size == (1080,1350)
    assert len([n for n in files if n.startswith('card-') and n.endswith('.png')])==7
    assert any(n.startswith('card-news-') and n.endswith('.json') for n in files)
    assert manifest['completed_outputs']==['cards']


def test_social_card_planning_failure_preserves_independent_blog(tmp_path,monkeypatch):
    from office.media import produce
    store, job_id = approved_job(tmp_path, blog=True, video=False, cards=True)
    def unavailable(*args,**kwargs):raise WorkflowError('카드 계획 도구 연결이 필요합니다')
    monkeypatch.setattr('office.cards.plan_cards',unavailable)
    manifest=produce(store,job_id)
    assert manifest['output_status']['blog']['state']=='completed'
    assert manifest['output_status']['cards']['state']=='failed'
    assert '계획 도구' in manifest['output_status']['cards']['error']


def test_overlay_only_scene_is_a_footage_layer_transparent_where_the_clip_shows(tmp_path):
    from office.media import draw_scene
    from PIL import Image
    scene = {'caption': '오버레이 확인', 'narration': '발음 전용', 'visual': '설명: 글자만 겹침'}
    path = tmp_path / 'overlay.png'
    draw_scene({'title': '제목'}, scene, 0, 1, path, overlay_only=True)
    image = Image.open(path)
    assert image.mode == 'RGBA' and image.size == (1080, 1920)
    # The clip shows through the middle; the top and bottom only get a soft dark gradient.
    assert image.getpixel((540, 1000))[3] == 0
    assert 0 < image.getpixel((540, 20))[3] < 255 and 0 < image.getpixel((540, 1900))[3] < 255
    # The caption is drawn opaque near the top third, never as a full-width opaque slide panel.
    caption = image.crop((70, 280, 1010, 680))
    assert caption.getchannel('A').getextrema()[1] == 255
    for y in range(560, 1620, 20):
        row = [image.getpixel((x, y))[3] for x in range(60, 1020, 8)]
        assert sum(alpha == 255 for alpha in row) < len(row) * .6, y
    meta = json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
    assert meta['drawing_source'] == 'overlay_only+approved_scene_fields' and meta['layout'] == 'footage_overlay'


def photo(tmp_path, color=(200, 40, 40), name='photo.png'):
    from PIL import Image
    path = tmp_path / name
    Image.new('RGB', (1024, 1536), color).save(path, 'PNG')
    return path


def test_photo_scene_is_full_bleed_with_outlined_caption_and_translucent_lower_third(tmp_path):
    from office.media import draw_scene
    from PIL import Image
    background = photo(tmp_path)
    flow = {'caption': '근거를 확인하고 승인', 'narration': '발음 전용', 'visual': 'flow: 근거 확인 → 원고 승인 → 제작'}
    path = tmp_path / 'scene.png'
    draw_scene({'title': '제목'}, flow, 0, 3, path, background=background)
    image = Image.open(path).convert('RGB')
    # Middle of the frame is the untouched photograph, not a navy blend.
    assert image.getpixel((540, 1000)) == (200, 40, 40)
    assert image.getpixel((200, 900)) == (200, 40, 40)
    # A dark outline surrounds the white headline.
    darkest, brightest = image.crop((70, 280, 1010, 680)).convert('L').getextrema()
    assert brightest > 235, 'white caption glyphs'
    # The photo under the top gradient never gets this dark; only the glyph outline does.
    assert darkest < 30, 'dark outline around glyphs'
    meta = json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
    assert meta['layout'] == 'footage_overlay' and meta['title_metrics']['stroke_width'] > 0
    assert meta['drawing_source'] == 'generated_background+approved_scene_fields'
    assert meta['kind'] == 'flow' and meta['lower_third']['box'][3] <= 1610
    top, bottom = meta['lower_third']['box'][1], meta['lower_third']['box'][3]
    assert bottom - top <= 520
    # The lower third is translucent: the photo still tints it.
    r, g, b = image.getpixel((72, top + 14))
    assert r > b and (r, g, b) != (200, 40, 40)


def test_photo_scene_keeps_metric_metadata_for_comparison_and_numbers(tmp_path):
    from office.media import draw_scene
    background = photo(tmp_path)
    comparison = tmp_path / 'comparison.png'
    draw_scene({'title': '제목'}, {'caption': '조건 판단 · 선택지 · 점수', 'narration': '발음',
               'visual': 'comparison: 조건에 해당? / 어떤 선택? / 정한 척도는?'}, 1, 5, comparison, background=background)
    meta = json.loads(comparison.with_suffix('.json').read_text(encoding='utf-8'))
    # The larger footage headline may wrap; the approved caption text itself is unchanged.
    assert ' '.join(meta['title_metrics']['displayed_text'].split()) == '조건 판단 · 선택지 · 점수'
    assert len(meta['comparison_metrics']) == 3
    numbers = tmp_path / 'numbers.png'
    draw_scene({'title': '제목'}, {'caption': '과제 507개 · 평가 20회 · 학습 50단계', 'narration': '발음',
               'visual': 'number: 507개 / 20회 / 50단계'}, 0, 1, numbers, background=background)
    meta = json.loads(numbers.with_suffix('.json').read_text(encoding='utf-8'))
    assert len(meta['number_metrics']) == 3 and all(not m['overflow'] for m in meta['number_metrics'])
    explanation = tmp_path / 'explanation.png'
    draw_scene({'title': '제목'}, {'caption': '한 줄 설명', 'narration': '발음', 'visual': '노트북 앞의 손'}, 0, 1, explanation, background=background)
    meta = json.loads(explanation.with_suffix('.json').read_text(encoding='utf-8'))
    assert meta['kind'] == 'explanation' and meta['lower_third'] is None


def test_still_photo_scene_moves_with_ken_burns_under_a_static_text_layer(tmp_path):
    from office.media import still_motion_command
    args = [str(a) for a in still_motion_command(tmp_path / 'bg.png', tmp_path / 'overlay.png', tmp_path / 'voice.wav', 4.0, tmp_path / 'clip-01.mp4', 1)]
    assert args[args.index('-loop') + 1] == '1' and str(tmp_path / 'bg.png') in args and str(tmp_path / 'overlay.png') in args
    graph = args[args.index('-filter_complex') + 1]
    assert 'zoompan=' in graph and 's=1080x1920' in graph and 'overlay=0:0' in graph
    assert '/96' in graph  # the move spans the whole 4 s scene at 24 fps, not 3 s then a freeze
    other = [str(a) for a in still_motion_command(tmp_path / 'bg.png', tmp_path / 'overlay.png', tmp_path / 'voice.wav', 4.0, tmp_path / 'clip-02.mp4', 2)]
    assert other[other.index('-filter_complex') + 1] != graph
    assert args[args.index('-t') + 1] == '4.0' and args[-1] == str(tmp_path / 'clip-01.mp4')


def test_clip_command_loops_generated_clip_under_overlay_for_voice_duration(tmp_path):
    from office.media import clip_command
    args = [str(a) for a in clip_command(tmp_path / 'gen.mp4', tmp_path / 'overlay.png', tmp_path / 'voice.wav', 3.25, tmp_path / 'clip-02.mp4')]
    assert Path(args[0]).name.lower() in {'ffmpeg', 'ffmpeg.exe'}
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


def test_stock_clip_renderer_runs_without_background_and_falls_back_only_on_declared_errors(tmp_path):
    from office.media import obtain_clip, scene_clip
    calls = []

    class Unavailable(WorkflowError):
        pass

    def stock(scene_index, background, out_path):
        calls.append((scene_index, background))
        if scene_index == 1:
            raise Unavailable('Pexels 검색 HTTP 429')
        out_path.write_bytes(b'clip')
        return {'provider': 'pexels', 'attribution': {'name': 'Kim'}}
    stock.generated_scenes = [0, 1]
    stock.needs_background = False
    stock.fallback_errors = (Unavailable,)
    path, meta = scene_clip(stock, tmp_path, 0, None)
    assert path.name == 'generated-01.mp4' and meta['provider'] == 'pexels' and calls == [(0, None)]
    assert obtain_clip(stock, tmp_path, 1, None) == (None, None, {'scene': 2, 'reason': 'Pexels 검색 HTTP 429'})

    def broken(scene_index, background, out_path):
        raise WorkflowError('승인된 장면 번호만')
    broken.generated_scenes = [0]
    broken.needs_background = False
    broken.fallback_errors = (Unavailable,)
    with pytest.raises(WorkflowError, match='승인'):
        obtain_clip(broken, tmp_path, 0, None)


def test_clip_summary_and_rights_and_description_credit_stock_creators(tmp_path):
    from office.exports import stock_credit_line, write_rights_manifest
    from office.media import clip_summary
    attribution = {'source': 'Pexels', 'name': 'Kim', 'user_url': 'https://www.pexels.com/@kim', 'page_url': 'https://www.pexels.com/video/a-1/',
                   'pexels_video_id': 1, 'license_url': 'https://www.pexels.com/license/'}
    clips = [{'provider': 'pexels', 'model': 'stock-footage', 'disclosure': 'Pexels 무료 실사 스톡 영상', 'scene': 1, 'sha256': 'a' * 64, 'attribution': attribution},
             {'provider': 'pexels', 'model': 'stock-footage', 'disclosure': 'Pexels 무료 실사 스톡 영상', 'scene': 3, 'sha256': 'b' * 64, 'attribution': {**attribution, 'name': 'Lee', 'pexels_video_id': 2}}]
    summary = clip_summary(clips)
    assert summary['scenes'] == [1, 3] and [a['name'] for a in summary['attributions']] == ['Kim', 'Lee']
    # A reused manifest summary rebuilds the same attributions.
    assert clip_summary([{**summary, 'scene': s} for s in summary['scenes']]) == summary
    assert stock_credit_line(summary['attributions']) == '영상 소스: Pexels (Kim, Lee) · https://www.pexels.com'
    packet = {'title': 't', 'body': 'b', 'evidence': []}
    rights = json.loads(write_rights_manifest(packet, tmp_path, stock_footage=summary['attributions']).read_text(encoding='utf-8'))
    assert rights['visual_source'].endswith('+pexels_stock_footage')
    assert {a['pexels_video_id'] for a in rights['external_visual_assets']} == {1, 2}
    assert all(a['license_url'] == 'https://www.pexels.com/license/' for a in rights['external_visual_assets'])
    plain = json.loads(write_rights_manifest(packet, tmp_path).read_text(encoding='utf-8'))
    assert plain['visual_source'] == 'first_party_programmatic_shapes_and_text' and plain['external_visual_assets'] == []


@requires_ffmpeg
def test_photo_backgrounds_render_ken_burns_video_with_static_footage_text(tmp_path):
    from office.media import produce, probe
    store, job_id = approved_job(tmp_path, blog=False)
    manifest = produce(store, job_id, voice_renderer=tone_renderer(), background_renderer=background_renderer())
    files = {x["name"]: store.artifacts / x["path"] for x in manifest["files"]}
    assert {"overlay-01.png", "overlay-02.png", "background-01.png"} <= set(files)
    video = next(s for s in probe(files["short.mp4"])["streams"] if s["codec_type"] == "video")
    assert (video["width"], video["height"]) == (1080, 1920)
    assert json.loads(files["clip-01.json"].read_text(encoding="utf-8"))["still_motion"] == "ken-burns-v1"


@requires_ffmpeg
def test_stock_footage_scenes_render_credit_pexels_and_fall_back_to_stills(tmp_path):
    import shutil as sh
    from office.media import command, produce, probe
    store, job_id = approved_job(tmp_path)
    sample = tmp_path / "sample.mp4"
    command([sh.which("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=720x1280:rate=24", "-t", "1", "-pix_fmt", "yuv420p", sample])

    class Unavailable(WorkflowError):
        pass

    def stock(scene_index, background, out_path):
        assert background is None
        if scene_index == 1:
            raise Unavailable("Pexels 검색 HTTP 429")
        sh.copyfile(sample, out_path)
        return {"provider": "pexels", "model": "stock-footage", "disclosure": "Pexels 무료 실사 스톡 영상",
                "attribution": {"source": "Pexels", "name": "Kim", "page_url": "https://www.pexels.com/video/x-1/", "pexels_video_id": 1,
                                "license_url": "https://www.pexels.com/license/"}}
    stock.cache_key = stock.asset_cache_key = "pexels-stock:test"
    stock.generated_scenes = [0, 1]
    stock.needs_background = False
    stock.fallback_errors = (Unavailable,)
    manifest = produce(store, job_id, voice_renderer=tone_renderer(), clip_renderer=stock)
    files = {x["name"]: store.artifacts / x["path"] for x in manifest["files"]}
    assert manifest["output_status"]["video"]["state"] == "completed"
    assert manifest["clips"]["provider"] == "pexels" and manifest["clips"]["scenes"] == [1]
    assert manifest["media"]["clip_issues"] == [{"scene": 2, "reason": "Pexels 검색 HTTP 429"}]
    assert "영상 소스: Pexels (Kim)" in files["description.txt"].read_text(encoding="utf-8")
    rights = json.loads(files["asset-rights.json"].read_text(encoding="utf-8"))
    assert rights["external_visual_assets"][0]["pexels_video_id"] == 1
    scene = json.loads(files["scene-01.json"].read_text(encoding="utf-8"))
    assert scene["drawing_source"] == "stock_footage_frame+approved_scene_fields" and scene["layout"] == "footage_overlay"
    assert json.loads(files["scene-02.json"].read_text(encoding="utf-8"))["drawing_source"] == "approved_scene_fields"
    video = next(s for s in probe(files["short.mp4"])["streams"] if s["codec_type"] == "video")
    assert (video["width"], video["height"]) == (1080, 1920)


@requires_ffmpeg
def test_synthetic_coupon_cta_reaches_real_mp4_subtitles_and_approved_blog_handoffs(tmp_path):
    """Real local encoder + synthetic tone and confirmations; never a real coupon or upload."""
    from office.offers import campaign_packet
    from office.media import produce, probe
    from tests.test_offer import coupon_offer
    store, job_id = approved_job(tmp_path)
    offer = coupon_offer()
    offer["url"] = "https://www.heobrain.kr/synthetic-fixture-not-a-product"
    current = store.set_offer(job_id, offer, "synthetic-test")
    packet = campaign_packet(current["source_packet"], current["offer"])
    packet["quality"] = {"status": "passed", "critical": False}
    source = store.save_source(job_id, packet, expected_hash=current["source_hash"])
    store.review_source(job_id, source["source_hash"], "approved", "synthetic-test")
    result = produce(store, job_id, voice_renderer=tone_renderer())
    files = {item["name"]: store.artifacts / item["path"] for item in result["files"]}
    assert next(stream for stream in probe(files["short.mp4"])["streams"] if stream["codec_type"] == "video")["width"] == 1080
    assert "50퍼센트" in files["captions.srt"].read_text(encoding="utf-8")
    assert "허브레인 점 케이알" in files["captions.srt"].read_text(encoding="utf-8")
    drawn_cta = files["scene-03.json"].read_text(encoding="utf-8")
    assert "50%" in drawn_cta and "heobrain.kr" in drawn_cta and "FIXTURE50" in drawn_cta
    assert "FIXTURE50" in files["description.txt"].read_text(encoding="utf-8")
    assert "50퍼센트" in files["youtube-script.md"].read_text(encoding="utf-8")
    handoff = json.loads(files["channel-handoff.json"].read_text(encoding="utf-8"))
    assert handoff["source_hash"] == source["source_hash"]
    assert result["offer_snapshot"]["coupon"]["discount_percent"] == 50
    assert all("blog" in item["outputs"] for item in result["files"] if item["name"] in ("channel-handoff.json", "threads-main.txt"))


def test_production_contract_only_keeps_public_fields_of_social_targets():
    from office.media import production_contract
    channels = [{"key": "threads_main", "platform": "threads", "locale": "ko", "public_url": "https://www.threads.com/@synthetic", "credentials_configured": True, "external_account_id": "PRIVATE_SENTINEL", "publication_enabled": True}, {"key": "slack", "platform": "slack", "public_url": "PRIVATE_WORKSPACE_SENTINEL"}]
    contract = production_contract(None, {"blog": True}, channel_registry=channels)
    assert "PRIVATE" not in json.dumps(contract) and "credentials_configured" not in json.dumps(contract)
    assert contract["channel_registry"] == [{"key": "threads_main", "platform": "threads", "locale": "ko", "public_url": "https://www.threads.com/@synthetic"}]
    changed = [{**channels[0], "credentials_configured": False}, channels[1]]
    assert production_contract(None, {"blog": True}, channel_registry=changed)["hash"] == contract["hash"]
    changed[0]["public_url"] = "https://www.threads.com/@other"
    assert production_contract(None, {"blog": True}, channel_registry=changed)["hash"] != contract["hash"]
