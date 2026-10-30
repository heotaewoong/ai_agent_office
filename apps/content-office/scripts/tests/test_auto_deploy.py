"""자동 배포 감시기: 판단 순서와 결과 기록. git·GitHub·배포 스크립트는 가짜다."""
import importlib.util
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'auto_deploy.py'
spec = importlib.util.spec_from_file_location('auto_deploy', SCRIPT)
auto = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auto)

OLD, NEW = 'a' * 40, 'b' * 40


class Opener:
    def __init__(self, runs):
        self.runs, self.calls = runs, 0

    def open(self, url, timeout=None):
        self.calls += 1
        return io.BytesIO(json.dumps({'check_runs': self.runs}).encode())


def run(conclusion='success', status='completed', sha=NEW):
    return {'name': 'verify', 'head_sha': sha, 'status': status, 'conclusion': conclusion, 'html_url': 'https://github.com/o/r/runs/9', 'started_at': '2026-10-30T05:00:00Z'}


class DecideTests(unittest.TestCase):
    base = dict(enabled=True, origin=NEW, deployed=OLD, attempted={}, ci={'state': 'success'}, deps_changed=[])

    def test_order_of_reasons(self):
        self.assertEqual(auto.decide(**{**self.base, 'enabled': False})[0], 'disabled')
        self.assertEqual(auto.decide(**{**self.base, 'deployed': NEW})[0], 'up_to_date')
        self.assertEqual(auto.decide(**{**self.base, 'attempted': {NEW: 'rolled_back'}})[0], 'skip_failed')
        self.assertEqual(auto.decide(**{**self.base, 'ci': {'state': 'failure'}})[0], 'ci_failed')
        self.assertEqual(auto.decide(**{**self.base, 'ci': {'state': 'pending', 'detail': '진행 중'}}), ('waiting_ci', '진행 중'))
        self.assertEqual(auto.decide(**{**self.base, 'ci': {'state': 'unknown'}})[0], 'waiting_ci')
        self.assertEqual(auto.decide(**{**self.base, 'deps_changed': ['apps/content-office/frontend/package-lock.json']})[0], 'needs_dependencies')
        self.assertEqual(auto.decide(**self.base)[0], 'deploy')

    def test_ci_state_reads_exact_commit_runs(self):
        self.assertEqual(auto.ci_state('o/r', NEW, Opener([run()]))['state'], 'success')
        self.assertEqual(auto.ci_state('o/r', NEW, Opener([run(status='in_progress', conclusion=None)]))['state'], 'pending')
        self.assertEqual(auto.ci_state('o/r', NEW, Opener([run('failure')]))['state'], 'failure')
        self.assertEqual(auto.ci_state('o/r', NEW, Opener([]))['state'], 'pending')
        self.assertEqual(auto.ci_state('o/r', NEW, Opener([run(sha=OLD)]))['state'], 'pending')

    def test_classify_results(self):
        self.assertEqual(auto.classify('deployed', '')[0], 'deployed')
        self.assertEqual(auto.classify('checks_failed', '')[0], 'failed')
        self.assertEqual(auto.classify('rolled_back', '')[0], 'failed')
        self.assertEqual(auto.classify('manual_recovery_required', '')[0], 'emergency_stop')
        self.assertEqual(auto.classify(None, 'The work window is open')[0], 'deferred')


class WatcherTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.state = Path(self.folder.name) / 'state'
        (self.state / 'runtime' / 'deployments').mkdir(parents=True)
        (self.state / 'runtime' / 'build-info.json').write_text(json.dumps({'commit': OLD}))
        self.deploy_result, self.commands, self.diff = 'deployed', [], ''

    def runner(self, command, cwd, env=None):
        self.commands.append([str(c) for c in command])
        if command[0] == 'git':
            return 0, {'fetch': '', 'rev-parse': NEW + '\n', 'diff': self.diff}[command[1]]
        release = self.state / 'runtime' / 'deployments' / ('run%d' % len(self.commands))
        release.mkdir()
        if self.deploy_result:
            (release / 'deployment.json').write_text(json.dumps({'status': self.deploy_result}))
        if self.deploy_result == 'deployed':
            (self.state / 'runtime' / 'build-info.json').write_text(json.dumps({'commit': NEW}))
        return (0 if self.deploy_result == 'deployed' else 1), 'output'

    def watcher(self, runs=None):
        self.opener = Opener([run()] if runs is None else runs)
        return auto.Watcher(Path(self.folder.name), self.state, slug='o/r', opener=self.opener, runner=self.runner)

    def switch(self, enabled):
        (self.state / 'runtime' / 'auto-deploy-switch.json').write_text(json.dumps({'enabled': enabled}))

    def deploy_calls(self):
        return [c for c in self.commands if c[0] == 'nice']

    def test_switch_off_by_default_never_deploys(self):
        record = self.watcher().run_once()
        self.assertEqual(record['decision'], 'disabled')
        self.assertEqual(self.deploy_calls(), [])

    def test_verified_commit_is_deployed_with_ci_flag_and_low_priority(self):
        self.switch(True)
        record = self.watcher().run_once()
        self.assertEqual(record['decision'], 'deployed')
        self.assertEqual(record['deployed'], NEW)
        call = self.deploy_calls()[0]
        self.assertEqual(call[:3], ['nice', '-n', '10'])
        self.assertEqual(call[-3:], [NEW, '--ci-verified-repo', 'o/r'])
        self.assertEqual(record['attempted'][NEW], 'deployed')
        second = self.watcher().run_once()
        self.assertEqual(second['decision'], 'up_to_date')
        self.assertEqual(len(self.deploy_calls()), 1)

    def test_failed_commit_is_not_retried(self):
        self.switch(True)
        self.deploy_result = 'checks_failed'
        self.assertEqual(self.watcher().run_once()['decision'], 'failed')
        self.assertEqual(self.watcher().run_once()['decision'], 'skip_failed')
        self.assertEqual(len(self.deploy_calls()), 1)

    def test_pending_or_failed_ci_never_reaches_the_server(self):
        self.switch(True)
        self.assertEqual(self.watcher([run(status='queued', conclusion=None)]).run_once()['decision'], 'waiting_ci')
        self.assertEqual(self.watcher([run('failure')]).run_once()['decision'], 'ci_failed')
        self.assertEqual(self.deploy_calls(), [])
        # 검증을 다시 돌려 통과하면 같은 커밋도 배포된다.
        self.assertEqual(self.watcher().run_once()['decision'], 'deployed')

    def test_dependency_change_waits_for_a_person(self):
        self.switch(True)
        self.diff = 'apps/content-office/backend/requirements-lock.txt\n'
        record = self.watcher().run_once()
        self.assertEqual(record['decision'], 'needs_dependencies')
        self.assertIn('requirements-lock.txt', record['reason'])
        self.assertEqual(self.deploy_calls(), [])

    def test_refused_before_release_is_deferred_and_retried(self):
        self.switch(True)
        self.deploy_result = None
        self.assertEqual(self.watcher().run_once()['decision'], 'deferred')
        self.deploy_result = 'deployed'
        self.assertEqual(self.watcher().run_once()['decision'], 'deployed')

    def test_manual_recovery_turns_the_switch_off(self):
        self.switch(True)
        self.deploy_result = 'manual_recovery_required'
        record = self.watcher().run_once()
        self.assertEqual(record['decision'], 'emergency_stop')
        switch = json.loads((self.state / 'runtime' / 'auto-deploy-switch.json').read_text(encoding='utf-8'))
        self.assertFalse(switch['enabled'])
        self.assertEqual(switch['actor'], 'auto-deploy')

    def test_history_records_changes_only(self):
        for _ in range(3):
            record = self.watcher().run_once()
        self.assertEqual(len(record['history']), 1)


if __name__ == '__main__':
    unittest.main()
