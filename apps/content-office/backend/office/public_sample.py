"""외부 추적(LangSmith) 연결 실험에 쓰는 공개 샘플.

운영 원고와 개인 자료(책, 사용자 원고, 개인 DB)는 원격 추적으로 보내지 않는다. 연결 실험은 이 폴더에
커밋한 공개 샘플로만 하고, 내용이 파일과 한 글자라도 다르면 원격 추적을 허락하지 않는다.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

from .store import WorkflowError, canonical, digest

PUBLIC_SAMPLE_DIR = Path(__file__).with_name("public_samples")
PROBE_PROJECT = "heobrain-public-probe"
_PRIVATE_MARKERS = ("book", "private", "personal", "original")


def _checked_in(name: str) -> dict:
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise WorkflowError("공개 샘플 이름이 올바르지 않습니다")
    path = PUBLIC_SAMPLE_DIR / (name + ".json")
    if not path.is_file():
        raise WorkflowError("커밋된 공개 샘플이 아닙니다")
    return json.loads(path.read_text(encoding="utf-8"))


def load_public_sample(name: str = "langsmith_probe") -> dict:
    sample = _checked_in(name)
    require_public_sample(sample)
    return copy.deepcopy(sample)


def require_public_sample(sample) -> None:
    """원격 추적을 허락하기 전 마지막 확인. 커밋된 파일과 같고, 개인 자료 흔적이 없어야 한다."""
    if not isinstance(sample, dict) or sample.get("public") is not True or not isinstance(sample.get("packet"), dict):
        raise WorkflowError("공개 샘플만 외부 추적으로 보낼 수 있습니다")
    if digest(sample) != digest(_checked_in(sample.get("name", ""))):
        raise WorkflowError("공개 샘플 파일과 내용이 다릅니다. 커밋된 샘플만 외부 추적으로 보낼 수 있습니다")
    packet = sample["packet"]
    if packet.get("preserve_original") or packet.get("source_input_hash"):
        raise WorkflowError("사용자 원고 보존 모드는 외부 추적으로 보낼 수 없습니다")
    for item in packet.get("evidence", []):
        url, kind = str(item.get("url", "")), str(item.get("source_kind", "")).lower()
        if not url.startswith("https://") or any(marker in kind for marker in _PRIVATE_MARKERS):
            raise WorkflowError("공개 주소가 아닌 근거가 있어 외부 추적으로 보낼 수 없습니다")


class ProbeProvider:
    """0원 가짜 모델. 판정은 정해진 결과를 돌려주고, 고치기는 원고를 그대로 돌려준다."""
    model = "probe-gen"
    judge_model = "probe-judge"

    def __init__(self, sample: dict):
        self.packet, self.calls = sample["packet"], []

    def generate(self, role, messages, schema, options=None):
        from .harness import BINARY_AXES
        self.calls.append(role)
        if role == "judge":
            return {"axes": {axis: {"passed": True, "reason": "공개 샘플 연결 실험"} for axis in BINARY_AXES},
                    "ungrounded_sentences": [], "korean_corrections": [],
                    "content_checks": {"source_sufficient": True, "topic_matches": True, "reason": "공개 샘플", "channel_topics": []}}
        return {key: copy.deepcopy(self.packet[key]) for key in ("title", "body", "video")}


def run_public_probe(*, send: bool = False, name: str = "langsmith_probe", project: str = PROBE_PROJECT) -> dict:
    """공개 샘플로 v2 검수를 한 번 돌린다. send=False면 아무것도 밖으로 보내지 않는다."""
    from .harness import review_until_ready_v2
    sample = load_public_sample(name)
    provider = ProbeProvider(sample)

    def review():
        return review_until_ready_v2(sample["packet"], provider, gen_model=provider.model, judge_model=provider.judge_model,
                                     w_type=sample.get("w_type"), public_sample=sample)

    if not send:
        from langsmith.run_helpers import tracing_context
        with tracing_context(enabled=False):
            result = review()
        return {"sent": False, "calls": provider.calls, "status": result["quality"]["status"], "project": None}
    if not os.environ.get("LANGSMITH_API_KEY"):
        raise WorkflowError("LANGSMITH_API_KEY가 없습니다. 키를 넣은 셸에서만 --send로 실행하세요")
    from langsmith import traceable
    from langsmith.run_helpers import tracing_context
    from langsmith.run_trees import get_cached_client
    os.environ["LANGSMITH_TRACING"] = "true"  # 운영 가드가 이 값을 보고 공개 샘플 확인을 요구한다.
    raw = provider.generate
    provider.generate = traceable(name="probe_model_call", run_type="llm")(raw)
    root = traceable(name="heobrain_public_probe", run_type="chain", metadata={"sample": name, "sample_sha256": digest(sample)})(review)
    with tracing_context(enabled=True, project_name=project):
        result = root()
    get_cached_client().flush()
    return {"sent": True, "calls": provider.calls, "status": result["quality"]["status"], "project": project}
