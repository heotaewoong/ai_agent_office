"""Explicit generated-clip profiles. Changing a profile never invokes or falls back to an API."""
from __future__ import annotations

import argparse
import os

from .store import WorkflowError, canonical, now

PROFILES = {'none': {'name': '생성 영상 없음 · 정지 장면', 'model': None},
            'runway-gen4-turbo': {'name': 'Runway Gen-4 Turbo · 5초 720×1280', 'model': 'gen4_turbo'},
            'runway-gen4.5': {'name': 'Runway Gen-4.5 · 5초 720×1280', 'model': 'gen4.5'}}


def profile_summary(store):
    profile = store.setting('clip_profile', {'id': 'none'})
    identity = profile.get('id')
    if identity not in PROFILES:
        raise WorkflowError('등록되지 않은 생성 영상 프로필입니다')
    paid = identity != 'none'
    return {**profile, 'name': PROFILES[identity]['name'], 'model': PROFILES[identity]['model'], 'paid': paid,
            'automatic_fallback': False, 'job_cap_krw': 3000 if paid else 0, 'max_clips_per_job': 3 if paid else 0,
            'configured': bool(os.environ.get('RUNWAYML_API_SECRET')),
            'key_source': 'RUNWAYML_API_SECRET 환경변수 · 실행하는 운영자가 설정' if paid else None,
            'note': '승인 원고에서 clip: generated로 지정한 장면에만 적용합니다. 배경 이미지 프로필이 함께 켜져 있어야 합니다'}


def select_profile(store, identity, *, actor):
    if identity not in PROFILES or not isinstance(actor, str) or not actor.strip():
        raise WorkflowError('등록된 프로필과 선택한 운영자 정보가 필요합니다')
    record = {'id': identity, 'selected_by': actor[:120], 'selected_at': now()}
    store.set_setting('clip_profile', record)
    store.event('clip_profile_selected', {**record, 'name': PROFILES[identity]['name'], 'automatic_fallback': False, 'paid_call_made': False})
    return profile_summary(store)


def clip_renderer_for_job(store, job):
    profile = profile_summary(store)
    if profile['id'] == 'none' or not job.get('selections', {}).get('video'):
        return None
    from .video_provider import generated_scene_indexes, make_runway_clip_renderer
    scenes = (job.get('source_packet') or {}).get('video', {}).get('scenes', [])
    if not generated_scene_indexes(scenes):
        return None
    return make_runway_clip_renderer(store, job_id=job['id'], allow_paid=True, model=profile['model'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['status', 'set'])
    parser.add_argument('--profile', choices=sorted(PROFILES))
    args = parser.parse_args()
    from .bootstrap import default_store
    store = default_store()
    try:
        if args.command == 'set':
            if not args.profile:
                parser.error('set 명령에는 --profile이 필요합니다')
            print(canonical(select_profile(store, args.profile, actor='local-operator-cli')))
        else:
            print(canonical(profile_summary(store)))
    except WorkflowError as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
