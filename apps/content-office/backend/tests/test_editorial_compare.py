import json

import pytest

pytest.importorskip("langgraph.checkpoint.sqlite")

from office import editorial_compare as experiment
from office.store import WorkflowError


def test_live_comparison_requires_explicit_cost_acknowledgement(tmp_path):
    output = tmp_path / "result.json"
    with pytest.raises(WorkflowError, match="명시"):
        experiment.compare({}, output, budget_krw=3000)
    assert not output.exists()


def test_isolated_pair_uses_same_material_and_caps_total_budget(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-only")
    class FakeProvider:
        def __init__(self, *args, **kwargs):
            pass
    monkeypatch.setattr(experiment, "Provider", FakeProvider)
    seen = []
    snapshot = {"model": "gpt-5.4-mini", "article": {"id": "same", "title": "비교", "url": "https://example.com/news", "evidence": [{"id": "E1", "claim": "동일 사실"}]}}
    def prepare(store, job_id, provider, engine):
        seen.append((engine, store.job(job_id)["article"], store.budget()["cap_krw"]))
        return {"source_packet": {"body": "동일 응답", "quality": {"status": "passed"}}}
    monkeypatch.setattr(experiment, "prepare_source", prepare)
    output = tmp_path / "result.json"
    experiment.compare(snapshot, output, budget_krw=3000, acknowledge_paid=True)
    assert [s[0] for s in seen] == ["legacy", "langgraph"]
    assert seen[0][1] == seen[1][1]
    assert sum(s[2] for s in seen) == 3000
    result = json.loads(output.read_text(encoding="utf-8"))
    assert not result["quality_improvement_proven"]
    assert not result["publication"]
    with pytest.raises(FileExistsError):
        experiment.compare(snapshot, output, budget_krw=3000, acknowledge_paid=True)
