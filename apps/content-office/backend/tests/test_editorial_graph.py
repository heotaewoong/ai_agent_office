import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

pytest.importorskip("langgraph.func")
pytest.importorskip("langgraph.checkpoint.sqlite")

from office.editorial import review_until_ready
from office.editorial_graph import run_editorial_graph
from office.store import WorkflowError


PACKET = {"title": "비교 소재", "body": "같은 원고와 같은 근거", "evidence": []}


class Provider:
    def __init__(self, blocked=False):
        self.blocked = blocked
        self.calls = []

    def generate(self, role, messages, schema, options=None):
        self.calls.append(copy.deepcopy((role, messages, schema, options)))
        if role == "gen":
            return copy.deepcopy(PACKET)
        if role == "refine":
            return {"title": "수정 원고", "body": "수정된 원고", "video": {"scenes": []}}
        return {"role": role, "score": 60 if self.blocked else 90, "passed": not self.blocked,
                "critical_issues": ["근거 오류"] if self.blocked else [], "minor_issues": [], "summary": "검토"}


def build(provider):
    packet = provider.generate("gen", [{"role": "user", "content": "동일 소재"}], {"type": "object"}, {"temperature": 0.6})
    return review_until_ready(packet, provider)


@pytest.mark.parametrize("blocked", [False, True])
def test_same_prompts_results_and_refine_limit(tmp_path, blocked):
    legacy, graph = Provider(blocked), Provider(blocked)
    expected = build(legacy)
    actual = run_editorial_graph(build, graph, checkpoint_path=tmp_path / "graph.db", identity={"material": "same", "model": "same"})
    assert actual == expected
    assert graph.calls == legacy.calls
    assert sum(c[0] == "refine" for c in graph.calls) == (2 if blocked else 0)


def test_completed_run_does_not_repeat_model_calls(tmp_path):
    provider = Provider()
    options = dict(checkpoint_path=tmp_path / "graph.db", identity={"model": "same"})
    first = run_editorial_graph(build, provider, **options)
    count = len(provider.calls)
    assert run_editorial_graph(build, provider, **options) == first
    assert len(provider.calls) == count


def test_unknown_model_result_is_not_blindly_retried(tmp_path):
    class Unknown(Provider):
        def generate(self, *args, **kwargs):
            self.calls.append("attempt")
            raise WorkflowError("모델 응답 불명")
    provider = Unknown()
    options = dict(checkpoint_path=tmp_path / "graph.db", identity={"model": "same"})
    with pytest.raises(WorkflowError, match="응답 불명"):
        run_editorial_graph(build, provider, **options)
    with pytest.raises(WorkflowError, match="대사") as unknown:
        run_editorial_graph(build, provider, **options)
    assert len(provider.calls) == 1
    assert "예약을 유지" in str(unknown.value) or "확인하지 못" in str(unknown.value)


def test_partial_checkpoint_replay_rejects_changed_prompt(tmp_path):
    provider = Provider()
    options = dict(checkpoint_path=tmp_path / "graph.db", identity={"source": "same"})
    def interrupted(p):
        p.generate("gen", [{"role": "user", "content": "old prompt"}], {}, {})
        raise RuntimeError("controlled interruption after completed task")
    with pytest.raises(RuntimeError):
        run_editorial_graph(interrupted, provider, **options)
    def changed(p):
        return p.generate("gen", [{"role": "user", "content": "changed prompt"}], {}, {})
    with pytest.raises(WorkflowError, match="프롬프트"):
        run_editorial_graph(changed, provider, **options)
    assert len(provider.calls) == 1


def test_changed_source_guard_blocks_even_cached_result(tmp_path):
    provider = Provider()
    options = dict(checkpoint_path=tmp_path / "graph.db", identity={"source_hash": "original"})
    run_editorial_graph(build, provider, **options)
    count = len(provider.calls)
    def guard():
        raise WorkflowError("원고 판본 변경")
    with pytest.raises(WorkflowError, match="판본"):
        run_editorial_graph(build, provider, check_current=guard, **options)
    assert len(provider.calls) == count


def test_different_model_or_source_gets_separate_run(tmp_path):
    provider = Provider()
    for identity in ({"model": "a", "source": "x"}, {"model": "b", "source": "x"}, {"model": "b", "source": "y"}):
        run_editorial_graph(build, provider, checkpoint_path=tmp_path / "graph.db", identity=identity)
    assert len(provider.calls) == 12


def test_external_tracing_is_not_enabled_implicitly(tmp_path, monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    provider = Provider()
    with pytest.raises(WorkflowError, match="외부 추적"):
        run_editorial_graph(build, provider, checkpoint_path=tmp_path / "graph.db", identity={})
    assert not provider.calls


def test_original_markdown_is_preserved(tmp_path):
    original = "저자의 원문  \n\n표와 공백을 그대로 둡니다."
    provider = Provider(blocked=True)
    def preserve(p):
        return review_until_ready(PACKET, p, original_markdown=original)
    result = run_editorial_graph(preserve, provider, checkpoint_path=tmp_path / "graph.db", identity={"source": original})
    assert result["body"] == original
    assert result["quality"]["status"] == "blocked"


def test_prepare_source_opt_in_preserves_legacy_contract_and_approvals(tmp_path):
    from office.editorial import prepare_source
    from office.store import Store
    article = {"id": "same-source", "title": "공식 뉴스 비교", "url": "https://example.com/news", "evidence": [{"id": "E1", "url": "https://example.com/news", "claim": "동일한 비교 근거"}]}
    results, traces = [], []
    for engine in ("legacy", "langgraph"):
        store = Store(tmp_path / engine)
        job = store.create_job(article)
        provider = Provider()
        result = prepare_source(store, job["id"], provider=provider, engine=engine)
        assert result["source_approval"] is None
        assert result["release_approval"] is None
        assert not store.tasks()
        results.append(result["source_packet"])
        traces.append(provider.calls)
    assert results[0] == results[1]
    assert traces[0] == traces[1]


def test_invalid_engine_and_missing_runtime_fail_before_source_work(tmp_path, monkeypatch):
    from office.editorial import prepare_source
    from office.store import Store
    from office import editorial_graph
    store = Store(tmp_path)
    with pytest.raises(WorkflowError, match="실행기"):
        prepare_source(store, "not-read", engine="unsupported")
    def unavailable():
        raise WorkflowError("의존성 없음")
    monkeypatch.setattr(editorial_graph, "require_graph_runtime", unavailable)
    with pytest.raises(WorkflowError, match="의존성"):
        prepare_source(store, "not-read", engine="langgraph")
    assert not store.jobs()
    assert store.budget()["spent_krw"] == 0


def test_real_process_death_and_new_process_resume(tmp_path):
    command = [sys.executable, "-m", "tests.test_editorial_graph", str(tmp_path)]
    failed = subprocess.run(command + ["crash"], capture_output=True, timeout=60)
    assert failed.returncode == 77, failed.stderr.decode(errors="replace")
    resumed = subprocess.run(command + ["resume"], capture_output=True, timeout=60)
    assert resumed.returncode == 0, resumed.stderr.decode(errors="replace")
    calls = (tmp_path / "calls.jsonl").read_text().splitlines()
    assert [json.loads(c)["role"] for c in calls] == ["gen", "critique", "eval", "korean"]
    assert json.loads((tmp_path / "result.json").read_text())["quality"]["status"] == "passed"


@pytest.mark.parametrize("engine,expected_entries", [("legacy", 5), ("graph", 4)])
def test_resume_with_real_provider_cache_does_not_overclaim_api_savings(tmp_path, engine, expected_entries):
    command = [sys.executable, "-m", "tests.test_editorial_graph", str(tmp_path), engine]
    first = subprocess.run(command + ["crash"], capture_output=True, timeout=60)
    assert first.returncode == 77, first.stderr.decode(errors="replace")
    second = subprocess.run(command + ["resume"], capture_output=True, timeout=60)
    assert second.returncode == 0, second.stderr.decode(errors="replace")
    assert len((tmp_path / "provider-entries.jsonl").read_text().splitlines()) == expected_entries
    assert len((tmp_path / "transport-calls.jsonl").read_text().splitlines()) == 4


def crash_probe(folder, mode):
    class Logged(Provider):
        def generate(self, role, *args, **kwargs):
            with (folder / "calls.jsonl").open("a") as stream:
                stream.write(json.dumps({"role": role}) + "\n")
            return super().generate(role, *args, **kwargs)
    def operation(provider):
        packet = provider.generate("gen", [{"role": "user", "content": "same"}], {}, {})
        if mode == "crash":
            os._exit(77)
        return review_until_ready(packet, provider)
    result = run_editorial_graph(operation, Logged(), checkpoint_path=folder / "graph.db", identity={"source": "same", "model": "same"})
    (folder / "result.json").write_text(json.dumps(result))


def cache_probe(folder, engine, mode):
    from office.providers import Provider as RealProvider
    from office.store import Store
    os.environ["OPENAI_API_KEY"] = "synthetic-only-never-sent"
    store = Store(folder / "provider-cache")
    active = {}
    class Response:
        status_code = 200
        def json(self):
            return {"id": "fixture", "usage": {"prompt_tokens": 10, "completion_tokens": 10}, "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(active["result"])}}]}
    def transport(*args, **kwargs):
        with (folder / "transport-calls.jsonl").open("a") as stream:
            stream.write(json.dumps({"role": active["role"]}) + "\n")
        return Response()
    class RealCached(RealProvider):
        def generate(self, role, messages, schema, options=None):
            with (folder / "provider-entries.jsonl").open("a") as stream:
                stream.write(json.dumps({"role": role}) + "\n")
            active.update(role=role, result=Provider().generate(role, messages, schema, options))
            if role == "korean":
                active["result"]["corrections"] = []
            return super().generate(role, messages, schema, options)
    provider = RealCached(store, model="gpt-5.4-mini", transport=transport)
    def operation(p):
        packet = p.generate("gen", [{"role": "user", "content": "same"}], {}, {"max_tokens": 100})
        if mode == "crash":
            os._exit(77)
        return review_until_ready(packet, p)
    if engine == "legacy":
        result = operation(provider)
    else:
        result = run_editorial_graph(operation, provider, checkpoint_path=folder / "graph.db", identity={"model": "gpt-5.4-mini", "source": "same"})
    (folder / "result.json").write_text(json.dumps(result))


if __name__ == "__main__":
    if len(sys.argv) == 4:
        cache_probe(Path(sys.argv[1]), sys.argv[2], sys.argv[3])
    else:
        crash_probe(Path(sys.argv[1]), sys.argv[2])
