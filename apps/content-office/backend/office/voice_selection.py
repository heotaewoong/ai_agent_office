"""Explicit voice profiles. Changing a profile never invokes or falls back to an API."""
from __future__ import annotations

import argparse
import os

from .store import WorkflowError, canonical, now

PROFILES = {'windows-heami': 'Windows Heami 한국어 · 로컬', 'gemini-kore': 'Gemini3.8 Flash TTS · Kore 한국어',
            'openai-tts': 'OpenAI gpt-4o-mini-tts · 한국어'}
KEY_SOURCES = {'gemini-kore': 'GEMINI_API_KEY 환경변수 · 실행하는 운영자가 설정',
               'openai-tts': 'OPENAI_API_KEY 환경변수 · 실행하는 운영자가 설정'}


def profile_summary(store):
    profile = store.setting('voice_profile', {'id': 'windows-heami'})
    identity = profile.get('id')
    if identity not in PROFILES:
        raise WorkflowError('등록되지 않은 음성 프로필입니다')
    paid = identity in KEY_SOURCES
    configured = {'windows-heami': os.name == 'nt', 'gemini-kore': bool(os.environ.get('GEMINI_API_KEY')),
                  'openai-tts': bool(os.environ.get('OPENAI_API_KEY'))}[identity]
    return {**profile, 'name': PROFILES[identity], 'paid': paid, 'configured': configured, 'key_source': KEY_SOURCES.get(identity),
            'automatic_fallback': False, 'job_cap_krw': 1000 if paid else 0,
            'note': '새 제작 요청에 적용합니다. 기존 결과의 실제 음성은 해당 제작물 메타데이터를 확인하세요'}


def availability(store=None):
    """Whether each voice would actually run on this server right now."""
    api_only = bool(store is not None and store.setting('content_api_only', False))
    windows = os.name == 'nt' and not api_only
    gemini, openai = bool(os.environ.get('GEMINI_API_KEY')), bool(os.environ.get('OPENAI_API_KEY'))
    return {'windows-heami': {'available': windows, 'retired': api_only, 'reason': '콘텐츠 제작은 API 전용입니다. OpenAI 또는 Gemini 음성을 선택하세요' if api_only else ('' if windows else 'Windows PC에서만 동작합니다. 이 서버(Linux)에서는 OpenAI 또는 Gemini 음성을 고르세요')},
            'gemini-kore': {'available': gemini, 'reason': '' if gemini else 'GEMINI_API_KEY가 서버에 없습니다'},
            'openai-tts': {'available': openai, 'reason': '' if openai else 'OPENAI_API_KEY가 서버에 없습니다'}}


def select_profile(store, identity, *, actor):
    if identity == 'windows-heami' and store.setting('content_api_only', False):
        raise WorkflowError('콘텐츠 제작은 API 전용입니다. OpenAI 또는 Gemini 음성을 선택하세요')
    if identity not in PROFILES or not isinstance(actor, str) or not actor.strip():
        raise WorkflowError('등록된 프로필과 선택한 운영자 정보가 필요합니다')
    record = {'id': identity, 'selected_by': actor[:120], 'selected_at': now()}
    store.set_setting('voice_profile', record)
    store.event('voice_profile_selected', {**record, 'name': PROFILES[identity], 'automatic_fallback': False, 'paid_call_made': False})
    return profile_summary(store)


def renderer_for_job(store, job):
    profile = profile_summary(store)
    if profile['id'] == 'windows-heami' and store.setting('content_api_only', False):
        raise WorkflowError('콘텐츠 제작은 API 전용입니다. OpenAI 또는 Gemini 음성을 선택하세요')
    if not job.get('selections', {}).get('video') or profile['id'] == 'windows-heami':
        return None
    if profile['id'] == 'openai-tts':
        from .openai_speech import make_openai_voice_renderer
        return make_openai_voice_renderer(store, job_id=job['id'], allow_paid=True)
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
