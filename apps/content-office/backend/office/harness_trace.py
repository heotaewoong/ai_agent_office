"""검수 하네스(v2_harness)의 단계별 기록. 로컬 JSONL에만 쓰고 외부 추적 서비스로 보내지 않는다.

- 한 줄 = 한 단계(validate, judge, refine, rollback). 입력과 출력은 해시만 남기고, 개인 자료(책 근거, 원문 보존 W4)가
  섞인 실행은 내용 요약(payload)을 남기지 않는다.
- layer는 실패가 어느 층에서 났는지 가르는 분류다(설계 v2 6장 '재는 것'과 같은 목적).
- 2026-11-27 추가: 줄마다 trace_id(원고 1건), span_id(그 실행 안의 순번), parent_span, 골든셋 카드 표지(labels:
  card_id, card_sha, trial)를 남긴다. meta는 코드가 정한 식별자(축 이름, 규칙 이름, 근거 ID, 모델 이름, 해시, 건수)만
  담으므로 개인 자료 실행에서도 지우지 않는다. 문장이나 원문은 meta에 넣지 않는다(_safe_meta가 길이와 형태를 막는다).
- 토큰과 원화는 events의 model_completed에 있다. editorial_role 이벤트의 editorial_run 앞 16자가 이 파일의 run_id와 같아서
  두 기록을 이어 볼 수 있다. 자동 재시도는 금지라 단계마다 재시도 횟수는 0이다.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .store import WorkflowError, canonical, digest

FAILURE_LAYERS = frozenset({"input_contract", "retrieval", "ranking", "query", "generation", "validate", "eval_judge", "refine", "guardrail"})
# 원고 검수 한 번이 끝난 이유. 앞의 일곱 개는 검수 함수 안에서, 뒤의 둘은 예외로 끝날 때 정해진다(예외는 그대로 다시 올린다).
STOP_REASONS = ("PASS", "REPAIRED", "STALLED", "ROLLED_BACK", "HOLD", "CAP_REACHED", "POLICY_BLOCKED", "BUDGET_EXHAUSTED", "FAILED")
LABEL_KEYS = ("card_id", "card_sha", "trial")
_META_TEXT_LIMIT = 120
_REMOTE_TRACING = ("LANGCHAIN_TRACING_V2", "LANGCHAIN_TRACING", "LANGSMITH_TRACING_V2", "LANGSMITH_TRACING")


def assert_no_remote_tracing(*, public_sample=None) -> None:
    """원격 추적이 켜져 있으면 검수를 시작하지 않는다(원고와 개인 자료가 밖으로 나가지 않게).

    예외는 하나: 저장소에 커밋한 공개 샘플(office/public_samples)과 글자까지 같은 입력으로 하는 연결 실험이다.
    """
    if any(os.environ.get(key, "").strip().lower() in ("1", "true", "yes") for key in _REMOTE_TRACING):
        if public_sample is not None:
            from .public_sample import require_public_sample
            require_public_sample(public_sample)
            return
        raise WorkflowError("검수 기록의 외부 추적 전송은 승인되지 않았습니다. 추적 환경 변수를 끄고 다시 실행하세요")


def _safe_meta(value, depth=0):
    """meta에는 식별자와 건수만 남긴다. 긴 문자열(문장일 수 있음)은 버리고, 깊은 구조는 자른다."""
    if value is None or isinstance(value, bool) or isinstance(value, int) or isinstance(value, float):
        return value
    if isinstance(value, str):
        return value if len(value) <= _META_TEXT_LIMIT else None
    if depth >= 3:
        return None
    if isinstance(value, (list, tuple)):
        return [_safe_meta(item, depth + 1) for item in list(value)[:50]]
    if isinstance(value, dict):
        return {str(key)[:_META_TEXT_LIMIT]: _safe_meta(item, depth + 1) for key, item in list(value.items())[:50]}
    return None


class TraceRecorder:
    def __init__(self, root, run_id: str, *, w_type: str | None = None, contains_private: bool = False, labels: dict | None = None):
        self.path = Path(root) / "traces" / (time.strftime("%Y-%m-%d") + ".jsonl")
        self.run_id, self.w_type, self.contains_private = run_id, w_type, contains_private
        self.labels = {key: _safe_meta((labels or {}).get(key)) for key in LABEL_KEYS} if labels else None
        self._sequence = 0

    def record(self, *, step: str, layer: str, input_obj=None, output_obj=None, elapsed_ms: int = 0, calls: int = 0,
               status: str = "ok", failure_reason: str | None = None, summary: dict | None = None, meta: dict | None = None,
               parent_span: str | None = None) -> dict:
        if layer not in FAILURE_LAYERS:
            raise ValueError(f"unknown layer {layer}")
        self._sequence += 1
        entry = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "run_id": self.run_id, "trace_id": self.run_id,
                 "span_id": f"{self.run_id}.{self._sequence}", "parent_span": parent_span, "labels": self.labels,
                 "w_type": self.w_type, "step": step,
                 "layer": layer, "status": status, "failure_reason": failure_reason, "elapsed_ms": int(elapsed_ms),
                 "model_calls": int(calls), "retry_count": 0, "input_sha256": digest(input_obj) if input_obj is not None else None,
                 "output_sha256": digest(output_obj) if output_obj is not None else None,
                 "private_redacted": self.contains_private,
                 "meta": _safe_meta(meta) if meta else None,
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
