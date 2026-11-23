#!/usr/bin/env python3
"""예전 자료함(heobrain-source-inbox)에서 내보낸 JSON을 콘텐츠 오피스 자료 창고로 옮긴다.

내보내기 파일은 자료함을 가진 계정이 읽기 전용으로 만든다. 이 스크립트는 --office-state의 자료 창고에만 쓰고,
같은 주소나 같은 본문은 다시 넣지 않는다. '초안 근거로 사용'은 모두 꺼진 채로 들어간다.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from office.source_library import import_inbox  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--office-state", type=Path, required=True)
    parser.add_argument("export", type=Path)
    args = parser.parse_args()
    rows = json.loads(args.export.read_text(encoding="utf-8"))
    results = import_inbox(args.office_state.resolve(strict=True), rows)
    counts = {kind: sum(row["result"] == kind for row in results) for kind in ("imported", "exists", "skipped", "rejected")}
    print(json.dumps({"counts": counts, "results": results}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
