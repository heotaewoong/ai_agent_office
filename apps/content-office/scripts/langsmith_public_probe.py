#!/usr/bin/env python3
"""LangSmith 연결 실험: 커밋된 공개 샘플만, 0원 가짜 모델로 v2 검수를 한 번 돌린다.

기본은 아무것도 보내지 않는 확인 실행이다. 실제로 보내려면 LANGSMITH_API_KEY를 넣은 셸에서 --send를 붙인다.
운영 원고와 개인 자료는 이 스크립트로 보낼 수 없다(office.public_sample.require_public_sample).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from office.public_sample import PROBE_PROJECT, run_public_probe  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--send", action="store_true", help="공개 샘플의 추적을 LangSmith로 보낸다")
    parser.add_argument("--project", default=PROBE_PROJECT)
    args = parser.parse_args(argv)
    print(json.dumps(run_public_probe(send=args.send, project=args.project), ensure_ascii=False))


if __name__ == "__main__":
    main()
