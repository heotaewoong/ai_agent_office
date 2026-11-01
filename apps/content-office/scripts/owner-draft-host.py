"""Windows Native Messaging host. Reviewed local code; no server-supplied code or passwords."""
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

AGENT = Path('C:/AI-Office/owner-social-agent')
sys.path.insert(0, str(AGENT))
import owner_agent as agent
import owner_bridge as bridge


def remote(expression):
    return bridge.remote('from office import owner_drafts as d\n' + expression)


def row_for(message):
    if not re.fullmatch(r'od_[0-9a-f]{24}', message.get('id', '')) or not re.fullmatch(r'claim_[0-9a-f]{16}', message.get('claim_id', '')):
        raise agent.OwnerError('초안 처리 키를 확인하세요')
    spec = bridge.argument({'id': message['id'], 'claim_id': message['claim_id']})
    return remote('v=' + spec + '\nprint(json.dumps(d.claimed(store,v["id"],v["claim_id"])))\n')


def youtube_metadata_matches(actual, expected):
    # YouTube drops terminal line breaks; inner paragraphs and spaces must still match.
    return (actual.get('title') == expected.get('title')
            and isinstance(actual.get('description'), str)
            and actual['description'].rstrip('\r\n') == expected['description'].rstrip('\r\n'))


def handle(message):
    if not isinstance(message, dict) or set(message) - {'command','id','claim_id','proof','file_name','offset'}:
        raise agent.OwnerError('지원하지 않는 PC 요청입니다')
    command = message.get('command')
    if command == 'status':
        # A live platform check; returns channel keys and booleans only.
        return {'ok': True, 'connections': bridge.sync_status()['channels'], 'public_publish': False}
    if command == 'poll':
        return {'ok': True, 'items': remote('print(json.dumps(d.pending(store)))\n'), 'public_publish': False}
    if command == 'claim':
        rid = message.get('id', '')
        if not re.fullmatch(r'od_[0-9a-f]{24}', rid):
            raise agent.OwnerError('초안 키가 올바르지 않습니다')
        return {'ok': True, 'item': remote('print(json.dumps(d.claim(store,' + bridge.argument(rid) + ',"owner-windows-native")))\n')}
    if command == 'receipt':
        proof = message.get('proof')
        if (not isinstance(proof, dict) or not re.fullmatch(r'od_[0-9a-f]{24}', message.get('id', ''))
                or not re.fullmatch(r'claim_[0-9a-f]{16}', message.get('claim_id', ''))):
            raise agent.OwnerError('초안 확인 결과가 필요합니다')
        if proof.get('claim_id') != message['claim_id']:
            raise agent.OwnerError('다른 PC 처리 결과입니다')
        # Recording an already-finished nonpublic result is allowed after the window expires.
        value = bridge.argument({'id': message['id'], 'proof': proof})
        result = remote('v=' + value + '\nr=d.receipt(store,v["id"],v["proof"])\nprint(json.dumps({"id":r["id"],"state":r["state"]}))\n')
        return {'ok': True, **result}
    if command not in ('youtube-private', 'asset-chunk'):
        raise agent.OwnerError('공개 게시·예약·인증값 요청은 지원하지 않습니다')
    row = row_for(message)
    if command == 'asset-chunk':
        record = next((r for r in row['files'] if r['name'] == message.get('file_name')), None)
        offset = message.get('offset')
        if not record or type(offset) is not int or offset < 0:
            raise agent.OwnerError('현재 초안의 파일 구간만 요청하세요')
        spec = bridge.argument({'id': row['id'], 'claim_id': row['claim_id'], 'name': record['name'], 'offset': offset})
        code = 'v=' + spec + '\nr=d.claimed(store,v["id"],v["claim_id"])\nf=next(f for f in r["files"] if f["name"]==v["name"])\np=d._file(store,f)\nassert v["offset"]<=p.stat().st_size\nwith p.open("rb") as stream:\n stream.seek(v["offset"]);raw=stream.read(192*1024)\nprint(json.dumps({"data":base64.b64encode(raw).decode(),"size":p.stat().st_size,"sha256":f["sha256"]}))\n'
        return {'ok': True, **remote(code)}
    if row['channel_key'] not in ('youtube_main_ko', 'youtube_english') or row['visibility'] != 'private':
        raise agent.OwnerError('이 경로는 YouTube 비공개 전용입니다')
    if agent.load_vault().get('youtube', {}).get(row['channel_key'], {}).get('channel_id') != row['account_id']:
        raise agent.OwnerError('PC 로그인 채널과 작업의 대상 계정 ID가 다릅니다')
    # Fetch bytes into RAM only, rechecking the current approval immediately beforehand.
    value = bridge.argument({'id': row['id'], 'claim_id': row['claim_id']})
    raw = bridge.remote('from office import owner_drafts as d\nv=' + value + '\nr=d.claimed(store,v["id"],v["claim_id"])\nf=next(f for f in r["files"] if f["name"]=="short.mp4")\nsys.stdout.buffer.write(d._file(store,f).read_bytes())\n', binary=True)
    record = next(r for r in row['files'] if r['name'] == 'short.mp4')
    if hashlib.sha256(raw).hexdigest() != record['sha256']:
        raise agent.OwnerError('영상 내용이 현재 승인된 파일과 다릅니다')
    packet = {'review_mode': 'ec2-memory', 'job_id': row['job_id'], 'channel_key': row['channel_key'],
              'asset_size': len(raw), 'asset_sha256': record['sha256'], 'title': row['title'],
              'description': row['text'], 'visibility': 'private', 'authorized_end': row['authorized_end']}
    packet['server_content_hash'] = hashlib.sha256(raw + json.dumps(agent.metadata(packet), sort_keys=True).encode()).hexdigest()
    result = agent.private_upload(row['channel_key'], raw, packet, agent.memory_review_hash(packet))
    # Requery title and description as well as the existing uploader's channel/private checks.
    token = agent.youtube_token(row['channel_key'])
    if isinstance(token, tuple):
        token = token[0]
    _, _, checked = agent.request(agent.VIDEO_URL + '?part=snippet,status&id=' + result['external_id'], headers={'Authorization':'Bearer ' + token})
    actual = checked.get('items', [])
    expected = agent.metadata(packet)
    if len(actual) != 1 or actual[0].get('status', {}).get('privacyStatus') != 'private' or not youtube_metadata_matches(actual[0].get('snippet', {}), expected['snippet']):
        raise agent.OwnerError('플랫폼 제목·본문·비공개 상태를 재확인하지 못했습니다')
    proof = {'state':'platform_private','claim_id':row['claim_id'],'content_hash':row['content_hash'],
             'account_id':row['account_id'],'external_id':result['external_id']}
    return handle({'command':'receipt','id':row['id'],'claim_id':row['claim_id'],'proof':proof})


def main():
    # No credentials or exception text are ever sent through the browser protocol.
    stream = sys.stdin.buffer
    while True:
        prefix = stream.read(4)
        if not prefix:
            return
        if len(prefix) != 4:
            return
        size, = struct.unpack('<I', prefix)
        if not 0 < size <= 1024 * 1024:
            return
        raw = stream.read(size)
        if len(raw) != size:
            return
        try:
            answer = handle(json.loads(raw))
        except Exception:
            answer = {'ok': False, 'error': 'PC 연결·현재 원고·계정·작업 시간을 확인하세요. 공개 발행은 실행하지 않았습니다.'}
        encoded = json.dumps(answer, ensure_ascii=False).encode('utf-8')
        if len(encoded) > 900_000:
            encoded = b'{"ok":false,"error":"response_too_large"}'
        sys.stdout.buffer.write(struct.pack('<I', len(encoded)) + encoded)
        sys.stdout.buffer.flush()


if __name__ == '__main__':
    main()
