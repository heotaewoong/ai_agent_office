"""Video destinations are review metadata, never permission to publish."""
from .store import WorkflowError

PLATFORMS = {'youtube_shorts': 'YouTube Shorts', 'instagram_reels': 'Instagram Reels'}


def selected_platforms(packet):
    value = (packet or {}).get('video_platforms', ['youtube_shorts'])
    if type(value) is not list or not 1 <= len(value) <= len(PLATFORMS) or any(type(x) is not str or x not in PLATFORMS for x in value) or len(set(value)) != len(value):
        raise WorkflowError('영상 목적지는 YouTube Shorts·Instagram Reels 중 하나 이상 중복 없이 선택하세요')
    return [key for key in PLATFORMS if key in value]


def require_platform(packet, platform):
    if platform not in selected_platforms(packet):
        raise WorkflowError('현재 승인 원고의 영상 목적지에 이 플랫폼이 없습니다. 외부 전송하지 않았습니다')


def set_platforms(store, job_id, expected_hash, platforms):
    values = selected_platforms({'video_platforms': platforms})
    job = store.job(job_id)
    if job.get('source_hash') != expected_hash or not (job.get('source_packet') or {}).get('body'):
        raise WorkflowError('현재 원고 판본을 확인한 뒤 영상 목적지를 저장하세요')
    if job['state'] in ('drafting', 'production_queued', 'producing', 'needs_reconciliation'):
        raise WorkflowError('진행 중인 작업을 확인한 뒤 영상 목적지를 변경하세요')
    with store.connection() as db:
        pending = db.execute("SELECT 1 FROM tasks WHERE state IN ('queued','running','unknown') AND json_extract(payload,'$.job_id')=?", (job_id,)).fetchone()
    if pending:
        raise WorkflowError('대기·진행·불명 작업을 먼저 확인하세요. 목적지는 변경하지 않았습니다')
    if selected_platforms(job['source_packet']) == values:
        return job
    from .channels import registry
    keys = ({'youtube_main_ko', 'youtube_english'} if 'youtube_shorts' in values else set()) | ({'instagram_main', 'instagram_english'} if 'instagram_reels' in values else set())
    snapshot = [{key: row.get(key) for key in ('key', 'platform', 'locale', 'public_url')} for row in registry(store) if row['key'] in keys]
    packet = {**job['source_packet'], 'video_platforms': values, 'video_platform_registry': snapshot}
    saved = store.save_source(job_id, packet, expected_hash=expected_hash)
    store.event('video_platforms_selected', {'platforms': values, 'external_published': False}, job_id)
    return saved
