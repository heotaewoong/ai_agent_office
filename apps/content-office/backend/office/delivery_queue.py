"""Private YouTube delivery bound to one human release decision and channel."""
from .store import WorkflowError,digest
from .channels import channel

def target(store,key,job):
    row=channel(store,key)
    if row.get('platform')!='youtube':raise WorkflowError('자동 비공개 업로드는 연결된 YouTube 채널만 지원합니다')
    if not row.get('credentials_configured'):
        from .youtube_oauth import client_configured
        if not client_configured():raise WorkflowError('Google OAuth 연결 구성이 아직 준비되지 않았습니다. 계정 로그인 전에 운영 설정을 확인해 주세요. 출고 승인은 저장하지 않았습니다')
        raise WorkflowError('설정에서 YouTube 계정을 먼저 연결해 주세요. 출고 승인은 저장하지 않았습니다')
    if row.get('publication_enabled') is not True:raise WorkflowError('해당 채널의 전송 허용을 먼저 확인해 주세요')
    if not row.get('external_account_id'):raise WorkflowError('연결한 YouTube 채널 ID를 먼저 확인해 주세요')
    language=((job.get('source_packet') or {}).get('audience') or {}).get('language')
    if language!=row.get('locale'):raise WorkflowError('승인 원고와 대상 채널 언어가 다릅니다')
    return row

def process(store,payload):
    from .youtube_delivery import deliver_youtube
    job=store.require_source_approval(payload['job_id'])
    if (job['source_hash']!=payload['source_hash'] or (job.get('manifest') or {}).get('hash')!=payload['manifest_hash'] or digest(job.get('release_approval'))!=payload['release_hash']):
        raise WorkflowError('비공개 전송을 기다리는 동안 원고·출고 승인이 변경되었습니다')
    row=target(store,payload['channel_key'],job)
    if digest(row)!=payload['channel_hash']:raise WorkflowError('전송을 기다리는 동안 대상 채널 설정이 변경되었습니다')
    result=deliver_youtube(store,job['id'],actor='release-approved-private-queue',channel_key=payload['channel_key'])
    return {key:result[key] for key in ('id','external_id','job_id','channel_key','state','visibility','privacy_status','upload_status','processing_status') if key in result}
