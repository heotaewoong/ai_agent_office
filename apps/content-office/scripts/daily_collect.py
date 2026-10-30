#!/usr/bin/env python3
"""매일 아침 뉴스 자동 수집 — cron이 15분마다 부른다(README '매일 아침 뉴스 자동 수집').

운영자가 제작 설정에서 켠 시각부터 15분 안의 첫 실행만 일한다. 짧은 작업 시간을 열어 RSS 수집과
한국어 카드 요약만 하고 스스로 닫는다. 작업자 시작·원고·제작·승인·발행은 하지 않는다.
OFFICE_ENV_FILE이 있으면 그 파일의 키를 읽는다(값은 출력하지 않는다).
"""
from __future__ import annotations

import os
import signal
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))


def main():
    from office.daily_collect import load_env_file, run_daily_collect
    env_file = os.environ.get("OFFICE_ENV_FILE")
    if env_file:
        load_env_file(env_file)
    from office.bootstrap import default_store
    from office.runtime import SEOUL, utcnow
    from office.store import canonical

    def interrupt(signum, frame):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, interrupt)
    result = run_daily_collect(default_store())
    print(canonical({"at": utcnow().astimezone(SEOUL).isoformat(), **result}), flush=True)


if __name__ == "__main__":
    main()
