#!/usr/bin/env python3
"""개발 팀 자동 배포 감시기. cron이 10분마다 부른다.

GitHub `verify`를 통과한 origin/main 커밋만 기존 deploy_ec2.py로 배포한다. 검증은 서버 밖에서 끝났으므로
서버에서는 빌드·상태 확인·자동 되돌리기만 한다. 사람이 끈 스위치는 존중하고, 감시기는 비상 정지 때만 끈다.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.request import build_opener

APP = Path(__file__).resolve().parents[1]
SLUG = os.environ.get('OFFICE_REPO_SLUG', 'heotaewoong/ai_agent_office')
HISTORY_LIMIT, ATTEMPT_LIMIT = 20, 50
GIVE_UP = {'checks_failed', 'rolled_back'}

_spec = importlib.util.spec_from_file_location('deploy_ec2', Path(__file__).with_name('deploy_ec2.py'))
deploy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(deploy)


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def write_json(path, value):
    path = Path(path)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, path)


def ci_state(slug, sha, opener=None):
    """GitHub `verify` 체크의 세 갈래 상태: success / pending / failure (없거나 읽지 못하면 pending·unknown)."""
    opener = opener or build_opener()
    url = 'https://api.github.com/repos/' + slug + '/commits/' + sha + '/check-runs?check_name=' + deploy.CI_CHECK + '&per_page=20'
    try:
        with opener.open(url, timeout=15) as response:
            payload = json.load(response)
    except (OSError, ValueError) as error:
        return {'state': 'unknown', 'detail': type(error).__name__}
    runs = [r for r in payload.get('check_runs', []) if r.get('name') == deploy.CI_CHECK and r.get('head_sha') == sha]
    if not runs:
        return {'state': 'pending', 'detail': 'GitHub 검증이 아직 시작되지 않았어요'}
    done = [r for r in runs if r.get('status') == 'completed']
    url = max(runs, key=lambda r: r.get('started_at') or '').get('html_url')
    if any(r.get('conclusion') != 'success' for r in done):
        return {'state': 'failure', 'url': url, 'detail': ', '.join(sorted({str(r.get('conclusion')) for r in done if r.get('conclusion') != 'success'}))}
    if len(done) < len(runs) or not done:
        return {'state': 'pending', 'url': url, 'detail': 'GitHub 검증 진행 중'}
    return {'state': 'success', 'url': url}


def decide(*, enabled, origin, deployed, attempted, ci, deps_changed):
    """배포할지와 그 이유. 서버 부하가 드는 배포는 마지막에만 고른다."""
    if not enabled:
        return 'disabled', '자동 배포가 꺼져 있어요'
    if origin == deployed:
        return 'up_to_date', '서버가 최신 main을 쓰고 있어요'
    if attempted.get(origin) in GIVE_UP:
        return 'skip_failed', '이 커밋은 서버 배포에서 이미 실패해 다음 커밋을 기다려요'
    if ci['state'] == 'failure':
        return 'ci_failed', 'GitHub 검증에서 실패한 커밋이에요'
    if ci['state'] != 'success':
        return 'waiting_ci', ci.get('detail') or 'GitHub 검증 결과를 기다려요'
    if deps_changed:
        return 'needs_dependencies', '의존성 목록이 바뀌어 사람이 서버 의존성을 준비해야 해요: ' + ', '.join(deps_changed)
    return 'deploy', 'GitHub 검증을 통과한 새 커밋을 배포해요'


DEFER_LIMIT = 5


def classify(status, message, failed_checks=()):
    """배포 스크립트 결과를 감시기 판단으로 바꾼다.

    deploy_ec2.py는 컷오버 전의 모든 오류를 checks_failed로 남긴다. 그중 실제 검사·빌드 실패는
    `<label>.failed` 파일이 남는다. 그 파일이 없으면(빌드 중 업무 기록 변경, 서비스 상태 변경 등)
    커밋 잘못이 아니므로 다음 주기에 다시 시도한다.
    """
    if status == 'deployed':
        return 'deployed', '배포했어요'
    if status == 'checks_failed' and failed_checks:
        return 'failed', '서버 빌드에서 실패했어요: ' + ', '.join(sorted(failed_checks))
    if status == 'rolled_back':
        return 'failed', '배포 뒤 확인에 실패해 이전 버전으로 되돌렸어요'
    if status == 'manual_recovery_required':
        return 'emergency_stop', '자동 복구에 실패했어요. 자동 배포를 끄고 사람의 확인을 기다려요'
    return 'deferred', '서버가 지금 배포를 받지 않아 다음 주기에 다시 봐요: ' + (message or '').strip()[-240:]


class Watcher:
    def __init__(self, repo, state, *, slug=SLUG, opener=None, runner=None):
        self.repo, self.state, self.slug = Path(repo), Path(state), slug
        self.runtime = self.state / 'runtime'
        self.switch_path = self.runtime / 'auto-deploy-switch.json'
        self.status_path = self.runtime / 'auto-deploy.json'
        self.opener, self.runner = opener, runner or self._run

    @staticmethod
    def _run(command, cwd, env=None):
        result = subprocess.run([str(p) for p in command], cwd=cwd, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=3600)
        return result.returncode, result.stdout + result.stderr

    def git(self, *args):
        code, output = self.runner(['git', *args], self.repo)
        if code:
            raise RuntimeError('git ' + args[0] + ' failed: ' + output.strip()[-200:])
        return output.strip()

    def deployed(self):
        return read_json(self.runtime / 'build-info.json', {}).get('commit')

    def deps_changed(self, deployed, origin):
        if not deployed:
            return []
        paths = [str(deploy.APP_PATH / p) for p in deploy.DEPENDENCIES]
        changed = self.git('diff', '--name-only', deployed, origin, '--', *paths)
        return [line for line in changed.splitlines() if line]

    def releases(self):
        folder = self.runtime / 'deployments'
        return {p.name for p in folder.iterdir()} if folder.is_dir() else set()

    def deploy(self, sha):
        before = self.releases()
        env = dict(os.environ)
        command = ['nice', '-n', '10', 'bash', str(APP / 'scripts/deploy-ec2.sh'), sha, '--ci-verified-repo', self.slug]
        code, output = self.runner(command, APP, env)
        new = sorted(self.releases() - before)
        if not new:
            return None, output, None, ()
        folder = self.runtime / 'deployments' / new[-1]
        status = read_json(folder / 'deployment.json', {}).get('status')
        failed = tuple(p.stem for p in folder.glob('*.failed'))
        return status, output, new[-1], failed

    def run_once(self):
        switch = read_json(self.switch_path, {'enabled': False})
        record = read_json(self.status_path, {'attempted': {}, 'history': []})
        record.setdefault('attempted', {})
        record.setdefault('history', [])
        enabled = bool(switch.get('enabled'))
        self.git('fetch', '--quiet', 'origin', 'main')
        origin, deployed = self.git('rev-parse', 'origin/main'), self.deployed()
        ci = ci_state(self.slug, origin, self.opener) if origin != deployed else {'state': 'success'}
        deps = self.deps_changed(deployed, origin) if ci['state'] == 'success' and origin != deployed else []
        decision, reason = decide(enabled=enabled, origin=origin, deployed=deployed, attempted=record['attempted'], ci=ci, deps_changed=deps)
        release = None
        # GitHub 검증 실패는 기록하지 않는다. 다시 실행해 통과하면 다음 주기에 배포된다.
        if decision == 'deploy':
            status, output, release, failed = self.deploy(origin)
            decision, reason = classify(status, output, failed)
            deferrals = record.setdefault('deferrals', {})
            if decision == 'deferred' and release:
                # 빌드까지 갔다가 일시적 이유로 멈춘 경우만 센다. 같은 커밋이 계속 그러면 빌드 반복을 멈춘다.
                deferrals[origin] = deferrals.get(origin, 0) + 1
                if deferrals[origin] >= DEFER_LIMIT:
                    decision, reason, status = 'failed', f'같은 커밋이 {DEFER_LIMIT}번 연속 보류돼 다음 커밋을 기다려요: ' + reason, 'checks_failed'
            if decision in ('deployed', 'failed'):
                record['attempted'][origin] = status
                deferrals.pop(origin, None)
            if decision == 'emergency_stop':
                write_json(self.switch_path, {'enabled': False, 'changed_at': now(), 'actor': 'auto-deploy', 'reason': reason})
                enabled = False
            deployed = self.deployed()
        record['attempted'] = dict(list(record['attempted'].items())[-ATTEMPT_LIMIT:])
        entry = {'at': now(), 'origin': origin, 'deployed': deployed, 'decision': decision, 'reason': reason, 'ci': ci, 'release': release}
        changed = not record['history'] or {k: record['history'][-1].get(k) for k in ('origin', 'decision')} != {'origin': origin, 'decision': decision}
        if changed:
            record['history'] = (record['history'] + [entry])[-HISTORY_LIMIT:]
        record.update(checked_at=entry['at'], enabled=enabled, origin=origin, deployed=deployed, ci=ci, decision=decision, reason=reason, slug=self.slug)
        write_json(self.status_path, record)
        return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, default=Path(os.environ.get('OFFICE_STATE_DIR', str(Path.home() / '.local/state/heobrain-content-office'))))
    args = parser.parse_args()
    repo = Path(subprocess.run(['git', 'rev-parse', '--show-toplevel'], cwd=APP, capture_output=True, text=True, check=True).stdout.strip())
    sys.path.insert(0, str(APP / 'backend'))
    from office.runtime import AlreadyRunning, ProcessLock
    try:
        with ProcessLock(args.state / 'runtime' / 'auto-deploy.lock'):
            record = Watcher(repo, args.state).run_once()
    except AlreadyRunning:
        print(now(), 'another auto-deploy check is running')
        return
    print(record['checked_at'], record['decision'], record['origin'][:10], record['reason'])


if __name__ == '__main__':
    main()
