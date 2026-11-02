#!/usr/bin/env python3
"""Lumi-only verified Slack intake candidate. No Slack writes or native SQL."""
import sys

if __name__ == '__main__' and not sys.flags.isolated:
    print('{"ok":false,"error":{"code":"isolated_runtime_required"}}')
    sys.exit(1)

import argparse
import asyncio
from decimal import Decimal
import hashlib
import hmac
import importlib.util
import json
import logging
import os
from pathlib import Path
import re
import stat
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener
import uuid

BASE = 'http://127.0.0.1:8510'
ORIGIN_FIELDS = ('PLATFORM', 'PROFILE', 'CHAT_ID', 'CHAT_TYPE', 'THREAD_ID', 'MESSAGE_ID', 'USER_ID', 'SCOPE_ID')
TS = re.compile(r'\d{9,16}\.\d{6}\Z')


class IntakeError(ValueError):
    pass


def context(env):
    result = {key.lower(): env.get('HERMES_SESSION_' + key, '') for key in ORIGIN_FIELDS}
    if (result['platform'] != 'slack' or result['profile'] != 'lumi' or env.get('HERMES_CRON_SESSION')
            or result['chat_type'] not in {'dm', 'group'}
            or not re.fullmatch('[CGD][A-Z0-9]{8,24}', result['chat_id'])
            or not re.fullmatch('[UW][A-Z0-9]{8,24}', result['user_id'])
            or not re.fullmatch('T[A-Z0-9]{8,24}', result['scope_id'])
            or not TS.fullmatch(result['message_id'])
            or (result['thread_id'] and not TS.fullmatch(result['thread_id']))):
        raise IntakeError('verified_slack_context_required')
    return result


def verify_message(ctx, identity, message, allowed, now):
    text = message.get('text')
    if (not allowed or '*' in allowed or any(not re.fullmatch('[UW][A-Z0-9]{8,24}', x) for x in allowed)
            or ctx['user_id'] not in allowed or identity.get('ok') is not True
            or identity.get('team_id') != ctx['scope_id'] or identity.get('user_id') == ctx['user_id']
            or not re.fullmatch('[UW][A-Z0-9]{8,24}', str(identity.get('user_id', '')))
            or message.get('user') != ctx['user_id'] or message.get('ts') != ctx['message_id']
            or message.get('team', ctx['scope_id']) != ctx['scope_id']
            or message.get('bot_id') or message.get('subtype') or message.get('edited')
            or message.get('files') or message.get('attachments')
            or (message.get('thread_ts') or message['ts']) != (ctx['thread_id'] or ctx['message_id'])
            or not isinstance(text, str) or not text.strip() or len(text) > 4000 or len(text.encode()) > 12000
            or not -30 <= Decimal(str(now)) - Decimal(ctx['message_id']) <= 600):
        raise IntakeError('slack_message_not_authorized')
    body = text.strip()
    own_mention = '<@' + identity['user_id'] + '>'
    if body.startswith(own_mention): body = body[len(own_mention):].strip()
    if not body: raise IntakeError('empty_request')
    ident = ':'.join((ctx['scope_id'], ctx['chat_id'], ctx['message_id']))
    return {'request_id': str(uuid.uuid5(uuid.NAMESPACE_URL, 'heobrain-slack-intake:' + ident)),
            'text_hash': hashlib.sha256(text.encode()).hexdigest(), 'text': body}


async def fetch_message(client, ctx):
    identity = await client.auth_test()
    params = dict(channel=ctx['chat_id'], oldest=ctx['message_id'], latest=ctx['message_id'], inclusive=True, limit=100)
    if ctx['thread_id'] and ctx['thread_id'] != ctx['message_id']:
        data = await client.conversations_replies(ts=ctx['thread_id'], **params)
    else:
        data = await client.conversations_history(**params)
    matches = [row for row in data.get('messages', []) if row.get('ts') == ctx['message_id']]
    if data.get('ok') is not True or len(matches) != 1: raise IntakeError('slack_message_unavailable')
    return identity, matches[0]


def relay_module():
    spec = importlib.util.spec_from_file_location('native_board_relay', Path(__file__).with_name('hermes-board-relay.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def trusted_code():
    directory = Path.home()/'.hermes/office-relay/code'
    if Path(__file__).resolve().parent != directory:
        raise IntakeError('native_owned_code_required')
    for path in (Path.home()/'.hermes', directory.parent, directory,
                 *(directory/name for name in ('slack-office-intake.py','hermes-board-relay.py','assistant_request_protocol.py'))):
        info = path.lstat()
        expected = stat.S_ISREG if path.name.endswith('.py') else stat.S_ISDIR
        if not expected(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o022:
            raise IntakeError('native_owned_code_required')


def protocol_module():
    # Deployment copies the exact shared module beside this native-owned helper.
    # Never import the Ubuntu-owned web application into this native process.
    spec = importlib.util.spec_from_file_location('assistant_request_protocol', Path(__file__).with_name('assistant_request_protocol.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


class NativeCreator:
    def __init__(self, native, state_file):
        self.module = relay_module()
        self.relay = self.module.Relay(native, state_file, source=lambda: {})

    def create(self, value):
        ident = value['request_id']
        payload = protocol_module().task_payload(ident, value['text'])
        try:
            result = self.relay.create(ident, payload)
        except self.module.RelayError as error:
            if error.code == 'native_admission_unknown':
                return {'request_id': ident, 'native_task_id': None, 'board': 'heobrain-office', 'status': 'admission_unknown'}
            raise IntakeError(error.code) from None
        return {'request_id': ident, 'native_task_id': result['task']['id'], 'board': 'heobrain-office', 'status': 'queued'}


def submit(value, expected_hash, creator, office):
    if not isinstance(expected_hash, str) or not hmac.compare_digest(value['text_hash'], expected_hash):
        raise IntakeError('current_message_hash_mismatch')
    ident = value['request_id']
    receipt = safe_receipt(creator.create(value), ident)
    if receipt['status'] == 'admission_unknown': return receipt
    try:
        current = office.lookup(ident)  # Original daemon attaches watch metadata; never create via GET.
    except (OSError, ValueError):
        return receipt  # Admission stands. A later GET may attach delivery without task resubmission.
    if current is None: return receipt
    current = safe_receipt(current, ident)
    if current['native_task_id'] != receipt['native_task_id']: raise IntakeError('request_conflict')
    return current


def safe_receipt(value, ident, origin=None):
    if (not isinstance(value, dict) or value.get('request_id') != ident or value.get('board') != 'heobrain-office'
            or value.get('status') not in {'queued','running','blocked','completed','failed','admission_unknown'}
            or (value.get('native_task_id') is not None and not re.fullmatch('t_[A-Za-z0-9_-]{1,80}', str(value['native_task_id'])))):
        raise IntakeError('invalid_office_receipt')
    result = {key: value.get(key) for key in ('request_id','native_task_id','board','status')}
    if origin:
        parsed = urlsplit(origin)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.path not in {'','/'} or parsed.query or parsed.fragment:
            raise IntakeError('invalid_office_origin')
        result['url'] = origin.rstrip('/') + '/office3d?assistant_request=' + ident
    return result


class OfficeReader:
    def __init__(self):
        self.opener = build_opener(ProxyHandler({}), relay_module().NoRedirect())
    def lookup(self, ident):
        if str(uuid.UUID(ident)) != ident: raise IntakeError('invalid_request')
        request = Request(BASE + '/api/assistant/requests/' + ident, method='GET')
        try:
            with self.opener.open(request, timeout=15) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000: raise IntakeError('office_response_limit')
                value = json.loads(raw)
                if not isinstance(value, dict): raise IntakeError('invalid_office_receipt')
                return value
        except HTTPError as error:
            if error.code == 404: return None
            raise IntakeError('office_request_rejected') from None


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('mode', choices=['inspect','submit','status'])
    parser.add_argument('--expected-sha256'); args = parser.parse_args()
    if sys.platform != 'linux' or os.geteuid() != 1001: raise IntakeError('native_runtime_required')
    trusted_code()
    ctx = context(os.environ)
    relay = relay_module(); config = relay.private_json(Path.home()/'.hermes/office-relay/config.json')
    runtime = relay.trusted_runtime(config)
    if Path(sys.executable).absolute() != Path(runtime['native_python']).absolute():
        import pwd
        owner = pwd.getpwuid(os.geteuid())
        env = {'HOME':str(Path.home()),'USER':owner.pw_name,'LOGNAME':owner.pw_name,'PATH':'/usr/bin:/bin','LANG':'C.UTF-8',
               **{'HERMES_SESSION_'+key:os.environ.get('HERMES_SESSION_'+key,'') for key in ORIGIN_FIELDS}}
        os.execve(runtime['native_python'], [runtime['native_python'],'-I','-B',str(Path(__file__).resolve()),*sys.argv[1:]], env)
    ident = str(uuid.uuid5(uuid.NAMESPACE_URL, 'heobrain-slack-intake:' + ':'.join((ctx['scope_id'],ctx['chat_id'],ctx['message_id']))))
    logging.disable(logging.CRITICAL)
    sys.path[:0] = [runtime['native_repo'], *runtime['pythonpath']]
    os.environ.update(HERMES_HOME=str(relay.LUMI_HOME),HERMES_PROFILE='lumi')
    from dotenv import load_dotenv
    load_dotenv(relay.LUMI_HOME/'.env', override=True)
    if any(os.environ.get(key,'').lower() in {'1','true','yes'} for key in ('SLACK_ALLOW_ALL_USERS','GATEWAY_ALLOW_ALL_USERS')):
        raise IntakeError('explicit_owner_allowlist_required')
    allowed = {value.strip() for value in os.environ.get('SLACK_ALLOWED_USERS','').split(',') if value.strip()}
    if (not allowed or ctx['user_id'] not in allowed or any(not re.fullmatch('[UW][A-Z0-9]{8,24}', x) for x in allowed)):
        raise IntakeError('explicit_owner_allowlist_required')
    if args.mode == 'status':
        result = OfficeReader().lookup(ident)
        if result is None: raise IntakeError('request_not_found')
        print(json.dumps({'ok':True, **safe_receipt(result,ident,config.get('office_origin'))})); return
    from gateway.config import load_gateway_config, Platform
    from slack_sdk.web.async_client import AsyncWebClient
    client = AsyncWebClient(token=load_gateway_config().platforms[Platform.SLACK].token, timeout=10, retry_handlers=[])
    identity, message = asyncio.run(fetch_message(client,ctx))
    value = verify_message(ctx,identity,message,allowed,time.time())
    if args.mode == 'inspect':
        print(json.dumps({'ok':True,'request_id':value['request_id'],'text_sha256':value['text_hash'],'characters':len(value['text'])})); return
    result = submit(value,args.expected_sha256,NativeCreator(relay.NativeHTTP(),config['state_file']),OfficeReader())
    print(json.dumps({'ok':True, **safe_receipt(result,ident,config.get('office_origin'))}))


if __name__ == '__main__':
    try: main()
    except Exception as error:
        code = str(error) if isinstance(error, IntakeError) and re.fullmatch('[a-z_]{1,80}', str(error)) else 'slack_intake_unavailable'
        print(json.dumps({'ok':False,'error':{'code':code}})); sys.exit(1)
