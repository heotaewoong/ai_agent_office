import json
import pytest
from office.store import WorkflowError


def plan():
    return {'subtitle_layout':'en-main-ko-sub','scenes':[{'caption':'관측과 분석 연결','narration':'관측과 분석을 연결해요.','subtitle_en':'Connect observation and analysis.','subtitle_ko':'관측과 분석을 연결해요.'}]}


def test_bilingual_plan_requires_both_languages_before_render():
    from office.bilingual_captions import validate_plan
    for key in ('subtitle_en','subtitle_ko'):
        p=plan();p['scenes'][0].pop(key)
        with pytest.raises(WorkflowError,match='영한'):validate_plan(p,require=True)
    with pytest.raises(WorkflowError,match='영한'):validate_plan({'scenes':plan()['scenes']},require=True)


def test_bilingual_srt_tracks_use_identical_audio_clock(tmp_path):
    from office.bilingual_captions import write_tracks
    p=plan();p['scenes']*=2
    files=write_tracks(p,[1.25,2.5],tmp_path)
    assert {f.name for f in files}=={'captions.srt','captions.en.srt','captions.ko.srt'}
    contents={f.name:f.read_text(encoding='utf-8') for f in files}
    for text in contents.values():
        assert '00:00:00,000 --> 00:00:01,250' in text
        assert '00:00:01,250 --> 00:00:03,750' in text
    assert 'Connect observation and analysis.\n관측과 분석을 연결해요.' in contents['captions.srt']
    assert '관측과 분석' not in contents['captions.en.srt']


def test_bilingual_draw_keeps_english_larger_and_both_inside_existing_title_space(tmp_path):
    from PIL import Image,ImageDraw
    from office.bilingual_captions import draw_captions
    image=Image.new('RGB',(1080,1920),'#112233')
    metrics=draw_captions(ImageDraw.Draw(image),plan()['scenes'][0],footage=False)
    assert metrics['en']['font_size']>metrics['ko']['font_size']
    assert metrics['en_box'][1]+metrics['en_box'][3]<=metrics['ko_box'][1]
    assert metrics['ko_box'][1]+metrics['ko_box'][3]<620
    assert not metrics['en'].get('truncated') and not metrics['ko'].get('truncated')


def test_editorial_schema_and_review_contract_include_full_bilingual_lines():
    from office.editorial import DRAFT_SCHEMA
    video=DRAFT_SCHEMA['properties']['video']
    assert 'subtitle_layout' in video['required']
    assert {'subtitle_en','subtitle_ko'}.issubset(video['properties']['scenes']['items']['required'])


def test_missing_new_subtitle_blocks_video_before_voice_but_preserves_blog(tmp_path):
    from tests.test_media import approved_job
    from office.media import produce
    store,job_id=approved_job(tmp_path)
    job=store.job(job_id);packet=job['source_packet'];packet['video']['scenes'][0].pop('subtitle_en')
    job=store.save_source(job_id,packet)
    store.review_source(job_id,job['source_hash'],'approved','synthetic',{'blog':True,'video':True})
    def forbidden(*args,**kwargs):pytest.fail('자막 없는 영상은 음성 제작 전에 막아야 합니다')
    manifest=produce(store,job_id,voice_renderer=forbidden)
    assert manifest['output_status']['video']['state']=='failed'
    assert manifest['output_status']['blog']['state']=='completed'


def test_new_subtitle_integrity_is_blocking_not_style_advisory():
    from office.editorial import deterministic_checks
    p=plan();p['scenes'][0].pop('subtitle_en')
    result=deterministic_checks({'title':'합성','body':'합성','video':p,'evidence':[]})
    assert not result['passed'] and any('영한' in x for x in result['blocking'])
