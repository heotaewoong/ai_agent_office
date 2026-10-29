"""구조도 화면의 데이터. 그림(공정·안전장치·상태 메모)은 config/architecture.json 문서에서, 실행 사실은 서버에서 읽는다.

자동으로 채우는 것: 실행 중인 커밋과 최근 커밋(git), 배포 시각과 테스트 결과(runtime/build-info.json, 배포 스크립트가 기록),
키 연결 여부(환경 변수 존재만, 값은 읽지 않음), 글·이미지 프로필, 작업 시간·작업자 상태, 모델별 실측 비용(이벤트와 이미지 영수증).
이 모듈은 아무것도 호출하거나 바꾸지 않는다.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .store import WorkflowError, canonical

APP_DIR = Path(__file__).resolve().parents[2]
DOC_PATH = Path(__file__).resolve().parents[1] / "config" / "architecture.json"
KEYS = {"openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY", "runway": "RUNWAYML_API_SECRET", "youtube": "YOUTUBE_CLIENT_ID"}


def load_doc(path=DOC_PATH):
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise WorkflowError(f"구조도 문서를 읽지 못했습니다: {error}") from None
    for key in ("headline", "summary", "flow", "unit_costs", "rails", "status"):
        if key not in doc:
            raise WorkflowError(f"구조도 문서에 '{key}' 항목이 없습니다")
    return doc


def _git(*args, cwd=APP_DIR):
    try:
        result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def git_info(cwd=APP_DIR, limit=12):
    head = _git("log", "-1", "--format=%H%x1f%cI%x1f%s", cwd=cwd)
    if not head:
        return {"commit": None, "committed_at": None, "subject": None, "recent": []}
    commit, committed_at, subject = head.split("\x1f", 2)
    recent = []
    for line in (_git("log", f"-{limit}", "--format=%h%x1f%cI%x1f%an%x1f%s", cwd=cwd) or "").splitlines():
        parts = line.split("\x1f", 3)
        if len(parts) == 4:
            recent.append({"commit": parts[0], "at": parts[1], "author": parts[2], "subject": parts[3]})
    return {"commit": commit, "committed_at": committed_at, "subject": subject, "recent": recent}


def parse_pytest(summary):
    """'434 passed, 7 skipped in 46.84s' → {"passed": 434, "skipped": 7, "failed": 0}"""
    counts = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    for number, word in re.findall(r"(\d+) (passed|failed|skipped|errors?)", summary or ""):
        counts["errors" if word.startswith("error") else word] += int(number)
    return counts


def parse_node_test(summary):
    """node --test 출력의 'ℹ pass 54' · 'ℹ fail 0' 줄."""
    counts = {"passed": 0, "failed": 0}
    for word, number in re.findall(r"ℹ (pass|fail) (\d+)", summary or ""):
        counts["passed" if word == "pass" else "failed"] = int(number)
    return counts


def record_build_info(root, *, backend_summary, frontend_summary, cwd=APP_DIR, now=None):
    """배포 스크립트가 테스트·빌드를 마친 뒤 부른다. runtime/build-info.json에 남긴다."""
    info = {"commit": (git_info(cwd, limit=1)["commit"]), "deployed_at": (now or datetime.now(timezone.utc)).isoformat(),
            "tests": {"backend": parse_pytest(backend_summary), "frontend": parse_node_test(frontend_summary)},
            "raw": {"backend": (backend_summary or "").strip()[-300:], "frontend": (frontend_summary or "").strip()[-300:]}}
    path = Path(root) / "runtime" / "build-info.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical(info), encoding="utf-8")
    return info


def usage(store, limit=5000):
    """역할·모델별 실측 비용. 글은 model_completed 이벤트, 이미지는 영수증에서 읽는다."""
    rows = defaultdict(lambda: {"calls": 0, "krw": 0.0})
    for event in store.events(limit=limit):
        if event["kind"] != "model_completed":
            continue
        data = event.get("data") or {}
        row = rows[(data.get("role") or "?", data.get("model") or "?")]
        row["calls"] += 1
        row["krw"] += float(data.get("estimated_krw") or 0)
    assets = store.root / "image-assets"
    if assets.is_dir():
        for receipt in assets.glob("*.json"):
            try:
                data = json.loads(receipt.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if data.get("status") != "complete":
                continue
            role = "card_image" if "card_index" in data else "image"
            model = (data.get("image_metadata") or {}).get("model") or "?"
            row = rows[(role, model)]
            row["calls"] += 1
            row["krw"] += float(data.get("estimated_krw") or 0)
    return [{"role": role, "model": model, "calls": v["calls"], "krw": round(v["krw"], 1), "per_call": round(v["krw"] / v["calls"], 1) if v["calls"] else 0}
            for (role, model), v in sorted(rows.items(), key=lambda item: -item[1]["krw"])]


def overview(store, *, doc_path=DOC_PATH, cwd=APP_DIR):
    from .image_selection import profile_summary as image_profile
    from .text_selection import profile_summary as text_profile
    build_path = store.root / "runtime" / "build-info.json"
    try:
        build = json.loads(build_path.read_text(encoding="utf-8")) if build_path.is_file() else None
    except (OSError, ValueError):
        build = None
    git = git_info(cwd)
    worker = store.setting("worker_status", {}) or {}
    window = store.setting("work_window", {}) or {}
    return {
        "doc": load_doc(doc_path),
        "git": git,
        "build": build,
        "build_matches_running_code": bool(build and git["commit"] and build.get("commit") == git["commit"]),
        "keys": {name: bool(os.environ.get(env)) for name, env in KEYS.items()},
        "profiles": {"text": text_profile(store)["model"], "image": image_profile(store)["id"]},
        "window": {"status": window.get("status"), "authorized_end": window.get("authorized_end")},
        "worker": {"state": worker.get("state"), "heartbeat": worker.get("heartbeat")},
        "budget": store.budget(),
        "usage": usage(store),
    }


def main():
    parser = argparse.ArgumentParser(description="배포 뒤 테스트 결과를 구조도 화면에 기록합니다")
    parser.add_argument("command", choices=["record"])
    parser.add_argument("--backend", required=True, help="pytest 마지막 요약 줄")
    parser.add_argument("--frontend", required=True, help="npm test 출력(ℹ pass/fail 줄 포함)")
    args = parser.parse_args()
    from .bootstrap import default_store
    print(canonical(record_build_info(default_store().root, backend_summary=args.backend, frontend_summary=args.frontend)))


if __name__ == "__main__":
    main()
