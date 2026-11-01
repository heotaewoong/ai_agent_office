"""Opt-in EC2 cinematic review bridge; never generates approvals or publishes."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import subprocess
import sys
from pathlib import Path


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def inside(root, candidate):
    root, candidate = Path(root).resolve(), Path(candidate).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError('path outside render storage')
    return candidate


def validate_cues(cues, duration):
    previous = 0
    for c in cues:
        if not (previous <= c['start'] < c['end'] <= duration):
            raise ValueError('caption time overlaps or leaves clip')
        if not all(isinstance(c.get(k), str) and c[k].strip() for k in ('en', 'ko')):
            raise ValueError('missing bilingual caption')
        previous = c['end']


def validate_snapshot(plan, current_source_hash):
    if current_source_hash != plan['source_hash_snapshot']:
        raise ValueError('source version changed; preserve outputs and stop')
    if sha256(plan['source']['path']) != plan['source']['sha256']:
        raise ValueError('input media changed')
    if sha256(plan['skill']['path']) != plan['skill']['sha256']:
        raise ValueError('skill version changed')


def assert_approvals_unchanged(before, after):
    for key in ('source_approval', 'release_approval', 'manifest', 'approved'):
        if before.get(key) != after.get(key):
            raise ValueError('approval or production state changed')


def validate_outputs(files, source, output_root, proof):
    if not proof.get('whole_decode'):
        raise ValueError('whole decode proof required')
    for f in files:
        f = inside(output_root, f)
        if f == Path(source).resolve() or not f.is_file():
            raise ValueError('original input cannot be registered as new output')
        if f.stat().st_size > 32 * 1024**2:
            raise ValueError('review output exceeds existing limit')


def write_new(path, data):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def store_for(args):
    if platform.system() != 'Linux':
        raise ValueError('media execution is EC2-only; local tests may import helpers')
    sys.path.insert(0, str(Path(args.backend_root).resolve()))
    from office.store import Store
    return Store(args.state_root)


def prepare(args):
    store = store_for(args)
    job = store.job(args.job_id)
    if job['source_hash'] != args.expected_hash:
        raise ValueError('source version changed before prepare')
    draft = next(d for d in store.drafts(args.job_id) if d['id'] == args.source_draft)
    if draft.get('source_hash_snapshot') != job['source_hash'] and not args.allow_previous_source_input:
        raise ValueError('previous source input requires explicit user selection')
    asset = next(a for a in draft['assets'] if a['name'] == args.source_name)
    source = inside(store.artifacts, store.artifacts / asset['path'])
    if sha256(source) != asset['sha256']:
        raise ValueError('registered input checksum mismatch')
    skill = Path(args.skill_root).resolve() / 'SKILL.md'
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,90}', args.output_id):
        raise ValueError('invalid output id')
    out = inside(store.artifacts, store.artifacts / args.output_id)
    out.mkdir(exist_ok=False)
    plan = {
        'version': 'cinematic-review-v1', 'mode': 'review-only',
        'job_id': args.job_id, 'source_hash_snapshot': job['source_hash'],
        'source': {'draft_id': draft['id'], 'name': asset['name'],
                   'path': str(source), 'sha256': asset['sha256']},
        'skill': {'path': str(skill), 'sha256': sha256(skill)},
        'output_root': str(out), 'paid_calls': 0, 'public_uploads': 0,
        'human_approval_created': False,
        'source_draft_hash_snapshot': draft.get('source_hash_snapshot'),
        'previous_source_explicitly_selected': draft.get('source_hash_snapshot') != job['source_hash'],
    }
    write_new(out / 'plan.json', plan)
    print(out / 'plan.json')


def verify(args):
    store = store_for(args)
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    validate_snapshot(plan, store.job(plan['job_id'])['source_hash'])
    files, items = [], []
    for name in args.file:
        f = inside(plan['output_root'], Path(plan['output_root']) / name)
        if f == Path(plan['source']['path']).resolve():
            raise ValueError('cannot overwrite original')
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-threads', '1',
                        '-i', str(f), '-f', 'null', '-'], check=True)
        q = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-count_frames',
                        '-show_streams', '-show_format', '-of', 'json', str(f)]))
        v = next(s for s in q['streams'] if s['codec_type'] == 'video')
        if int(v['nb_read_frames']) != args.frames or abs(float(q['format']['duration']) - args.duration) > .1:
            raise ValueError('unexpected frame count or duration')
        if (v['width'], v['height']) != (args.width, args.height):
            raise ValueError('unexpected dimensions')
        files.append(f)
        items.append({'file': f.name, 'sha256': sha256(f), 'frames': args.frames,
                      'duration': float(q['format']['duration']), 'bytes': f.stat().st_size})
    proof = {'plan_sha256': sha256(args.plan), 'skill_sha256': plan['skill']['sha256'],
             'whole_decode': True, 'native_playback': False, 'items': items}
    validate_outputs(files, plan['source']['path'], plan['output_root'], proof)
    write_new(Path(plan['output_root']) / 'verification.json', proof)


def register(args):
    store = store_for(args)
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    before = store.job(plan['job_id'])
    validate_snapshot(plan, before['source_hash'])
    out = Path(plan['output_root'])
    if (out / 'registration.json').exists():
        raise ValueError('already registered; inspect receipt rather than register twice')
    proof = json.loads((out / 'verification.json').read_text(encoding='utf-8'))
    if proof['plan_sha256'] != sha256(args.plan):
        raise ValueError('plan changed after verification')
    files = [inside(out, out / item['file']) for item in proof['items']]
    validate_outputs(files, plan['source']['path'], out, proof)
    for item, f in zip(proof['items'], files):
        if item['sha256'] != sha256(f):
            raise ValueError('output changed after verification')
    from office.editorial_assets import register_assets
    result = register_assets(store, plan['job_id'], plan['source_hash_snapshot'], args.title,
        'Explicit cinematic skill review. Original media preserved; technical checks recorded. '
        'Not a source/release approval or public upload. Skill SHA256: ' + plan['skill']['sha256'],
        [(f.name, f) for f in files])
    assert_approvals_unchanged(before, store.job(plan['job_id']))
    write_new(out / 'registration.json', result)
    print(result['id'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-root', required=True)
    parser.add_argument('--backend-root', required=True)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare')
    for field in ('job-id', 'expected-hash', 'source-draft', 'source-name', 'skill-root', 'output-id'):
        p.add_argument('--' + field, required=True)
    p.set_defaults(run=prepare)
    p.add_argument('--allow-previous-source-input', action='store_true',
                   help='Only when the user explicitly selected this older media input')
    p = sub.add_parser('verify')
    p.add_argument('--plan', required=True)
    p.add_argument('--file', action='append', required=True)
    for field, typ in [('frames', int), ('duration', float), ('width', int), ('height', int)]:
        p.add_argument('--' + field, type=typ, required=True)
    p.set_defaults(run=verify)
    p = sub.add_parser('register')
    p.add_argument('--plan', required=True)
    p.add_argument('--title', required=True)
    p.set_defaults(run=register)
    args = parser.parse_args()
    args.run(args)


if __name__ == '__main__':
    main()
