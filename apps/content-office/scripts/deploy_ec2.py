#!/usr/bin/env python3
"""Check an exact commit in isolation, then deploy without resetting a branch."""
from __future__ import annotations

import argparse
from contextlib import ExitStack, closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.request import ProxyHandler, build_opener
from uuid import uuid4

APP_PATH = Path('apps/content-office')
DEPENDENCIES = ('backend/requirements.txt', 'backend/requirements-lock.txt', 'backend/pyproject.toml',
                'backend/poetry.lock', 'backend/uv.lock', 'frontend/package.json', 'frontend/package-lock.json',
                'frontend/npm-shrinkwrap.json', 'frontend/pnpm-lock.yaml', 'frontend/yarn.lock')
PREPARED_MANIFESTS = ('requirements.txt', 'requirements-lock.txt')


class DeployError(RuntimeError):
    def __init__(self, message, output=''):
        super().__init__(message)
        self.output = output


CI_CHECK = 'verify'
SLUG = re.compile(r'^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')


def ci_verification(slug, sha, *, opener=None):
    """Ask GitHub directly whether this exact commit passed the off-server `verify` check.

    Server-side tests are skipped only when this returns; a flag alone never skips them.
    """
    if not SLUG.match(slug or '') or not re.fullmatch(r'[0-9a-f]{40}', sha or ''):
        raise DeployError('CI verification needs owner/repo and a full 40-character SHA.')
    opener = opener or build_opener()
    url = 'https://api.github.com/repos/' + slug + '/commits/' + sha + '/check-runs?check_name=' + CI_CHECK + '&per_page=20'
    try:
        with opener.open(url, timeout=15) as response:
            payload = json.load(response)
    except (OSError, ValueError) as error:
        raise DeployError('Could not read the GitHub verification result; server tests were not skipped.') from error
    runs = [run for run in payload.get('check_runs', []) if run.get('name') == CI_CHECK and run.get('head_sha') == sha]
    passed = [run for run in runs if run.get('status') == 'completed' and run.get('conclusion') == 'success']
    failed = [run for run in runs if run.get('status') == 'completed' and run.get('conclusion') != 'success']
    if not passed or failed:
        state = ', '.join(sorted({str(run.get('conclusion') or run.get('status')) for run in runs})) or 'missing'
        raise DeployError('GitHub verification has not passed for this commit (' + state + '); nothing was deployed.')
    best = max(passed, key=lambda run: run.get('completed_at') or '')
    return {'source': 'github-actions', 'check': CI_CHECK, 'repo': slug, 'url': best.get('html_url'), 'completed_at': best.get('completed_at')}


def run(command, *, cwd, env=None):
    try:
        result = subprocess.run([str(part) for part in command], cwd=cwd, env=env, capture_output=True,
                                text=True, encoding='utf-8', errors='replace', timeout=1800)
    except subprocess.TimeoutExpired:
        raise DeployError('Command timed out: ' + str(command[0])) from None
    if result.returncode:
        raise DeployError('Command failed: ' + str(command[0]) + ' (exit ' + str(result.returncode) + ')', result.stdout + result.stderr)
    return result.stdout


def isolated_env(parent, folder):
    allowed = {'PATH', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'LANG', 'TZ', 'CONTENT_OFFICE_FONT'}
    env = {key: value for key, value in parent.items() if key.upper() in allowed or key.startswith('LC_')}
    home = folder / 'home'
    home.mkdir()
    env.update(HOME=str(home), USERPROFILE=str(home), CODEX_HOME=str(home / '.codex'),
               TMPDIR=str(folder), TMP=str(folder), TEMP=str(folder), OFFICE_STATE_DIR=str(folder / 'state'),
               NEXT_TELEMETRY_DISABLED='1', NODE_OPTIONS='--max-old-space-size=1200',
               OFFICE_API_URL='http://127.0.0.1:8510')
    return env


def validate_locked_packages(requirements, lock, packages, marker_environment):
    """Check exact installed pins, including platform markers, without installing anything."""
    from packaging.requirements import InvalidRequirement, Requirement
    from packaging.utils import canonicalize_name
    def parse(text):
        try:
            values = [Requirement(line.strip()) for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#')]
        except InvalidRequirement as error:
            raise DeployError('Prepared dependencies must use plain package requirements.') from error
        if any(value.url for value in values):
            raise DeployError('Prepared dependencies cannot use URLs or editable packages.')
        return [value for value in values if not value.marker or value.marker.evaluate(marker_environment)]
    locked = {}
    for value in parse(lock):
        name, pins = canonicalize_name(value.name), list(value.specifier)
        if name in locked or len(pins) != 1 or pins[0].operator != '==' or '*' in pins[0].version:
            raise DeployError('Prepared dependency lock must contain unique exact pins.')
        locked[name] = pins[0].version
    installed = {canonicalize_name(name): version for name, version in packages.items()}
    if any(installed.get(name) != version for name, version in locked.items()) or set(installed) - set(locked) - {'pip', 'setuptools', 'wheel'}:
        raise DeployError('Prepared installed packages do not match the exact dependency lock.')
    for value in parse(requirements):
        name = canonicalize_name(value.name)
        if name not in locked or not value.specifier.contains(installed[name], prereleases=True):
            raise DeployError('Prepared installed packages do not satisfy target requirements.')


class Deployment:
    def __init__(self, repo, state, target, *, runner=run, lock_type=None, identity=None, ci=None, prepared_backend_venv=None):
        self.repo, self.state, self.target = Path(repo).resolve(), Path(state).resolve(), target.lower()
        # ci: the result of ci_verification() for this exact target. When present, tests ran off-server.
        self.ci = ci
        self.prepared_backend_venv = Path(prepared_backend_venv) if prepared_backend_venv is not None else None
        self.prepared_backend_evidence = None
        self.app = self.repo / APP_PATH
        if self.state.is_relative_to(self.repo) or self.app.resolve() != self.app:
            raise DeployError('State must be outside the checkout and the app path must not escape it.')
        self.validate_state_paths()
        self.runner, self.env = runner, os.environ.copy()
        self.env['OFFICE_STATE_DIR'] = str(self.state)
        # A caller omitting the environment path must not silently drop the live API keys.
        env_file = self.env.get('OFFICE_ENV_FILE')
        registry = self.state / 'runtime/services.json'
        if not env_file and registry.is_file():
            env_file = json.loads(registry.read_text(encoding='utf-8')).get('env_file')
        if env_file:
            env_path = Path(env_file).expanduser().resolve()
            if not env_path.is_file():
                raise DeployError('The saved runtime environment file is missing; no service was stopped.')
            self.env['OFFICE_ENV_FILE'] = str(env_path)
        if lock_type is None or identity is None:
            sys.path.insert(0, str(self.app / 'backend'))
            from office.runtime import ProcessLock, process_identity
            lock_type, identity = lock_type or ProcessLock, identity or process_identity
        self.Lock, self.identity = lock_type, identity
        self.release = None

    def validate_state_paths(self):
        # Operational metadata and locks must be local regular paths, including
        # before restart/rollback; neither internal nor external symlinks are used.
        for relative in ('runtime', 'runtime/deployments', 'runtime/services.json', 'runtime/build-info.json',
                         'runtime/services-management.lock', 'runtime/deploy.lock', 'runtime/no-hooks',
                         'office.sqlite3', 'watcher.lock', 'worker.lock'):
            path = self.state / relative
            if path.is_symlink() or not path.resolve().is_relative_to(self.state):
                raise DeployError('Protected state path must stay inside the state root without symlinks: ' + relative)

    def git(self, *args, cwd=None, raw=False):
        env = {key: value for key, value in self.env.items() if not key.startswith('GIT_')}
        output = self.runner(['git', '-c', 'core.hooksPath=' + str(self.state / 'runtime/no-hooks'),
                             '-c', 'core.fsmonitor=false', '-c', 'gc.auto=0', *args], cwd=cwd or self.repo, env=env)
        return output if raw else output.strip()

    def validate_prepared_backend(self):
        path = self.prepared_backend_venv
        live = self.app / 'backend/.venv'
        if (not path.is_absolute() or path.resolve() != path or not path.is_dir()
                or any(part.is_symlink() for part in (path, *path.parents))
                or any(path.is_relative_to(root) or root.is_relative_to(path) for root in (self.repo, self.state, live.resolve()))):
            raise DeployError('Prepared venv path must be an absolute, separate directory without symlink ancestors.')
        manifest_path, config = path / 'heobrain-prepared.json', path / 'pyvenv.cfg'
        if any(item.is_symlink() or not item.is_file() for item in (manifest_path, config)) or not (path / 'bin/python').is_file():
            raise DeployError('Prepared venv must contain its regular preparation manifest and venv configuration.')
        if not re.search(r'^include-system-site-packages\s*=\s*false\s*$', config.read_text(), re.MULTILINE | re.IGNORECASE):
            raise DeployError('Prepared venv must exclude system site packages.')
        manifests = {name: self.git('show', self.target + ':' + (APP_PATH / 'backend' / name).as_posix(), raw=True) for name in PREPARED_MANIFESTS}
        hashes = {name: hashlib.sha256(text.encode()).hexdigest() for name, text in manifests.items()}
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if manifest.get('manifest_sha256') != hashes:
            raise DeployError('Prepared manifest hashes do not match target backend requirements and lock.')
        with tempfile.TemporaryDirectory(prefix='office-venv-check-') as isolated:
            env = isolated_env(self.env, Path(isolated))
            probe = ('import importlib.metadata as m,json,sys; from packaging.markers import default_environment; '
                     'from packaging.utils import canonicalize_name; '
                     'print(json.dumps(dict(prefix=sys.prefix,base_prefix=sys.base_prefix,python_version=sys.version.split()[0],'
                     'packages={canonicalize_name(d.metadata["Name"]):d.version for d in m.distributions()},marker_environment=default_environment())))')
            actual = json.loads(self.runner([path / 'bin/python', '-I', '-c', probe], cwd=isolated, env=env))
            if Path(actual['prefix']).resolve() != path or actual['prefix'] == actual['base_prefix']:
                raise DeployError('Prepared interpreter does not belong to the candidate venv.')
            if actual['packages'] != manifest.get('packages') or actual['python_version'] != manifest.get('python_version'):
                raise DeployError('Prepared installed packages or Python version changed after preparation.')
            validate_locked_packages(manifests['requirements.txt'], manifests['requirements-lock.txt'], actual['packages'], actual['marker_environment'])
            self.runner([path / 'bin/python', '-I', '-m', 'pip', 'check'], cwd=isolated, env=env)
        evidence = {'path': str(path), 'manifest_sha256': hashes, 'python_version': actual['python_version'],
                    'packages_sha256': hashlib.sha256(json.dumps(actual['packages'], sort_keys=True).encode()).hexdigest()}
        if self.prepared_backend_evidence is not None and self.prepared_backend_evidence != evidence:
            raise DeployError('Prepared backend environment changed during deployment.')
        self.prepared_backend_evidence = evidence

    def clean_head(self, expected=None):
        if self.git('status', '--porcelain', '--untracked-files=no'):
            raise DeployError('Tracked changes found; preserve them and resolve manually before deploying.')
        head = self.git('rev-parse', 'HEAD')
        if expected and head != expected:
            raise DeployError('HEAD changed during deployment; no source was overwritten.')
        return head

    def business_state(self):
        """Read one logical snapshot; deployment records contain only its hash."""
        self.validate_state_paths()
        path = self.state / 'office.sqlite3'
        if not path.is_file():
            raise DeployError('An existing state DB is required; deployment never initializes production state.')
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
            row = db.execute("SELECT value FROM settings WHERE key='work_window'").fetchone()
            window = json.loads(row[0]) if row else {}
            end = datetime.fromisoformat(window['authorized_end']) if window.get('authorized_end') else None
            if not end or end.tzinfo is None or end > datetime.now(timezone.utc):
                raise DeployError('The work window is open or unconfirmed; close it before deploying.')
            fingerprint = hashlib.sha256()
            tables = db.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
            for name, schema in tables:
                fingerprint.update(json.dumps([name, schema], ensure_ascii=False).encode())
                quoted = '"' + name.replace('"', '""') + '"'
                rows = sorted(json.dumps(row, ensure_ascii=False, separators=(',', ':')) for row in db.execute('SELECT * FROM ' + quoted))
                for row in rows:
                    fingerprint.update(row.encode())
            return fingerprint.hexdigest()

    def owner(self, expected=frozenset(('api', 'frontend'))):
        self.validate_state_paths()
        record = json.loads((self.state / 'runtime/services.json').read_text(encoding='utf-8'))
        if record.get('scope') != 'heobrain-content-office' or Path(record.get('app_dir', '')).resolve() != self.app:
            raise DeployError('Service registry belongs to another app; no process will be stopped.')
        alive = set()
        for name, saved in record.get('services', {}).items():
            current = self.identity(saved.get('pid'))
            if current and current.get('start_ticks') == saved.get('start_ticks'):
                alive.add(name)
        if alive != set(expected):
            raise DeployError('Owned service state changed, or a worker/watcher is active; deployment stopped.')
        return record

    def preflight(self):
        if not re.fullmatch('[0-9a-f]{40}', self.target):
            raise DeployError('Pass a full reviewed 40-character commit SHA, never a branch or abbreviation.')
        previous = self.clean_head()
        if self.git('rev-parse', '--verify', self.target + '^{commit}') != self.target:
            raise DeployError('Target must be an available commit; fetch separately before deploying.')
        self.git('merge-base', '--is-ancestor', previous, self.target)
        changed = set(self.git('diff', '--name-only', previous, self.target, '--', *((APP_PATH / path).as_posix() for path in DEPENDENCIES)).splitlines())
        allowed = {(APP_PATH / 'backend' / name).as_posix() for name in PREPARED_MANIFESTS} if self.prepared_backend_venv is not None else set()
        if changed - allowed:
            raise DeployError('Dependency manifests/locks changed; review and prepare dependencies separately.')
        if self.prepared_backend_venv is not None:
            self.validate_prepared_backend()
        self.owner()
        if not (self.app / 'frontend/.next/BUILD_ID').is_file():
            raise DeployError('An existing production build is required for rollback; do initial setup separately.')
        if (self.app / 'frontend/.next').is_symlink():
            raise DeployError('The live build must be a directory owned by this checkout, not a symlink.')
        return previous, self.business_state()

    def check(self, label, command, cwd, env):
        try:
            output = self.runner(command, cwd=cwd, env=env)
        except BaseException as error:
            (self.release / (label + '.failed')).write_text('Command failed in isolated staging.\n')
            (self.release / (label + '.log')).write_text(getattr(error, 'output', ''), encoding='utf-8')
            raise
        (self.release / (label + '.log')).write_text(output, encoding='utf-8')
        return output

    def stage(self):
        stage = self.release / 'stage'
        self.git('worktree', 'add', '--detach', str(stage), self.target)
        app = stage / APP_PATH
        for folder in (stage, app, app / 'backend', app / 'frontend'):
            if any((folder / name).exists() for name in ('.env', '.env.local', '.env.production', '.env.production.local', '.env.test', '.env.test.local')):
                raise DeployError('A tracked runtime environment file exists in staging; key-free checks cannot be guaranteed.')
        for relative in ('backend/.venv', 'frontend/node_modules'):
            source = self.prepared_backend_venv if relative == 'backend/.venv' and self.prepared_backend_venv is not None else self.app / relative
            if not source.is_dir():
                raise DeployError('Existing dependency directory is missing: ' + relative)
            (app / relative).symlink_to(source, target_is_directory=True)
        python = (self.prepared_backend_venv or self.app / 'backend/.venv') / 'bin/python'
        node = shutil.which('node', path=self.env.get('PATH'))
        if not python.is_file() or not node:
            raise DeployError('Existing Linux venv Python and Node must already be installed.')
        with tempfile.TemporaryDirectory(prefix='office-deploy-check-') as isolated:
            env = isolated_env(self.env, Path(isolated))
            if self.ci:
                # The same exact commit already passed every test off-server; only build what will run here.
                (self.release / 'tests.skipped').write_text('Tests ran off-server: ' + json.dumps(self.ci, ensure_ascii=False) + '\n', encoding='utf-8')
                backend = frontend = ''
            else:
                backend = self.check('backend', [python, '-m', 'pytest', '-q'], app / 'backend', env)
                if (app / 'scripts/tests/test_deploy_ec2.py').is_file():
                    self.check('deployment', [python, '-m', 'unittest', 'discover', '-s', str(app / 'scripts/tests'), '-p', 'test_deploy_ec2.py'], stage, env)
                self.check('typecheck', [node, 'node_modules/typescript/bin/tsc', '--noEmit', '--incremental', 'false'], app / 'frontend', env)
                frontend = self.check('frontend', [node, '--experimental-strip-types', '--test', *sorted((app / 'frontend/tests').glob('*.test.ts'))], app / 'frontend', env)
                world = sorted((stage / 'sites/office-world/tests').glob('*.test.mjs'))
                if world:
                    self.check('world', [node, '--test', *world], stage, env)
            self.check('build', [node, 'node_modules/next/dist/bin/next', 'build', '--webpack'], app / 'frontend', env)
        if not (app / 'frontend/.next/BUILD_ID').is_file():
            raise DeployError('The staged production build has no BUILD_ID.')
        if self.git('status', '--porcelain', '--untracked-files=no', cwd=stage):
            raise DeployError('Checks modified tracked staged sources; do not deploy an unreviewed tree.')
        return app / 'frontend/.next', backend, frontend

    def service(self, action):
        self.validate_state_paths()
        self.runner(['bash', str(self.app / ('scripts/' + action + '-local.sh'))], cwd=self.app, env=self.env)

    def health(self):
        opener = build_opener(ProxyHandler({}))
        until = time.monotonic() + 30
        while time.monotonic() < until:
            try:
                with opener.open('http://127.0.0.1:8510/api/health', timeout=2) as response:
                    payload = json.load(response)
                    if response.geturl() != 'http://127.0.0.1:8510/api/health' or payload.get('status') != 'ok' or payload.get('scope') != 'local-content-office':
                        raise ValueError('Backend not ready')
                with opener.open('http://127.0.0.1:3110/', timeout=2) as response:
                    if response.status == 200 and response.geturl() == 'http://127.0.0.1:3110/':
                        return
            except (OSError, ValueError):
                time.sleep(.25)
        raise DeployError('API/frontend health checks did not pass.')

    def record(self, status, **values):
        path = self.release / 'deployment.json'
        previous = json.loads(path.read_text()) if path.exists() else {}
        previous.update(status=status, target=self.target, **values)
        path.write_text(json.dumps(previous, ensure_ascii=False, indent=2), encoding='utf-8')

    def execute(self):
        runtime = self.state / 'runtime'
        repo_lock = Path(self.git('rev-parse', '--path-format=absolute', '--git-common-dir')) / 'heobrain-deploy.lock'
        with ExitStack() as locks:
            for path in (repo_lock, runtime / 'deploy.lock', self.state / 'watcher.lock', self.state / 'worker.lock'):
                if path.is_symlink():
                    raise DeployError('A deployment/service lock is a symlink; no lock file was overwritten.')
                locks.enter_context(self.Lock(path))
            previous, fingerprint = self.preflight()
            run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid4().hex[:8]
            self.release = runtime / 'deployments' / run_id
            self.release.mkdir(parents=True)
            helper = self.release / 'deploy_ec2.py'
            shutil.copy2(__file__, helper)
            resume = ['env', 'OFFICE_STATE_DIR=' + str(self.state)]
            if self.env.get('OFFICE_ENV_FILE'):
                resume.append('OFFICE_ENV_FILE=' + self.env['OFFICE_ENV_FILE'])
            resume += [str(self.app / 'backend/.venv/bin/python'), str(helper), '<reviewed-40-character-SHA>', '--repo', str(self.repo)]
            self.record('checking', previous=previous, business_hash=fingerprint, repo=str(self.repo), state_dir=str(self.state),
                        preserved_helper=str(helper), next_deploy_command=resume, ci=self.ci, prepared_backend=self.prepared_backend_evidence)
            build = self.app / 'frontend/.next'
            before = build.with_name('.next.before-' + run_id)
            candidate = build.with_name('.next.candidate-' + run_id)
            venv = self.app / 'backend/.venv'
            previous_venv = venv.with_name('.venv.before-' + run_id)
            info = runtime / 'build-info.json'
            self.validate_state_paths()
            old_info = info.read_bytes() if info.exists() else None
            if old_info is not None:
                (self.release / 'build-info.before.json').write_bytes(old_info)
            cutover = False
            try:
                staged, backend, frontend = self.stage()
                shutil.copytree(staged, candidate)
                self.clean_head(previous)
                self.owner()
                if self.business_state() != fingerprint:
                    raise DeployError('Business records changed during checks; live source/build were preserved.')
                if self.prepared_backend_venv is not None:
                    self.validate_prepared_backend()
                cutover = True
                self.service('stop')
                self.owner(expected=())
                self.clean_head(previous)
                self.git('merge', '--ff-only', self.target)
                if self.prepared_backend_venv is not None:
                    venv.rename(previous_venv)
                    venv.symlink_to(self.prepared_backend_venv, target_is_directory=True)
                if build.exists():
                    build.rename(before)
                candidate.rename(build)
                self.service('start')
                self.health()
                self.owner()
                if self.business_state() != fingerprint:
                    raise DeployError('Business fingerprint changed; the database was not restored or overwritten.')
                counts = dict(passed=0, failed=0, skipped=0, errors=0)
                for n, word in re.findall(r'(\d+) (passed|failed|skipped|errors?)', backend):
                    counts['errors' if word.startswith('error') else word] = int(n)
                front_counts = {word: int(n) for word, n in re.findall(r'(?:# |ℹ )(pass|fail) (\d+)', frontend)}
                build_info = {'commit': self.target, 'deployed_at': datetime.now(timezone.utc).isoformat(),
                              'raw': {'backend': backend[-300:], 'frontend': frontend[-300:]},
                              'tests': {'ci': self.ci} if self.ci else {'backend': counts, 'frontend': {'passed': front_counts.get('pass', 0), 'failed': front_counts.get('fail', 0)}}}
                self.validate_state_paths()
                info.write_text(json.dumps(build_info, ensure_ascii=False), encoding='utf-8')
                self.record('deployed', actual_head=self.clean_head(self.target), previous_build=str(before), business_unchanged=True,
                            previous_backend_venv=str(previous_venv) if self.prepared_backend_venv is not None else None)
                return self.release
            except BaseException as error:
                if cutover:
                    try:
                        # Both service scripts need .venv/bin/python, even when link creation failed.
                        if previous_venv.exists() or previous_venv.is_symlink():
                            if venv.is_symlink() and venv.resolve() == self.prepared_backend_venv:
                                venv.unlink()
                            elif venv.exists() or venv.is_symlink():
                                raise DeployError('Live venv changed during recovery; preserve both environments for manual recovery.')
                            previous_venv.rename(venv)
                        self.service('stop')
                        self.owner(expected=())
                        head = self.clean_head()
                        if head not in (previous, self.target):
                            raise DeployError('HEAD belongs to a later operator; manual recovery is required.')
                        if head != previous:
                            self.git('checkout', '--detach', previous)
                        if before.exists():
                            if build.exists():
                                build.rename(build.with_name('.next.failed-' + run_id))
                            before.rename(build)
                        self.validate_state_paths()
                        if old_info is not None:
                            info.write_bytes(old_info)
                        elif info.exists():
                            info.rename(self.release / 'build-info.failed.json')
                        self.service('start')
                        self.health()
                        self.owner()
                        detached = not bool(self.git('branch', '--show-current'))
                        self.record('rolled_back', actual_head=self.clean_head(previous), detached=detached, error_type=type(error).__name__)
                    except BaseException as recovery:
                        self.record('manual_recovery_required', actual_head=self.git('rev-parse', 'HEAD'), error_type=type(error).__name__, recovery_type=type(recovery).__name__, previous_build=str(before))
                        raise DeployError('Recovery stopped without forcing source changes. Preserve artifacts: ' + str(self.release)) from recovery
                    raise DeployError(str(error) + '; restored previous SHA ' + previous + (' (detached HEAD)' if detached else '') + '; artifacts: ' + str(self.release)) from error
                else:
                    self.record('checks_failed', actual_head=self.git('rev-parse', 'HEAD'), error_type=type(error).__name__)
                raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', help='Reviewed full 40-character Git commit SHA; fetch separately first')
    parser.add_argument('--repo', type=Path, help='Explicit live repository root when using the preserved recovery helper')
    parser.add_argument('--ci-verified-repo', metavar='OWNER/REPO',
                        help='Skip server-side tests only if GitHub reports the `verify` check passed for this exact commit')
    parser.add_argument('--prepared-backend-venv', type=Path,
                        help='Use a separately prepared Linux venv with matching heobrain-prepared.json; never install during deployment')
    args = parser.parse_args()
    app = Path(__file__).resolve().parents[1]
    repo = args.repo.resolve() if args.repo else Path(run(['git', 'rev-parse', '--show-toplevel'], cwd=app).strip()).resolve()
    if Path(run(['git', 'rev-parse', '--show-toplevel'], cwd=repo).strip()).resolve() != repo:
        parser.error('--repo must name the repository root itself')
    state = Path(os.environ.get('OFFICE_STATE_DIR', str(Path.home() / '.local/state/heobrain-content-office')))
    operation = None
    try:
        ci = ci_verification(args.ci_verified_repo, args.target.lower()) if args.ci_verified_repo else None
        operation = Deployment(repo, state, args.target, ci=ci, prepared_backend_venv=args.prepared_backend_venv)
        path = operation.execute()
        print('Deployed exact commit ' + args.target + '; verification artifacts: ' + str(path))
    except (DeployError, OSError, ValueError) as error:
        artifacts = '; deployment artifacts: ' + str(operation.release) if operation and operation.release else ''
        parser.exit(1, str(error) + artifacts + '\n')


if __name__ == '__main__':
    main()
