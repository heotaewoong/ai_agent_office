"""Reviewed BrowserOS MCP runner. Local static code; nonpublic, source-approved items only.

No install/service registration or browser settings changes. --once always needs --id.
An adapter becomes eligible for --enable only after this runner independently reopens
and compares a real saved draft. A successful test never enables watch automatically.

Examples (real nonpublic writes, to be run only by the owner):
  python owner-browseros-drafts.py --once --id od_<24 hex characters>
  python owner-browseros-drafts.py --enable tistory_main
  python owner-browseros-drafts.py --watch
  python owner-browseros-drafts.py --disable tistory_main
  python owner-browseros-drafts.py --status

Official connection reference: https://docs.browseros.com/neo/mcp/manual
Tool contracts are discovered from the installed server's tools/list; no AI model
or downloaded scripts are invoked. LinkedIn's occupied singleton stays in the
office queue. DOM contracts and native typing still require an owner-run real E2E
per account/version; fake tests cannot create verification evidence.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import time
import urllib.request
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
ADAPTER = ROOT / 'owner-browseros-adapters.js'
ENDPOINT = 'http://127.0.0.1:9200/mcp'
CHANNELS = ('youtube_main_ko', 'youtube_english', 'linkedin_personal', 'threads_main',
            'tistory_main', 'naver_blog_main')
DEFAULT_STATE = Path('C:/AI-Office/owner-social-agent/browseros-drafts-state.json')


def stamp():
    return datetime.now(timezone.utc).isoformat()


def normalized(value):
    return value.replace('\r\n', '\n').replace('\r', '\n').strip()


def unwrap_value(value):
    if isinstance(value, str):
        # BrowserOS marks page-derived results as untrusted. Parse only the JSON
        # between the marker header and footer; never evaluate returned strings.
        match = re.fullmatch(r'\[UNTRUSTED_PAGE_CONTENT[^\n]*\][^\n]*\n(.*)\n\[END_UNTRUSTED_PAGE_CONTENT[^\n]*\]', value, re.S)
        if match:
            value = match.group(1)
        return json.loads(value)
    return value


def adapter_expression(operation, payload):
    # Both layers are JSON string literals. Source text is never interpolated as code.
    data = json.dumps(json.dumps({'operation': operation, **payload}, ensure_ascii=True))
    return '(' + ADAPTER.read_text(encoding='utf-8') + ')(JSON.parse(' + data + '))'


class MCP:
    """Stdlib Streamable HTTP client for the installed official tools/list schema."""
    def __init__(self, transport=None):
        self.transport = transport or self._http
        self.sequence = 0
        self.session = None
        self.http_session = None
        self.rpc('initialize', dict(protocolVersion='2024-11-05', capabilities={},
                                  clientInfo=dict(name='heobrain-reviewed-drafts', version='1')))
        self.rpc('notifications/initialized', {}, notification=True)
        tools = self.rpc('tools/list', {})['tools']
        self.tools = {t['name']: t for t in tools}
        if not {'run', 'tabs', 'navigate'}.issubset(self.tools):
            raise ValueError('browseros_tool_contract_missing')

    def _http(self, packet):
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream',
                   'MCP-Protocol-Version': '2024-11-05'}
        if self.http_session:
            headers['Mcp-Session-Id'] = self.http_session
        request = urllib.request.Request(ENDPOINT, json.dumps(packet).encode(), headers, method='POST')
        with urllib.request.urlopen(request, timeout=45) as response:
            self.http_session = response.headers.get('Mcp-Session-Id', self.http_session)
            raw = response.read().decode()
            if not raw:
                return {}
            if response.headers.get('Content-Type', '').startswith('text/event-stream'):
                messages = [json.loads(line[5:].strip()) for line in raw.splitlines() if line.startswith('data:')]
                return next((m for m in messages if m.get('id') == packet.get('id')), {})
            return json.loads(raw)

    def rpc(self, method, params, notification=False):
        self.sequence += 1
        packet = dict(jsonrpc='2.0', method=method, params=params)
        if not notification:
            packet['id'] = self.sequence
        answer = self.transport(packet)
        if answer.get('error'):
            raise RuntimeError('browseros_protocol_error')
        return answer.get('result', {})

    def call(self, name, arguments):
        if name not in self.tools:
            raise ValueError('unlisted_tool')
        if self.session:
            arguments = {**arguments, 'session': self.session}
        result = self.rpc('tools/call', dict(name=name, arguments=arguments))
        self.session = result.get('_meta', {}).get('com.browseros/session', self.session)
        if result.get('isError'):
            raise RuntimeError('browseros_tool_error')
        structured = result.get('structuredContent')
        if name == 'run':
            if not isinstance(structured, dict) or not structured.get('ok'):
                raise RuntimeError('browseros_run_failed')
            return unwrap_value(structured.get('value'))
        return result

    def evaluate(self, page, operation, payload):
        params = json.dumps(dict(expression=adapter_expression(operation, payload),
                                 awaitPromise=True, returnByValue=True))
        code = ('const r=await browser.cdpJsonForPage(' + json.dumps(page)
                + ',"Runtime.evaluate",' + json.dumps(params) + ');'
                + 'if(r.exceptionDetails)throw Error("adapter_evaluation_failed");return r.result.value;')
        value = self.call('run', dict(code=code, timeout=30000))
        if not isinstance(value, dict):
            raise ValueError('invalid_adapter_result')
        return value

    def new_page(self, url):
        def listed():
            result = self.call('tabs', dict(action='list'))
            text = '\n'.join(c.get('text', '') for c in result.get('content', []) if c.get('type') == 'text')
            return {int(n) for n in re.findall(r'^\[(\d+)\] ', text, re.M)}
        before = listed()
        self.call('tabs', dict(action='new', url=url, background=True))
        created = listed() - before
        if len(created) != 1:
            raise ValueError('new_page_id_ambiguous')
        return created.pop()

    def type_text(self, page, value):
        return self.call('run', dict(code='await browser.input(' + json.dumps(page) + ').type('
                                    + json.dumps(value) + ');return {ok:true};'))


class State:
    def __init__(self, path):
        self.path = Path(path)
        self.data = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else dict(channels={}, attempts={})

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temporary, self.path)


@contextmanager
def exclusive(path):
    """Kernel lock releases on crash. Never expires a lease while a sender is alive."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            if path.stat().st_size == 0:
                stream.write(b'0')
                stream.flush()
                stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def validate(row):
    if row.get('channel_key') not in CHANNELS or not re.fullmatch(r'od_[0-9a-f]{24}', row.get('id', '')):
        raise ValueError('unsupported_target')
    if not re.fullmatch(r'[0-9a-f]{64}', row.get('content_hash', '')) or not row.get('account_id'):
        raise ValueError('invalid_approved_content')
    if not isinstance(row.get('text'), str) or len(row['text']) > 150000 or not isinstance(row.get('title'), str):
        raise ValueError('invalid_text')
    end = datetime.fromisoformat(row.get('authorized_end', '').replace('Z', '+00:00'))
    if end <= datetime.now(timezone.utc):
        raise ValueError('window_expired')
    expected = 'private' if row['channel_key'].startswith('youtube_') else 'draft'
    if row.get('visibility') != expected or row.get('publish_at') or row.get('public_publish'):
        raise ValueError('public_or_scheduled_forbidden')


def validate_proof(row, result):
    if not all(result.get(k) is True for k in ('ok', 'verified', 'persisted', 'account_verified')):
        raise ValueError('independent_reopen_required')
    if normalized(result.get('text', '')) != normalized(row['text']):
        raise ValueError('reopened_body_mismatch')
    if row['channel_key'] in ('tistory_main', 'naver_blog_main') and normalized(result.get('title', '')) != normalized(row['title']):
        raise ValueError('reopened_title_mismatch')
    external = result.get('external_id', '')
    parsed = urlparse(external)
    domains = dict(tistory_main='onethingflow.tistory.com', naver_blog_main='blog.naver.com',
                   linkedin_personal='www.linkedin.com', threads_main='www.threads.com')
    if (parsed.scheme != 'https' or parsed.hostname != domains.get(row['channel_key'])
            or '/draft/od_' in external or not result.get('list_key') or len(external) > 500):
        raise ValueError('observed_platform_identity_required')


class Browser:
    def __init__(self, mcp):
        self.mcp = mcp
        self.pages = {}

    def preflight(self, row):
        urls = dict(tistory_main='https://onethingflow.tistory.com/manage/newpost/',
                    naver_blog_main='https://blog.naver.com/oneflowwhy/postwrite',
                    linkedin_personal='https://www.linkedin.com/feed/', threads_main='https://www.threads.com/')
        page = self.mcp.new_page(urls[row['channel_key']])
        self.pages[row['id']] = page
        return self.mcp.evaluate(page, 'prepare', {'item': row})

    def deliver(self, row, recheck):
        page = self.pages[row['id']]
        payload = {'item': row}
        operations = ('fill', 'save', 'open-list', 'open-draft', 'verify')
        if row['channel_key'] == 'naver_blog_main':
            for operation, value in (('focus-title', row['title']), ('focus-body', row['text'])):
                recheck()
                result = self.mcp.evaluate(page, operation, payload)
                if not result.get('ok'):
                    raise ValueError(result.get('reason', 'naver_focus_failed'))
                recheck()
                self.mcp.type_text(page, value)
            operations = ('check-input', 'save', 'open-list', 'open-draft', 'verify')
        for operation in operations:
            recheck()
            if operation == 'open-list':
                self.mcp.call('navigate', dict(page=page, action='reload'))
            result = self.mcp.evaluate(page, operation, payload)
            if not result.get('ok'):
                raise ValueError(result.get('reason', operation + '_failed'))
            if operation == 'open-draft':
                payload['ticket'] = result
        return result


class Runner:
    def __init__(self, host, browser, state, version=None):
        self.host, self.browser, self.state = host, browser, state
        self.version = version or hashlib.sha256(Path(__file__).read_bytes() + ADAPTER.read_bytes()).hexdigest()

    def request(self, command, **fields):
        answer = self.host.handle(dict(command=command, **fields))
        if not answer.get('ok'):
            raise ValueError('native_host_rejected')
        return answer

    def enable(self, channel):
        record = self.state.data['channels'].get(channel, {})
        if channel not in CHANNELS or record.get('version') != self.version or not record.get('verified_at'):
            raise ValueError('real_save_reopen_verification_required')
        record['enabled'] = True
        self.state.save()

    def once(self, rid, rows=None):
        if not re.fullmatch(r'od_[0-9a-f]{24}', rid):
            raise ValueError('explicit_single_id_required')
        if rid in self.state.data['attempts']:
            return dict(id=rid, state='already_attempted')
        rows = self.request('poll')['items'] if rows is None else rows
        candidates = [r for r in rows if r.get('id') == rid]
        if len(candidates) != 1:
            return dict(id=rid, state='not_pending')
        row = candidates[0]
        if row.get('channel_key', '').startswith('instagram'):
            return dict(id=rid, state='unsupported_instagram', reason='office_hold_approval_2_preserved')
        claimed = None
        mutation = False
        try:
            validate(row)
            youtube = row['channel_key'].startswith('youtube_')
            if not youtube:
                ready = self.browser.preflight(row)
                if not ready.get('ok') or not ready.get('account_verified') or not ready.get('empty'):
                    return dict(id=rid, state='blocked', reason=ready.get('reason', 'account_or_empty_editor_required'))
            claimed = self.request('claim', id=rid)['item']
            validate(claimed)
            if any(claimed.get(k) != row.get(k) for k in ('id', 'channel_key', 'account_id', 'content_hash', 'source_hash', 'title', 'text', 'visibility')):
                raise ValueError('approved_content_changed_during_claim')
            def recheck():
                current = self.host.row_for(dict(id=rid, claim_id=claimed['claim_id']))
                validate(current)
                if any(current.get(k) != claimed.get(k) for k in ('content_hash', 'account_id', 'source_hash', 'title', 'text')):
                    raise ValueError('approval_changed_before_action')
            recheck()
            # Filling can trigger a native autosave. Journal before the first write,
            # not only before clicking Save; a crash must never cause an auto retry.
            self.state.data['attempts'][rid] = dict(state='unknown', channel=claimed['channel_key'],
                                                  claim_id=claimed['claim_id'], at=stamp())
            self.state.save()
            mutation = True
            if youtube:
                result = self.request('youtube-private', id=rid, claim_id=claimed['claim_id'])
                if result.get('state') != 'platform_private':
                    raise ValueError('private_upload_unverified')
                final_state = 'platform_private'
                evidence = dict(external_id=result.get('external_id'), native_requery=True)
            else:
                result = self.browser.deliver(claimed, recheck)
                validate_proof(claimed, result)
                final_state = 'platform_draft'
                self.receipt(claimed, final_state, external_id=result['external_id'])
                evidence = {k: result[k] for k in ('external_id', 'list_key')}
            self.state.data['attempts'][rid].update(state=final_state, evidence=evidence)
            previous = self.state.data['channels'].get(claimed['channel_key'], {})
            enabled = (previous.get('enabled') is True and previous.get('version') == self.version
                       and previous.get('account_id') == claimed['account_id'])
            self.state.data['channels'][claimed['channel_key']] = dict(version=self.version, account_id=claimed['account_id'],
                verified_at=stamp(), enabled=enabled, evidence=evidence, verified_item=rid)
            self.state.save()
            return dict(id=rid, state=final_state)
        except Exception as error:
            state = 'unknown' if mutation else 'blocked'
            # Exception strings may contain remote data. Persist only reviewed codes.
            reason = str(error) if isinstance(error, ValueError) and re.fullmatch(r'[a-z0-9_]{1,100}', str(error)) else 'connection_or_adapter_interrupted'
            if claimed:
                try:
                    self.receipt(claimed, state, reason=reason)
                except Exception:
                    pass
            if mutation:
                self.state.data['attempts'][rid].update(state='unknown', reason=reason)
                self.state.save()
            return dict(id=rid, state=state, reason=reason)

    def receipt(self, row, state, **fields):
        proof = {k: row[k] for k in ('claim_id', 'content_hash', 'account_id')}
        proof.update(state=state, **fields)
        return self.request('receipt', id=row['id'], claim_id=row['claim_id'], proof=proof)

    def tick(self):
        rows = self.request('poll')['items']
        results = []
        for row in rows:
            record = self.state.data['channels'].get(row.get('channel_key'), {})
            if record.get('enabled') is True and record.get('version') == self.version and record.get('account_id') == row.get('account_id'):
                results.append(self.once(row['id'], rows))
        return results


def load_host():
    spec = importlib.util.spec_from_file_location('reviewed_owner_draft_host', 'C:/AI-Office/owner-social-agent/draft_host.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--once', action='store_true')
    modes.add_argument('--watch', action='store_true')
    modes.add_argument('--enable', choices=CHANNELS)
    modes.add_argument('--disable', choices=CHANNELS)
    modes.add_argument('--status', action='store_true')
    parser.add_argument('--id')
    parser.add_argument('--state', type=Path, default=DEFAULT_STATE)
    args = parser.parse_args()
    if args.once != bool(args.id):
        parser.error('--once requires exactly one --id; --id is forbidden for other modes')
    with exclusive(args.state.with_suffix('.lock')):
        state = State(args.state)
        if args.status:
            print(json.dumps(state.data, ensure_ascii=False, indent=2))
            return
        app = Runner(None, None, state)
        if args.enable:
            app.enable(args.enable)
            print(json.dumps(dict(enabled=args.enable)))
            return
        if args.disable:
            if args.disable in state.data['channels']:
                state.data['channels'][args.disable]['enabled'] = False
                state.save()
            return
        app.host = load_host()
        app.browser = Browser(MCP())
        if args.once:
            print(json.dumps(app.once(args.id), ensure_ascii=False))
        else:
            while True:
                try:
                    results = app.tick()
                    if results:
                        print(json.dumps(results, ensure_ascii=False), flush=True)
                except Exception:
                    print('{"state":"blocked","reason":"connection_unavailable"}', flush=True)
                time.sleep(30)


if __name__ == '__main__':
    main()
