"""legacy 검수와 v2_harness 검수를 같은 원고로 나란히 돌려 비교한다(실행기를 바꾸기 전 확인용).

- 유료 모델을 부르므로 acknowledge_paid=True 없이는 돌지 않는다. 사람이 승인한 뒤에만 쓴다.
  비용은 넘겨받은 Provider의 작업 예산 장부와 상한(set_job_budget)을 그대로 따른다. 이 모듈이 따로 한도를 늘리지 않는다.
- 원고를 새로 만들지 않고, 이미 있는 원고(source_packet) 하나를 두 검수기에 각각 넣는다. 운영 작업과 승인은 바꾸지 않는다.
- 결과: 모델 호출 수, 판정 호출 절약, 고친 횟수, 통과 여부, 되돌림 여부. 상태 폴더의 evals/reports에 JSON으로 남긴다.
"""
from __future__ import annotations

import copy
import json
import time
from pathlib import Path

from .store import WorkflowError


class CountingProvider:
    def __init__(self, inner):
        self.inner, self.roles = inner, []
        self.model, self.judge_model = getattr(inner, "model", None), getattr(inner, "judge_model", None)

    def generate(self, role, messages, schema, options=None):
        self.roles.append(role)
        return self.inner.generate(role, messages, schema, options)


def compare_editorial_engines(packet: dict, *, legacy_provider, harness_provider, acknowledge_paid: bool = False,
                              root=None, w_type=None, checks_fn=None, brief=None) -> dict:
    if acknowledge_paid is not True:
        raise WorkflowError("비교는 유료 모델을 부릅니다. acknowledge_paid=True로 승인한 뒤에만 실행합니다")
    from .editorial import review_until_ready
    from .harness import review_until_ready_v2

    legacy, harness = CountingProvider(legacy_provider), CountingProvider(harness_provider)
    started = time.monotonic()
    old = review_until_ready(copy.deepcopy(packet), legacy, checks_fn=checks_fn, brief=brief)
    middle = time.monotonic()
    new = review_until_ready_v2(copy.deepcopy(packet), harness, checks_fn=checks_fn, brief=brief, w_type=w_type,
                                gen_model=harness.model, judge_model=harness.judge_model)
    finished = time.monotonic()
    report = {
        "legacy": {"calls": len(legacy.roles), "roles": legacy.roles, "status": old["quality"]["status"],
                   "model_reviews_passed": old["quality"]["advisories"]["model_reviews_passed"], "refines": old["quality"]["refine_count"],
                   "seconds": round(middle - started, 1)},
        "v2_harness": {"calls": len(harness.roles), "roles": harness.roles, "status": new["quality"]["status"],
                       "model_reviews_passed": new["quality"]["advisories"]["model_reviews_passed"],
                       "refines": new["quality"]["refine_count"], "rolled_back": new["quality"]["harness"]["rolled_back"],
                       "judge_skipped_rounds": new["quality"]["harness"]["judge_skipped_rounds"], "seconds": round(finished - middle, 1)},
    }
    report["calls_saved"] = report["legacy"]["calls"] - report["v2_harness"]["calls"]
    if root is not None:
        path = Path(root) / "evals" / "reports" / f"compare-{time.strftime('%Y%m%dT%H%M%S')}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report["path"] = str(path)
    return report
