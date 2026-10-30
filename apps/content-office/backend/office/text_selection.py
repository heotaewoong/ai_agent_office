"""Explicit text (원고·검수·퀴즈·카드) model profiles. Changing a profile never calls a provider or falls back."""
from __future__ import annotations

import argparse
import os

from .providers import OPENAI_PRICES, PRICES, provider_for
from .store import WorkflowError, canonical, now

PROFILES = {
    "codex-subscription-text": "Codex 구독 · 글·검수",
    'gemini-3.8-flash': 'Gemini 3.8 Flash · 글',
    'gemini-3.5-flash-lite': 'Gemini 3.5 Flash-Lite · 글 (가벼움)',
    'gpt-5.4-mini': 'OpenAI gpt-5.4-mini · 글',
    'gpt-5.5': 'OpenAI gpt-5.5 · 글 (최상급)',
}
DEFAULT = 'gemini-3.8-flash'
KEY_SOURCE = {'gemini': 'GEMINI_API_KEY 환경변수 · 실행하는 운영자가 설정', 'openai': 'OPENAI_API_KEY 환경변수 · 실행하는 운영자가 설정'}
KEY_ENV = {'gemini': 'GEMINI_API_KEY', 'openai': 'OPENAI_API_KEY'}


def current_model(store):
    model = store.setting('model') or os.environ.get('OFFICE_MODEL', DEFAULT)
    return model if model in PROFILES else DEFAULT


def profile_summary(store):
    identity = current_model(store)
    if identity == "codex-subscription-text":
        from .codex_text_provider import subscription_status
        return {**store.setting("text_profile", {"id": identity}), "id": identity, "name": PROFILES[identity], "model": identity, "provider": "codex-subscription", "paid": False, "automatic_fallback": False, **subscription_status(), "key_source": "앱 실행 계정의 Codex ChatGPT 로그인", "note": "구독 한도 사용. 원고·검수·퀴즈·카드 문구에 적용하며 API로 자동 전환하지 않습니다"}
    provider = provider_for(identity)
    price = (OPENAI_PRICES if provider == 'openai' else PRICES)[identity]
    record = store.setting('text_profile', {'id': identity})
    if record.get('id') != identity:
        record = {'id': identity}
    return {**record, 'name': PROFILES[identity], 'model': identity, 'provider': provider, 'paid': True, 'automatic_fallback': False,
            'configured': bool(os.environ.get(KEY_ENV[provider])), 'key_source': KEY_SOURCE[provider],
            'price_usd_per_million': {'input': price['input_usd_million'], 'output': price['output_usd_million']},
            'note': '원고 생성·비평·평가·수정·국어 검수·퀴즈·카드뉴스 호출에 쓰는 모델입니다. 새 요청부터 적용되며 실패해도 다른 제공자로 넘어가지 않습니다'}


def select_profile(store, identity, *, actor):
    if identity not in PROFILES or not isinstance(actor, str) or not actor.strip():
        raise WorkflowError('등록된 프로필과 선택한 운영자 정보가 필요합니다')
    record = {'id': identity, 'selected_by': actor[:120], 'selected_at': now()}
    store.set_setting('text_profile', record)
    store.set_setting('model', identity)
    store.event('text_profile_selected', {**record, 'name': PROFILES[identity], 'provider': 'codex-subscription' if identity == 'codex-subscription-text' else provider_for(identity), 'automatic_fallback': False, 'paid_call_made': False})
    return profile_summary(store)


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
