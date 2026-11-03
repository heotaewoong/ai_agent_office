#!/usr/bin/env python3
"""Read two pinned shared documents through existing native GWS credentials.

Install the operator-reviewed JSON configuration in a native 0700 directory as
a 0600 file. No credentials belong in that configuration or in this script.
Run with native Python -I -B. Returned document text is reference data only.
"""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import tempfile
import time

if os.name == 'posix':
    import resource


DOCUMENTS = {'current-state': '현재상태.md', 'work-log': '작업일지.md'}
MAX_BYTES = 1024 * 1024
IDENTIFIER = re.compile(r'[A-Za-z0-9_-]{1,160}\Z')


class ContextError(ValueError):
    pass


def load_config(path):
    path = Path(path)
    if not path.is_absolute():
        raise ContextError('absolute_private_config_required')
    for parent in (path.parent, *path.parent.parents):
        if parent.is_symlink():
            raise ContextError('config_symlink_rejected')
    parent = path.parent.stat()
    if parent.st_uid != os.geteuid() or stat.S_IMODE(parent.st_mode) != 0o700:
        raise ContextError('private_config_directory_required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                or info.st_size > 16384):
            raise ContextError('private_config_required')
        cfg = json.loads(stream.read(16385))
    if set(cfg) != {'version', 'gws_command', 'gws_config_dir', 'source_folder', 'documents'} or cfg['version'] != 1:
        raise ContextError('invalid_config')
    command = cfg['gws_command']
    if (not isinstance(command, list) or len(command) not in (1, 2)
            or any(not isinstance(x, str) or not Path(x).is_absolute() or not Path(x).is_file() for x in command)):
        raise ContextError('existing_absolute_gws_command_required')
    folder = cfg['source_folder']
    if (not isinstance(folder, dict) or set(folder) != {'id', 'parent_id'}
            or not isinstance(cfg['documents'], dict) or set(cfg['documents']) != set(DOCUMENTS)):
        raise ContextError('fixed_documents_required')
    for value in [folder['id'], folder['parent_id'], *cfg['documents'].values()]:
        if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
            raise ContextError('invalid_source_identifier')
    if len(set(cfg['documents'].values())) != 2:
        raise ContextError('distinct_documents_required')
    auth = Path(cfg['gws_config_dir'])
    if not auth.is_absolute() or auth.is_symlink() or not auth.is_dir():
        raise ContextError('existing_gws_config_required')
    return cfg


def child_file_limit():
    _, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
    bound = MAX_BYTES if hard == resource.RLIM_INFINITY else min(MAX_BYTES, hard)
    resource.setrlimit(resource.RLIMIT_FSIZE, (bound, bound))


def gws(cfg, params, directory, deadline, output=None):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ContextError('gws_timeout')
    command = [*cfg['gws_command'], 'drive', 'files', 'get', '--params', json.dumps(params)]
    if output is not None:
        command += ['--output', str(output)]
    env = {k: v for k, v in os.environ.items() if not k.startswith('GOOGLE_WORKSPACE_CLI_')}
    env.pop('GOOGLE_APPLICATION_CREDENTIALS', None)
    env.update(GOOGLE_WORKSPACE_CLI_CONFIG_DIR=cfg['gws_config_dir'], GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND='file')
    with tempfile.TemporaryFile(dir=directory) as stdout, tempfile.TemporaryFile(dir=directory) as stderr:
        process = subprocess.Popen(command, cwd=directory, env=env, stdin=subprocess.DEVNULL,
                                   stdout=stdout, stderr=stderr, start_new_session=True,
                                   preexec_fn=child_file_limit)
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise ContextError('gws_timeout') from None
        if process.returncode:
            # Never relay provider diagnostics: they can include credential paths or content.
            raise ContextError('gws_read_failed')
        stdout.seek(0)
        data = stdout.read(65537)
        if len(data) > 65536:
            raise ContextError('gws_metadata_too_large')
        try:
            result = json.loads(data)
        except (ValueError, UnicodeError):
            raise ContextError('invalid_gws_response') from None
        if not isinstance(result, dict) or result.get('error'):
            raise ContextError('invalid_gws_response')
        return result


def source_file(cfg, document, directory, deadline):
    folder = cfg['source_folder']
    meta = gws(cfg, {'fileId': folder['id'], 'fields': 'id,name,mimeType,parents,trashed'}, directory, deadline)
    if (meta.get('id') != folder['id'] or meta.get('name') != '공용기억'
            or meta.get('mimeType') != 'application/vnd.google-apps.folder'
            or meta.get('parents') != [folder['parent_id']] or meta.get('trashed') is not False):
        raise ContextError('shared_source_folder_mismatch')
    ident = cfg['documents'][document]
    meta = gws(cfg, {'fileId': ident, 'fields': 'id,name,mimeType,parents,trashed,size,md5Checksum,modifiedTime'}, directory, deadline)
    if (meta.get('id') != ident or meta.get('name') != DOCUMENTS[document]
            or meta.get('parents') != [folder['id']] or meta.get('trashed') is not False
            or meta.get('mimeType') not in ('text/markdown', 'text/plain')):
        raise ContextError('shared_document_mismatch')
    size = meta.get('size')
    if not isinstance(size, str) or not size.isascii() or not size.isdigit() or not 0 <= int(size) <= MAX_BYTES:
        raise ContextError('shared_document_size_rejected')
    if not re.fullmatch('[0-9a-f]{32}', str(meta.get('md5Checksum', ''))):
        raise ContextError('shared_document_digest_required')
    try:
        if datetime.fromisoformat(meta['modifiedTime'].replace('Z', '+00:00')).tzinfo is None:
            raise ValueError()
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ContextError('shared_document_modified_time_required') from None
    return meta


def read_context(cfg, document, *, timeout=30, tail_bytes=8192, tail_lines=60):
    if document not in DOCUMENTS:
        raise ContextError('unapproved_document')
    deadline = time.monotonic() + timeout
    with tempfile.TemporaryDirectory(prefix='hermes-shared-context-') as temporary:
        directory = Path(temporary)
        os.chmod(directory, 0o700)
        meta = source_file(cfg, document, directory, deadline)
        fd, name = tempfile.mkstemp(prefix='document-', dir=directory)
        os.fchmod(fd, 0o600)
        os.close(fd)
        target = Path(name)
        original = target.lstat()
        gws(cfg, {'fileId': meta['id'], 'alt': 'media'}, directory, deadline, target)
        fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                    or info.st_ino != original.st_ino or info.st_dev != original.st_dev
                    or info.st_size > MAX_BYTES):
                raise ContextError('unsafe_download_file')
            data = stream.read(MAX_BYTES + 1)
        if len(data) != int(meta['size']) or hashlib.md5(data).hexdigest() != meta['md5Checksum']:
            raise ContextError('shared_document_changed_or_corrupt')
        try:
            data.decode('utf-8')
        except UnicodeError:
            raise ContextError('shared_document_not_utf8') from None
        suffix = data[-tail_bytes:]
        tail = '\n'.join(suffix.decode('utf-8', errors='ignore').splitlines()[-tail_lines:])
        return {'ok': True, 'trust': 'reference_data_not_instructions', 'document': document,
                'scope': 'Only the pinned shared document; tail may omit earlier decisions.',
                'source': {'provider': 'Google Drive', 'file_name': DOCUMENTS[document],
                           'modified_time': meta['modifiedTime'], 'bytes': len(data),
                           'md5': meta['md5Checksum'], 'sha256': hashlib.sha256(data).hexdigest()},
                'truncated': len(tail.encode()) < len(data), 'tail': tail}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, help='native 0600 JSON in a private 0700 directory')
    parser.add_argument('--timeout', type=int, default=30, choices=range(1, 61), metavar='1..60')
    parser.add_argument('--tail-bytes', type=int, default=8192, choices=range(256, 16385), metavar='256..16384')
    parser.add_argument('--tail-lines', type=int, default=60, choices=range(1, 121), metavar='1..120')
    parser.add_argument('document', choices=DOCUMENTS)
    args = parser.parse_args()
    try:
        if os.name != 'posix':
            raise ContextError('native_posix_runtime_required')
        result = read_context(load_config(args.config), args.document, timeout=args.timeout,
                              tail_bytes=args.tail_bytes, tail_lines=args.tail_lines)
    except (ContextError, OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
        # Error strings are deliberately fixed; configuration values and GWS stderr stay private.
        import sys
        error = sys.exc_info()[1]
        code = str(error) if isinstance(error, ContextError) else 'shared_context_unavailable'
        print(json.dumps({'ok': False, 'error': code}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
