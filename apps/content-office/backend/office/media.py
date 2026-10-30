"""Approval-gated, local production. Successful voices survive later failures."""
from __future__ import annotations
import base64
from array import array
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
from PIL import Image, ImageDraw, ImageFont
from .exports import korean_font, write_blog_exports, write_reference_pdf, write_rights_manifest, write_video_exports
from .store import WorkflowError, digest, canonical
RENDER_VERSION = 'office-media-5-preserved-source-photos'
VOICE_CACHE_VERSION = 'office-media-1'

def command(args, timeout=180):
    try:
        result = subprocess.run([str(a) for a in args], capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WorkflowError('로컬 제작 도구를 실행하지 못했습니다. FFmpeg·PowerShell 경로와 실행 시간을 확인하세요') from exc
    if result.returncode:
        raise WorkflowError(f'로컬 제작 도구가 실패했습니다 (종료 코드 {result.returncode})')
    return result.stdout

def executable(name):
    value = shutil.which(name)
    if not value:
        raise WorkflowError(f'{name} 실행 파일이 없습니다')
    return value

def probe(path):
    try:
        return json.loads(command([executable('ffprobe'), '-v', 'error', '-show_streams', '-show_format', '-of', 'json', path]))
    except (ValueError, KeyError) as exc:
        raise WorkflowError('미디어 길이와 스트림을 확인할 수 없습니다') from exc

def audio_duration(path):
    info = probe(path)
    if not any((s.get('codec_type') == 'audio' for s in info.get('streams', []))):
        raise WorkflowError('유효한 음성 스트림이 없습니다')
    duration = float(info.get('format', {}).get('duration', 0))
    if not math.isfinite(duration) or duration <= 0:
        raise WorkflowError('실제 음성 길이가 유효하지 않습니다')
    pcm = command([executable('ffmpeg'), '-v', 'error', '-i', path,
                   '-t', '65', '-map', '0:a:0', '-ac', '1', '-ar', '8000',
                   '-f', 's16le', 'pipe:1'])
    samples = array('h')
    samples.frombytes(pcm)
    if not samples or max(abs(value) for value in samples) <= 32:
        raise WorkflowError('음성 결과가 무음입니다. 음성 설정을 확인하고 다시 제작하세요')
    return duration

def powershell(script):
    encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
    return command([executable('powershell.exe'), '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded], 150).decode('utf-8', errors='replace')

def windows_local_path(path, *, platform=None):
    # The built-in voice is Windows System.Speech; there is no WSL bridge any more.
    if (platform or os.name) != 'nt':
        raise WorkflowError('Windows 기본 음성은 Windows에서만 생성합니다. Linux(EC2)에서는 유료 음성 프로필을 선택하세요')
    return Path(path)

def local_voice(text, out_path):
    if not isinstance(text, str) or not text.strip():
        raise WorkflowError('음성 대본이 비어 있습니다')
    payload = base64.b64encode(text.encode('utf-8')).decode('ascii')
    voice_payload = base64.b64encode(local_voice_configuration()['voice'].encode('utf-8')).decode('ascii')
    script = "$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'\n$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new()\nAdd-Type -AssemblyName System.Speech\n$s=[System.Speech.Synthesis.SpeechSynthesizer]::new();$folder=$null\ntry {\n $voice=$s.GetInstalledVoices() | Where-Object {$_.Enabled -and $_.VoiceInfo.Culture.Name -eq 'ko-KR'} | Select-Object -First 1\n if(-not $voice){throw 'NO_KOREAN_VOICE'}\n $folder=Join-Path ([IO.Path]::GetTempPath()) ('hb-office-'+[Guid]::NewGuid().ToString('N'))\n [IO.Directory]::CreateDirectory($folder)|Out-Null\n $inputFile=Join-Path $folder 'narration.txt';$outputFile=Join-Path $folder 'speech.wav'\n [IO.File]::WriteAllBytes($inputFile,[Convert]::FromBase64String('PAYLOAD'))\n $s.SelectVoice($voice.VoiceInfo.Name);$s.Rate=0;$s.SetOutputToWaveFile($outputFile)\n $s.Speak([IO.File]::ReadAllText($inputFile,[Text.Encoding]::UTF8));$s.SetOutputToNull()\n [pscustomobject]@{path=$outputFile;folder=$folder;voice=$voice.VoiceInfo.Name}|ConvertTo-Json -Compress\n} catch {if($folder){Remove-Item -LiteralPath $folder -Recurse -Force -ErrorAction SilentlyContinue};throw} finally {$s.Dispose()}\n".replace('PAYLOAD', payload)
    script = script.replace("$voice=$s.GetInstalledVoices()", "$voiceName=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + voice_payload + "'));$voice=$s.GetInstalledVoices()")
    script = script.replace("$_.VoiceInfo.Culture.Name -eq 'ko-KR'", "$_.VoiceInfo.Culture.Name -eq 'ko-KR' -and $_.VoiceInfo.Name -eq $voiceName")
    try:
        response = json.loads(powershell(script).strip())
    except (WorkflowError, ValueError) as exc:
        raise WorkflowError('Windows 한국어 음성을 생성하지 못했습니다. ko-KR 음성과 PowerShell 연결을 확인하세요. 유료 대체 음성은 자동 호출하지 않습니다') from exc
    folder = response.get('folder', '')
    if not re.fullmatch('hb-office-[0-9a-f]{32}', folder.replace('\\', '/').rsplit('/', 1)[-1]):
        raise WorkflowError('음성 임시 폴더 안전 검증 실패')
    try:
        source = windows_local_path(response['path'])
        if source.parent != windows_local_path(folder) or source.name != 'speech.wav':
            raise WorkflowError('음성 임시 경로 안전 검증 실패')
        shutil.copyfile(source, out_path)
    finally:
        powershell("$ErrorActionPreference='Stop';Remove-Item -LiteralPath '" + folder.replace("'", "''") + "' -Recurse -Force")
    return {'voice': response['voice'], 'provider': 'windows-system-speech', 'model': 'installed-ko-KR', 'disclosure': 'Windows 한국어 합성 음성'}
local_voice.cache_key = 'windows-system-speech-ko-KR-rate0-v1'


def local_voice_configuration():
    return {'provider': 'windows-system-speech', 'voice': os.environ.get('OFFICE_LOCAL_VOICE', 'Microsoft Heami Desktop'),
            'model': 'installed-ko-KR', 'rate': 0, 'contract': 'explicit-installed-voice-v1'}


def voice_identity(renderer):
    if renderer is local_voice:
        return digest(local_voice_configuration())
    return str(getattr(renderer, 'asset_cache_key', getattr(renderer, 'cache_key', getattr(renderer, '__qualname__', 'injected-renderer'))))


def background_identity(renderer):
    if renderer is None:
        return None
    return str(getattr(renderer, 'cache_key', getattr(renderer, '__qualname__', 'injected-background-renderer')))


def production_contract(voice_renderer, selections, image_renderer=None, clip_renderer=None, channel_registry=None):
    """Bind outputs to actual code, font bytes, the selected voice, background image and generated clip configuration."""
    renderer = voice_renderer or local_voice
    visual = any(selections.get(kind) for kind in ('video', 'cards', 'pdf'))
    scenes_drawn = bool(selections.get('video') or selections.get('cards'))
    from .channel_handoff import SOCIAL_TARGETS
    channel_registry = [{key: row.get(key) for key in ('key', 'platform', 'locale', 'public_url')}
                        for row in (channel_registry or []) if row.get('key') in SOCIAL_TARGETS]
    font_sha, font_status = None, 'not_required'
    if visual:
        try:
            font_sha, font_status = file_hash(korean_font()), 'ready'
        except (WorkflowError, OSError):
            # A visual preflight failure must not prevent independent text exports.
            font_status = 'unavailable'
    config = {'renderer_version': RENDER_VERSION, 'voice_cache_version': VOICE_CACHE_VERSION,
              'implementation_sha256': file_hash(Path(__file__)),
              'export_implementation_sha256': file_hash(Path(__file__).with_name('exports.py')),
              'offer_implementation_sha256': file_hash(Path(__file__).with_name('offers.py')),
              'channel_handoff_implementation_sha256': file_hash(Path(__file__).with_name('channel_handoff.py')),
              'channel_registry': channel_registry if selections.get('blog') else None,
              'font_sha256': font_sha, 'font_status': font_status,
              'voice': (voice_identity(renderer) if renderer is local_voice else str(getattr(renderer, 'cache_key', voice_identity(renderer)))) if selections.get('video') else None,
              'voice_asset_key': voice_identity(renderer) if selections.get('video') else None,
              'background': background_identity(image_renderer) if scenes_drawn else None,
              'background_asset_key': str(getattr(image_renderer, 'asset_cache_key', background_identity(image_renderer))) if (scenes_drawn and image_renderer is not None) else None,
              'clip': background_identity(clip_renderer) if selections.get('video') else None,
              'clip_asset_key': str(getattr(clip_renderer, 'asset_cache_key', background_identity(clip_renderer))) if (selections.get('video') and clip_renderer is not None) else None,
              'selections': dict(selections)}
    if selections.get('cards'):
        config['cards_implementation_sha256']=file_hash(Path(__file__).with_name('cards.py'))
        config['cards_pipeline_sha256']=file_hash(Path(__file__).with_name('social_production.py'))
    return {**config, 'hash': digest(config)}

def wrap_text(draw, text, font, width):
    """Keep Korean words intact; split only tokens wider than the whole box."""
    lines = []
    for paragraph in str(text).splitlines() or ['']:
        line = ''
        for word in paragraph.split():
            candidate = (line + ' ' + word).strip()
            if draw.textlength(candidate, font=font) <= width:
                line = candidate
                continue
            if line:
                lines.append(line)
                line = ''
            for char in word:
                if line and draw.textlength(line + char, font=font) > width:
                    lines.append(line)
                    line = ''
                line += char
        lines.append(line)
    return lines


def text_box(draw, text, box, size=56, fill='#ffffff', *, minimum_size=20, truncate=False, font_path=None, line_gap=None):
    x, y, width, height = box
    face = str(font_path or korean_font())
    def fitted(value):
        for font_size in range(size, minimum_size - 1, -2):
            font = ImageFont.truetype(face, font_size)
            lines = wrap_text(draw, value, font, width)
            line_height = font_size + (line_gap if line_gap is not None else max(8, font_size // 4))
            if len(lines) * line_height <= height:
                return font, lines, line_height, font_size
        return None
    value = str(text)
    result = fitted(value)
    shortened = False
    if result is None and truncate:
        # An ellipsis identifies a displayed excerpt; the full approved text stays in metadata.
        while len(value) > 1 and result is None:
            value = value[:-2].rstrip()
            result = fitted(value + '…')
        shortened = True
    if result is None:
        raise WorkflowError('화면 문장이 너무 깁니다. 제목이나 장면 자막을 줄여주세요')
    font, lines, line_height, font_size = result
    for index, line in enumerate(lines):
        draw.text((x, y + index * line_height), line, font=font, fill=fill)
    return {'font_size': font_size, 'lines': len(lines), 'overflow': False, 'truncated': shortened, 'displayed_text': '\n'.join(lines)}


NUMBER_VALUE = r'[+−-]?\d+(?:[,.]\d+)*(?:천만|백만|천|백|만|억|조|[KMBT])?'
# Long units must precede prefixes: 3개월 is not a count of 3개.
NUMBER_PATTERN = r'(?:[$₩]\s*' + NUMBER_VALUE + r'|' + NUMBER_VALUE + r'(?:\s*(?:~|–|—)\s*' + NUMBER_VALUE + r')?\s*(?:퍼센트포인트|퍼센트|%포인트|%p|%|개월|개국|단계|시간|달러|토큰|tokens?|USD|KRW|ms|GB|MB|배|명|개|건|원|초|분|일|년|점|회|종))'


def numeric_facts(text):
    facts = []
    for match in re.finditer(NUMBER_PATTERN, str(text), re.I):
        value = re.sub(r'\s+', '', match.group())
        if value not in {f['value'] for f in facts}:
            line_start = str(text).rfind('\n', 0, match.start()) + 1
            line_end = str(text).find('\n', match.end())
            sentence = str(text)[line_start:line_end if line_end >= 0 else None].strip()
            facts.append({'value': value, 'context': sentence})
    return facts


def clean_visual_label(value):
    value = re.sub(r'^(?:flow|comparison|process|number|explanation|설명|흐름도?|순서|단계|비교|과정)\s*[:：]\s*', '', value.strip(), flags=re.I)
    return value.strip(' []()"\'')


def scene_content(scene, index=0):
    caption = str(scene.get('caption', '')).strip()
    narration = str(scene.get('narration', '')).strip()
    visual = str(scene.get('visual', '')).strip()
    requested = 'explanation'
    for markers, kind in [(('compar','비교',' vs '),'comparison'), (('number','숫자','수치'),'number'), (('flow','흐름','단계','→','->'),'flow')]:
        if any(marker in visual.lower() for marker in markers):
            requested = kind
            break
    steps = []
    for text in (visual, caption):
        if re.search(r'→|->|⇒', text):
            found = [clean_visual_label(s) for s in re.split(r'\s*(?:→|->|⇒)\s*', text)]
            if 2 <= len(found) <= 5 and all(found):
                steps = found
                break
    comparison = []
    # Explicit visual lists describe the compared concepts, not speech text.
    # A slash separated three-way comparison must not collapse to explanation.
    if requested == 'comparison':
        labels = re.split(r'\s+/\s+|\s*(?:→|->|⇒)\s*', clean_visual_label(visual))
        if 2 <= len(labels) <= 5 and all(labels):
            comparison = labels
    for text in (visual, caption):
        if comparison:
            break
        pair = re.split(r'\s+(?:vs\.?|versus|대비|↔)\s+', clean_visual_label(text), maxsplit=1, flags=re.I)
        if len(pair) == 2 and all(pair):
            comparison = [part.strip().rstrip('.') for part in pair]
            break
        pair = re.split(r'\s*(?:반면|하지만)\s*', text, maxsplit=1)
        if len(pair) == 2 and all(pair):
            comparison = [part.strip(' ,.') for part in pair]
            break
        korean_pair = re.match(r'^(.+?)(?:과|와)\s+(.+?)(?:을|를)?\s+비교(?:합니다|했습니다)?[.!]?$', text)
        if korean_pair:
            comparison = [part.strip() for part in korean_pair.groups()]
            break
    numbers = numeric_facts(caption)
    # Visual instructions describe the picture ('문의 1건, 분류 우선 흐름'), not a metric to headline.
    # Take numbers from them only when the visual explicitly asks for a number scene.
    if not numbers and requested == 'number' and not re.search(r'박스|카드|픽셀|px|레이아웃|글꼴|font|columns?', visual, re.I):
        numbers = numeric_facts(visual)
    if requested == 'flow' and steps:
        kind = 'flow'
    elif requested == 'comparison' and comparison:
        kind = 'comparison'
    elif requested == 'number' and numbers:
        kind = 'number'
    elif steps:
        kind = 'flow'
    elif comparison:
        kind = 'comparison'
    elif numbers and requested != 'explanation':
        kind = 'number'
    else:
        kind = 'explanation'
    visual_text = clean_visual_label(visual) if re.match(r'^(?:explanation|설명)\s*[:：]', visual, re.I) else ''
    facts = [part.strip() for part in re.split(r'\s+/\s+|\n', visual_text) if part.strip()]
    return {'kind': kind, 'caption': caption, 'narration': narration, 'numbers': numbers, 'steps': steps, 'comparison': comparison, 'key_phrases': facts or [caption]}


def scene_kind(scene, index):
    return scene_content(scene, index)['kind']


def approved_display_title(plan):
    candidates = plan.get('thumbnails')
    titles = [str(c.get('title', '')).strip() for c in candidates if isinstance(c, dict)] if isinstance(candidates, list) else []
    original = str(plan.get('thumbnail_title') or plan.get('title', '')).strip()
    if len(original) <= 38:
        return original
    short = [title for title in titles if 4 <= len(title) <= 38]
    return short[0] if short else original


def cover_background(source, size=(1080, 1920)):
    """Scale a generated background to cover the frame, then dim it so the local text layer stays readable."""
    with Image.open(source) as opened:
        background = opened.convert('RGB')
    width, height = background.size
    if width <= 0 or height <= 0:
        raise WorkflowError('배경 이미지를 읽을 수 없습니다')
    scale = max(size[0] / width, size[1] / height)
    resized = background.resize((max(size[0], math.ceil(width * scale)), max(size[1], math.ceil(height * scale))), Image.LANCZOS)
    left, top = (resized.width - size[0]) // 2, (resized.height - size[1]) // 2
    frame = resized.crop((left, top, left + size[0], top + size[1]))
    # 생성 배경이 보이도록 35%만 눌러 두고, 글자 가독성은 굵은 제목과 장면 패널이 맡는다.
    return Image.blend(frame, Image.new('RGB', size, '#0b1327'), 0.35)


def draw_scene(plan, scene, index, total, path, *, background=None, background_meta=None, overlay_only=False):
    content = scene_content(scene, index)
    if overlay_only:
        # Transparent text layer composited over a generated clip; the clip supplies the picture.
        image = Image.new('RGBA', (1080, 1920), (0, 0, 0, 0))
    else:
        image = cover_background(background) if background else Image.new('RGB', (1080, 1920), '#0b1327')
    draw = ImageDraw.Draw(image)
    accent = ['#6de8d5', '#9aa7ff', '#ffc684', '#94d9ff'][index % 4]
    if overlay_only:
        draw.rounded_rectangle((60, 80, 1020, 570), 28, fill=(11, 19, 39, 200))
    else:
        for n in range(4):
            draw.arc((760-n*35, -170+n*50, 1320+n*35, 390+n*50), 70, 310, fill='#1b2c48', width=3)
    text_box(draw, 'HeoBrain / AI 개념 노트', (85, 100, 900, 70), 32, accent)
    # The current scene is the headline. The approved global title remains in
    # the plan/thumbnail, rather than competing with every scene's explanation.
    title_metrics = text_box(draw, content['caption'], (85, 235, 910, 310), 80, minimum_size=46, font_path=korean_font('bold'))
    kind = content['kind']
    comparison_metrics = []
    number_metrics = []
    if kind == 'flow':
        steps = content['steps']
        node_height = min(205, int(860 / len(steps)) - 35)
        for order, label in enumerate(steps):
            y = 640 + order * (node_height + 35)
            draw.rounded_rectangle((95, y, 985, y+node_height), 24, fill='#192c45', outline=accent, width=2)
            text_box(draw, label, (135, y+30, 810, node_height-45), 52, minimum_size=28)
            if order < len(steps)-1:
                draw.line((540, y+node_height, 540, y+node_height+28), fill=accent, width=4)
                draw.polygon([(531,y+node_height+20),(549,y+node_height+20),(540,y+node_height+31)],fill=accent)
    elif kind == 'comparison':
        count = len(content['comparison'])
        for column, label in enumerate(content['comparison']):
            if count == 2:
                x, y, width, height = 75 + column * 475, 680, 455, 720
            else:
                height = int(900 / count) - 25
                x, y, width = 85, 620 + column * (height + 25), 910
            draw.rounded_rectangle((x, y, x+width, y+height), 28, fill='#192c45', outline=accent if column % 2 == 0 else '#9aa7ff', width=3)
            comparison_metrics.append(text_box(draw, label, (x+35, y+40, width-70, height-75), 58, minimum_size=28))
    elif kind == 'number':
        facts = content['numbers']
        for order, fact in enumerate(facts):
            if len(facts) <= 2:
                width = 920 if len(facts) == 1 else 455
                x, y, height = 80 + order * 475, 720, 600
            else:
                height = int(900 / len(facts)) - 25
                x, y, width = 85, 620 + order * (height + 25), 910
            draw.rounded_rectangle((x, y, x+width, y+height), 30, fill='#192c45', outline=accent, width=3)
            number_metrics.append(text_box(draw, fact['value'], (x+35, y+55, width-70, min(160, height-100)), 125 if len(facts) == 1 else 85, accent, minimum_size=28))
    else:
        phrases = [phrase for phrase in content['key_phrases'] if phrase != content['caption']]
        for order, phrase in enumerate(phrases):
            height = int(900 / len(phrases)) - 30
            y = 620 + order * (height + 30)
            draw.rounded_rectangle((80, y, 1000, y+height), 32, fill='#192c45')
            draw.rectangle((115, y+35, 125, y+height-35), fill=accent)
            text_box(draw, phrase, (165, y+50, 760, height-85), 58, minimum_size=28)
    if overlay_only:
        draw.rounded_rectangle((60, 1770, 1020, 1875), 20, fill=(11, 19, 39, 200))
    text_box(draw, f'{index+1:02} / {total:02} · 출처와 한계는 설명란 확인', (85, 1790, 910, 70), 28, '#b8c9e4')
    image.save(path, 'PNG')
    record = {**content, 'title_metrics': title_metrics, 'comparison_metrics': comparison_metrics, 'number_metrics': number_metrics, 'drawing_source': 'approved_scene_fields'}
    if overlay_only:
        record['drawing_source'] = 'overlay_only+approved_scene_fields'
    if background:
        record.update(drawing_source='generated_background+approved_scene_fields', background_sha256=file_hash(background),
                      background_provider=str((background_meta or {}).get('provider', 'injected'))[:80],
                      background_disclosure=str((background_meta or {}).get('disclosure', '생성 배경 이미지'))[:200])
    write_json(path.with_suffix('.json'), record)
    return kind


def thumbnail_concepts(plan):
    supplied = plan.get('thumbnails')
    captions = [str(s.get('caption', '')).strip() for s in plan.get('scenes', []) if s.get('caption')]
    result = []
    for index in range(5):
        item = supplied[index] if isinstance(supplied, list) and index < len(supplied) and isinstance(supplied[index], dict) else {}
        result.append({'title': str(item.get('title') or approved_display_title(plan)),
                       'subtitle': str(item.get('subtitle') or (captions[index % len(captions)] if captions else plan.get('description', ''))),
                       'angle': str(item.get('angle') or ['핵심 설명','비교 관점','근거 확인','흐름 이해','검토 포인트'][index]),
                       'layout': ['editorial_headline','split_context','fact_spotlight','process_strip','question_focus'][index],
                       'from_approved_concept': bool(item)})
    return result


def luminance(color):
    rgb = [int(color.lstrip('#')[i:i+2],16)/255 for i in (0,2,4)]
    linear = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in rgb]
    return .2126*linear[0]+.7152*linear[1]+.0722*linear[2]


def assess_thumbnail(plan, concept, metrics, foreground, background, source_text=None):
    source = source_text or '\n'.join([str(plan.get('title','')), str(plan.get('description',''))] + [str(s.get('caption',''))+' '+str(s.get('narration','')) for s in plan.get('scenes',[])])
    candidate = concept['title']+' '+concept['subtitle']
    def grams(text):
        clean = re.sub(r'[^\w가-힣]', '', text.lower())
        return {clean[i:i+2] for i in range(max(0,len(clean)-1))}
    candidate_grams = grams(candidate)
    overlap = len(candidate_grams & grams(source)) / max(1, len(candidate_grams))
    source_values = {f['value'] for f in numeric_facts(source)}
    unsupported = [f['value'] for f in numeric_facts(candidate) if f['value'] not in source_values]
    alignment = 0 if unsupported else 5 if overlap >= .7 else 4 if overlap >= .45 else 3 if overlap >= .25 else 2 if overlap >= .1 else 1
    contrast = (max(luminance(foreground),luminance(background))+.05)/(min(luminance(foreground),luminance(background))+.05)
    font_size = metrics.get('title_font_size', metrics.get('minimum_font_size', 0))
    readability = 5 if font_size >= 64 else 4 if font_size >= 52 else 3 if font_size >= 44 else 2 if font_size >= 36 else 1
    if metrics.get('subtitle_font_size', 37) < 32:
        readability = min(readability, 4)
    title_fit = 0 if metrics.get('overflow') else 1 if metrics.get('truncated') else 5 if metrics.get('title_lines',0) <= 3 else 3
    warnings = []
    if unsupported: warnings.append('원고 본문에서 확인되지 않은 수치: '+', '.join(unsupported))
    if alignment < 3: warnings.append('원고와 표현의 겹침이 낮아 본문 일치를 사람이 확인해야 합니다')
    if metrics.get('truncated'): warnings.append('긴 제목을 생략 표시했습니다. 더 짧은 승인 제목을 선택하세요')
    if metrics.get('subtitle_truncated'): warnings.append('긴 보조 설명을 일부 생략 표시했습니다. 원고와 함께 확인하세요')
    if readability < 3: warnings.append('작은 화면에서 제목 읽기가 어려울 수 있습니다')
    scores = {'readability': readability, 'contrast': 5 if contrast >= 7 else 4 if contrast >= 4.5 else 1, 'title_fit': title_fit, 'source_alignment': alignment}
    reason = f"제목 {font_size}px·{metrics.get('title_lines',0)}줄, 명암비 {contrast:.1f}:1, 본문 표현 겹침 {overlap:.0%}."
    return {'scores': scores, 'contrast_ratio': round(contrast,2), 'text_metrics': metrics,
            'assessment_kind':'local_layout_heuristic', 'selection_reason': reason,
            'assessment_limit':'로컬 배치·표현 일치 휴리스틱입니다. 사실성 검증·CTR·성과 측정이 아닙니다.',
            'warnings': warnings, 'human_selection':'pending'}


def draw_thumbnails(plan, folder, *, source_text=None):
    concepts = thumbnail_concepts(plan)
    palettes = [('#0b152d','#6de8d5'),('#171537','#c1b2ff'),('#2a1b19','#ffc684'),('#112830','#91e3f8'),('#1d2241','#e4f18d')]
    paths, reviews = [], []
    explicit_flow = next((scene_content(s)['steps'] for s in plan.get('scenes',[]) if scene_content(s)['steps']), [])
    for index, (concept, (background, accent)) in enumerate(zip(concepts,palettes)):
        image = Image.new('RGB',(1280,720),background)
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((35,35,1245,685),32,outline=accent,width=2)
        text_box(draw,'HeoBrain / AI 뉴스 쉽게 이해하기',(70,75,1080,55),28,accent)
        text_box(draw,concept['angle'],(75,135,1080,45),26,'#c8d4e9',minimum_size=24,truncate=True)
        layout = concept['layout']
        if layout == 'editorial_headline':
            draw.rectangle((72,205,85,515),fill=accent)
            title_box=(120,220,1030,290);subtitle_box=(120,550,1020,100)
        elif layout == 'split_context':
            draw.rounded_rectangle((865,205,1190,620),25,fill='#252344',outline=accent,width=2)
            text_box(draw,concept['subtitle'],(900,350,250,220),36,minimum_size=28,truncate=True)
            title_box=(75,215,725,335);subtitle_box=(75,580,725,70)
        elif layout == 'fact_spotlight':
            draw.ellipse((875,245,1205,575),outline=accent,width=9)
            # Highlight this approved headline's metric, never an unrelated scene's.
            match = re.search(f'(?:{NUMBER_PATTERN}|{NUMBER_VALUE}(?:번)?)', concept['title'], re.I)
            fact = re.sub(r'\s+', '', match.group()) if match else '핵심'
            text_box(draw,fact,(915,350,255,120),70,accent,minimum_size=44,truncate=True)
            title_box=(75,220,745,300);subtitle_box=(75,560,1080,90)
        elif layout == 'process_strip':
            title_box=(75,205,1115,240);subtitle_box=(75,600,1115,55)
            nodes=explicit_flow[:3] or [str(s.get('caption','')) for s in plan.get('scenes',[])][:3]
            for n,label in enumerate(nodes):
                x=75+n*385
                draw.rounded_rectangle((x,475,x+355,575),20,fill='#20424b',outline=accent,width=2)
                text_box(draw,label,(x+20,495,315,65),30,minimum_size=24,truncate=True)
                if explicit_flow and n < len(nodes)-1:
                    draw.line((x+358,525,x+381,525),fill=accent,width=3)
        else:
            draw.polygon([(1040,185),(1210,355),(1040,525),(870,355)],outline=accent,width=3)
            title_box=(95,230,1010,280);subtitle_box=(95,555,1040,90)
            # Keep the reading surface opaque so decoration never crosses title glyphs.
            draw.rounded_rectangle((75,205,1150,530),25,fill=background)
        title_metrics=text_box(draw,concept['title'],title_box,82,minimum_size=48,truncate=True)
        subtitle_metrics=text_box(draw,concept['subtitle'],subtitle_box,37,minimum_size=28,truncate=True)
        metrics={'minimum_font_size':min(title_metrics['font_size'],subtitle_metrics['font_size']),
                 'title_font_size':title_metrics['font_size'],'title_lines':title_metrics['lines'],
                 'subtitle_font_size':subtitle_metrics['font_size'],
                 'overflow':title_metrics['overflow'] or subtitle_metrics['overflow'],
                 'truncated':title_metrics['truncated'],'subtitle_truncated':subtitle_metrics['truncated']}
        review={**concept, **assess_thumbnail(plan,concept,metrics,'#ffffff',background,source_text)}
        if layout == 'fact_spotlight':
            review['spotlight_value'] = fact
        path=folder/f'thumbnail-{index+1:02}.png'
        image.save(path,'PNG');paths.append(path);reviews.append({'name':path.name,**review})
    write_json(folder/'thumbnail-review.json',{'assessment_kind':'local_layout_heuristic','candidates':reviews})
    return paths


def stamp(seconds):
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f'{h:02}:{m:02}:{s:02},{ms:03}'

def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write_json(path, data):
    partial = path.with_name(path.name + '.partial')
    partial.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(partial, path)

def scene_background(background_renderer, folder, index):
    """Fetch one approved scene's generated background; returns (path, metadata) or (None, None)."""
    if background_renderer is None:
        return None, None
    path = folder / f'background-{index + 1:02}.png'
    meta = background_renderer(index, path) or {}
    if not path.is_file():
        raise WorkflowError('배경 이미지 렌더러가 파일을 만들지 않았습니다')
    return path, meta


def scene_clip(clip_renderer, folder, index, background):
    """Fetch a generated clip for an opted-in scene. Needs the generated background as the input frame."""
    if clip_renderer is None or index not in list(getattr(clip_renderer, 'generated_scenes', [])):
        return None, None
    if not background:
        raise WorkflowError('생성 영상 장면에는 배경 이미지 프로필이 켜져 있어야 합니다. 유료 영상은 호출하지 않았습니다')
    path = folder / f'generated-{index + 1:02}.mp4'
    meta = clip_renderer(index, background, path) or {}
    if not path.is_file():
        raise WorkflowError('생성 영상 렌더러가 파일을 만들지 않았습니다')
    return path, meta


def clip_command(generated, overlay, audio, duration, out):
    """Loop the generated clip under the transparent text layer for exactly the voice duration."""
    graph = ('[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=24[bg];'
             '[bg][1:v]overlay=0:0:format=auto[v]')
    # Pure argument builder; command() reports a missing ffmpeg when the list is actually run.
    return [shutil.which('ffmpeg') or 'ffmpeg', '-y', '-v', 'error', '-stream_loop', '-1', '-i', generated, '-i', overlay, '-i', audio,
            '-filter_complex', graph, '-map', '[v]', '-map', '2:a', '-t', str(duration),
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '24', '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-ar', '48000', '-ac', '2', '-movflags', '+faststart', out]


def render_short(plan, folder, *, voice_renderer=None, check_current=None, source_text=None, voice_cache_dir=None, background_renderer=None, clip_renderer=None):
    scenes = plan.get('scenes', [])
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= 12:
        raise WorkflowError('영상에는 1~12개 장면이 필요합니다')
    for scene in scenes:
        if not isinstance(scene, dict) or any((not isinstance(scene.get(k), str) or not scene[k].strip() for k in ('narration', 'caption'))):
            raise WorkflowError('각 장면의 음성 대본과 화면 자막이 필요합니다')
    renderer = voice_renderer or local_voice
    voice_key = voice_identity(renderer)
    voice_cache_dir = Path(voice_cache_dir or folder)
    voice_cache_dir.mkdir(parents=True, exist_ok=True)
    durations = []
    audios = []
    metadata = []
    for index, scene in enumerate(scenes):
        if check_current:
            check_current()
        key = digest({'narration': scene['narration'], 'voice': voice_key, 'version': VOICE_CACHE_VERSION})[:24]
        audio = voice_cache_dir / f'voice-{key}.wav'
        info_path = audio.with_suffix('.json')
        cached = json.loads(info_path.read_text(encoding="utf-8")) if info_path.is_file() else None
        if not audio.is_file() or not cached or file_hash(audio) != cached.get('sha256'):
            partial = audio.with_name(audio.name + '.partial.wav')
            try:
                raw_meta = renderer(scene['narration'], partial) or {}
                duration = audio_duration(partial)
                os.replace(partial, audio)
                safe_meta = {k: str(raw_meta[k])[:200] for k in ('voice', 'provider', 'model', 'disclosure') if k in raw_meta}
                cached = {**safe_meta, 'duration': duration, 'sha256': file_hash(audio), 'cache_key': voice_key}
                write_json(info_path, cached)
            finally:
                partial.unlink(missing_ok=True)
        durations.append(audio_duration(audio))
        audios.append(audio)
        metadata.append(cached)
    if sum(durations) > 60:
        raise WorkflowError(f'실제 음성이 60초를 초과합니다 ({sum(durations):.1f}초). 대본 수정이 필요합니다. 성공 음성은 보존했습니다')
    if check_current:
        check_current()
    subtitles = []
    elapsed = 0.0
    paths = list(audios)
    templates = []
    backgrounds = []
    clips = []
    for index, (scene, audio, duration) in enumerate(zip(scenes, audios, durations)):
        if check_current:
            check_current()
        image = folder / f'scene-{index + 1:02}.png'
        background, background_meta = scene_background(background_renderer, folder, index)
        templates.append(draw_scene(plan, scene, index, len(scenes), image, background=background, background_meta=background_meta))
        paths.extend([image, image.with_suffix('.json')] + ([background] if background else []))
        if background_meta:
            backgrounds.append(background_meta)
        generated, generated_meta = scene_clip(clip_renderer, folder, index, background)
        clip = folder / f'clip-{index + 1:02}.mp4'
        clip_meta = clip.with_suffix('.json')
        cached_clip = json.loads(clip_meta.read_text(encoding="utf-8")) if clip_meta.is_file() else {}
        if generated:
            overlay = folder / f'overlay-{index + 1:02}.png'
            draw_scene(plan, scene, index, len(scenes), overlay, overlay_only=True)
            paths.extend([overlay, overlay.with_suffix('.json'), generated])
            clips.append({**generated_meta, 'scene': index + 1, 'sha256': file_hash(generated)})
            clip_key = digest({'generated': file_hash(generated), 'overlay': file_hash(overlay), 'audio': file_hash(audio), 'version': RENDER_VERSION})
            if not clip.is_file() or cached_clip.get('key') != clip_key or cached_clip.get('sha256') != file_hash(clip):
                command(clip_command(generated, overlay, audio, duration, clip), 300)
                write_json(clip_meta, {'key': clip_key, 'sha256': file_hash(clip), 'generated_clip': True})
        else:
            clip_key = digest({'image': file_hash(image), 'audio': file_hash(audio), 'version': RENDER_VERSION})
            if not clip.is_file() or cached_clip.get('key') != clip_key or cached_clip.get('sha256') != file_hash(clip):
                command([executable('ffmpeg'), '-y', '-v', 'error', '-loop', '1', '-framerate', '24', '-i', image, '-i', audio, '-t', str(duration), '-vf', "zoompan=z='min(zoom+0.00035,1.025)':d=1:s=1080x1920:fps=24,setsar=1", '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '24', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ar', '48000', '-ac', '2', '-movflags', '+faststart', clip], 300)
                write_json(clip_meta, {'key': clip_key, 'sha256': file_hash(clip)})
        subtitles.append(f'{index + 1}\n{stamp(elapsed)} --> {stamp(elapsed + duration)}\n{scene['narration']}\n')
        elapsed += duration
    srt = folder / 'captions.srt'
    srt.write_text('\n'.join(subtitles), encoding='utf-8')
    paths.append(srt)
    concat = folder / 'concat.txt'
    concat.write_text('\n'.join((f"file 'clip-{i + 1:02}.mp4'" for i in range(len(scenes)))), encoding='ascii')
    video = folder / 'short.mp4'
    command([executable('ffmpeg'), '-y', '-v', 'error', '-f', 'concat', '-safe', '1', '-i', concat, '-c', 'copy', '-movflags', '+faststart', video], 300)
    info = probe(video)
    streams = info.get('streams', [])
    actual = float(info['format']['duration'])
    v = next((s for s in streams if s.get('codec_type') == 'video'), {})
    a = next((s for s in streams if s.get('codec_type') == 'audio'), {})
    if (v.get('width'), v.get('height')) != (1080, 1920) or not a or abs(actual - elapsed) > 0.3 or (actual > 60):
        raise WorkflowError('영상 해상도·실제 음성·자막 시간 검증 실패')
    paths.append(video)
    thumbs = draw_thumbnails(plan, folder, source_text=source_text)
    paths.append(folder / 'thumbnail-review.json')
    paths.extend(thumbs)
    cover = folder / 'shorts-cover.png'
    shutil.copyfile(folder / 'scene-01.png', cover)
    paths.append(cover)
    media = {'duration': actual, 'speech_duration': elapsed, 'scene_durations': durations, 'voice': metadata[0].get('voice', voice_key), 'voice_provider': metadata[0].get('provider', 'injected'), 'voice_disclosure': metadata[0].get('disclosure', '합성 음성'), 'resolution': [1080, 1920], 'scene_templates': templates, 'visual_review': 'pending', 'listening_review': 'pending', 'synthetic_voice': True}
    if backgrounds:
        media['background'] = background_summary(backgrounds)
    if clips:
        media['clips'] = clip_summary(clips)
    write_json(folder / 'media.json', media)
    paths.append(folder / 'media.json')
    return {'files': paths, 'media': media, 'thumbnails': thumbs, 'backgrounds': backgrounds, 'clips': clips}


def clip_summary(clips):
    first = clips[0]
    return {'provider': str(first.get('provider', 'injected'))[:80], 'model': str(first.get('model', ''))[:80],
            'disclosure': str(first.get('disclosure', '생성 영상 장면'))[:200], 'scenes': [int(c['scene']) for c in clips],
            'count': len(clips)}


def background_summary(backgrounds):
    first = backgrounds[0]
    return {'provider': str(first.get('provider', 'injected'))[:80], 'model': str(first.get('model', ''))[:80],
            'disclosure': str(first.get('disclosure', '생성 배경 이미지'))[:200], 'scenes': len(backgrounds)}

def artifact_record(root, path):
    relative = path.relative_to(root).as_posix()
    sha = file_hash(path)
    asset_id = 'asset_' + digest({'path': relative, 'sha256': sha})[:24]
    kinds = {'.mp4': 'video', '.wav': 'audio', '.png': 'image', '.pdf': 'pdf', '.srt': 'captions', '.html': 'html', '.md': 'markdown', '.txt': 'text', '.json': 'json'}
    return {'id': asset_id, 'name': path.name, 'kind': kinds.get(path.suffix, 'file'), 'url': '/api/artifacts/' + asset_id, 'size': path.stat().st_size, 'sha256': sha, 'path': relative}

@contextmanager
def production_lock(folder):
    lock = folder / '.production.lock'
    fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    acquired = False
    try:
        # Kernel locks are released on process exit, including a killed worker.
        # Keep the inode in place so concurrent workers always lock the same file.
        if os.name == 'nt':
            import msvcrt
            if os.fstat(fd).st_size == 0:
                os.write(fd, b'0')
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        acquired = True
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, str(os.getpid()).encode())
        yield
    except (BlockingIOError, PermissionError) as exc:
        if acquired:
            raise
        raise WorkflowError('같은 원고의 제작이 이미 실행 중입니다') from exc
    finally:
        os.close(fd)

def produce(store, job_id, *, voice_renderer=None, background_renderer=None, clip_renderer=None):
    # This guard must run before directory creation or any external voice or image callback.
    job = store.require_source_approval(job_id)
    source_hash = job['source_hash']
    selections = dict(job['selections'])
    packet = job['source_packet']
    if voice_renderer is None:
        from .voice_selection import renderer_for_job
        voice_renderer = renderer_for_job(store, job)
    if background_renderer is None:
        from .image_selection import background_renderer_for_job
        background_renderer = background_renderer_for_job(store, job)
    if clip_renderer is None:
        from .video_selection import clip_renderer_for_job
        clip_renderer = clip_renderer_for_job(store, job)
    if not re.fullmatch('job_[a-zA-Z0-9_-]+', job_id) or not re.fullmatch('[0-9a-f]{64}', source_hash):
        raise WorkflowError('제작 경로 식별자가 유효하지 않습니다')
    root = store.artifacts.resolve()
    source_folder = root / job_id / source_hash
    from .channels import registry
    channel_registry = registry(store) if selections.get('blog') else None
    contract = production_contract(voice_renderer, selections, image_renderer=background_renderer, clip_renderer=clip_renderer, channel_registry=channel_registry)
    folder = source_folder / ('production-' + contract['hash'][:24])
    voice_cache_dir = root / job_id / 'voices'
    if not folder.resolve().is_relative_to(root) or not voice_cache_dir.resolve().is_relative_to(root):
        raise WorkflowError('제작 경로가 허용 범위를 벗어났습니다')
    folder.mkdir(parents=True, exist_ok=True)

    def check_current():
        current = store.require_source_approval(job_id)
        if current['source_hash'] != source_hash or current['selections'] != selections:
            raise WorkflowError('제작 중 원고 또는 제작 선택이 변경되었습니다. 현재 원고를 다시 승인하세요')
    with production_lock(source_folder):
        check_current()
        files = []
        media = {}
        thumbs = []
        backgrounds = []
        clips = []
        output_status = {}
        output_files = {}
        store.event('production_started', {'source_hash': source_hash, 'role': '영상·자료 제작'}, job_id)
        try:
            def run_output(kind, action):
                nonlocal media, thumbs, backgrounds, clips
                if not selections.get(kind):
                    return
                check_current()
                try:
                    previous = job.get('manifest') or {}
                    if previous.get('production_contract', {}).get('hash') == contract['hash'] and previous.get('output_status', {}).get(kind, {}).get('state') == 'completed':
                        old_records = [record for record in previous.get('files', []) if kind in record.get('outputs', [])]
                        valid = bool(old_records)
                        for record in old_records:
                            path = (root / record['path']).resolve()
                            valid = valid and path.is_relative_to(root) and path.is_file() and file_hash(path) == record['sha256']
                        if valid and kind=='cards':
                            metadata=next((r for r in old_records if r['name'].startswith('card-news-') and r['name'].endswith('.json')),None)
                            current_cards=store.job(job_id).get('cards') or {}
                            valid=bool(metadata and metadata['sha256']==hashlib.sha256(canonical(current_cards).encode('utf-8')).hexdigest())
                        if valid:
                            output_files[kind] = [root / record['path'] for record in old_records]
                            output_status[kind] = {'state': 'completed', 'files': len(output_files[kind])}
                            if kind == 'video':
                                media = previous.get('media', {})
                                thumbs = [root / record['path'] for record in previous.get('thumbnail_candidates', [])]
                            if previous.get('background') and kind in ('video', 'cards') and not backgrounds:
                                backgrounds = [dict(previous['background'])] * int(previous['background'].get('scenes', 1))
                            if previous.get('clips') and kind == 'video' and not clips:
                                clips = [{**previous['clips'], 'scene': scene} for scene in previous['clips'].get('scenes', [])]
                            store.event('output_reused', {'output': kind, 'source_hash': source_hash, 'files': len(old_records)}, job_id)
                            return
                    output_files[kind] = action()
                    output_status[kind] = {'state': 'completed', 'files': len(output_files[kind])}
                    store.event('output_completed', {'output': kind, 'files': len(output_files[kind]), 'source_hash': source_hash}, job_id)
                except Exception as error:
                    # A stale source invalidates every output; an isolated renderer error does not.
                    check_current()
                    message = str(error) if isinstance(error, WorkflowError) else '제작 도구 오류. 운영 기록을 확인하세요'
                    output_status[kind] = {'state': 'failed', 'error': message, 'successful_assets_preserved': True}
                    store.event('output_failed', {'output': kind, 'error': message, 'source_hash': source_hash, 'successful_assets_preserved': True}, job_id)

            def video_output():
                nonlocal media, thumbs, backgrounds, clips
                if contract['font_status'] != 'ready':
                    raise WorkflowError('한국어 폰트를 확인한 뒤 영상 제작을 다시 요청하세요. 유료 음성은 호출하지 않았습니다')
                exports = write_video_exports(packet, folder, job.get('offer'))
                rendered = render_short(packet['video'], folder, voice_renderer=voice_renderer, check_current=check_current, source_text=packet['body'], voice_cache_dir=voice_cache_dir, background_renderer=background_renderer, clip_renderer=clip_renderer)
                media, thumbs = rendered['media'], rendered['thumbnails']
                backgrounds = backgrounds or rendered['backgrounds']
                clips = clips or rendered['clips']
                return exports + rendered['files']

            def card_output():
                from .social_production import card_paths
                check_current()
                if contract['font_status']!='ready':
                    raise WorkflowError('한국어 폰트를 확인한 뒤 카드뉴스 제작을 다시 요청하세요. 새 유료 호출은 하지 않았습니다')
                return card_paths(store,job_id,source_hash,folder)

            from .channel_handoff import write_channel_handoffs
            run_output('blog', lambda: write_blog_exports(packet, folder, job.get('offer')) + write_channel_handoffs(packet, folder, job.get('offer'), source_hash=source_hash, language=(packet.get('audience') or {}).get('language'), channels=channel_registry))
            run_output('video', video_output)
            run_output('cards', card_output)
            run_output('pdf', lambda: [write_reference_pdf(packet, folder, job.get('offer'))])
            completed = [kind for kind, status in output_status.items() if status['state'] == 'completed']
            if not completed:
                reasons = '; '.join(status.get('error', '') for status in output_status.values())
                raise WorkflowError(reasons or '완료된 제작물이 없습니다')
            shared = write_rights_manifest(packet, folder)
            files = [shared] + [path for paths in output_files.values() for path in paths]
            records = [{**artifact_record(root, path), 'outputs': ['shared'] if path == shared else [kind for kind, paths in output_files.items() if path in paths]} for path in sorted(set(files))]
            from .offers import offer_snapshot
            manifest = {'source_hash': source_hash, 'offer_snapshot': offer_snapshot(job.get('offer')), 'production_contract': contract, 'output_status': output_status, 'completed_outputs': completed, 'files': records, 'media': media, 'thumbnail_candidates': [r for r in records if r['name'] in {p.name for p in thumbs}], 'warnings': ['게시·업로드는 실행되지 않았습니다', '완료된 제작물을 선택해 출고 승인②을 받습니다. 영상은 음성 청취와 화면 검토가 필요합니다']}
            if backgrounds and any(kind in completed for kind in ('video', 'cards')):
                manifest['background'] = background_summary(backgrounds)
                manifest['warnings'].append('배경은 생성 이미지이며 한국어 글자는 로컬 레이어입니다. 출고 전 화면 검토가 필요합니다')
            if clips and 'video' in completed:
                manifest['clips'] = clip_summary(clips)
                manifest['warnings'].append('일부 장면은 생성 영상입니다. 손·글자·로고·피사체 변형을 실제로 재생해 확인하세요')
            if thumbs:
                local_reviews = json.loads((folder / 'thumbnail-review.json').read_text(encoding="utf-8"))['candidates']
                by_name = {review['name']: review for review in local_reviews}
                manifest['thumbnail_candidates'] = [{**record, **by_name[record['name']]} for record in manifest['thumbnail_candidates']]
                eligible = [candidate for candidate in manifest['thumbnail_candidates'] if candidate['scores']['source_alignment'] >= 3 and candidate['scores']['title_fit'] >= 3]
                best = max(eligible, key=lambda candidate: (sum(candidate['scores'].values()), candidate['scores']['source_alignment']), default=None)
                manifest['best_candidate_id'] = best['id'] if best else None
                manifest['thumbnail_recommendation_note'] = '로컬 가독성·대비·제목 배치·원고 표현 일치 기준의 검토 제안입니다. 사람의 최종 선택이 필요합니다.'
            manifest['hash'] = digest({'source_hash': source_hash, 'selections': selections, 'production_contract': contract, 'output_status': output_status, 'files': records, 'thumbnail_candidates': manifest['thumbnail_candidates'], 'best_candidate_id': manifest.get('best_candidate_id'), 'version': RENDER_VERSION})
            check_current()
            write_json(folder / 'manifest.json', manifest)
            # The Store transaction closes the check/write race with source edits.
            store.save_manifest_if_current(job_id, source_hash, selections, manifest)
            store.event('production_verified', {'hash': manifest['hash'], 'source_hash': source_hash, 'files': len(records), 'role': 'QA'}, job_id)
            return manifest
        except Exception as exc:
            store.event('production_failed', {'source_hash': source_hash, 'role': '영상·자료 제작', 'reason': str(exc) if isinstance(exc, WorkflowError) else '제작 도구 오류', 'successful_assets_preserved': True}, job_id)
            if isinstance(exc, WorkflowError):
                raise
            raise WorkflowError('제작 중 오류가 발생했습니다. 성공한 자산은 보존했고 외부 게시는 수행하지 않았습니다') from exc
