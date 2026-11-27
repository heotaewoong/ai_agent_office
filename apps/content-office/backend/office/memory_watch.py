"""요청마다 웹 서버 메모리(RSS)를 재서, 크게 뛴 요청만 api.log에 남긴다(0원, 요청당 /proc 한 번 읽기).

2026-11-27 운영에서 웹 서버가 한 번 1.3GB까지 올랐다(감시 프로그램 재시작 기준 1.4GB). 어느 요청 때문인지 알 수 없어서 붙인다.
"""
from __future__ import annotations

import sys
import time

JUMP_MB = 150      # 한 요청 동안 이만큼 넘게 늘면 남긴다.
HIGH_MB = 900      # 요청이 끝났을 때 이보다 크면 남긴다(감시 프로그램 기준 1,400MB 전에 알 수 있게).


def rss_mb() -> int | None:
    try:
        with open("/proc/self/status", encoding="ascii") as status:
            for line in status:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def note(method: str, path: str, before: int | None, after: int | None, seconds: float, out=None) -> str | None:
    if before is None or after is None:
        return None
    if after - before < JUMP_MB and after < HIGH_MB:
        return None
    line = f"MEMORY {method} {path[:120]} rss {before}MB -> {after}MB ({after - before:+d}MB) in {seconds:.1f}s"
    print(line, file=out or sys.stderr, flush=True)
    return line


def install(app) -> None:
    @app.middleware("http")
    async def memory_watch(request, call_next):
        before, started = rss_mb(), time.monotonic()
        try:
            return await call_next(request)
        finally:
            note(request.method, request.url.path, before, rss_mb(), time.monotonic() - started)
