#!/usr/bin/env python3
"""Native webhook script: retain external data for human review; never create a task."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import time

PROFILE, BOARD, TENANT = 'lumi', 'heobrain-office', 'heobrain-world'
ROUTE = 'heobrain-review-intake'
MAX_BYTES, MAX_PENDING = 16384, 512
FIELDS = {'version', 'event_id', 'occurred_at', 'profile', 'tenant', 'board', 'type', 'text'}


def validate(value, storage, now):
    if (not isinstance(value, dict) or set(value) != FIELDS
            or type(value['version']) is not int or value['version'] != 1
            or (value['profile'], value['board'], value['tenant'], value['type']) != (PROFILE, BOARD, TENANT, 'inquiry')
            or type(value['occurred_at']) is not int or abs(now - value['occurred_at']) > 300
            or not isinstance(value['event_id'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value['event_id'])):
        raise ValueError('invalid_event')
    text = value['text']
    if (not isinstance(text, str) or not text.strip() or len(text) > 4000
            or storage.CREDENTIAL_BODY.search(text)
            or any(ord(ch) < 32 and ch not in '\n\t\r' for ch in text)):
        raise ValueError('unsafe_text')
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    if len(encoded) > MAX_BYTES:
        raise ValueError('payload_limit')
    return encoded


def retain(value, pending, storage, *, now=None):
    now = int(time.time()) if now is None else now
    encoded = validate(value, storage, now)
    info = pending.lstat()
    if (not stat.S_ISDIR(info.st_mode)
            or (os.name != 'nt' and (info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700))):
        raise ValueError('private_directory_required')
    digest = hashlib.sha256(encoded).hexdigest()
    ident = hashlib.sha256((PROFILE + ':' + ROUTE + ':' + value['event_id']).encode()).hexdigest()
    path = pending / (ident + '.json')
    # Reuse the existing relay's cross-process lock and private atomic writer, not its task API.
    with storage.admission_file_lock(pending / '.intake'):
        previous = storage.private_json(path, missing=True)
        if previous:
            if (previous.get('sha256') != digest or previous.get('event') != value
                    or previous.get('status') != 'pending_review'):
                raise ValueError('delivery_conflict')
            return {'status': 'duplicate', 'receipt': ident}
        if path.exists():
            raise ValueError('invalid_existing_record')
        if sum(1 for _ in pending.glob('*.json')) >= MAX_PENDING:
            raise ValueError('capacity_reached')
        storage.save_private_json(path, {'status': 'pending_review', 'sha256': digest,
                                        'received_at': now, 'event': value})
    return {'status': 'pending_review', 'receipt': ident}


def check_candidate(default, lumi, subscriptions):
    """Read-only guard for the proposed native config; it never writes/enables a receiver."""
    webhook = default.get('platforms', {}).get('webhook', {})
    extra = webhook.get('extra', {})
    if (default.get('gateway', {}).get('multiplex_profiles') is not True or webhook.get('enabled') is not True
            or extra != {'host': '127.0.0.1', 'port': 8644, 'max_body_bytes': MAX_BYTES,
                         'rate_limit': 5, 'script_timeout_seconds': 5}
            or lumi.get('platforms', {}).get('webhook', {}).get('enabled', False) is not False):
        raise ValueError('unsafe_receiver_config')
    if not isinstance(subscriptions, dict) or set(subscriptions) != {ROUTE}:
        raise ValueError('unexpected_routes')
    route = subscriptions[ROUTE]
    expected = {'profile': PROFILE, 'events': ['inquiry'], 'prompt': '', 'skills': [], 'deliver': 'log',
                'script': 'hermes-webhook-intake.py', 'toolsets': ['web']}
    if (not isinstance(route, dict) or set(route) - set(expected) - {'secret', 'description', 'created_at'}
            or any(route.get(key) != value for key, value in expected.items())
            or not isinstance(route.get('secret'), str) or len(route['secret'].strip()) < 32
            or route['secret'] == 'INSECURE_NO_AUTH'):
        raise ValueError('unsafe_route_config')
    return {'status': 'candidate_valid', 'profile': PROFILE, 'board': BOARD, 'tenant': TENANT}


def private_path(path, *, directory=False):
    info = path.lstat()
    if (path.is_symlink() or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
            or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & (0o022 if directory else 0o177)):
        raise ValueError('untrusted_installation')


def native_storage():
    if os.name == 'nt':
        raise ValueError('native_installation_required')
    import pwd
    home = Path(pwd.getpwuid(os.geteuid()).pw_dir)
    root = home / '.hermes'
    own = root / 'profiles/lumi/scripts/hermes-webhook-intake.py'
    helper = root / 'office-relay/code/hermes-board-relay.py'
    if Path(__file__).absolute() != own or own.resolve() != own:
        raise ValueError('native_installation_required')
    for path in (own, helper):
        private_path(path)
        parent = path.parent
        while parent != home:
            private_path(parent, directory=True)
            parent = parent.parent
    pending = root / 'profiles/lumi/webhook-intake/pending-review'
    private_path(pending.parent, directory=True)
    spec = importlib.util.spec_from_file_location('native_webhook_storage', helper)
    storage = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(storage)
    return storage, pending


def read_event(stream):
    # Native serializes with ensure_ascii=True; keep its bounded transport separate from UTF-8 payload size.
    raw = stream.read(MAX_BYTES * 6 + 1)
    if len(raw) > MAX_BYTES * 6:
        raise ValueError('payload_limit')
    return json.loads(raw)


def main():
    try:
        value = read_event(sys.stdin.buffer)
        storage, pending = native_storage()
        receipt = retain(value, pending, storage)
        print('webhook_intake ' + receipt['status'] + ' ' + receipt['receipt'], file=sys.stderr)
        code = 0
    except Exception:
        # Native script failures are consumed (HTTP ignored), never retried or turned into agent work.
        print('webhook_intake refused; operator review required', file=sys.stderr)
        code = 1
    print('[SILENT]')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
