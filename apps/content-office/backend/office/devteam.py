"""개발 팀 상태: GitHub 검증 → 서버 배포 → 확인.

배포는 scripts/auto_deploy.py(서버 cron)와 scripts/deploy_ec2.py가 한다. 이 모듈은 그 기록을 읽어 보여주고,
사람이 켜고 끄는 자동 배포 스위치 하나만 쓴다. 콘텐츠 승인 ⓪①②③과는 무관하다.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .store import now

DECISION_LABELS = {
    "disabled": "자동 배포 꺼짐",
    "up_to_date": "최신 버전 운영 중",
    "waiting_ci": "GitHub 검증 기다림",
    "ci_failed": "GitHub 검증 실패",
    "skip_failed": "실패한 커밋 건너뜀",
    "needs_dependencies": "의존성 준비 필요",
    "deployed": "배포 완료",
    "failed": "배포 실패·이전 버전 유지",
    "deferred": "서버 사정으로 다음 주기 재시도",
    "emergency_stop": "비상 정지·사람 확인 필요",
}
DEPLOY_LABELS = {"deployed": "배포 완료", "checks_failed": "빌드 실패", "rolled_back": "되돌림", "manual_recovery_required": "수동 복구 필요", "checking": "진행 중"}


def _read(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _runtime(root):
    return Path(root) / "runtime"


def recent_deployments(root, limit=8):
    folder = _runtime(root) / "deployments"
    if not folder.is_dir():
        return []
    rows = []
    for release in sorted((p for p in folder.iterdir() if p.is_dir()), key=lambda p: p.name, reverse=True)[:limit]:
        info = _read(release / "deployment.json", {})
        status = info.get("status", "unknown")
        rows.append({"id": release.name, "status": status, "label": DEPLOY_LABELS.get(status, status), "commit": (info.get("target") or "")[:10], "ci_verified": bool(info.get("ci"))})
    return rows


def dev_status(root):
    runtime = _runtime(root)
    switch = _read(runtime / "auto-deploy-switch.json", {"enabled": False})
    watcher = _read(runtime / "auto-deploy.json", None)
    build = _read(runtime / "build-info.json", {})
    summary = None
    if watcher:
        summary = {key: watcher.get(key) for key in ("checked_at", "decision", "reason", "origin", "deployed", "slug")}
        summary["label"] = DECISION_LABELS.get(watcher.get("decision"), watcher.get("decision"))
        summary["ci"] = {k: (watcher.get("ci") or {}).get(k) for k in ("state", "url", "detail")}
        summary["history"] = [{k: h.get(k) for k in ("at", "origin", "decision", "reason")} | {"label": DECISION_LABELS.get(h.get("decision"), h.get("decision"))} for h in (watcher.get("history") or [])[-8:]][::-1]
    return {
        "version": 1,
        "enabled": bool(switch.get("enabled")),
        "switch": {k: switch.get(k) for k in ("changed_at", "actor", "reason")},
        "watcher": summary,
        "watcher_installed": watcher is not None,
        "running": {"commit": (build.get("commit") or "")[:10], "deployed_at": build.get("deployed_at"), "ci_verified": bool((build.get("tests") or {}).get("ci"))},
        "deployments": recent_deployments(root),
    }


def set_switch(root, enabled, actor="local-operator"):
    runtime = _runtime(root)
    runtime.mkdir(parents=True, exist_ok=True)
    path = runtime / "auto-deploy-switch.json"
    value = {"enabled": bool(enabled), "changed_at": now(), "actor": actor}
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, path)
    return value
