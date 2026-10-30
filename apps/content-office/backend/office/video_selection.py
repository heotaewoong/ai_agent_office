"""Explicit clip profiles (generated or free stock footage). Changing a profile never invokes or falls back to an API.

The default stays 'none'; no automatic path (daily collect, retries, workers) ever switches it on.
"""
from __future__ import annotations

import argparse
import os

from .store import WorkflowError, canonical, now

PROFILES = {'none': {'name': '생성 영상 없음 · 정지 장면', 'model': None},
            'pexels-stock': {'name': 'Pexels 무료 실사 영상 · 장면별 클립', 'model': None},
            'runway-grok-lite': {'name': 'Runway Grok Imagine 1.5 Lite · 720p · 가장 저렴', 'model': 'grok_imagine_1_5_lite'},
            'runway-gen4-turbo': {'name': 'Runway Gen-4 Turbo · 5초 720×1280', 'model': 'gen4_turbo'},
            'runway-gen4.5': {'name': 'Runway Gen-4.5 · 5초 720×1280', 'model': 'gen4.5'}}
STOCK = 'pexels-stock'


def availability(store=None):
    """Whether each option would actually run on this server right now, with a Korean reason when not."""
    runway = bool(os.environ.get('RUNWAYML_API_SECRET'))
    image_on = True
    if store is not None:
        image_on = (store.setting('image_profile', {'id': 'none'}) or {}).get('id', 'none') != 'none'
    result = {'none': {'available': True, 'reason': ''},
              STOCK: {'available': bool(os.environ.get('PEXELS_API_KEY')),
                      'reason': '' if os.environ.get('PEXELS_API_KEY') else 'PEXELS_API_KEY가 서버에 없습니다. 무료 키를 받아 환경 파일에 넣은 뒤 고를 수 있습니다'}}
    balance = None
    if runway and store is not None:
        from .video_provider import runway_credit_balance
        balance = runway_credit_balance(store)
    for identity in PROFILES:
        if identity.startswith('runway-'):
            reason = '' if runway else 'RUNWAYML_API_SECRET가 서버에 없습니다'
            if not reason and balance is None:
                reason = 'Runway 크레딧 잔액을 확인하지 못했습니다(네트워크 또는 키 확인 필요)'
            elif not reason and balance <= 0:
                reason = 'Runway 크레딧 잔액이 0입니다. 개발자 포털에서 크레딧을 충전하세요'
            elif not reason and not image_on:
                reason = 'Runway 영상은 생성 배경을 첫 장면으로 씁니다. 배경 이미지 프로필을 먼저 켜세요'
            result[identity] = {'available': not reason, 'reason': reason}
    return result


def profile_summary(store):
    profile = store.setting('clip_profile', {'id': 'none'})
    identity = profile.get('id')
    if identity not in PROFILES:
        raise WorkflowError('등록되지 않은 생성 영상 프로필입니다')
    paid = identity.startswith('runway-')
    runway_configured = bool(os.environ.get('RUNWAYML_API_SECRET'))
    pexels_configured = bool(os.environ.get('PEXELS_API_KEY'))
    from .video_provider import CREDIT_USD, FX_KRW, clip_limits, credits_per_clip, paid_clips_today
    limits = clip_limits(store)
    summary = {**profile, 'name': PROFILES[identity]['name'], 'model': PROFILES[identity]['model'], 'paid': paid,
               'automatic_fallback': False, 'job_cap_krw': 3000 if paid else 0,
               'max_clips_per_job': limits['max_clips_per_video'] if paid else 0,
               'configured': runway_configured, 'runway_configured': runway_configured, 'pexels_configured': pexels_configured,
               'clip_limits': limits, 'paid_clips_today': paid_clips_today(store),
               'key_source': 'RUNWAYML_API_SECRET 환경변수 · 실행하는 운영자가 설정' if paid else None,
               'note': '기본은 첫 장면(훅) 1개만 유료 클립으로 만듭니다. clip: generated로 지정한 장면이 있으면 그 장면을 우선합니다. '
                       '배경 이미지 프로필이 함께 켜져 있어야 하고, 같은 장면은 저장된 클립을 다시 써서 두 번 결제하지 않습니다'}
    if paid:
        credits = credits_per_clip(PROFILES[identity]['model'])
        summary.update(credits_per_clip=credits, reservation_krw_per_clip=int(credits * CREDIT_USD * FX_KRW))
    if identity == STOCK:
        from .stock_video import LICENSE_URL, MAX_DOWNLOADS_PER_JOB
        summary.update(configured=pexels_configured, max_clips_per_job=MAX_DOWNLOADS_PER_JOB, license_url=LICENSE_URL,
                       key_source='PEXELS_API_KEY 환경변수 · 무료 키를 운영자가 설정',
                       note='승인 장면마다 Pexels 실사 영상을 검색해 붙입니다. 배경 이미지가 필요 없고 비용이 없습니다. '
                            '받지 못한 장면은 정지 화면으로 만들고, 출처(Pexels·작가명)를 설명란과 권리 기록에 남깁니다')
    return summary


def select_profile(store, identity, *, actor):
    if identity not in PROFILES or not isinstance(actor, str) or not actor.strip():
        raise WorkflowError('등록된 프로필과 선택한 운영자 정보가 필요합니다')
    record = {'id': identity, 'selected_by': actor[:120], 'selected_at': now()}
    store.set_setting('clip_profile', record)
    store.event('clip_profile_selected', {**record, 'name': PROFILES[identity]['name'], 'automatic_fallback': False, 'paid_call_made': False})
    return profile_summary(store)


def set_clip_limits(store, *, max_clips_per_video, daily_paid_clips, actor):
    """Operator-only: paid clips per video (1-3) and per KST day across all jobs (0-10)."""
    from .video_provider import MAX_CLIPS_PER_JOB, MAX_DAILY_PAID_CLIPS, clip_limits
    if type(max_clips_per_video) is not int or not 1 <= max_clips_per_video <= MAX_CLIPS_PER_JOB:
        raise WorkflowError(f'영상당 유료 클립은 1~{MAX_CLIPS_PER_JOB}개로 정하세요')
    if type(daily_paid_clips) is not int or not 0 <= daily_paid_clips <= MAX_DAILY_PAID_CLIPS:
        raise WorkflowError(f'하루 유료 클립 한도는 0~{MAX_DAILY_PAID_CLIPS}개로 정하세요')
    if not isinstance(actor, str) or not actor.strip():
        raise WorkflowError('한도를 바꾼 운영자 정보가 필요합니다')
    store.set_setting('clip_limits', {'max_clips_per_video': max_clips_per_video, 'daily_paid_clips': daily_paid_clips,
                                      'selected_by': actor[:120], 'selected_at': now()})
    store.event('clip_limits_changed', {'max_clips_per_video': max_clips_per_video, 'daily_paid_clips': daily_paid_clips,
                                        'actor': actor[:120], 'paid_call_made': False})
    return clip_limits(store)


def paid_clip_estimate(store, job):
    """What a production of this job may pay for generated clips, shown before the operator confirms."""
    profile = profile_summary(store)
    scenes = (job.get('source_packet') or {}).get('video', {}).get('scenes', []) or []
    if not profile['paid'] or not job.get('selections', {}).get('video') or not scenes:
        return {'paid': False, 'clips': 0, 'credits': 0, 'reservation_krw': 0, 'label': ''}
    from .video_provider import CREDIT_USD, FX_KRW, clip_limits, credits_per_clip, generated_scene_indexes, paid_clips_today
    limits = clip_limits(store)
    clips = len(generated_scene_indexes(scenes, limits['max_clips_per_video']))
    credits = clips * credits_per_clip(profile['model'])
    krw = int(credits * CREDIT_USD * FX_KRW)
    return {'paid': clips > 0, 'clips': clips, 'credits': credits, 'usd': round(credits * CREDIT_USD, 2), 'reservation_krw': krw,
            'model': profile['model'], 'profile': profile['id'], 'daily_cap': limits['daily_paid_clips'], 'used_today': paid_clips_today(store),
            'label': f'유료: 영상 클립 {clips}개 · 약 {credits}크레딧(${credits * CREDIT_USD:.2f}, 예약 {krw:,}원)',
            'note': '같은 장면·같은 배경이면 저장된 클립을 다시 써서 추가 비용이 없습니다. 하루 한도와 잔액 확인을 통과해야 호출합니다'}


def clip_renderer_for_job(store, job):
    profile = profile_summary(store)
    if profile['id'] == 'none' or not job.get('selections', {}).get('video'):
        return None
    scenes = (job.get('source_packet') or {}).get('video', {}).get('scenes', [])
    if profile['id'] == STOCK:
        if not scenes:
            return None
        from .stock_video import make_pexels_clip_renderer
        return make_pexels_clip_renderer(store, job_id=job['id'])
    from .video_provider import generated_scene_indexes, make_runway_clip_renderer
    if not generated_scene_indexes(scenes):
        return None
    return make_runway_clip_renderer(store, job_id=job['id'], allow_paid=True, model=profile['model'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['status', 'set', 'limits'])
    parser.add_argument('--profile', choices=sorted(PROFILES))
    parser.add_argument('--per-video', type=int)
    parser.add_argument('--daily', type=int)
    args = parser.parse_args()
    from .bootstrap import default_store
    store = default_store()
    try:
        if args.command == 'set':
            if not args.profile:
                parser.error('set 명령에는 --profile이 필요합니다')
            print(canonical(select_profile(store, args.profile, actor='local-operator-cli')))
        elif args.command == 'limits':
            if args.per_video is None or args.daily is None:
                parser.error('limits 명령에는 --per-video와 --daily가 필요합니다')
            print(canonical(set_clip_limits(store, max_clips_per_video=args.per_video, daily_paid_clips=args.daily, actor='local-operator-cli')))
        else:
            print(canonical(profile_summary(store)))
    except WorkflowError as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
