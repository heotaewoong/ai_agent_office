"""Explicit, paid, isolated A/B runner. Never opens the production workflow DB."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import time

from .editorial import prepare_source
from .providers import Provider, provider_for
from .store import Store, WorkflowError, canonical, digest


def compare(snapshot, output, *, budget_krw, acknowledge_paid=False):
    if not acknowledge_paid:
        raise WorkflowError("실모델 비교는 별도 비용 확인 뒤 명시적으로 실행하세요")
    if type(budget_krw) is not int or not 2 <= budget_krw <= 3000:
        raise WorkflowError("확인한 비교 예산은 총 2~3000원 범위로 지정하세요")
    from .editorial_graph import require_graph_runtime
    require_graph_runtime()
    model = snapshot.get("model")
    if provider_for(model) != "openai" or not os.environ.get("OPENAI_API_KEY"):
        raise WorkflowError("동일 OpenAI 모델과 실행 환경의 API 인증이 필요합니다. 다른 모델로 전환하지 않습니다")
    article = snapshot.get("article") or {}
    if not article.get("evidence"):
        raise WorkflowError("비교 전에 고정된 출처 근거를 준비하세요")
    output = Path(output)
    # A pre-existing report must never silently start another paid comparison.
    result = {"state": "running", "model": model, "material_hash": digest(snapshot), "total_cap_krw": budget_krw,
              "quality_improvement_proven": False, "runs": {}, "publication": False}
    with output.open("x", encoding="utf-8") as stream:
        stream.write(canonical(result))
    for engine in ("legacy", "langgraph"):
        with tempfile.TemporaryDirectory(prefix="office-editorial-ab-") as folder:
            store = Store(folder, budget_krw=budget_krw // 2)
            store.set_setting("work_window", {"status": "active", "authorized_end": (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat()})
            job = store.create_job(article, brief=snapshot.get("brief"))
            calls = []
            class TracedProvider(Provider):
                def generate(self, role, messages, schema, options=None):
                    calls.append({"role": role, "request_hash": digest({"messages": messages, "schema": schema, "options": options})})
                    return super().generate(role, messages, schema, options)
            provider = TracedProvider(store, model=model, job_id=job["id"])
            started = time.perf_counter()
            try:
                completed = prepare_source(store, job["id"], provider=provider, engine=engine)
                packet = completed["source_packet"]
                row = {"state": "completed", "packet": packet, "packet_hash": digest(packet),
                       "human_approved": False, "quality_scores_are_model_judgments": True}
            except WorkflowError:
                row = {"state": "blocked", "reason": "예산·근거·모델 결과를 확인하세요. 제공자 원문 오류는 저장하지 않았습니다"}
            row.update(elapsed_seconds=round(time.perf_counter() - started, 3), calls=calls, budget=store.budget())
            result["runs"][engine] = row
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["state"] = "completed" if all(r["state"] == "completed" for r in result["runs"].values()) else "blocked"
    result["interpretation"] = "동일 소재·모델·기준의 1건 비교다. 모델 출력의 변동과 실행기 효과를 구분해야 하며 자기평가 점수로 품질 향상을 확정하지 않는다."
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"state": result["state"], "report": str(output), "quality_improvement_proven": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--budget-krw", required=True, type=int)
    parser.add_argument("--acknowledge-paid-comparison", action="store_true")
    args = parser.parse_args()
    snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    print(json.dumps(compare(snapshot, args.output, budget_krw=args.budget_krw, acknowledge_paid=args.acknowledge_paid_comparison), ensure_ascii=False))


if __name__ == "__main__":
    main()
