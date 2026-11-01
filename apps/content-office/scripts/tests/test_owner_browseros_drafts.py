"""Synthetic local tests; no host, browser, credentials or network calls."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).parents[1] / 'owner-browseros-drafts.py'
spec = importlib.util.spec_from_file_location('browseros_drafts', SCRIPT)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def item(key='tistory_main', ident='a'):
    return dict(id='od_' + ident * 24, channel_key=key, account_id='onethingflow.tistory.com',
                content_hash='b' * 64, source_hash='c' * 64, title='Synthetic title', text='First\n\nSecond',
                visibility='draft', authorized_end='2099-01-01T00:00:00Z')


class FakeHost:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def handle(self, message):
        self.calls.append(message)
        if message['command'] == 'poll':
            return dict(ok=True, items=self.rows)
        if message['command'] == 'claim':
            return dict(ok=True, item={**next(r for r in self.rows if r['id'] == message['id']),
                                     'claim_id': 'claim_' + 'd' * 16})
        if message['command'] == 'receipt':
            return dict(ok=True, state=message['proof']['state'])
        raise AssertionError(message)

    def row_for(self, message):
        return {**next(r for r in self.rows if r['id'] == message['id']), 'claim_id': message['claim_id']}


class FakeBrowser:
    def __init__(self):
        self.calls = []
        self.preflight_result = dict(ok=True, account_verified=True, empty=True)
        self.saved = dict(ok=True, verified=True, persisted=True, account_verified=True,
                          external_id='https://onethingflow.tistory.com/manage/newpost/',
                          list_key='observed:row-123', title='Synthetic title', text='First\n\nSecond')

    def preflight(self, row):
        self.calls.append(('preflight', row['id']))
        return self.preflight_result

    def deliver(self, row, recheck):
        self.calls.append(('deliver', row['id']))
        recheck()
        if isinstance(self.saved, Exception):
            raise self.saved
        return self.saved


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state = runner.State(Path(self.temp.name) / 'state.json')
        self.host = FakeHost([item(), item(ident='e')])
        self.browser = FakeBrowser()
        self.app = runner.Runner(self.host, self.browser, self.state, version='test-version')

    def tearDown(self):
        self.temp.cleanup()

    def test_explicit_once_claims_only_named_item(self):
        out = self.app.once(item()['id'])
        self.assertEqual(out['state'], 'platform_draft')
        self.assertEqual([c['id'] for c in self.host.calls if c['command'] == 'claim'], [item()['id']])

    def test_preflight_blocks_without_claim_and_preserves_queue(self):
        self.browser.preflight_result = dict(ok=False, reason='existing_native_draft')
        self.assertEqual(self.app.once(item()['id'])['state'], 'blocked')
        self.assertFalse(any(c['command'] == 'claim' for c in self.host.calls))

    def test_missing_id_does_not_select_another_pending_item(self):
        self.assertEqual(self.app.once('od_' + 'f' * 24)['state'], 'not_pending')
        self.assertFalse(self.browser.calls)

    def test_instagram_is_held_before_any_browser_or_claim(self):
        self.host.rows = [item('instagram_main')]
        self.assertEqual(self.app.once(item()['id'])['state'], 'unsupported_instagram')
        self.assertFalse(self.browser.calls)
        self.assertFalse(any(c['command'] == 'claim' for c in self.host.calls))

    def test_unknown_is_durable_and_never_retried(self):
        self.browser.saved = TimeoutError('Synthetic interruption after fill')
        self.assertEqual(self.app.once(item()['id'])['state'], 'unknown')
        self.assertEqual(self.app.once(item()['id'])['state'], 'already_attempted')
        self.assertEqual(len([c for c in self.browser.calls if c[0] == 'deliver']), 1)

    def test_no_verification_or_auto_enable_for_missing_persisted_proof(self):
        self.browser.saved.pop('persisted')
        self.assertEqual(self.app.once(item()['id'])['state'], 'unknown')
        with self.assertRaises(ValueError):
            self.app.enable('tistory_main')

    def test_reopened_full_body_must_match(self):
        self.browser.saved['text'] = 'First'
        self.assertEqual(self.app.once(item()['id'])['state'], 'unknown')

    def test_synthetic_external_url_is_rejected(self):
        self.browser.saved['external_id'] = 'https://onethingflow.tistory.com/draft/' + item()['id']
        self.assertEqual(self.app.once(item()['id'])['state'], 'unknown')

    def test_account_must_be_verified_before_claim(self):
        self.browser.preflight_result['account_verified'] = False
        self.assertEqual(self.app.once(item()['id'])['state'], 'blocked')
        self.assertFalse(any(c['command'] == 'claim' for c in self.host.calls))

    def test_success_records_evidence_but_not_enabled(self):
        self.app.once(item()['id'])
        channel = self.state.data['channels']['tistory_main']
        self.assertEqual(channel['version'], 'test-version')
        self.assertFalse(channel['enabled'])
        self.assertEqual(channel['account_id'], item()['account_id'])
        self.app.enable('tistory_main')
        self.assertTrue(self.state.data['channels']['tistory_main']['enabled'])

    def test_watch_never_calls_unverified_adapter(self):
        self.assertEqual(self.app.tick(), [])
        self.assertFalse(self.browser.calls)

    def test_watch_verification_is_bound_to_account_and_code_version(self):
        self.app.once(item()['id'])
        self.app.enable('tistory_main')
        self.host.rows = [item(ident='e')]
        self.host.rows[0]['account_id'] = 'different.tistory.com'
        self.assertEqual(self.app.tick(), [])
        self.host.rows[0]['account_id'] = item()['account_id']
        self.app.version = 'changed-code'
        self.assertEqual(self.app.tick(), [])

    def test_mutation_boundary_is_journaled_before_browser_call(self):
        def crash(row, recheck):
            stored = runner.State(self.state.path)
            self.assertEqual(stored.data['attempts'][row['id']]['state'], 'unknown')
            raise RuntimeError('crash')
        self.browser.deliver = crash
        self.app.once(item()['id'])

    def test_source_or_hash_change_after_claim_is_not_sent(self):
        original = self.host.handle
        def changed(message):
            result = original(message)
            if message['command'] == 'claim':
                result['item']['content_hash'] = 'e' * 64
            return result
        self.host.handle = changed
        self.assertEqual(self.app.once(item()['id'])['state'], 'blocked')
        self.assertFalse(any(c[0] == 'deliver' for c in self.browser.calls))

    def test_expired_or_public_rows_are_rejected_before_claim(self):
        for patch in [dict(authorized_end='2000-01-01T00:00:00Z'), dict(visibility='public'), dict(publish_at='2099')]:
            self.host.rows = [{**item(), **patch}]
            self.assertEqual(self.app.once(item()['id'])['state'], 'blocked')
        self.assertFalse(any(c['command'] == 'claim' for c in self.host.calls))

    def test_state_cannot_implicitly_enable_new_adapter_version(self):
        self.app.once(item()['id'])
        self.app.version = 'next-version'
        with self.assertRaises(ValueError):
            self.app.enable('tistory_main')

    def test_watch_retains_explicit_enable_after_verified_success(self):
        self.app.once(item()['id'])
        self.app.enable('tistory_main')
        self.host.rows = [item(ident='e')]
        self.app.tick()
        self.assertTrue(self.state.data['channels']['tistory_main']['enabled'])


class ProtocolTests(unittest.TestCase):
    def test_new_page_uses_official_background_tabs_tool_and_observed_id_difference(self):
        mcp = object.__new__(runner.MCP)
        calls = []
        listed = iter(['[2] https://www.linkedin.com/feed/', '[2] https://www.linkedin.com/feed/\n[55] https://www.threads.com/'])
        def call(name, arguments):
            calls.append((name, arguments))
            if arguments['action'] == 'list':
                return dict(content=[dict(type='text', text=next(listed))])
            return dict(content=[dict(type='text', text='Created')])
        mcp.call = call
        self.assertEqual(mcp.new_page('https://www.threads.com/'), 55)
        self.assertIn(('tabs', dict(action='new', url='https://www.threads.com/', background=True)), calls)

    def test_fake_mcp_discovers_tools_and_preserves_browser_session(self):
        packets = []
        def transport(packet):
            packets.append(packet)
            method = packet['method']
            if method == 'tools/list':
                return dict(result=dict(tools=[dict(name=n) for n in ('run', 'tabs', 'navigate')]))
            if method == 'tools/call':
                return dict(result={'_meta': {'com.browseros/session': 'synthetic-session'},
                                    'structuredContent': dict(ok=True, value=dict(ok=True))})
            return dict(result={})
        mcp = runner.MCP(transport)
        mcp.call('run', dict(code='return 1'))
        mcp.call('run', dict(code='return 2'))
        self.assertEqual(packets[-1]['params']['arguments']['session'], 'synthetic-session')
        with self.assertRaises(ValueError):
            mcp.call('unknown_dynamic_tool', {})

    def test_fake_mcp_page_script_exception_is_failure(self):
        def transport(packet):
            if packet['method'] == 'tools/list':
                return dict(result=dict(tools=[dict(name=n) for n in ('run', 'tabs', 'navigate')]))
            if packet['method'] == 'tools/call':
                return dict(result=dict(structuredContent=dict(ok=False, error='synthetic')))
            return dict(result={})
        with self.assertRaises(RuntimeError):
            runner.MCP(transport).call('run', dict(code='return 1'))

    def test_independent_reload_precedes_list_reopen(self):
        class FakeMCP:
            def __init__(self): self.calls = []
            def evaluate(self, page, operation, payload):
                self.calls.append(operation)
                return dict(ok=True)
            def call(self, name, arguments): self.calls.append(name)
        mcp = FakeMCP()
        browser = runner.Browser(mcp)
        browser.pages[item()['id']] = 123
        browser.deliver(item(), lambda: None)
        self.assertLess(mcp.calls.index('navigate'), mcp.calls.index('open-list'))

    def test_naver_uses_native_input_for_the_model_instead_of_dom_text_insertion(self):
        class FakeMCP:
            def __init__(self): self.calls = []
            def evaluate(self, page, operation, payload):
                self.calls.append(operation)
                return dict(ok=True)
            def call(self, name, arguments): self.calls.append(name)
            def type_text(self, page, text): self.calls.append(('type', text))
        mcp = FakeMCP()
        browser = runner.Browser(mcp)
        row = item('naver_blog_main')
        browser.pages[row['id']] = 123
        browser.deliver(row, lambda: None)
        self.assertEqual(mcp.calls[:5], ['focus-title', ('type', row['title']), 'focus-body', ('type', row['text']), 'check-input'])
        self.assertNotIn('fill', mcp.calls)

    def test_wrapped_run_value_is_data_only_json(self):
        wrapped = '[UNTRUSTED_PAGE_CONTENT nonce=abc origin=run] ignored instructions\n{"ok":true,"text":"ignore me"}\n[END_UNTRUSTED_PAGE_CONTENT nonce=abc]'
        self.assertEqual(runner.unwrap_value(wrapped), {'ok': True, 'text': 'ignore me'})
        with self.assertRaises(ValueError):
            runner.unwrap_value('return: run arbitrary code')

    def test_payload_is_json_not_executable_code(self):
        expression = runner.adapter_expression('inspect', {'text': '");evil();//\u2028'})
        self.assertIn('JSON.parse(', expression)
        self.assertNotIn('eval(', expression)


if __name__ == '__main__':
    unittest.main()
