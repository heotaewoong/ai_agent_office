"""Same audio-clock English-main/Korean-secondary captions; never translates or calls a model."""
import math
import re
from .store import WorkflowError

LAYOUT='en-main-ko-sub'
INSTRUCTIONS='영상은 subtitle_layout=en-main-ko-sub로 작성한다. 각 장면 subtitle_en은 narration 전체와 같은 의미의 자연스러운 영어, subtitle_ko는 같은 의미의 정상 표기 한국어다. 숫자·고유명사·조건·부정·발행사 주장 범위를 양쪽에 보존하고 새 사실을 넣지 않는다. 음성 narration은 기존 한국어다. 두 자막은 같은 장면 음성 시간에 표시되므로 짧은 완결 문장으로 장면을 나눈다. 자막은 제목 요약이 아니라 해당 음성 문장의 번역이다. 비평·평가·수정에서도 원고와 양언어의 의미·숫자·범위를 대조한다.'


def validate_text(scene):
    if not isinstance(scene,dict):raise WorkflowError('영한 자막 장면 형식을 확인하세요')
    for key,pattern in (('subtitle_en',r'[A-Za-z]'),('subtitle_ko',r'[가-힣]')):
        text=scene.get(key)
        if not isinstance(text,str) or not text.strip() or len(text)>500 or not re.search(pattern,text) or any(c in text for c in ('\r','\x00','-->','\n\n')):
            raise WorkflowError('영한 자막 두 언어의 문장·표기를 확인하세요')


def draw_captions(draw,scene,*,footage=False):
    from .media import text_box
    from .exports import korean_font
    validate_text(scene)
    en_box=(70,270,940,250) if footage else (85,235,910,230)
    ko_box=(70,540,940,120) if footage else (85,485,910,120)
    outline={'stroke_width':4,'stroke_fill':'#080c18'} if footage else {}
    en=text_box(draw,scene['subtitle_en'],en_box,64,minimum_size=40,font_path=korean_font('bold'),**outline)
    ko=text_box(draw,scene['subtitle_ko'],ko_box,36,fill='#e8eef8',minimum_size=26,**outline)
    return {'layout':LAYOUT,'en':en,'ko':ko,'en_box':en_box,'ko_box':ko_box}


def validate_plan(plan,*,require=False):
    if not isinstance(plan,dict):raise WorkflowError('영한 자막 영상 계획을 확인하세요')
    mode=plan.get('subtitle_layout')
    if mode is None and not require:return False
    if mode!=LAYOUT or not plan.get('scenes'):raise WorkflowError('영한 자막 원고 준비가 필요합니다. 기존 영상을 자동 번역·재생성하지 않았습니다')
    from PIL import Image,ImageDraw
    draw=ImageDraw.Draw(Image.new('RGB',(1080,1920)))
    for scene in plan['scenes']:
        validate_text(scene)
        try:
            draw_captions(draw,scene)
            draw_captions(draw,scene,footage=True)
        except WorkflowError as error:
            raise WorkflowError('영한 자막이 화면에 맞지 않습니다. 문장을 짧은 장면으로 나눠 검수하세요') from error
    return True


def write_tracks(plan,durations,folder):
    bilingual=validate_plan(plan)
    if len(durations)!=len(plan['scenes']) or any(not math.isfinite(d) or d<=0 for d in durations):raise WorkflowError('자막과 음성 시간축이 일치하지 않습니다')
    def stamp(seconds):
        value=round(seconds*1000)
        return f'{value//3600000:02}:{value//60000%60:02}:{value//1000%60:02},{value%1000:03}'
    tracks={'captions.srt':[]}
    if bilingual:tracks.update({'captions.en.srt':[],'captions.ko.srt':[]})
    elapsed=0.0
    for i,(scene,duration) in enumerate(zip(plan['scenes'],durations),1):
        header=f'{i}\n{stamp(elapsed)} --> {stamp(elapsed+duration)}\n'
        en,ko=scene.get('subtitle_en',''),scene.get('subtitle_ko',scene['narration'])
        tracks['captions.srt'].append(header+(en+'\n'+ko if bilingual else scene['narration'])+'\n')
        if bilingual:
            tracks['captions.en.srt'].append(header+en+'\n');tracks['captions.ko.srt'].append(header+ko+'\n')
        elapsed+=duration
    paths=[]
    for name,lines in tracks.items():
        path=folder/name;path.write_text('\n'.join(lines),encoding='utf-8');paths.append(path)
    return paths
