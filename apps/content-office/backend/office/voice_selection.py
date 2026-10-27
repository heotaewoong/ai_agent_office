"""Explicit voice profiles. Changing a profile never invokes or falls back to an API."""
from __future__ import annotations

import argparse

from .store import WorkflowError, canonical, now

PROFILES = {'windows-heami': 'Windows Heami 한국어 · 로컬', 'gemini-kore': 'Gemini3.8 Flash TTS · Kore 한국어'}


def profile_summary(store):
    profile = store.setting('voice_profile', {'id': 'windows-heami'})
    identity = profile.get('id')
    if identity not in PROFILES:
        raise WorkflowError('등록되지 않은 음성 프로필입니다')
    return {**profile, 'name': PROFILES[identity], 'paid': identity == 'gemini-kore',
            'automatic_fallback': False, 'job_cap_krw': 1000 if identity == 'gemini-kore' else 0,
            'note': '새 제작 요청에 적용합니다. 기존 결과의 실제 음성은 해당 제작물 메타데이터를 확인하세요'}


def select_profile(store, identity, *, actor):
    if identity not in PROFILES or not isinstance(actor, str) or not actor.strip():
        raise WorkflowError('등록된 프로필과 선택한 운영자 정보가 필요합니다')
    record = {'id': identity, 'selected_by': actor[:120], 'selected_at': now()}
    store.set_setting('voice_profile', record)
    store.event('voice_profile_selected', {**record, 'name': PROFILES[identity], 'automatic_fallback': False, 'paid_call_made': False})
    return profile_summary(store)


def renderer_for_job(store, job):
    profile = profile_summary(store)
    if not job.get('selections', {}).get('video') or profile['id'] == 'windows-heami':
        return None
    from .speech_provider import make_gemini_voice_renderer
    return make_gemini_voice_renderer(store, job_id=job['id'], allow_paid=True, voice='Kore', synthetic_only=False)


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
