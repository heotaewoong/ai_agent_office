"""Explicit production migration; preserves jobs, approvals, budgets and unknown costs."""
import os
import json
from .store import WorkflowError, canonical, now

KEY = 'content_api_only'
REASON = '콘텐츠 제작은 API 전용으로 전환됐습니다. 제작 설정에서 API 모델을 선택하세요'


def require_subscription_allowed(store):
    if store.setting(KEY, False):
        raise WorkflowError(REASON)


def activate(store, *, text_model, actor, preserve_dormant_cost_ids=()):
    from .text_selection import PROFILES
    from .providers import provider_for
    if not isinstance(actor, str) or not actor.strip() or text_model not in PROFILES or provider_for(text_model) != 'openai':
        raise WorkflowError('API 전환의 글 모델과 담당자를 확인하세요')
    if not os.environ.get('OPENAI_API_KEY'):
        raise WorkflowError('OPENAI_API_KEY가 없어 제작 경로를 바꾸지 않았습니다')
    with store.connection(transaction=True) as db:
        if db.execute("SELECT 1 FROM tasks WHERE state='running' OR (state='queued' AND kind!='refresh')").fetchone():
            raise WorkflowError('진행 중이거나 대기 중인 작업이 있습니다. 완료 후 API로 전환하세요')
        # A queued refresh has no captured model/production contract; it will use the new API profiles.
        reserved = db.execute("SELECT id,updated_at FROM costs WHERE state='reserved'").fetchall()
        window_row = db.execute("SELECT value FROM settings WHERE key='work_window'").fetchone()
        window = json.loads(window_row[0]) if window_row else {}
        from datetime import datetime, timezone
        current = datetime.now(timezone.utc)
        dormant_ok = (preserve_dormant_cost_ids and window.get('authorized_start') and window.get('authorized_end')
                      and datetime.fromisoformat(window['authorized_end']) <= current
                      and set(preserve_dormant_cost_ids) == {r[0] for r in reserved}
                      and all(datetime.fromisoformat(r[1]) < datetime.fromisoformat(window['authorized_start']) for r in reserved))
        if reserved and not dormant_ok:
            raise WorkflowError('응답을 기다리는 모델·미디어 호출이 있습니다. 결과 확인 후 API로 전환하세요')
        before = {}
        for key in ('model', 'text_profile', 'image_profile', 'voice_profile', KEY):
            row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
            before[key] = json.loads(row[0]) if row else None
        if before.get(KEY) is True and before.get('model') == text_model and (before.get('image_profile') or {}).get('id') == 'openai-gpt-image' and (before.get('voice_profile') or {}).get('id') == 'openai-tts':
            return {'changed': False, 'api_only': True, 'text_model': text_model}
        at = now()
        def profile(identity):
            return {'id': identity, 'selected_by': actor, 'selected_at': at}
        values = {KEY: True, 'model': text_model, 'text_profile': profile(text_model),
                  'image_profile': profile('openai-gpt-image'), 'voice_profile': profile('openai-tts')}
        # The original voice record may include explicit voice settings; preserve them when already API-backed.
        if (before.get('voice_profile') or {}).get('id') == 'openai-tts':
            values['voice_profile'] = before['voice_profile']
        for key, value in values.items():
            db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', (key, canonical(value)))
        store._event(db, 'content_api_mode_activated', {'actor': actor, 'before': before, 'after': values,
                     'paid_call_made': False, 'unknown_costs_preserved': True,
                     'dormant_reservations_preserved': list(preserve_dormant_cost_ids)})
    return {'changed': True, 'api_only': True, 'text_model': text_model}
