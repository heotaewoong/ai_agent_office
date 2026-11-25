"""검수 하네스(v2_harness)의 단계별 기록. 로컬 JSONL에만 쓰고 외부 추적 서비스로 보내지 않는다.

- 한 줄 = 한 단계(validate, judge, refine, rollback). 입력과 출력은 해시만 남기고, 개인 자료(책 근거, 원문 보존 W4)가
  섞인 실행은 내용 요약(payload)을 남기지 않는다.
- layer는 실패가 어느 층에서 났는지 가르는 분류다(설계 v2 6장 '재는 것'과 같은 목적).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .store import WorkflowError, canonical, digest

FAILURE_LAYERS = frozenset({"input_contract", "retrieval", "ranking", "query", "generation", "validate", "eval_judge", "refine", "guardrail"})
_REMOTE_TRACING = ("LANGCHAIN_TRACING_V2", "LANGCHAIN_TRACING", "LANGSMITH_TRACING_V2", "LANGSMITH_TRACING")


def assert_no_remote_tracing() -> None:
    """원격 추적이 켜져 있으면 검수를 시작하지 않는다(원고와 개인 자료가 밖으로 나가지 않게)."""
    if any(os.environ.get(key, "").strip().lower() in ("1", "true", "yes") for key in _REMOTE_TRACING):
        raise WorkflowError("검수 기록의 외부 추적 전송은 승인되지 않았습니다. 추적 환경 변수를 끄고 다시 실행하세요")


class TraceRecorder:
    def __init__(self, root, run_id: str, *, w_type: str | None = None, contains_private: bool = False):
        self.path = Path(root) / "traces" / (time.strftime("%Y-%m-%d") + ".jsonl")
        self.run_id, self.w_type, self.contains_private = run_id, w_type, contains_private

    def record(self, *, step: str, layer: str, input_obj=None, output_obj=None, elapsed_ms: int = 0, calls: int = 0,
               status: str = "ok", failure_reason: str | None = None, summary: dict | None = None) -> dict:
        if layer not in FAILURE_LAYERS:
            raise ValueError(f"unknown layer {layer}")
        entry = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "run_id": self.run_id, "w_type": self.w_type, "step": step,
                 "layer": layer, "status": status, "failure_reason": failure_reason, "elapsed_ms": int(elapsed_ms),
                 "model_calls": int(calls), "input_sha256": digest(input_obj) if input_obj is not None else None,
                 "output_sha256": digest(output_obj) if output_obj is not None else None,
                 "private_redacted": self.contains_private,
                 "payload": None if self.contains_private else summary}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(canonical(entry) + "\n")
        except OSError:
            pass  # 기록을 못 해도 검수 결과는 그대로 돌려준다.
        return entry


def read_traces(root, day: str | None = None) -> list[dict]:
    path = Path(root) / "traces" / ((day or time.strftime("%Y-%m-%d")) + ".jsonl")
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, ValueError):
        return []
