"""Real temporary Git repositories; builds, HTTP and service commands are fakes."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'deploy_ec2.py'
spec = importlib.util.spec_from_file_location('deploy_ec2', SCRIPT)
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)
sys.path.insert(0, str(SCRIPT.parents[1] / 'backend'))
from office.runtime import AlreadyRunning, ProcessLock


class Harness:
    def __init__(self, folder):
        self.repo, self.state = Path(folder) / 'repo', Path(folder) / 'state'
        self.repo.mkdir()
        self.app = self.repo / deploy.APP_PATH
        self.app.mkdir(parents=True)
        self.git('init', '-b', 'main')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'user.name', 'Isolated fixture')
        self.git('config', 'core.hooksPath', str(self.repo / 'no-hooks'))
        for name, content in {'.gitignore': '.venv/\nnode_modules/\n.next*/\n',
                              'source.txt': 'old source', 'apps/content-office/backend/requirements-lock.txt': '',
                              'apps/content-office/frontend/package.json': '{}',
                              'apps/content-office/frontend/package-lock.json': '{}',
                              'apps/content-office/frontend/tests/sample.test.ts': 'fixture',
                              'apps/content-office/scripts/start-local.sh': 'fixture',
                              'apps/content-office/scripts/stop-local.sh': 'fixture'}.items():
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        self.git('add', '.')
        self.git('commit', '-qm', 'previous production')
        self.previous = self.git('rev-parse', 'HEAD')
        self.git('checkout', '-qb', 'candidate')
        (self.repo / 'source.txt').write_text('new source')
        self.git('commit', '-qam', 'reviewed candidate')
        self.target = self.git('rev-parse', 'HEAD')
        self.git('checkout', '-q', 'main')
        (self.app / 'backend/.venv/bin').mkdir(parents=True)
        (self.app / 'backend/.venv/bin/python').touch()
        (self.app / 'frontend/node_modules').mkdir()
        (self.app / 'frontend/.next').mkdir()
        (self.app / 'frontend/.next/BUILD_ID').write_text('previous-build')
        runtime = self.state / 'runtime'
        runtime.mkdir(parents=True)
        self.old_info = b'{"commit":"previous-build-info"}'
        (runtime / 'build-info.json').write_bytes(self.old_info)
        with closing(sqlite3.connect(self.state / 'office.sqlite3')) as db, db:
            db.executescript('CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT); CREATE TABLE costs(id TEXT,state TEXT); CREATE TABLE approvals(id TEXT,decision TEXT);')
            db.execute('INSERT INTO settings VALUES(?,?)', ('work_window', json.dumps({'authorized_end': (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()})))
            db.execute('INSERT INTO costs VALUES(?,?)', ('untouched', 'unknown'))
            db.execute('INSERT INTO approvals VALUES(?,?)', ('untouched', 'approved'))
        self.running = {11, 12}
        self.registry = {'scope': 'heobrain-content-office', 'app_dir': str(self.app.resolve()),
                         'services': {'api': {'pid': 11, 'start_ticks': 101}, 'frontend': {'pid': 12, 'start_ticks': 102}}}
        (runtime / 'services.json').write_text(json.dumps(self.registry))
        self.calls, self.start_count, self.health_count = [], 0, 0
        self.fail_build = self.fail_start = self.fail_health = self.dirty_build = self.dirty_start = False
        self.started, self.finish = None, None

    def git(self, *args):
        return deploy.run(['git', '-c', 'core.fsmonitor=false', '-c', 'gc.auto=0', '-c', 'commit.gpgsign=false', *args], cwd=self.repo).strip()

    def identity(self, pid):
        return {'start_ticks': 90 + pid} if pid in self.running else None

    def runner(self, command, *, cwd, env=None):
        if str(command[0]) == 'git':
            return deploy.run(command, cwd=cwd, env=env)
        if str(command[0]) == 'bash':
            action = 'stop' if str(command[1]).endswith('stop-local.sh') else 'start'
            self.calls.append(action)
            self.running.clear()
            if action == 'start':
                self.start_count += 1
                if self.start_count == 1 and self.dirty_start:
                    (self.repo / 'source.txt').write_text('operator change during restart')
                    raise deploy.DeployError('fake start failed with a concurrent edit')
                if self.start_count == 1 and self.fail_start:
                    raise deploy.DeployError('fake start failed')
                self.running.update((11, 12))
            return ''
        # Every test/build runs against the detached worktree, before live source/build changes.
        assert self.git('rev-parse', 'HEAD') == self.previous
        assert (self.app / 'frontend/.next/BUILD_ID').read_text() == 'previous-build'
        assert self.state != Path(env['OFFICE_STATE_DIR'])
        assert not any(name in env for name in ('OPENAI_API_KEY', 'OFFICE_REAL_MEDIA_E2E', 'OFFICE_ENV_FILE', 'AWS_ACCESS_KEY_ID'))
        assert Path(env['HOME']).is_relative_to(Path(env['TMPDIR']))
        if 'build' in command:
            if self.started:
                self.started.set()
                assert self.finish.wait(10)
            if self.fail_build:
                raise deploy.DeployError('fake build failure')
            build = Path(cwd) / '.next'
            build.mkdir()
            (build / 'BUILD_ID').write_text(self.target)
            if self.dirty_build:
                (self.repo / 'source.txt').write_text('operator change during build')
        return '5 passed in 0.01s\n' if '-m' in command else '# pass 6\n# fail 0\n'

    def health(self):
        self.health_count += 1
        if self.health_count == 1 and self.fail_health:
            raise deploy.DeployError('fake health failure')

    def deployment(self, target=None):
        value = deploy.Deployment(self.repo, self.state, target or self.target, runner=self.runner,
                                  lock_type=ProcessLock, identity=self.identity)
        value.env = {'PATH': os.environ['PATH'], 'OPENAI_API_KEY': 'fixture-secret',
                     'OFFICE_REAL_MEDIA_E2E': '1', 'OFFICE_ENV_FILE': 'never-read'}
        value.health = self.health
        return value

    def unchanged(self):
        assert self.git('rev-parse', 'HEAD') == self.previous
        assert (self.app / 'frontend/.next/BUILD_ID').read_text() == 'previous-build'
        assert (self.state / 'runtime/build-info.json').read_bytes() == self.old_info
        assert self.running == {11, 12}


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory(prefix='office-deploy-fixture-')
        self.addCleanup(self.folder.cleanup)
        self.h = Harness(self.folder.name)
        # Production is Linux. Fake dependency links avoid requiring Windows symlink privileges.
        if os.name == 'nt':
            self.links = []
            def fake_link(path, target, **kwargs):
                self.links.append((path, target))
                path.mkdir()
            self.link_patch = patch.object(Path, 'symlink_to', fake_link)
            self.link_patch.start()
            self.addCleanup(self.link_patch.stop)

    def test_saved_environment_path_is_reused_when_caller_omits_it(self):
        env_file = self.h.state / 'runtime.env'
        env_file.write_text('OPENAI_API_KEY=synthetic-fixture-only\n')
        self.h.registry['env_file'] = str(env_file)
        (self.h.state / 'runtime/services.json').write_text(json.dumps(self.h.registry))
        with patch.dict(os.environ):
            os.environ.pop('OFFICE_ENV_FILE', None)
            operation = deploy.Deployment(self.h.repo, self.h.state, self.h.target,
                runner=self.h.runner, lock_type=ProcessLock, identity=self.h.identity)
        self.assertEqual(operation.env['OFFICE_ENV_FILE'], str(env_file.resolve()))
        self.assertNotIn('synthetic-fixture-only', str(operation.env))
        env_file.unlink()
        with patch.dict(os.environ):
            os.environ.pop('OFFICE_ENV_FILE', None)
            with self.assertRaisesRegex(deploy.DeployError, 'environment file is missing'):
                deploy.Deployment(self.h.repo, self.h.state, self.h.target,
                    runner=self.h.runner, lock_type=ProcessLock, identity=self.h.identity)
        self.assertEqual(self.h.running, {11, 12})

    def test_exact_success_preserves_business_data_and_previous_build(self):
        value = self.h.deployment()
        before = value.business_state()
        release = value.execute()
        self.assertEqual(self.h.git('rev-parse', 'HEAD'), self.h.target)
        self.assertEqual(self.h.git('rev-parse', 'main'), self.h.target)
        self.assertEqual(value.business_state(), before)
        self.assertEqual(self.h.calls, ['stop', 'start'])
        self.assertEqual((self.h.app / 'frontend/.next/BUILD_ID').read_text(), self.h.target)
        backups = list((self.h.app / 'frontend').glob('.next.before-*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / 'BUILD_ID').read_text(), 'previous-build')
        self.assertEqual((release / 'build-info.before.json').read_bytes(), self.h.old_info)
        self.assertEqual(json.loads((release / 'deployment.json').read_text())['status'], 'deployed')
        self.assertTrue((release / 'deploy_ec2.py').is_file())
        info = json.loads((self.h.state / 'runtime/build-info.json').read_text())
        self.assertEqual(info['tests']['backend'], {'passed': 5, 'failed': 0, 'skipped': 0, 'errors': 0})
        self.assertEqual(info['tests']['frontend'], {'passed': 6, 'failed': 0})

    def test_ci_verified_deploy_runs_no_server_tests_but_still_builds(self):
        value = self.h.deployment()
        value.ci = {'source': 'github-actions', 'check': 'verify', 'url': 'https://github.com/o/r/runs/1'}
        seen, inner = [], value.runner
        def recording(command, *, cwd, env=None):
            seen.append([str(part) for part in command])
            return inner(command, cwd=cwd, env=env)
        value.runner = recording
        release = value.execute()
        tools = [cmd for cmd in seen if cmd[0] not in ('git', 'bash')]
        self.assertTrue(tools and all('build' in cmd for cmd in tools), tools)
        self.assertFalse(any('pytest' in cmd or '--test' in cmd or 'node_modules/typescript/bin/tsc' in cmd for cmd in seen))
        info = json.loads((self.h.state / 'runtime/build-info.json').read_text())
        self.assertEqual(info['tests'], {'ci': value.ci})
        self.assertTrue((release / 'tests.skipped').is_file())
        self.assertEqual(json.loads((release / 'deployment.json').read_text())['ci'], value.ci)

    def test_ci_verification_needs_a_passed_verify_run_for_the_exact_commit(self):
        sha = self.h.target
        class Opener:
            def __init__(self, payload): self.payload, self.urls = payload, []
            def open(self, url, timeout=None):
                self.urls.append(url)
                return io.BytesIO(json.dumps(self.payload).encode())
        run = {'name': 'verify', 'head_sha': sha, 'status': 'completed', 'conclusion': 'success',
               'html_url': 'https://github.com/o/r/runs/2', 'completed_at': '2026-10-30T05:00:00Z'}
        opener = Opener({'check_runs': [run]})
        result = deploy.ci_verification('o/r', sha, opener=opener)
        self.assertEqual(result['url'], run['html_url'])
        self.assertIn('/commits/' + sha + '/check-runs', opener.urls[0])
        for payload in ({'check_runs': []}, {'check_runs': [{**run, 'conclusion': 'failure'}]},
                        {'check_runs': [{**run, 'status': 'in_progress', 'conclusion': None}]},
                        {'check_runs': [{**run, 'head_sha': self.h.previous}]},
                        {'check_runs': [run, {**run, 'conclusion': 'failure'}]}):
            with self.assertRaisesRegex(deploy.DeployError, 'has not passed'):
                deploy.ci_verification('o/r', sha, opener=Opener(payload))
        with self.assertRaisesRegex(deploy.DeployError, 'owner/repo'):
            deploy.ci_verification('not a slug', sha, opener=opener)
        class Broken:
            def open(self, url, timeout=None): raise OSError('offline')
        with self.assertRaisesRegex(deploy.DeployError, 'not skipped'):
            deploy.ci_verification('o/r', sha, opener=Broken())

    def test_dirty_source_blocks_before_checks_or_service_changes(self):
        (self.h.repo / 'source.txt').write_text('operator edit')
        with self.assertRaisesRegex(deploy.DeployError, 'Tracked changes'):
            self.h.deployment().execute()
        self.h.unchanged()
        self.assertEqual(self.h.calls, [])
        self.assertEqual((self.h.repo / 'source.txt').read_text(), 'operator edit')

    def test_short_or_branch_target_is_never_resolved_to_latest(self):
        for target in ('main', self.h.target[:8]):
            with self.assertRaisesRegex(deploy.DeployError, '40-character'):
                self.h.deployment(target).execute()
        self.h.unchanged()

    def test_changed_dependency_lock_blocks_without_installing(self):
        self.h.git('checkout', '-q', 'candidate')
        (self.h.app / 'frontend/package-lock.json').write_text('{"changed":true}')
        self.h.git('commit', '-qam', 'dependency change')
        target = self.h.git('rev-parse', 'HEAD')
        self.h.git('checkout', '-q', 'main')
        with self.assertRaisesRegex(deploy.DeployError, 'Dependency'):
            self.h.deployment(target).execute()
        self.h.unchanged()
        self.assertEqual(self.h.calls, [])

    def test_divergent_head_is_not_reset_or_merged(self):
        self.h.git('checkout', '-qb', 'local-only')
        (self.h.repo / 'local.txt').write_text('preserve local commit')
        self.h.git('add', 'local.txt')
        self.h.git('commit', '-qm', 'local-only commit')
        original = self.h.git('rev-parse', 'HEAD')
        with self.assertRaises(deploy.DeployError):
            self.h.deployment().execute()
        self.assertEqual(self.h.git('rev-parse', 'HEAD'), original)
        self.assertEqual(self.h.calls, [])

    def test_open_or_missing_work_window_blocks(self):
        for window in ({}, {'authorized_end': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}):
            with closing(sqlite3.connect(self.h.state / 'office.sqlite3')) as db, db:
                db.execute("UPDATE settings SET value=? WHERE key='work_window'", (json.dumps(window),))
            with self.assertRaisesRegex(deploy.DeployError, 'window'):
                self.h.deployment().execute()
        self.h.unchanged()

    def test_foreign_service_registry_never_signals_a_process(self):
        path = self.h.state / 'runtime/services.json'
        path.write_text(json.dumps({**self.h.registry, 'app_dir': str(self.h.repo / 'someone-else')}))
        with self.assertRaisesRegex(deploy.DeployError, 'another app'):
            self.h.deployment().execute()
        self.h.unchanged()
        self.assertEqual(self.h.calls, [])

    def test_state_and_app_paths_cannot_escape_their_declared_roots(self):
        with self.assertRaisesRegex(deploy.DeployError, 'outside the checkout'):
            deploy.Deployment(self.h.repo, self.h.repo / 'state', self.h.target, lock_type=ProcessLock, identity=self.h.identity)

    def test_protected_state_symlinks_never_read_or_change_external_files(self):
        for relative in ('runtime/build-info.json', 'runtime/services.json', 'runtime/services-management.lock'):
            with self.subTest(path=relative):
                path = self.h.state / relative
                original = path.read_bytes() if path.exists() else None
                external = Path(self.folder.name) / ('external-' + path.name)
                sentinel = original if original is not None else b'external-lock-sentinel'
                external.write_bytes(sentinel)
                existing = self.h.deployment()
                if path.exists():
                    path.unlink()
                os.symlink(external, path)
                try:
                    with self.assertRaisesRegex(deploy.DeployError, 'Protected state path'):
                        self.h.deployment()
                    with self.assertRaisesRegex(deploy.DeployError, 'Protected state path'):
                        existing.owner()
                    with self.assertRaisesRegex(deploy.DeployError, 'Protected state path'):
                        existing.service('stop')
                    self.assertEqual(external.read_bytes(), sentinel)
                    self.assertEqual(self.h.calls, [])
                finally:
                    path.unlink()
                    if original is not None:
                        path.write_bytes(original)
        self.h.unchanged()

    def test_cli_lock_contention_exits_cleanly_without_hiding_programming_errors(self):
        args = ['deploy_ec2.py', self.h.target, '--repo', str(self.h.repo)]
        with patch.object(sys, 'argv', args), patch.dict(os.environ, {'OFFICE_STATE_DIR': str(self.h.state)}):
            with ProcessLock(self.h.state / 'runtime/deploy.lock'), patch('sys.stderr', new_callable=io.StringIO) as error:
                with self.assertRaises(SystemExit) as stopped:
                    deploy.main()
                self.assertEqual(stopped.exception.code, 1)
                self.assertIn('already running: deploy.lock', error.getvalue())
                self.assertNotIn('Traceback', error.getvalue())
            with patch.object(deploy.Deployment, 'execute', side_effect=RuntimeError('programming error')):
                with self.assertRaisesRegex(RuntimeError, 'programming error'):
                    deploy.main()
        self.h.unchanged()
        self.assertEqual(self.h.calls, [])

    def test_build_failure_keeps_running_production_unchanged(self):
        self.h.fail_build = True
        value = self.h.deployment()
        with self.assertRaisesRegex(deploy.DeployError, 'build failure'):
            value.execute()
        self.h.unchanged()
        self.assertEqual(self.h.calls, [])
        self.assertEqual(json.loads((value.release / 'deployment.json').read_text())['status'], 'checks_failed')

    def test_restart_failure_restores_old_detached_head_without_rewriting_main(self):
        self.h.fail_start = True
        value = self.h.deployment()
        with self.assertRaisesRegex(deploy.DeployError, 'start failed'):
            value.execute()
        self.h.unchanged()
        self.assertEqual(self.h.git('rev-parse', 'main'), self.h.target)
        self.assertEqual(self.h.git('branch', '--show-current'), '')
        self.assertEqual(json.loads((value.release / 'deployment.json').read_text())['status'], 'rolled_back')
        self.assertEqual(self.h.calls, ['stop', 'start', 'stop', 'start'])

    def test_health_failure_restores_old_build_and_services(self):
        self.h.fail_health = True
        with self.assertRaisesRegex(deploy.DeployError, 'health failure'):
            self.h.deployment().execute()
        self.h.unchanged()

    def test_operator_edit_during_checks_is_preserved_before_cutover(self):
        self.h.dirty_build = True
        with self.assertRaisesRegex(deploy.DeployError, 'Tracked changes'):
            self.h.deployment().execute()
        self.h.unchanged()
        self.assertEqual(self.h.calls, [])
        self.assertEqual((self.h.repo / 'source.txt').read_text(), 'operator change during build')

    def test_operator_edit_during_failed_restart_requires_manual_recovery(self):
        self.h.dirty_start = True
        value = self.h.deployment()
        with self.assertRaisesRegex(deploy.DeployError, 'Recovery stopped'):
            value.execute()
        self.assertEqual((self.h.repo / 'source.txt').read_text(), 'operator change during restart')
        self.assertEqual(self.h.git('rev-parse', 'HEAD'), self.h.target)
        self.assertEqual(json.loads((value.release / 'deployment.json').read_text())['status'], 'manual_recovery_required')
        self.assertEqual(len(list((self.h.app / 'frontend').glob('.next.before-*'))), 1)

    def test_concurrent_deployment_is_rejected_by_the_os_lock(self):
        self.h.started, self.h.finish = Event(), Event()
        first = self.h.deployment()
        other_state = self.h.state.with_name('other-state')
        shutil.copytree(self.h.state, other_state)
        duplicate = deploy.Deployment(self.h.repo, other_state, self.h.target, runner=self.h.runner,
                                      lock_type=ProcessLock, identity=self.h.identity)
        duplicate.env = first.env.copy()
        with ThreadPoolExecutor(max_workers=1) as pool:
            active = pool.submit(first.execute)
            try:
                self.assertTrue(self.h.started.wait(10))
                with self.assertRaises(AlreadyRunning):
                    duplicate.execute()
            finally:
                self.h.finish.set()
            active.result(timeout=15)
        self.assertEqual(self.h.calls, ['stop', 'start'])

    def test_active_worker_lock_is_not_taken_over(self):
        with ProcessLock(self.h.state / 'worker.lock'):
            with self.assertRaises(AlreadyRunning):
                self.h.deployment().execute()
        self.h.unchanged()
        self.assertEqual(self.h.calls, [])


if __name__ == '__main__':
    unittest.main()
