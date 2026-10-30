"""Explicit background image profiles. Changing a profile never invokes or falls back to an API."""
from __future__ import annotations

import argparse
import os

from .store import WorkflowError, canonical, now

PROFILES = {'none': '생성 배경 없음 · 글자 카드만', 'openai-gpt-image': 'OpenAI gpt-image-2.5 배경 · 한국어 글자는 로컬 레이어',
            'codex-subscription': 'Codex 구독(ChatGPT 로그인) 배경 · 한국어 글자는 로컬 레이어'}


def profile_summary(store):
    profile = store.setting('image_profile', {'id': 'none'})
    identity = profile.get('id')
    if identity not in PROFILES:
        raise WorkflowError('등록되지 않은 이미지 프로필입니다')
    paid = identity == 'openai-gpt-image'
    openai_configured = bool(os.environ.get('OPENAI_API_KEY'))
    summary = {**profile, 'name': PROFILES[identity], 'paid': paid, 'automatic_fallback': False,
               'job_cap_krw': 2000 if paid else 0, 'configured': openai_configured, 'openai_configured': openai_configured,
               'key_source': 'OPENAI_API_KEY 환경변수 · 실행하는 운영자가 설정' if paid else None,
               'note': '새 제작 요청에 적용합니다. 기존 결과의 실제 배경은 해당 제작물 메타데이터를 확인하세요'}
    if identity == 'codex-subscription':
        from .codex_image_provider import codex_status, used_today
        status = codex_status()
        summary.update(configured=status['configured'], daily_cap_images=status['daily_cap_images'], used_today=used_today(store),
                       key_source='ChatGPT 로그인 · 앱 실행 계정에서 codex login (API 키 사용 안 함)')
    return summary


def availability(store=None):
    """Whether each background option would actually run on this server right now (same checks as `configured`)."""
    from .codex_image_provider import codex_status
    openai = bool(os.environ.get('OPENAI_API_KEY'))
    codex = codex_status()['configured']
    return {'none': {'available': True, 'reason': ''},
            'openai-gpt-image': {'available': openai, 'reason': '' if openai else 'OPENAI_API_KEY가 서버에 없습니다'},
            'codex-subscription': {'available': codex, 'reason': '' if codex else '이 서버의 앱 계정에 codex CLI 설치와 ChatGPT 로그인(codex login)이 없습니다'}}


def select_profile(store, identity, *, actor):
    if identity not in PROFILES or not isinstance(actor, str) or not actor.strip():
        raise WorkflowError('등록된 프로필과 선택한 운영자 정보가 필요합니다')
    record = {'id': identity, 'selected_by': actor[:120], 'selected_at': now()}
    store.set_setting('image_profile', record)
    store.event('image_profile_selected', {**record, 'name': PROFILES[identity], 'automatic_fallback': False, 'paid_call_made': False})
    return profile_summary(store)


def background_renderer_for_job(store, job):
    profile = profile_summary(store)
    selections = job.get('selections', {})
    if profile['id'] == 'none' or not (selections.get('video') or selections.get('cards')):
        return None
    if profile['id'] == 'codex-subscription':
        from .codex_image_provider import make_codex_background_renderer
        return make_codex_background_renderer(store, job_id=job['id'])
    from .image_provider import make_openai_background_renderer
    return make_openai_background_renderer(store, job_id=job['id'], allow_paid=True)


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
