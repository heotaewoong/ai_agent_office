#!/usr/bin/env python3
"""Native-owned, peer-UID-scoped Unix relay. No task executor or native notifier subscriptions.

Protocol: one bounded JSON line per connection; operations board/task/create/subscribe/delivery_status.
Run only from the reviewed native-owned copy with the installed Hermes interpreter. Notifications
are disabled unless the owner enables them in the private config. Only fixed status metadata is sent.
"""
import argparse
import asyncio
from contextlib import contextmanager
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import signal
import socket
import socketserver
import sqlite3
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
import uuid

BOARD, TENANT = 'heobrain-office', 'heobrain-world'
NATIVE_HOME = Path.home() / '.hermes'
NATIVE_DB = NATIVE_HOME / 'kanban/boards/heobrain-office/kanban.db'
TOKEN_FILE = NATIVE_HOME / 'webapp/session-token'
LUMI_HOME = NATIVE_HOME / 'profiles/lumi'
MAX_INPUT, MAX_OUTPUT = 32768, 2 * 1024 * 1024
TASK = re.compile(r't_[A-Za-z0-9_-]{1,80}\Z')
PROFILES = {'default', 'mybots-sage', 'lumi', 'ada', 'ethan', 'mia', 'noah', 'oliver', 'sam'}
CREDENTIAL_BODY = re.compile(r'https?://[^/\s]*@|bearer\s+[A-Za-z0-9._~+/-]+|(?:token|secret|password|api[_-]?key)\s*[:=]|sk-[A-Za-z0-9]{12,}|xox[baprs]-[A-Za-z0-9-]+', re.I)


class RelayError(ValueError):
    def __init__(self, code, message='요청한 비서 연결을 확인할 수 없습니다.'):
        super().__init__(message)
        self.code = code


def request_uuid(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise RelayError('invalid_request')
    return value


def task_id(value):
    if not isinstance(value, str) or not TASK.fullmatch(value):
        raise RelayError('invalid_task')
    return value


def private_json(path, missing=False):
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    except FileNotFoundError:
        if missing:
            return {}
        raise
    with os.fdopen(fd) as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or (os.name != 'nt' and (info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600)):
            raise RelayError('private_file_required')
        text = handle.read(MAX_OUTPUT + 1)
        if len(text.encode()) > MAX_OUTPUT:
            raise RelayError('state_limit')
        data = json.loads(text)
        if not isinstance(data, dict):
            raise RelayError('invalid_state')
        return data


def save_private_json(path, value):
    if path.exists():
        private_json(path)
    info = path.parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or (os.name != 'nt' and (info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077)):
        raise RelayError('private_directory_required')
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, prefix='.relay-', delete=False) as handle:
            name = handle.name
            os.chmod(name, 0o600)
            json.dump(value, handle, ensure_ascii=False, separators=(',', ':'))
            handle.flush(); os.fsync(handle.fileno())
        os.replace(name, path)
        if os.name != 'nt':
            directory = os.open(path.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


@contextmanager
def admission_file_lock(path):
    """One private lock inode coordinates admission across relay instances, not just threads."""
    fd = os.open(str(path) + '.lock', os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    locked = False
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or (os.name != 'nt' and (info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600)):
            raise RelayError('private_file_required')
        if info.st_size == 0:
            os.write(fd, b'\0'); os.fsync(fd)
        deadline = time.monotonic() + 1
        while not locked:
            try:
                os.lseek(fd, 0, os.SEEK_SET)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    raise RelayError('native_admission_unknown') from None
                time.sleep(.02)
        yield
    finally:
        if locked:
            if os.name == 'nt':
                os.lseek(fd, 0, os.SEEK_SET); msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def load_admissions(path):
    data = private_json(path, missing=True)
    if len(data) > 4096:
        raise RelayError('admission_limit')
    for rid, row in data.items():
        request_uuid(rid)
        if (not isinstance(row, dict) or set(row) != {'request_id', 'payload_hash', 'phase', 'native_task_id'}
                or row['request_id'] != rid or not re.fullmatch('[0-9a-f]{64}', str(row['payload_hash']))
                or row['phase'] not in {'posting', 'unknown', 'admitted'}):
            raise RelayError('invalid_admission_state')
        if row['native_task_id'] is not None:
            task_id(row['native_task_id'])
        elif row['phase'] == 'admitted':
            raise RelayError('invalid_admission_state')
    return data


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class NativeHTTP:
    def __init__(self):
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def call(self, method, route, payload=None):
        fd = os.open(TOKEN_FILE, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(fd) as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600:
                raise RelayError('native_credentials_unavailable')
            token = handle.read(257).strip()
        if not re.fullmatch(r'[A-Za-z0-9_-]{32,256}', token):
            raise RelayError('native_credentials_unavailable')
        query = {'profile': 'default', 'board': BOARD}
        if route == 'board':
            query['tenant'] = TENANT
        req = Request('http://127.0.0.1:9119/api/plugins/kanban/' + route + '?' + urlencode(query),
                      method=method, data=json.dumps(payload).encode() if payload is not None else None,
                      headers={'X-Hermes-Session-Token': token, 'Content-Type': 'application/json'})
        with self.opener.open(req, timeout=5) as response:
            raw = response.read(MAX_OUTPUT + 1)
        if len(raw) > MAX_OUTPUT:
            raise RelayError('native_response_limit')
        # Even an accidental echoed owner credential cannot cross the Unix boundary.
        data = json.loads(raw.decode().replace(token, '[redacted]'))
        if not isinstance(data, dict):
            raise RelayError('native_invalid_response')
        return data

    def board(self):
        return self.call('GET', 'board')

    def task(self, ident):
        return self.call('GET', 'tasks/' + task_id(ident))

    def create(self, payload):
        return self.call('POST', 'tasks', payload)


def scoped_card(card):
    if not isinstance(card, dict) or card.get('tenant') != TENANT:
        raise RelayError('foreign_task')
    task_id(card.get('id'))
    keys = {'id', 'title', 'body', 'assignee', 'status', 'tenant', 'idempotency_key', 'current_run_id', 'created_at', 'started_at', 'completed_at', 'result', 'latest_summary'}
    return {key: value for key, value in card.items() if key in keys}


def approved_target(source_id):
    with sqlite3.connect(NATIVE_DB.as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        rows = db.execute("SELECT chat_id FROM kanban_notify_subs WHERE task_id=? AND platform='slack' AND notifier_profile='lumi'", (task_id(source_id),)).fetchall()
    if len(rows) != 1 or not re.fullmatch(r'[CGD][A-Z0-9]{8,24}', rows[0]['chat_id']):
        raise RelayError('notification_target_unavailable')
    return {'chat_id': rows[0]['chat_id']}


def status_message(metadata, office_origin=None):
    if set(metadata) != {'request_id', 'task_id', 'run_id', 'event_id', 'participants', 'terminal_state'}:
        raise RelayError('invalid_status_metadata')
    request_uuid(metadata['request_id']); task_id(metadata['task_id'])
    if (type(metadata['run_id']) is not int or metadata['run_id'] <= 0 or type(metadata['event_id']) is not int or metadata['event_id'] <= 0
            or metadata['terminal_state'] not in {'completed', 'blocked'} or not isinstance(metadata['participants'], list)
            or not 1 <= len(metadata['participants']) <= 9 or any(p not in PROFILES for p in metadata['participants'])):
        raise RelayError('invalid_status_metadata')
    state = '완료' if metadata['terminal_state'] == 'completed' else '추가 확인 필요'
    message = f"3D 비서 업무 {state}\n요청 {metadata['request_id'][:8]} · 업무 {metadata['task_id']}\n실행 {metadata['run_id']} · 기록 {metadata['event_id']}\n참여 " + ', '.join(metadata['participants'])
    if office_origin:
        parsed = urlsplit(office_origin)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {'', '/'}:
            raise RelayError('invalid_office_origin')
        message += '\n인증된 오피스에서 결과 확인: ' + office_origin.rstrip('/') + '/office3d'
    return message


def notice_reference(notice):
    if notice is None:
        return None
    status_message(notice)
    return {key: notice[key] for key in ('request_id', 'task_id', 'run_id', 'event_id', 'terminal_state')}


def remember_receipt(row):
    if row['notice'] is None:
        return
    reference = notice_reference(row['notice'])
    entry = {'notice': row['notice'], 'state': row['state'], 'message_id': row['message_id']}
    row['receipts'] = [old for old in row.get('receipts', []) if notice_reference(old['notice']) != reference] + [entry]
    row['receipts'] = row['receipts'][-16:]
    row['notice_cursor'] = max(row.get('notice_cursor', 0), reference['event_id'])


class SlackSender:
    def __init__(self, private_config, runtime, office_origin=None):
        self.private_config, self.runtime, self.office_origin = private_config, runtime, office_origin

    def child(self, mode, target, metadata):
        status_message(metadata['notice'], self.office_origin)
        import pwd
        username = pwd.getpwuid(os.geteuid()).pw_name
        env = {'HOME': str(Path.home()), 'USER': username, 'LOGNAME': username, 'LANG': 'C.UTF-8',
               'PATH': '/usr/bin:/bin', 'HERMES_HOME': str(LUMI_HOME), 'HERMES_PROFILE': 'lumi'}
        result = subprocess.run([self.runtime['native_python'], str(Path(__file__).resolve()), '--config', str(self.private_config), '--slack', mode],
                                input=json.dumps({'target': target, **metadata, 'office_origin': self.office_origin}),
                                text=True, capture_output=True, timeout=13, env=env, cwd=self.runtime['native_repo'])
        if result.returncode or len(result.stdout.encode()) > 4096:
            raise RelayError('notification_ack_unknown')
        return json.loads(result.stdout)

    def send(self, target, metadata):
        return self.child('send', target, {'notice': metadata})

    def readback(self, target, metadata):
        return self.child('readback', target, metadata).get('confirmed') is True


def trusted_runtime(config):
    if not all(config.get(key) for key in ('native_python', 'native_repo', 'pythonpath')):
        raise RelayError('status_sender_runtime_required')
    if not isinstance(config['pythonpath'], list) or len(config['pythonpath']) > 8:
        raise RelayError('invalid_runtime_configuration')
    if os.name != 'nt':
        import grp
        import pwd
        owner = pwd.getpwuid(os.geteuid())
        group = grp.getgrgid(owner.pw_gid)
        private_group = (group.gr_gid == owner.pw_gid
                         and not any(user.pw_gid == owner.pw_gid and user.pw_uid != owner.pw_uid for user in pwd.getpwall())
                         and not any(member != owner.pw_name for member in group.gr_mem))
    for value, directory in [(config['native_python'], False), (config['native_repo'], True), *[(value, True) for value in config['pythonpath']]]:
        path = Path(value)
        info = path.stat()
        if not path.is_absolute() or (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)) is False:
            raise RelayError('invalid_runtime_configuration')
        if os.name != 'nt':
            # Check both the configured link ancestry and its resolved target; service GID is unrelated.
            for candidate in {path, path.resolve(strict=True)}:
                for node in (candidate, *candidate.parents):
                    node_info = node.stat()
                    mode = stat.S_IMODE(node_info.st_mode)
                    if node_info.st_uid not in {0, owner.pw_uid} or mode & 0o002:
                        raise RelayError('invalid_runtime_configuration')
                    if mode & 0o020:
                        if (not stat.S_ISDIR(node_info.st_mode) or node_info.st_uid == 0
                                or node_info.st_uid != owner.pw_uid or node_info.st_gid != owner.pw_gid or not private_group):
                            raise RelayError('invalid_runtime_configuration')
                        try:
                            if {'system.posix_acl_access', 'system.posix_acl_default'} & set(os.listxattr(node)):
                                raise RelayError('invalid_runtime_configuration')
                        except (AttributeError, OSError):
                            raise RelayError('invalid_runtime_configuration') from None
    if not os.access(config['native_python'], os.X_OK):
        raise RelayError('invalid_runtime_configuration')
    return {key: config[key] for key in ('native_python', 'native_repo', 'pythonpath')}


def slack_child(mode, runtime):
    """Isolated Lumi config scope; exact text-only native helper, no files or thread target."""
    logging.disable(logging.CRITICAL)
    raw = sys.stdin.buffer.readline(MAX_INPUT + 1)
    if len(raw) > MAX_INPUT:
        raise RelayError('request_limit')
    value = json.loads(raw)
    if set(value) - {'target', 'notice', 'message_id', 'office_origin'} or not re.fullmatch(r'[CGD][A-Z0-9]{8,24}', value['target']):
        raise RelayError('invalid_status_metadata')
    text = status_message(value['notice'], value.get('office_origin'))
    if Path(sys.executable).absolute() != Path(runtime['native_python']).absolute():
        raise RelayError('native_runtime_required')
    sys.path[:0] = [runtime['native_repo'], *runtime['pythonpath']]
    from dotenv import load_dotenv
    load_dotenv(LUMI_HOME / '.env', override=True)
    from gateway.config import load_gateway_config, Platform
    from plugins.platforms.slack.adapter import _standalone_post_text
    from slack_sdk.web.async_client import AsyncWebClient
    config = load_gateway_config().platforms.get(Platform.SLACK)
    if not config or not config.token:
        raise RelayError('status_sender_unavailable')
    client_id = str(uuid.uuid5(uuid.UUID(value['notice']['request_id']), str(value['notice']['event_id']) + ':' + value['notice']['terminal_state']))

    async def perform():
        client = AsyncWebClient(token=config.token, timeout=10, retry_handlers=[])
        if mode == 'send':
            class TextClient:
                async def chat_postMessage(self, **kwargs):
                    return await client.chat_postMessage(**kwargs, client_msg_id=client_id)
            data = await _standalone_post_text(TextClient(), value['target'], text, {'unfurl_links': False, 'unfurl_media': False}, None)
            if data.get('ok') is not True or data.get('channel') != value['target'] or not re.fullmatch(r'\d{9,16}\.\d{6}', str(data.get('ts', ''))):
                raise RelayError('notification_ack_unknown')
            return {'message_id': data['ts']}
        identity = await client.auth_test()
        user_id, bot_id = identity.get('user_id'), identity.get('bot_id')
        if (identity.get('ok') is not True or not isinstance(user_id, str) or not isinstance(bot_id, str)
                or not re.fullmatch(r'[UW][A-Z0-9]{8,24}', user_id) or not re.fullmatch(r'B[A-Z0-9]{8,24}', bot_id)):
            raise RelayError('notification_identity_unavailable')
        data = await client.conversations_history(channel=value['target'], limit=100)
        confirmed = any(message.get('user') == user_id and message.get('bot_id') == bot_id
                        and re.fullmatch(r'\d{9,16}\.\d{6}', str(message.get('ts', '')))
                        and message.get('thread_ts') in {None, message.get('ts')}
                        and message.get('text') == text and not message.get('files') and not message.get('attachments')
                        and (message.get('client_msg_id') == client_id or (value.get('message_id') and message.get('ts') == value['message_id']))
                        for message in data.get('messages', []))
        return {'confirmed': bool(confirmed)}
    print(json.dumps(asyncio.run(perform())))


class Relay:
    def __init__(self, native, state_file, *, source, sender=None, notify_enabled=False, allow_uid=1000, read_probe_uid=None):
        if allow_uid != 1000 or read_probe_uid not in {None, 1001}:
            raise RelayError('invalid_peer_configuration')
        self.native, self.state_file, self.source, self.sender = native, Path(state_file), source, sender
        self.notify_enabled, self.allow_uid, self.read_probe_uid = notify_enabled, allow_uid, read_probe_uid
        self.lock, self.create_lock = threading.RLock(), threading.Lock()
        self.admissions_file = self.state_file.with_name(self.state_file.name + '.admissions.json')
        self.admissions, self.poll_offset = load_admissions(self.admissions_file), 0
        self.watches = private_json(self.state_file, missing=True)
        if len(self.watches) > 128:
            raise RelayError('watch_limit')
        required = {'request_id', 'task_id', 'state', 'subscription_id', 'target_hash', 'notice', 'message_id'}
        for rid, row in self.watches.items():
            if not isinstance(row, dict) or not required <= row.keys() or row.keys() - required - {'error_code', 'receipts', 'notice_cursor'}:
                raise RelayError('invalid_watch_state')
            request_uuid(rid); task_id(row['task_id'])
            if (row['request_id'] != rid or row['state'] not in {'watching', 'pending', 'sent_unverified', 'confirmed', 'unknown'}
                    or any(not re.fullmatch('[0-9a-f]{64}', str(row[key])) for key in ('subscription_id', 'target_hash'))
                    or (row['message_id'] is not None and not re.fullmatch(r'\d{9,16}\.\d{6}', str(row['message_id'])))
                    or (row.get('error_code') and not re.fullmatch('[a-z_]{1,80}', str(row['error_code'])))):
                raise RelayError('invalid_watch_state')
            if row['notice'] is not None:
                status_message(row['notice'])
                if row['notice']['request_id'] != rid:
                    raise RelayError('invalid_watch_state')
            elif row['state'] != 'watching':
                raise RelayError('invalid_watch_state')
            if 'receipts' not in row:
                row['receipts'] = []
                remember_receipt(row)  # Upgrade historical metadata without losing its delivery fence.
            if not isinstance(row['receipts'], list) or len(row['receipts']) > 16:
                raise RelayError('invalid_watch_state')
            seen = set()
            for receipt in row['receipts']:
                if (not isinstance(receipt, dict) or set(receipt) != {'notice', 'state', 'message_id'}
                        or receipt['state'] not in {'pending', 'sent_unverified', 'confirmed', 'unknown'}
                        or (receipt['message_id'] is not None and not re.fullmatch(r'\d{9,16}\.\d{6}', str(receipt['message_id'])))):
                    raise RelayError('invalid_watch_state')
                ref = notice_reference(receipt['notice'])
                if not ref or ref['request_id'] != rid or ref['event_id'] in seen:
                    raise RelayError('invalid_watch_state')
                seen.add(ref['event_id'])
            row.setdefault('notice_cursor', max(seen, default=0))
            if (type(row['notice_cursor']) is not int or row['notice_cursor'] < max(seen, default=0)
                    or (row['notice'] and row['notice_cursor'] < row['notice']['event_id'])):
                raise RelayError('invalid_watch_state')

    def board(self):
        data = self.native.board()
        return {'columns': [{'name': col['name'], 'tasks': [scoped_card(card) for card in col.get('tasks', []) if card.get('tenant') == TENANT]} for col in data['columns']]}

    def task(self, ident):
        data = self.native.task(task_id(ident))
        card = scoped_card(data['task'])
        if card['id'] != ident:
            raise RelayError('native_invalid_response')
        return {'task': card, 'events': [{k: e.get(k) for k in ('id', 'task_id', 'run_id', 'kind', 'created_at')} for e in data.get('events', []) if e.get('task_id') == ident],
                'runs': [{k: r.get(k) for k in ('id', 'task_id', 'profile', 'status', 'outcome', 'started_at', 'ended_at', 'summary')} for r in data.get('runs', []) if r.get('task_id') == ident],
                'links': {key: [task_id(x) for x in data.get('links', {}).get(key, [])] for key in ('parents', 'children')}}

    def create(self, rid, payload):
        expected = {'title': '3D 비서 요청 · ' + rid[:8], 'assignee': 'lumi', 'tenant': TENANT,
                    'idempotency_key': 'office-world:' + rid, 'max_runtime_seconds': 300, 'goal_mode': False}
        if (not isinstance(payload, dict) or not (set(expected) | {'body'}) <= payload.keys()
                or payload.keys() - set(expected) - {'body', 'skills'}
                or payload.get('skills', ['heobrain-office-coordinator']) != ['heobrain-office-coordinator']
                or any(type(payload[k]) is not type(v) or payload[k] != v for k, v in expected.items())):
            raise RelayError('invalid_create')
        body = payload['body']
        if not isinstance(body, str) or not body.strip() or len(body) > 8000 or len(body.encode()) > 24000 or CREDENTIAL_BODY.search(body) or any(ord(ch) < 32 and ch not in '\n\t\r' for ch in body):
            raise RelayError('unsafe_request_body')
        effective = {**expected, 'body': body, 'skills': ['heobrain-office-coordinator']}
        payload_hash = hashlib.sha256(json.dumps(effective, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        with self.create_lock, admission_file_lock(self.admissions_file):
            self.admissions = load_admissions(self.admissions_file)
            previous = self.admissions.get(rid)
            if previous and previous['payload_hash'] != payload_hash:
                raise RelayError('request_conflict')
            cards = [card for col in self.board()['columns'] for card in col['tasks'] if card.get('idempotency_key') == expected['idempotency_key']]
            if len(cards) > 1 or (cards and (cards[0].get('body') != body or cards[0].get('assignee') != 'lumi')):
                raise RelayError('request_conflict')
            if cards:
                if not previous and len(self.admissions) >= 4096:
                    raise RelayError('admission_limit')
                self.admissions[rid] = {'request_id': rid, 'payload_hash': payload_hash, 'phase': 'admitted', 'native_task_id': cards[0]['id']}
                save_private_json(self.admissions_file, self.admissions)
                return {'task': cards[0]}
            if previous:
                # A restart cannot turn a lost POST acknowledgement into permission to POST again.
                raise RelayError('native_admission_unknown')
            if len(self.admissions) >= 4096:
                raise RelayError('admission_limit')
            self.admissions[rid] = {'request_id': rid, 'payload_hash': payload_hash, 'phase': 'posting', 'native_task_id': None}
            save_private_json(self.admissions_file, self.admissions)
            try:
                card = scoped_card(self.native.create(effective)['task'])
                if card.get('idempotency_key') != expected['idempotency_key'] or card.get('body') != body or card.get('assignee') != 'lumi':
                    raise RelayError('native_invalid_response')
                self.admissions[rid].update(phase='admitted', native_task_id=card['id'])
                save_private_json(self.admissions_file, self.admissions)
                return {'task': card}
            except Exception:
                self.admissions[rid]['phase'] = 'unknown'
                save_private_json(self.admissions_file, self.admissions)
                raise RelayError('native_admission_unknown') from None

    def reference(self, rid, ident):
        data = self.task(ident)
        if data['task'].get('idempotency_key') != 'office-world:' + rid or data['task'].get('assignee') != 'lumi':
            raise RelayError('request_conflict')
        return data

    def subscribe(self, rid, ident):
        self.reference(rid, ident)
        target = self.source()['chat_id']
        with self.lock:
            old = self.watches.get(rid)
            if old and old['task_id'] != ident:
                raise RelayError('request_conflict')
            if not old:
                if len(self.watches) >= 128:
                    raise RelayError('watch_limit')
                self.watches[rid] = {'request_id': rid, 'task_id': ident, 'state': 'watching',
                                     'subscription_id': hashlib.sha256((rid + ':' + ident).encode()).hexdigest(),
                                     'target_hash': hashlib.sha256(target.encode()).hexdigest(), 'notice': None, 'message_id': None,
                                     'receipts': [], 'notice_cursor': 0}
                save_private_json(self.state_file, self.watches)
            return self.delivery_status(rid, ident)

    def delivery_status(self, rid, ident):
        with self.lock:
            row = dict(self.watches[rid]) if rid in self.watches else None
            if row and row['task_id'] != ident:
                raise RelayError('request_conflict')
        current = self.terminal(row) if row and row['notice'] is not None else None
        if not row or row['notice'] is None:
            self.reference(rid, ident)
        stored_ref = notice_reference(row['notice']) if row else None
        verified = bool(row and row['state'] == 'confirmed' and stored_ref is not None and stored_ref == notice_reference(current))
        state = row['state'] if row else 'not_attached'
        if state == 'confirmed' and not verified:
            state = 'watching'
        error = ({'code': row['error_code'], 'message': '상태 알림의 연결·실행 근거를 확인해야 합니다.'} if row and row.get('error_code') else None)
        return {'task_id': ident, 'request_id': rid, 'state': state, 'notice_ref': stored_ref,
                'subscription_id': row['subscription_id'] if row else None, 'target_hash': row['target_hash'] if row else None,
                'external_delivery_verified': verified,
                'error': error if self.notify_enabled else {'code': 'status_sender_disabled', 'message': '상태 전용 알림 연결은 서버 검토 후 활성화해야 합니다.'}}

    def terminal(self, row):
        nodes, queue = {}, [(row['task_id'], None)]
        while queue:
            ident, parent = queue.pop(0)
            if ident not in nodes and len(nodes) >= 5:
                raise RelayError('native_graph_limit')
            data = nodes.get(ident) or (self.reference(row['request_id'], ident) if parent is None else self.task(ident))
            if parent and parent not in data['links']['parents']:
                raise RelayError('native_graph_invalid')
            if ident in nodes:
                continue
            nodes[ident] = data
            queue.extend((child, ident) for child in data['links']['children'])
        # A visited-node shortcut cannot establish acyclicity or the longest shared path.
        edges = {ident: set(data['links']['children']) for ident, data in nodes.items()}
        incoming = {ident: {parent for parent, children in edges.items() if ident in children} for ident in nodes}
        if any(incoming[ident] != set(nodes[ident]['links']['parents']) for ident in nodes):
            raise RelayError('native_graph_invalid')
        indegree, longest = {ident: len(parents) for ident, parents in incoming.items()}, {ident: 0 for ident in nodes}
        ready = [ident for ident in nodes if indegree[ident] == 0]
        visited = 0
        while ready:
            ident = ready.pop(0); visited += 1
            for child in edges[ident]:
                longest[child] = max(longest[child], longest[ident] + 1)
                indegree[child] -= 1
                if indegree[child] == 0:
                    ready.append(child)
        if visited != len(nodes):
            raise RelayError('native_graph_invalid')
        if max(longest.values()) > 3:
            raise RelayError('native_graph_limit')
        participants = sorted({node['task']['assignee'] for node in nodes.values()})
        if any(profile not in PROFILES for profile in participants):
            raise RelayError('native_graph_invalid')
        prefix = 'office-world:' + row['request_id']
        allowed = {prefix, *(prefix + ':' + role for role in ('work', 'work-a', 'work-b', 'verify', 'final'))}
        roles = {}
        for ident, node in nodes.items():
            key = node['task'].get('idempotency_key')
            if key not in allowed or key in roles:
                raise RelayError('native_collaboration_invalid')
            roles[key] = ident
        has_single = prefix + ':work' in roles
        if has_single and any(prefix + ':' + role in roles for role in ('work-a', 'work-b')):
            raise RelayError('native_collaboration_invalid')
        required = {prefix, prefix + ':verify', prefix + ':final', *(prefix + ':' + role for role in (('work',) if has_single else ('work-a', 'work-b')))}
        if not required <= roles.keys():
            return None  # Intake completion is not the collaboration's completion receipt.
        if roles.keys() != required or roles[prefix] != row['task_id']:
            raise RelayError('native_collaboration_invalid')
        work_ids = {roles[key] for key in roles if key.endswith((':work', ':work-a', ':work-b'))}
        verify, final = roles[prefix + ':verify'], roles[prefix + ':final']
        workers = {nodes[ident]['task']['assignee'] for ident in work_ids}
        verifier = nodes[verify]['task']['assignee']
        if (nodes[row['task_id']]['task']['assignee'] != 'lumi' or nodes[final]['task']['assignee'] != 'lumi'
                or 'lumi' in workers or verifier in workers | {'lumi'} or not 3 <= len(participants) <= 4
                or incoming[row['task_id']] or any(incoming[ident] != {row['task_id']} for ident in work_ids)
                or incoming[verify] != work_ids or incoming[final] != work_ids | {verify}):
            raise RelayError('native_collaboration_invalid')
        completions = {}
        for ident, node in nodes.items():
            latest = max(node['runs'], key=lambda run: run['id'], default=None)
            if node['task']['status'] == 'blocked':
                events = [e for e in node['events'] if latest and e['kind'] == 'blocked' and e['run_id'] == latest['id']]
                if (not latest or latest['status'] != 'blocked' or latest['outcome'] != 'blocked'
                        or latest['profile'] != node['task']['assignee'] or not latest['ended_at']):
                    return None
                if events:
                    event = max(events, key=lambda e: e['id'])
                    return {'request_id': row['request_id'], 'task_id': ident, 'run_id': event['run_id'], 'event_id': event['id'], 'participants': participants, 'terminal_state': 'blocked'}
                return None
            matches = [e for e in node['events'] if latest and e['kind'] == 'completed' and e['run_id'] == latest['id']]
            if node['task']['status'] != 'done' or not latest or latest['status'] != 'done' or latest['outcome'] != 'completed' or latest['profile'] != node['task']['assignee'] or not latest['ended_at'] or not matches:
                return None
            completions[ident] = max(matches, key=lambda e: e['id'])
        event = completions[final]
        if event['id'] != max(proof['id'] for proof in completions.values()):
            return None
        return {'request_id': row['request_id'], 'task_id': event['task_id'], 'run_id': event['run_id'], 'event_id': event['id'], 'participants': participants, 'terminal_state': 'completed'}

    def tick(self):
        if not self.notify_enabled or self.sender is None:
            return
        with self.lock:
            rows = list(self.watches.values())
            snapshot = [dict(row) for row in (rows[self.poll_offset:] + rows[:self.poll_offset])[:8]]
            self.poll_offset = (self.poll_offset + 8) % len(rows) if rows else 0
        for row in snapshot:
            try:
                target = self.source()['chat_id']
                if hashlib.sha256(target.encode()).hexdigest() != row['target_hash']:
                    continue
                if row['state'] in {'pending', 'sent_unverified', 'unknown'}:
                    confirmed = self.sender.readback(target, {'notice': row['notice'], 'message_id': row['message_id']})
                    row['state'] = 'confirmed' if confirmed else ('unknown' if row['state'] == 'pending' else row['state'])
                    if confirmed:
                        row.pop('error_code', None)
                    with self.lock:
                        remember_receipt(row)
                        self.watches[row['request_id']] = row; save_private_json(self.state_file, self.watches)
                    if not confirmed:
                        continue  # An unresolved old send fences later notices; it is never reposted.
                notice = self.terminal(row)
                if (not notice or notice_reference(notice) == notice_reference(row['notice'])
                        or notice['event_id'] <= row.get('notice_cursor', 0)):
                    continue
                status_message(notice)
                row.update(state='pending', notice=notice, message_id=None)
                row.pop('error_code', None)
                with self.lock:
                    remember_receipt(row)
                    self.watches[row['request_id']] = row; save_private_json(self.state_file, self.watches)
                try:
                    receipt = self.sender.send(target, notice)
                    row.update(state='sent_unverified', message_id=receipt.get('message_id'))
                except Exception:
                    row.update(state='unknown', error_code='notification_ack_unknown')
                with self.lock:
                    remember_receipt(row)
                    self.watches[row['request_id']] = row; save_private_json(self.state_file, self.watches)
            except Exception as error:
                # Persist a safe code, never the native exception, summary or transport response.
                row['error_code'] = error.code if isinstance(error, RelayError) else 'notification_unavailable'
                with self.lock:
                    self.watches[row['request_id']] = row; save_private_json(self.state_file, self.watches)

    def handle(self, value, uid):
        try:
            if uid != self.allow_uid and not (uid == self.read_probe_uid and isinstance(value, dict) and value.get('op') in {'board', 'task', 'delivery_status'}):
                raise RelayError('forbidden')
            if not isinstance(value, dict) or value.get('op') not in {'board', 'task', 'create', 'subscribe', 'delivery_status'}:
                raise RelayError('invalid_operation')
            op = value['op']
            expected = {'board': {'op'}, 'task': {'op', 'task_id'}, 'create': {'op', 'request_id', 'payload'}, 'subscribe': {'op', 'request_id', 'task_id'}, 'delivery_status': {'op', 'request_id', 'task_id'}}[op]
            if set(value) != expected:
                raise RelayError('invalid_fields')
            if op == 'board':
                result = self.board()
            elif op == 'task':
                result = self.task(task_id(value['task_id']))
            else:
                rid = request_uuid(value['request_id'])
                result = self.create(rid, value['payload']) if op == 'create' else getattr(self, op)(rid, task_id(value['task_id']))
            packet = {'ok': True, 'result': result}
            if len(json.dumps(packet).encode()) > MAX_OUTPUT - 1:
                raise RelayError('response_limit')
            return packet
        except RelayError as error:
            return {'ok': False, 'error': {'code': error.code, 'message': str(error)}}
        except Exception:
            return {'ok': False, 'error': {'code': 'native_unavailable', 'message': '기존 비서 연결의 응답을 확인할 수 없습니다.'}}


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.request.settimeout(15)
        try:
            _, uid, _ = struct.unpack('3i', self.request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i')))
            if uid not in {self.server.app.allow_uid, self.server.app.read_probe_uid}:
                packet = self.server.app.handle({}, uid)
            else:
                raw = self.rfile.readline(MAX_INPUT + 1)
                if len(raw) > MAX_INPUT or not raw.endswith(b'\n'):
                    raise RelayError('request_limit')
                packet = self.server.app.handle(json.loads(raw), uid)
        except Exception:
            packet = {'ok': False, 'error': {'code': 'invalid_request', 'message': '비서 연결 요청 형식을 확인해 주세요.'}}
        try:
            self.wfile.write(json.dumps(packet, ensure_ascii=False).encode() + b'\n')
        except OSError:
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path)
    parser.add_argument('--slack', choices=['send', 'readback'])
    args = parser.parse_args()
    if sys.platform != 'linux' or os.geteuid() != 1001:
        raise RelayError('native_runtime_required')
    config = private_json(args.config)
    allowed = {'socket_path', 'socket_gid', 'state_file', 'source_task_id', 'notify_enabled', 'allow_uid', 'read_probe_uid', 'office_origin', 'native_python', 'native_repo', 'pythonpath'}
    if set(config) - allowed or config.get('allow_uid', 1000) != 1000 or type(config.get('notify_enabled', False)) is not bool:
        raise RelayError('invalid_configuration')
    runtime = trusted_runtime(config) if config.get('notify_enabled') or args.slack else None
    if args.slack:
        slack_child(args.slack, runtime); return
    script_info = Path(__file__).lstat()
    script_parent = Path(__file__).parent.lstat()
    if (not stat.S_ISREG(script_info.st_mode) or script_info.st_uid != os.geteuid() or stat.S_IMODE(script_info.st_mode) & 0o022
            or not stat.S_ISDIR(script_parent.st_mode) or script_parent.st_uid != os.geteuid() or stat.S_IMODE(script_parent.st_mode) & 0o022
            or not Path(config['state_file']).is_absolute()):
        raise RelayError('native_owned_script_required')
    socket_path = Path(config['socket_path'])
    info = socket_path.parent.lstat()
    if not socket_path.is_absolute() or socket_path.exists() or socket_path.is_symlink() or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o027:
        raise RelayError('private_socket_directory_required')
    source_id = task_id(config['source_task_id'])
    source = lambda: approved_target(source_id)
    source()
    app = Relay(NativeHTTP(), config['state_file'], source=source, sender=SlackSender(args.config, runtime, config.get('office_origin')) if runtime else None,
                notify_enabled=config.get('notify_enabled', False), allow_uid=config.get('allow_uid', 1000), read_probe_uid=config.get('read_probe_uid'))
    class LocalServer(socketserver.UnixStreamServer):
        def handle_error(self, request, client_address):
            pass
    server = LocalServer(str(socket_path), Handler)
    server.app = app
    os.chown(socket_path, -1, int(config['socket_gid'])); os.chmod(socket_path, 0o660)
    socket_inode = socket_path.lstat().st_ino
    server.timeout = 1
    stop = threading.Event()
    def watch():
        while not stop.wait(10):
            app.tick()
    thread = threading.Thread(target=watch, daemon=True); thread.start()
    def terminate(*_):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    try:
        server.serve_forever(poll_interval=1)
    finally:
        stop.set(); server.server_close()
        try:
            current = socket_path.lstat()
            if stat.S_ISSOCK(current.st_mode) and current.st_uid == os.geteuid() and current.st_ino == socket_inode:
                socket_path.unlink()
        except FileNotFoundError:
            pass


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # No exception, command, configuration, token or native response is printed.
        print('{"ok":false,"error":{"code":"relay_unavailable","message":"비서 연결을 확인해 주세요."}}')
        sys.exit(1)
