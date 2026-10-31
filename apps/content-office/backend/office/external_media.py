"""Import verified edited media without fabricating model QA or human approval."""
from __future__ import annotations
import hashlib
import json
import re
import shutil
import subprocess
from .store import WorkflowError, digest

REQUIRED = ('short.mp4', 'source-original.md', 'captions.srt', 'thumbnail-01.png', 'description.txt')
BUSY = ('drafting', 'production_queued', 'producing', 'needs_reconciliation')


def files_for(store, job, draft_id):
    draft = next((d for d in store.drafts(job['id']) if d['id'] == draft_id), None)
    if not draft:
        raise WorkflowError('연결할 편집 검토본이 없습니다')
    records = {a['name']: a for a in draft.get('assets', [])}
    if not set(REQUIRED).issubset(records):
        raise WorkflowError('영상·원문·자막·표지·설명 5개 파일이 필요합니다')
    paths, root = {}, store.artifacts.resolve()
    for name in REQUIRED:
        a = records[name]
        path = (root / a['path']).resolve()
        if not path.is_relative_to(root) or not path.is_file() or not 0 < path.stat().st_size <= 100_000_000:
            raise WorkflowError('편집 파일 경로·크기가 올바르지 않습니다')
        checksum = hashlib.sha256()
        with path.open('rb') as content:
            for chunk in iter(lambda: content.read(1024 * 1024), b''):
                checksum.update(chunk)
        if path.stat().st_size != a['size'] or checksum.hexdigest() != a['sha256']:
            raise WorkflowError('편집 파일이 등록 당시와 다릅니다')
        paths[name] = path
    return draft, records, paths


def _probe(path, decode=False):
    try:
        result = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)], timeout=45))
        video = next(x for x in result['streams'] if x['codec_type'] == 'video')
        audio = next(x for x in result['streams'] if x['codec_type'] == 'audio')
        seconds = float(result['format']['duration'])
        if not 0 < seconds <= 120 or video.get('codec_name') != 'h264' or audio.get('codec_name') != 'aac' or not 0 < video.get('width',0) <= 4096 or not 0 < video.get('height',0) <= 4096:
            raise ValueError()
        if decode:
            check = subprocess.run(['nice', '-n', '15', 'ffmpeg', '-v', 'error', '-threads', '1', '-i', str(path), '-f', 'null', '-'], capture_output=True, timeout=180)
            if check.returncode or check.stderr:
                raise ValueError()
        return {'seconds': seconds, 'width': video['width'], 'height': video['height'], 'codec': 'h264/aac', 'full_decode': decode}
    except (ValueError, KeyError, StopIteration, OSError, subprocess.SubprocessError):
        raise WorkflowError('영상·음성 스트림이나 전체 재생 검사를 통과하지 못했습니다') from None


def _text(path):
    if path.stat().st_size > 100_000:
        raise WorkflowError('검토 텍스트가 너무 큽니다')
    try:
        return path.read_text('utf8')
    except UnicodeError:
        raise WorkflowError('원문·자막의 UTF-8 형식을 확인하세요') from None


def validate_packet(store, job):
    packet = job.get('source_packet') or {}
    spec = packet.get('external_media') or {}
    if spec.get('version') != 'external-media-v1' or spec.get('scope') != 'private_review_only':
        raise WorkflowError('기존 편집본 연결 명세가 없습니다')
    _, records, paths = files_for(store, job, spec.get('draft_id'))
    if {n: records[n]['sha256'] for n in REQUIRED} != spec.get('asset_hashes') or packet.get('body') != _text(paths['source-original.md']):
        raise WorkflowError('검토 원문 또는 연결 파일 판본이 변경되었습니다')
    if packet.get('source_input_hash') != digest(packet['body']):
        raise WorkflowError('원문 보존 해시가 다릅니다')
    return records, paths


def prepare_review(store, job_id, draft_id, expected_hash):
    job = store.job(job_id)
    if job.get('source_hash') != expected_hash or job['state'] in BUSY:
        raise WorkflowError('현재 원고 판본·작업 상태를 다시 확인하세요')
    draft, records, paths = files_for(store, job, draft_id)
    if draft.get('source_hash_snapshot') != expected_hash:
        raise WorkflowError('이전 원고의 검토본입니다. 현재 원고와 대조해 다시 등록하세요')
    text, caption = _text(paths['source-original.md']), _text(paths['captions.srt'])
    spoken = []
    timings = []
    for chunk in re.split(r'\n\s*\n', caption.strip()):
        lines = chunk.splitlines()
        timing = next((i for i, line in enumerate(lines) if '-->' in line), None)
        if timing is None:
            raise WorkflowError('자막 시간 형식이 올바르지 않습니다')
        match = re.fullmatch(r'(\d{2}):([0-5]\d):([0-5]\d),(\d{3}) --> (\d{2}):([0-5]\d):([0-5]\d),(\d{3})', lines[timing])
        if not match:
            raise WorkflowError('자막 시간 형식이 올바르지 않습니다')
        numbers = [int(x) for x in match.groups()]
        clock = lambda q: q[0] * 3600 + q[1] * 60 + q[2] + q[3] / 1000
        timings.append((clock(numbers[:4]), clock(numbers[4:])))
        spoken.extend(lines[timing + 1:])
    normalize = lambda value: re.sub(r'\s+', '', value)
    if not text.strip() or normalize(text) != normalize(''.join(spoken)):
        raise WorkflowError('원문과 전체 자막 문장이 일치하지 않습니다')
    info = _probe(paths['short.mp4'])
    previous_end = 0.0
    for start, end in timings:
        if start < previous_end - 0.01 or end <= start or end > info['seconds'] + 0.1:
            raise WorkflowError('자막 시간 범위·순서가 영상과 다릅니다')
        previous_end = end
    packet = {
        'title': draft['title'], 'body': text, 'preserve_original': True,
        'source_input_hash': digest(text), 'audience': {'language': 'ko'}, 'evidence': [],
        'video': {'title': draft['title'], 'description': _text(paths['description.txt']), 'tags': [],
                  'scenes': [{'narration': text, 'caption': '기존 편집본의 전체 자막 사용', 'visual': '기존 편집 영상 그대로'}]},
        'quality': {'status': 'external_review_required', 'critical': False, 'reviews': [],
                    'note': '모델 검수 통과가 아닙니다. 원문·음성·자막·권리·혜택 표현을 사람이 직접 확인해야 합니다.'},
        'external_media': {'version': 'external-media-v1', 'draft_id': draft_id,
                           'asset_hashes': {n: records[n]['sha256'] for n in REQUIRED},
                           'technical': info, 'scope': 'private_review_only'},
    }
    return store.save_source(job_id, packet, expected_hash=expected_hash)


def adopt_reviewed(store, job_id, expected_hash, reviewed):
    job = store.job(job_id)
    if reviewed is not True or job.get('source_hash') != expected_hash or job['state'] in BUSY:
        raise WorkflowError('현재 판본을 직접 검토한 뒤 원고 승인①이 필요합니다')
    records, paths = validate_packet(store, job)
    selections = {'video': True, 'blog': True, 'cards': False, 'pdf': False}
    approval = job.get('source_approval') or {}
    if approval.get('version') != expected_hash or approval.get('decision') != 'approved' or approval.get('selections') != selections:
        job = store.review_source(job_id, expected_hash, 'approved', 'local-operator', selections, external_media_reviewed=True)
    else:
        job = store.require_source_approval(job_id)
    if job.get('manifest') and job['manifest'].get('imported_external_media') == job['source_packet']['external_media']:
        return job
    _probe(paths['short.mp4'], decode=True)
    folder = store.artifacts / job_id / expected_hash / ('external-' + digest(job['source_packet']['external_media'])[:16])
    folder.mkdir(parents=True, exist_ok=True)
    for name, path in paths.items():
        target = folder / name
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest() != records[name]['sha256']:
                raise WorkflowError('기존 가져오기 파일이 달라 덮어쓰지 않았습니다')
        else:
            shutil.copyfile(path, target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != records[name]['sha256']:
            raise WorkflowError('파일 복사 중 편집본이 변경되었습니다')
    from .exports import write_blog_exports, write_video_exports
    packet = job['source_packet']
    blog = write_blog_exports(packet, folder)
    video_exports = write_video_exports(packet, folder)
    (folder / 'asset-rights.json').write_text(json.dumps({
        'mode': 'imported_edited_media', 'operator_attested_for': 'private_review_only',
        'public_distribution_cleared': False, 'assets': packet['external_media']['asset_hashes'],
        'note': '본인 음성·AI 재연·후기·혜택 표현의 비공개 검토입니다. 공개 사용 승인 아님.',
    }, ensure_ascii=False), 'utf8')
    from .media import artifact_record
    blog_names = {p.name for p in blog}
    video_names = {p.name for p in video_exports} | {'short.mp4', 'captions.srt', 'thumbnail-01.png'}
    for name in ['instagram-main-caption.txt', 'threads-main.txt', 'linkedin-personal.txt']:
        (folder / name).write_text(packet['title'] + '\n\n' + packet['body'] + '\n\n' + packet['video']['description'], 'utf8')
        blog_names.add(name)
    names = sorted(blog_names | video_names | {'source-original.md', 'asset-rights.json'})
    assets = [{**artifact_record(store.artifacts, folder / name), 'outputs': ['shared'] if name in ['source-original.md', 'asset-rights.json'] else (['blog'] if name in blog_names else ['video'])} for name in names]
    manifest = {
        'source_hash': expected_hash, 'files': assets, 'completed_outputs': ['blog', 'video'],
        'output_status': {'blog': {'state': 'completed'}, 'video': {'state': 'completed'}},
        'thumbnail_candidates': [a for a in assets if a['name'] == 'thumbnail-01.png'], 'selected_thumbnail_id': None,
        'imported_external_media': packet['external_media'], 'production_method': 'imported_edited_media',
        'warnings': ['재렌더·새 모델 호출 없이 기존 편집본을 가져왔습니다', '비공개 검토용입니다. 공개 게시 전에 권리·혜택을 재검수하세요', '표지를 선택하고 영상·음성·자막 확인 후 출고 승인②을 해주세요'],
    }
    manifest['hash'] = digest(manifest)
    (folder / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), 'utf8')
    return store.save_manifest_if_current(job_id, expected_hash, selections, manifest)
