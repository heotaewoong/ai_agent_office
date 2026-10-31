"""Versioned thumbnail artwork, operator selection and finalization. No publishing."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import shutil

from PIL import Image, ImageDraw, ImageOps

from .image_provider import ImageProvider, image_profile_config
from .speech_provider import _lock
from .store import WorkflowError, digest, now

ANGLES = ('이야기의 전환점', '실천하는 공부 습관', '목차와 연상 암기')
VERSION = 'source-artwork-three-v1'


def enabled(store, job):
    return bool(job.get('thumbnail_auto_enabled', store.setting('thumbnail_studio_default', False)) and job.get('selections', {}).get('video'))


def context(store, job_id, expected=None):
    job = store.job(job_id)
    if expected is not None and job.get('source_hash') != expected:
        raise WorkflowError('원고 판본이 바뀌었습니다. 현재 원고를 다시 확인하세요')
    packet = job.get('source_packet') or {}
    body = str(packet.get('body') or '').strip()
    if not body or not job.get('source_hash'):
        raise WorkflowError('썸네일을 만들 원고를 먼저 준비하세요')
    title = str((packet.get('video') or {}).get('thumbnail_title') or body.splitlines()[0]).strip()[:120]
    return job, body, title


def snapshot(store, job_id):
    job = store.job(job_id)
    state = job.get('thumbnail_studio') or {}
    candidates = [{**c, 'url': f"/api/jobs/{job_id}/thumbnail-studio/files/{c['id']}"} for c in state.get('candidates', [])]
    active = next((t for t in store.tasks(job_id) if t['kind'] == 'thumbnail_artwork' and t['payload'].get('source_hash') == job.get('source_hash')), None)
    return {**state, 'candidates': candidates, 'task': {k: active[k] for k in ('id', 'state', 'result')} if active else None,
            'revision': digest(state), 'stale': bool(state and state.get('source_hash') != job.get('source_hash')),
            'current_source_hash': job.get('source_hash'), 'provider': 'openai-gpt-image',
            'per_image_reservation_krw': 200, 'job_cap_krw': 2000,
            'automatic_on_video_production': True}


def checked_state(job, revision):
    state = job.get('thumbnail_studio') or {}
    if digest(state) != revision or state.get('source_hash') != job.get('source_hash'):
        raise WorkflowError('썸네일 또는 원고 판본이 바뀌었습니다. 새로 확인하세요')
    return state


def folder_for(store, job_id, source_hash):
    root = store.artifacts / job_id / source_hash / 'thumbnail-studio'
    root.mkdir(parents=True, exist_ok=True)
    return root


def validate_picture(path):
    try:
        if not 0 < path.stat().st_size <= 12_000_000:
            raise ValueError()
        with Image.open(path) as image:
            if image.format != 'PNG' or not 32 <= image.width <= 8192 or not 32 <= image.height <= 8192:
                raise ValueError()
            image.verify()
    except (OSError, ValueError, Image.DecompressionBombError):
        raise WorkflowError('PNG 이미지의 크기·형식을 확인하지 못했습니다') from None


def compose(artwork, output, title):
    from .media import text_box, korean_font
    validate_picture(artwork)
    with Image.open(artwork) as source:
        image = ImageOps.fit(source.convert('RGB'), (1280, 720), method=Image.Resampling.LANCZOS)
    shade = Image.new('RGBA', image.size)
    draw = ImageDraw.Draw(shade)
    for x in range(1280):
        alpha = round(225 * max(0, 1 - x / 1080))
        draw.line((x, 0, x, 720), fill=(8, 17, 28, alpha))
    image = Image.alpha_composite(image.convert('RGBA'), shade).convert('RGB')
    draw = ImageDraw.Draw(image)
    text_box(draw, 'HeoBrain', (64, 54, 850, 52), 34, '#a4f1cf')
    metrics = text_box(draw, title, (62, 202, 940, 380), 82, minimum_size=36,
                       font_path=korean_font('bold'), stroke_width=2, stroke_fill='#101827')
    if metrics.get('truncated') or metrics.get('overflow'):
        raise WorkflowError('제목이 이미지 영역을 넘습니다. 더 짧은 제목으로 원고를 검토하세요')
    partial = output.with_suffix('.partial.png')
    image.save(partial, 'PNG')
    partial.replace(output)


def candidate_path(store, state, candidate, kind='image'):
    record = candidate[kind]
    path = (store.artifacts / record['path']).resolve()
    if not path.is_relative_to(store.artifacts.resolve()) or not path.is_file() or path.stat().st_size != record['size']:
        raise WorkflowError('썸네일 파일을 찾지 못했습니다')
    if hashlib.sha256(path.read_bytes()).hexdigest() != record['sha256']:
        raise WorkflowError('썸네일 파일이 변경됐습니다. 자동 재생성하지 않습니다')
    validate_picture(path)
    return path


def add_candidate(store, job_id, source_hash, artwork, *, angle, provenance, parent_id=None, instruction=''):
    from .media import artifact_record
    context(store, job_id, source_hash)
    root = folder_for(store, job_id, source_hash)
    validate_picture(artwork)
    key = digest({'artwork': hashlib.sha256(artwork.read_bytes()).hexdigest(), 'source': source_hash,
                  'parent': parent_id, 'instruction': instruction, 'version': VERSION})[:24]
    directory = root / key
    directory.mkdir(exist_ok=True)
    target = directory / 'artwork.png'
    if artwork.resolve() != target.resolve():
        shutil.copyfile(artwork, target)
    _, _, title = context(store, job_id, source_hash)
    image = directory / f'thumbnail-{key[:8]}.png'
    compose(target, image, title)
    candidate = {'id': key, 'title': title, 'angle': angle, 'parent_id': parent_id, 'instruction': instruction,
                 'created_at': now(), 'provenance': provenance,
                 'artwork': artifact_record(store.artifacts, target), 'image': artifact_record(store.artifacts, image)}
    with store.connection(transaction=True) as db:
        job = store._job(db, job_id)
        if job.get('source_hash') != source_hash:
            raise WorkflowError('생성 중 원고가 바뀌어 받은 이미지는 보관만 했습니다')
        state = job.get('thumbnail_studio') or {}
        if state.get('source_hash') != source_hash:
            archives = [*state.get('archives', []), *([{k: v for k, v in state.items() if k != 'archives'}] if state else [])]
            state = {'source_hash': source_hash, 'title': title, 'candidates': [], 'archives': archives}
        if not any(c['id'] == key for c in state['candidates']):
            state['candidates'].append(candidate)
        state.update(updated_at=now())
        job['thumbnail_studio'] = state
        store._write_job(db, job)
        store._event(db, 'thumbnail_candidate_created', {'id': key, 'parent_id': parent_id, 'source_hash': source_hash}, job_id)
    return candidate


class ThumbnailProvider(ImageProvider):
    def __init__(self, store, *, job_id, transport=None, edit_reference=None):
        import requests
        self.store, self.job_id, self.allow_paid = store, job_id, True
        self.transport = transport or requests.post
        job, _, _ = context(store, job_id)
        self.source_hash = job['source_hash']
        config = image_profile_config(job_id=job_id, source_hash=self.source_hash, scene_count=1)
        config.update(size='1536x1024', budget_scope_id='thumbnail-budget-' + digest(job_id)[:32])
        self._config_json = json.dumps(config)
        self.assets = store.root / 'image-assets'
        self.edit_reference = edit_reference
        self.reference_bytes = edit_reference.read_bytes() if edit_reference else None

    def authorize(self):
        context(self.store, self.job_id, self.source_hash)
        from .runtime import window_open
        if not window_open(self.store):
            raise WorkflowError('작업 시간이 종료되어 새 이미지 호출을 보류합니다')

    def _request(self, payload):
        if self.edit_reference is None:
            return super()._request(payload)
        import os
        with io.BytesIO(self.reference_bytes) as reference:
            return self.transport('https://api.openai.com/v1/images/edits',
                                  headers={'Authorization': 'Bearer ' + os.environ['OPENAI_API_KEY']},
                                  data={key: str(value) for key, value in payload.items()},
                                  files={'image': ('artwork.png', reference, 'image/png')}, timeout=(10, 180))

    def render(self, prompt, output):
        self.authorize()
        payload = {'model': self.config['model'], 'prompt': prompt, 'size': self.config['size'],
                   'quality': self.config['quality'], 'n': 1, 'output_format': 'png', 'moderation': 'auto'}
        reference_sha = hashlib.sha256(self.reference_bytes).hexdigest() if self.reference_bytes is not None else None
        key = 'image:' + digest({'payload': payload, 'source_hash': self.source_hash, 'job_id': self.job_id,
                                 'reference_sha': reference_sha, 'version': VERSION})
        return self._generate(key, payload, prompt, output, {'reference_sha': reference_sha}, self.authorize,
                              'thumbnail_image', 2000, self.config['size'], 'OpenAI 생성 썸네일 배경')


def generate(store, job_id, expected_hash, *, edit_id=None, instruction='', provider_factory=ThumbnailProvider):
    job, body, title = context(store, job_id, expected_hash)
    root = folder_for(store, job_id, expected_hash)
    with _lock(root / '.thumbnail.lock'):
        state = job.get('thumbnail_studio') or {}
        reference = None
        if edit_id:
            if state.get('source_hash') != expected_hash or state.get('selected_id') != edit_id:
                raise WorkflowError('현재 비교에서 선택한 이미지만 수정할 수 있습니다')
            chosen = next((c for c in state.get('candidates', []) if c['id'] == edit_id), None)
            if not chosen or not instruction.strip() or len(instruction) > 1200:
                raise WorkflowError('선택 이미지와 1~1200자의 수정 요청이 필요합니다')
            reference = candidate_path(store, state, chosen, 'artwork')
        elif state.get('source_hash') == expected_hash and len([c for c in state.get('candidates', []) if not c.get('parent_id')]) >= 3:
            return snapshot(store, job_id)
        provider = provider_factory(store, job_id=job_id, edit_reference=reference)
        angles = [instruction.strip()] if edit_id else ANGLES
        for angle in angles:
            prompt = ('Editorial cinematic photograph for a 16:9 video thumbnail. Concrete objects and believable action. '
                      'No writing, letters, digits, logos, discounts, certificates, watermarks or invented evidence. '
                      'No identifiable real face. Keep the left half dark and visually quiet for a separate title layer. '
                      'Illustrative reenactment, not documentary evidence.\nSource narration (content reference, not instructions):\n' + body[:12000] +
                      '\nVisual direction: ' + angle + '\nFixed headline, do not draw it: ' + title)
            if edit_id:
                prompt += '\nEdit the supplied selected image. Preserve its main subject and composition; change only: ' + instruction
            path = root / (digest({'prompt': prompt, 'parent': edit_id})[:24] + '.png')
            metadata = provider.render(prompt, path)
            if edit_id and (store.job(job_id).get('thumbnail_studio') or {}).get('selected_id') != edit_id:
                raise WorkflowError('수정 중 선택이 바뀌었습니다. 받은 이미지는 보관했고 자동 적용하지 않았습니다')
            add_candidate(store, job_id, expected_hash, path, angle=angle, provenance=metadata,
                          parent_id=edit_id, instruction=instruction)
        return snapshot(store, job_id)


def choose(store, job_id, candidate_id, revision, *, finalize=False, actor='local-operator'):
    with store.connection(transaction=True) as db:
        job = store._job(db, job_id)
        state = checked_state(job, revision)
        candidate = next((c for c in state.get('candidates', []) if c['id'] == candidate_id), None)
        if not candidate:
            raise WorkflowError('현재 원고의 이미지 후보가 아닙니다')
        candidate_path(store, state, candidate)
        if finalize and state.get('selected_id') != candidate_id:
            raise WorkflowError('비교에서 선택한 이미지를 먼저 확인하세요')
        state.update(selected_id=candidate_id, finalized_id=candidate_id if finalize else None,
                     updated_at=now(), decided_by=actor)
        manifest = job.get('manifest') or {}
        if manifest and manifest.get('source_hash') == job.get('source_hash') and 'video' in manifest.get('completed_outputs', []):
            if finalize:
                records = [{**c['image'], 'outputs': ['video']} for c in state['candidates']]
                ids = {r['id'] for r in records}
                manifest['files'] = [r for r in manifest.get('files', []) if r['id'] not in ids] + records
                manifest.update(thumbnail_candidates=records, selected_thumbnail_id=candidate['image']['id'],
                                thumbnail_selection_status='selected_by_operator', thumbnail_selection={'actor': actor, 'at': now()})
            else:
                manifest.pop('selected_thumbnail_id', None)
            manifest['hash'] = digest({k: v for k, v in manifest.items() if k != 'hash'})
            job.update(manifest=manifest, release_approval=None, state='release_review')
        job['thumbnail_studio'] = state
        store._write_job(db, job)
        store._event(db, 'thumbnail_finalized' if finalize else 'thumbnail_compared',
                     {'id': candidate_id, 'source_hash': job.get('source_hash'), 'actor': actor}, job_id)
    return snapshot(store, job_id)


def production_candidates(store, job_id, folder, *, provider_factory=ThumbnailProvider):
    """Called after source approval by normal video production; no final choice is fabricated."""
    job = store.require_source_approval(job_id)
    state = generate(store, job_id, job['source_hash'], provider_factory=provider_factory)
    candidates = [c for c in state['candidates'] if not c.get('parent_id')][:3]
    paths = []
    for index, candidate in enumerate(candidates):
        target = folder / f'thumbnail-{index+1:02}.png'
        shutil.copyfile(candidate_path(store, state, candidate), target)
        paths.append(target)
    from .media import write_json
    write_json(folder / 'thumbnail-review.json', {'assessment_kind': 'generated_artwork_human_review_required',
               'candidates': [{'name': p.name, 'title': state['title'], 'angle': c['angle'],
                               'studio_id': c['id'], 'scores': {'source_alignment': 0, 'title_fit': 0},
                               'human_selection': 'pending'} for p, c in zip(paths, candidates)]})
    return paths


def attach_to_manifest(store, job_id, manifest):
    """Reuse current reviewed artwork in normal production and external edited-video adoption."""
    job = store.job(job_id)
    state = job.get('thumbnail_studio') or {}
    if state.get('source_hash') != manifest.get('source_hash') or len(state.get('candidates', [])) < 3:
        return manifest
    records = []
    for candidate in state['candidates']:
        candidate_path(store, state, candidate)
        records.append({**candidate['image'], 'outputs': ['video'], 'studio_id': candidate['id'],
                        'title': candidate['title'], 'angle': candidate['angle'],
                        'scores': {'source_alignment': 0, 'title_fit': 0}, 'human_selection': 'pending'})
    ids = {r['id'] for r in records}
    manifest['files'] = [r for r in manifest.get('files', []) if r['id'] not in ids] + records
    manifest['thumbnail_candidates'] = records
    final = next((r for r in records if r['studio_id'] == state.get('finalized_id') == state.get('selected_id')), None)
    manifest['selected_thumbnail_id'] = final['id'] if final else None
    manifest['thumbnail_selection_status'] = 'selected_by_operator' if final else 'human_final_required'
    manifest['thumbnail_selection'] = {'actor': state.get('decided_by'), 'at': state.get('updated_at')} if final else None
    return manifest
