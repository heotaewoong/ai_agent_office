"""자료 조사(run_research) 한 번의 기록. 로컬 JSONL에만 쓰고 외부 추적 서비스로 보내지 않는다.

- 한 줄 = 조사 한 번. 바깥 호출이 0회인 조사(범위 밖, 창고 판정 맞음, 조사 필요 없음)도 남긴다.
- 개인 DB(책) 문장은 이 경로에 들어오지 않는다. 기획 제목과 그 제목으로 만든 검색어, 공개 후보의 주소와 제목만 남긴다.
- 검색 골든셋 trace_schema.md의 card_trace와 같은 칸 이름을 쓴다.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

_SCALAR_OPTIONS = ("summary", "area", "kind", "experience_first", "auto", "force")


def _status(result, trace, error) -> str:
    if error:
        return "error"
    if not isinstance(result, dict):
        return "unknown"
    if result.get("plan", {}).get("blocked"):
        return "blocked"
    if trace and trace.get("skipped_by_verdict"):
        return "skipped_by_verdict"
    return "searched" if result.get("searched") else "no_outside_call"


def record_research(root, title, options, result, trace, error, elapsed_ms) -> dict | None:
    at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    plan = (result or {}).get("plan") or {}
    queries = (result or {}).get("queries") or {}
    jobs = (trace or {}).get("jobs") or []
    entry = {
        "at": at, "run_id": hashlib.sha256(f"{at}|{title}".encode("utf-8")).hexdigest()[:16], "kind": "research",
        "title": str(title or "")[:300],
        "options": {key: (bool(options[key]) if key == "summary" else options[key]) for key in _SCALAR_OPTIONS if key in options},
        "custom_query": bool(options.get("query")),
        "status": _status(result, trace, error), "error": error, "elapsed_ms": int(elapsed_ms),
        "plan": {key: plan.get(key) for key in ("area", "area_guessed", "kind", "kind_guessed", "blocked", "need", "experience_first")}
                | {"claims": [claim.get("id") for claim in plan.get("claims") or []],
                   "fact_need": (plan.get("fact") or {}).get("need"), "fact_providers": (plan.get("fact") or {}).get("providers"),
                   "example_need": (plan.get("example") or {}).get("need")},
        "queries": {"english": queries.get("english"), "names": queries.get("names"), "terms": len(queries.get("terms") or []),
                    "translated": bool(queries.get("translated"))},
        "library": (trace or {}).get("library"),
        "verdict": ((result or {}).get("verdict") or {}).get("verdict"),
        "outside": {"jobs": jobs, "fact_lane_called": any(job in ("pubmed", "openalex", "arxiv", "github", "official") for job in jobs),
                    "example_lane_called": "creator" in jobs},
        "candidates": [{"key": row.get("key"), "lane": row.get("lane"), "provider": row.get("provider"), "url": row.get("url"),
                        "title": str(row.get("title", ""))[:160], "in_library": row.get("in_library")}
                       for row in (result or {}).get("candidates") or []],
        "notes": len((result or {}).get("notes") or []),
    }
    try:
        path = Path(root) / "traces" / ("research-" + time.strftime("%Y-%m-%d") + ".jsonl")
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError:
        return None  # 기록을 못 해도 조사 결과는 그대로 돌려준다.
    return entry


def read_research_traces(root, day: str | None = None) -> list[dict]:
    path = Path(root) / "traces" / ("research-" + (day or time.strftime("%Y-%m-%d")) + ".jsonl")
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, ValueError):
        return []
