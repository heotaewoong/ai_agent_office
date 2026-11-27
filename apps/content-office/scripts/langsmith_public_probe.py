#!/usr/bin/env python3
"""LangSmith 연결 실험: 커밋된 공개 샘플만, 0원 가짜 모델로 v2 검수를 한 번 돌린다.

기본은 아무것도 보내지 않는 확인 실행이다. --send를 붙이면 보내는데, 셸에 LANGSMITH_API_KEY가 없으면
본인만 읽을 수 있는 키 파일(~/.config/heobrain-content-office/langsmith.key, 바꾸려면 HEOBRAIN_LANGSMITH_KEY_FILE)을 읽는다.
키 값은 화면과 기록 어디에도 쓰지 않는다. 운영 원고와 개인 자료는 이 스크립트로 보낼 수 없다(office.public_sample.require_public_sample).
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from office.public_sample import PROBE_PROJECT, run_public_probe  # noqa: E402

KEY_FILE = Path.home() / ".config" / "heobrain-content-office" / "langsmith.key"


def load_key_file(environ=os.environ):
    """셸에 키가 없을 때만 키 파일을 읽어 이 프로세스에만 넣는다. 읽었으면 'file', 셸에 있으면 'env', 없으면 None."""
    if environ.get("LANGSMITH_API_KEY"):
        return "env"
    path = Path(environ.get("HEOBRAIN_LANGSMITH_KEY_FILE") or KEY_FILE)
    if not path.is_file():
        return None
    if os.name != "nt" and path.stat().st_mode & 0o077:
        raise SystemExit(f"{path} 권한을 600으로 바꾼 뒤 다시 실행하세요. 다른 계정이 읽을 수 있는 키 파일은 쓰지 않아요")
    key = path.read_text(encoding="utf-8").strip()
    if not key:
        return None
    environ["LANGSMITH_API_KEY"] = key
    return "file"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--send", action="store_true", help="공개 샘플의 추적을 LangSmith로 보낸다")
    parser.add_argument("--project", default=PROBE_PROJECT)
    args = parser.parse_args(argv)
    key_source = load_key_file() if args.send else None
    result = run_public_probe(send=args.send, project=args.project)
    print(json.dumps({**result, "key_source": key_source}, ensure_ascii=False))


if __name__ == "__main__":
    main()
