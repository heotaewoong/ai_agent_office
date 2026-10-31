"""Video destinations are review metadata, never permission to publish."""
from .store import WorkflowError, digest, now

PLATFORMS = {'youtube_shorts': 'YouTube Shorts', 'instagram_reels': 'Instagram Reels'}


def selected_platforms(packet):
    value = (packet or {}).get('video_platforms', ['youtube_shorts'])
    if type(value) is not list or not 1 <= len(value) <= len(PLATFORMS) or any(type(x) is not str or x not in PLATFORMS for x in value) or len(set(value)) != len(value):
        raise WorkflowError('영상 목적지는 YouTube Shorts·Instagram Reels 중 하나 이상 중복 없이 선택하세요')
    return [key for key in PLATFORMS if key in value]


def require_platform(packet, platform):
    if platform not in selected_platforms(packet):
        raise WorkflowError('현재 승인 원고의 영상 목적지에 이 플랫폼이 없습니다. 외부 전송하지 않았습니다')


def effective_packet(job):
    source = job.get('source_packet') or {}
    delivery = job.get('video_delivery') or {}
    return {**source, 'video_platforms': delivery.get('platforms', selected_platforms(source)),
            'video_platform_registry': delivery.get('channel_registry', source.get('video_platform_registry', []))}


def set_platforms(store, job_id, expected_hash, platforms, expected_delivery_hash=None):
    values = selected_platforms({'video_platforms': platforms})
    from .channels import registry
    keys = ({'youtube_main_ko', 'youtube_english'} if 'youtube_shorts' in values else set()) | ({'instagram_main', 'instagram_english'} if 'instagram_reels' in values else set())
    snapshot = [{key: row.get(key) for key in ('key', 'platform', 'locale', 'public_url')} for row in registry(store) if row['key'] in keys]
    with store.connection(transaction=True) as db:
        job = store._job(db, job_id)
        if job.get('source_hash') != expected_hash or not (job.get('source_packet') or {}).get('body'):
            raise WorkflowError('현재 원고 판본을 확인한 뒤 출고 목적지를 저장하세요')
        if expected_delivery_hash is not None and (job.get('video_delivery') or {}).get('hash', '') != expected_delivery_hash:
            raise WorkflowError('다른 화면에서 출고 목적지가 변경되었습니다. 새로고침하세요')
        if job['state'] in ('drafting', 'production_queued', 'producing', 'needs_reconciliation'):
            raise WorkflowError('진행 중인 작업을 확인한 뒤 영상 목적지를 변경하세요')
        if db.execute("SELECT 1 FROM tasks WHERE state IN ('queued','running','unknown') AND json_extract(payload,'$.job_id')=?", (job_id,)).fetchone():
            raise WorkflowError('대기·진행·불명 작업을 먼저 확인하세요. 목적지는 변경하지 않았습니다')
        current = job.get('video_delivery') or {}
        if selected_platforms(effective_packet(job)) == values and current.get('channel_registry') == snapshot:
            return job
        record = {'platforms': values, 'channel_registry': snapshot}
        record.update(hash=digest(record), selected_at=now())
        job['video_delivery'] = record
        # Delivery metadata belongs to release②, never to the approved source①.
        job['release_approval'] = None
        manifest = job.get('manifest')
        if manifest:
            manifest.setdefault('render_hash', manifest['hash'])
            manifest['delivery_targets'] = record
            manifest['hash'] = digest({k: v for k, v in manifest.items() if k != 'hash'})
            job['state'] = 'partial_release_review' if any(s.get('state') != 'completed' for s in manifest.get('output_status', {}).values()) else 'release_review'
        store._event(db, 'video_platforms_selected', {'platforms': values, 'delivery_hash': record['hash'], 'source_approval_preserved': True, 'external_published': False}, job_id)
        return store._write_job(db, job)
