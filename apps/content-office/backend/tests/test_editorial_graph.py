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
        review = {"role": role, "score": 60 if self.blocked else 90, "passed": not self.blocked,
                  "critical_issues": ["근거 오류"] if self.blocked else [], "minor_issues": [], "summary": "검토"}
        if role == "korean":
            review["corrections"] = []
        else:
            review["content_checks"] = {"source_sufficient": True, "topic_matches": True,
                                        "reason": "합성 원문과 일치", "channel_topics": []}
        return review


def build(provider):
    packet = provider.generate("gen", [{"role": "user", "content": "동일 소재"}], {"type": "object"}, {"temperature": 0.6})
    return review_until_ready(packet, provider, checks_fn=lambda p: {"passed": True, "issues": []})


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


@pytest.mark.parametrize("key", ["LANGSMITH_TRACING", "LANGSMITH_TRACING_V2", "LANGCHAIN_TRACING", "LANGCHAIN_TRACING_V2"])
def test_external_tracing_is_not_enabled_implicitly(tmp_path, monkeypatch, key):
    monkeypatch.setenv(key, "true")
    provider = Provider()
    with pytest.raises(WorkflowError, match="외부 추적"):
        run_editorial_graph(build, provider, checkpoint_path=tmp_path / "graph.db", identity={})
    assert not provider.calls


def test_original_markdown_is_preserved(tmp_path):
    original = "저자의 원문  \n\n표와 공백을 그대로 둡니다."
    provider = Provider(blocked=True)
    def preserve(p):
        return review_until_ready(PACKET, p, original_markdown=original, checks_fn=lambda p: {"passed": False, "issues": ["fixture hard block"], "blocking": ["fixture hard block"]})
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
    for options in ({}, {"engine": "langgraph"}):
        with pytest.raises(WorkflowError, match="의존성"):
            prepare_source(store, "not-read", **options)
    assert not store.jobs()
    assert store.budget()["spent_krw"] == 0


@pytest.mark.parametrize("after_step", range(1, 13))
def test_real_process_death_after_each_generation_review_and_refine(tmp_path, after_step):
    command = [sys.executable, "-m", "tests.test_editorial_graph", str(tmp_path), "steps", str(after_step)]
    failed = subprocess.run(command + ["crash"], capture_output=True, timeout=60)
    assert failed.returncode == 77, failed.stderr.decode(errors="replace")
    resumed = subprocess.run(command + ["resume"], capture_output=True, timeout=60)
    assert resumed.returncode == 0, resumed.stderr.decode(errors="replace")
    calls = [json.loads(line)["role"] for line in (tmp_path / "calls.jsonl").read_text().splitlines()]
    assert calls == ["gen", "critique", "eval", "korean", "refine", "critique", "eval", "korean", "refine", "critique", "eval", "korean"]
    result = json.loads((tmp_path / "result.json").read_text())
    assert result == build(Provider(blocked=True))
    assert result["quality"]["refine_count"] == 2
    assert result["quality"]["status"] == "passed"
    assert result["quality"]["advisories"]["model_reviews_passed"] is False


@pytest.mark.parametrize("engine,expected_entries", [("legacy", 5), ("graph", 4)])
def test_resume_with_real_provider_cache_does_not_overclaim_api_savings(tmp_path, engine, expected_entries):
    command = [sys.executable, "-m", "tests.test_editorial_graph", str(tmp_path), engine]
    first = subprocess.run(command + ["crash"], capture_output=True, timeout=60)
    assert first.returncode == 77, first.stderr.decode(errors="replace")
    second = subprocess.run(command + ["resume"], capture_output=True, timeout=60)
    assert second.returncode == 0, second.stderr.decode(errors="replace")
    assert len((tmp_path / "provider-entries.jsonl").read_text().splitlines()) == expected_entries
    assert len((tmp_path / "transport-calls.jsonl").read_text().splitlines()) == 4



def test_unknown_result_cannot_be_retried_by_changing_run_identity(tmp_path):
    class Unknown(Provider):
        def generate(self, *args, **kwargs):
            self.calls.append("attempt")
            raise WorkflowError("model result unknown after dispatch")
    provider = Unknown()
    path = tmp_path / "graph.db"
    with pytest.raises(WorkflowError, match="unknown"):
        run_editorial_graph(build, provider, checkpoint_path=path, identity={"job_id": "same-job", "model": "first"})
    with pytest.raises(WorkflowError, match="대사|확인하지 못|불명"):
        run_editorial_graph(build, provider, checkpoint_path=path, identity={"job_id": "same-job", "model": "changed"})
    assert provider.calls == ["attempt"]


def test_brief_changed_during_experience_lookup_blocks_generation(tmp_path, monkeypatch):
    from office import improvements
    from office.editorial import prepare_source
    from office.store import Store
    from tests.test_agent_editorial import evidence_job, FullProvider
    store = Store(tmp_path)
    job = evidence_job(store)
    original = improvements.experience_context
    def changed(store, snapshot):
        result = original(store, snapshot)
        brief = copy.deepcopy(store.job(job["id"])["brief"])
        brief["problem"] = "changed while collecting context"
        store.update_job(job["id"], brief=brief)
        return result
    monkeypatch.setattr(improvements, "experience_context", changed)
    provider = FullProvider("AI 도구 비교")
    with pytest.raises(WorkflowError, match="변경|판본|맥락"):
        prepare_source(store, job["id"], provider=provider, engine="langgraph")
    assert provider.roles == []
    assert store.job(job["id"])["source_packet"] is None




def test_evaluate_only_keeps_existing_video_and_does_not_generate_or_refine(tmp_path):
    from office.editorial import prepare_source
    from office.store import Store
    from tests.test_agent_editorial import evidence_job, FullProvider
    store = Store(tmp_path)
    job = evidence_job(store)
    packet = FullProvider("AI 도구 비교")._packet()
    packet.update(audience=job["brief"], evidence=job["article"]["evidence"],
                  source_article_url=job["article"]["url"], quality={"status": "passed", "critical": False})
    original = store.save_source(job["id"], packet)
    provider = Provider(blocked=True)
    result = prepare_source(store, job["id"], provider=provider, evaluate_only=True)
    assert [call[0] for call in provider.calls] == ["critique", "eval", "korean"]
    assert result["source_packet"]["body"] == original["source_packet"]["body"]
    assert result["source_packet"]["video"] == original["source_packet"]["video"]
    assert result["source_packet"]["quality"]["refine_count"] == 0
    assert result["source_packet"]["quality"]["advisories"]["model_reviews_passed"] is False
    assert result["source_approval"] is None and result["release_approval"] is None
    assert not store.tasks()



def test_default_engine_reuses_completed_checkpoint_without_duplicate_editorial_events(tmp_path, monkeypatch):
    from office.editorial import prepare_source
    from office.store import Store
    from tests.test_agent_editorial import evidence_job, FullProvider
    store = Store(tmp_path)
    job = evidence_job(store)
    provider = FullProvider("AI 도구 비교")
    save = store.save_source
    def interrupted(*args, **kwargs):
        raise RuntimeError("controlled interruption before final source save")
    monkeypatch.setattr(store, "save_source", interrupted)
    with pytest.raises(RuntimeError, match="controlled interruption"):
        prepare_source(store, job["id"], provider=provider)
    before = [event for event in store.events(job["id"]) if event["kind"] == "editorial_role"]
    assert len(before) == 3
    assert provider.roles == ["gen", "critique", "eval", "korean"]
    monkeypatch.setattr(store, "save_source", save)
    result = prepare_source(store, job["id"], provider=provider)
    after = [event for event in store.events(job["id"]) if event["kind"] == "editorial_role"]
    assert after == before
    assert provider.roles == ["gen", "critique", "eval", "korean"]
    assert result["state"] == "source_review"
    assert result["source_approval"] is None and result["release_approval"] is None


def test_completed_subscription_checkpoint_cannot_bypass_api_only_policy(tmp_path, monkeypatch):
    from office.editorial import prepare_source
    from office.store import Store
    from tests.test_agent_editorial import evidence_job, FullProvider
    store = Store(tmp_path)
    job = evidence_job(store)
    provider = FullProvider("AI 도구 비교")
    provider.model = "codex-subscription-text"
    save = store.save_source
    def interrupted(*args, **kwargs):
        raise RuntimeError("controlled interruption before final source save")
    monkeypatch.setattr(store, "save_source", interrupted)
    with pytest.raises(RuntimeError, match="controlled interruption"):
        prepare_source(store, job["id"], provider=provider)
    calls = list(provider.roles)
    monkeypatch.setattr(store, "save_source", save)
    store.set_setting("content_api_only", True)
    with pytest.raises(WorkflowError, match="API"):
        prepare_source(store, job["id"], provider=provider)
    assert provider.roles == calls
    assert store.job(job["id"])["source_packet"] is None
    assert store.job(job["id"])["source_approval"] is None


SINGLE_SCHEMA = {"type": "object", "properties": {"passed": {"type": "boolean"}},
                 "required": ["passed"], "additionalProperties": False}


class SingleResponse:
    status_code = 200
    def json(self):
        return {"id": "synthetic", "usage": {"prompt_tokens": 10, "completion_tokens": 10},
                "choices": [{"finish_reason": "stop", "message": {"content": '{"passed":true}'}}]}


def single_call(provider):
    return provider.generate("eval", [{"role": "user", "content": "synthetic request"}], SINGLE_SCHEMA, {"max_tokens": 100})


@pytest.mark.parametrize("reason,pattern", [("budget", "예산"), ("price", "단가|요금"), ("window", "시간")])
def test_real_provider_preflight_rejection_can_resume_without_unknown_cost(tmp_path, monkeypatch, reason, pattern):
    from office.providers import Provider as RealProvider
    from office.store import Store
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-never-sent")
    store = Store(tmp_path / "state", budget_krw=0 if reason == "budget" else 10000)
    store.set_setting("price_valid_until", "2000-01-01T00:00:00+00:00" if reason == "price" else "2999-01-01T00:00:00+00:00")
    if reason == "window":
        store.set_setting("work_window", {"authorized_end": "2000-01-01T00:00:00+00:00"})
    calls = []
    def transport(*args, **kwargs):
        calls.append("sent")
        return SingleResponse()
    provider = RealProvider(store, model="gpt-5.4-mini", transport=transport)
    options = {"checkpoint_path": tmp_path / "graph.db", "identity": {"job_id": "preflight", "reason": reason}}
    for _ in range(2):
        with pytest.raises(WorkflowError, match=pattern):
            run_editorial_graph(single_call, provider, **options)
    assert calls == []
    with store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM costs").fetchone()[0] == 0
    store.set_setting("budget_cap", 10000)
    store.set_setting("price_valid_until", "2999-01-01T00:00:00+00:00")
    store.set_setting("work_window", {})
    assert run_editorial_graph(single_call, provider, **options) == {"passed": True}
    assert calls == ["sent"]
    assert store.budget()["reserved_krw"] == 0
    with store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM costs WHERE state='settled'").fetchone()[0] == 1



def test_provider_cached_result_stays_free_after_budget_and_price_close(tmp_path, monkeypatch):
    from office.providers import Provider as RealProvider
    from office.store import Store
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-never-sent")
    store = Store(tmp_path / "state")
    store.set_setting("price_valid_until", "2999-01-01T00:00:00+00:00")
    calls = []
    def transport(*args, **kwargs):
        calls.append("sent")
        return SingleResponse()
    provider = RealProvider(store, model="gpt-5.4-mini", transport=transport)
    path = tmp_path / "graph.db"
    assert run_editorial_graph(single_call, provider, checkpoint_path=path, identity={"run": "first"}) == {"passed": True}
    store.set_setting("budget_cap", 0)
    store.set_setting("price_valid_until", "2000-01-01T00:00:00+00:00")
    before = store.budget()
    assert run_editorial_graph(single_call, provider, checkpoint_path=path, identity={"run": "second"}) == {"passed": True}
    assert calls == ["sent"] and store.budget() == before


def test_real_provider_unknown_response_keeps_reservation_and_never_retransmits(tmp_path, monkeypatch):
    import requests
    from office.providers import Provider as RealProvider
    from office.store import Store
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-never-sent")
    store = Store(tmp_path / "state")
    store.set_setting("price_valid_until", "2999-01-01T00:00:00+00:00")
    calls = []
    def lost(*args, **kwargs):
        calls.append("sent")
        raise requests.ConnectionError("synthetic response lost")
    provider = RealProvider(store, model="gpt-5.4-mini", transport=lost)
    options = {"checkpoint_path": tmp_path / "graph.db", "identity": {"job_id": "unknown"}}
    with pytest.raises(WorkflowError, match="예약|확인하지 못"):
        run_editorial_graph(single_call, provider, **options)
    before = store.budget()
    with pytest.raises(WorkflowError, match="대사"):
        run_editorial_graph(single_call, provider, **options)
    assert calls == ["sent"]
    assert store.budget() == before and before["reserved_krw"] > 0
    with store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM costs WHERE state='unknown'").fetchone()[0] == 1


def test_process_death_after_dispatch_preserves_reserved_cost_and_blocks_replay(tmp_path):
    from office.store import Store
    command = [sys.executable, "-m", "tests.test_editorial_graph", str(tmp_path), "transport"]
    failed = subprocess.run(command + ["crash"], capture_output=True, timeout=60)
    assert failed.returncode == 79, failed.stderr.decode(errors="replace")
    store = Store(tmp_path / "provider-state")
    before = store.budget()
    assert before["reserved_krw"] > 0 and before["spent_krw"] == 0
    resumed = subprocess.run(command + ["resume"], capture_output=True, timeout=60)
    assert resumed.returncode == 0, resumed.stderr.decode(errors="replace")
    assert (tmp_path / "transport-calls.jsonl").read_text().splitlines() == ['{"sent": true}']
    assert Store(tmp_path / "provider-state").budget() == before
    assert not (tmp_path / "result.json").exists()
    assert "대사" in (tmp_path / "blocked.txt").read_text(encoding="utf-8")


def boundary_probe(folder, after_step, mode):
    class Logged(Provider):
        def generate(self, role, *args, **kwargs):
            with (folder / "calls.jsonl").open("a") as stream:
                stream.write(json.dumps({"role": role}) + "\n")
            return super().generate(role, *args, **kwargs)
    def operation(provider):
        class Boundary:
            def __init__(self):
                self.step = 0
            def generate(self, *args, **kwargs):
                result = provider.generate(*args, **kwargs)
                self.step += 1
                if mode == "crash" and self.step == after_step:
                    os._exit(77)
                return result
        return build(Boundary())
    result = run_editorial_graph(operation, Logged(blocked=True), checkpoint_path=folder / "graph.db", identity={"job_id": "all-steps", "source": "same"})
    (folder / "result.json").write_text(json.dumps(result))


def transport_death_probe(folder, mode):
    from office.providers import Provider as RealProvider
    from office.store import Store
    os.environ["OPENAI_API_KEY"] = "synthetic-never-sent"
    store = Store(folder / "provider-state")
    store.set_setting("price_valid_until", "2999-01-01T00:00:00+00:00")
    def transport(*args, **kwargs):
        with (folder / "transport-calls.jsonl").open("a") as stream:
            stream.write(json.dumps({"sent": True}) + "\n")
            stream.flush()
        if mode == "crash":
            os._exit(79)
        raise AssertionError("uncertain transmission must never be repeated")
    provider = RealProvider(store, model="gpt-5.4-mini", transport=transport)
    try:
        result = run_editorial_graph(single_call, provider, checkpoint_path=folder / "graph.db", identity={"job_id": "uncertain-call"})
    except WorkflowError as error:
        if mode != "resume":
            raise
        (folder / "blocked.txt").write_text(str(error), encoding="utf-8")
    else:
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
        return review_until_ready(packet, p, checks_fn=lambda p: {"passed": True, "issues": []})
    if engine == "legacy":
        result = operation(provider)
    else:
        result = run_editorial_graph(operation, provider, checkpoint_path=folder / "graph.db", identity={"model": "gpt-5.4-mini", "source": "same"})
    (folder / "result.json").write_text(json.dumps(result))


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[2] == "steps":
        boundary_probe(Path(sys.argv[1]), int(sys.argv[3]), sys.argv[4])
    elif len(sys.argv) == 4 and sys.argv[2] == "transport":
        transport_death_probe(Path(sys.argv[1]), sys.argv[3])
    elif len(sys.argv) == 4:
        cache_probe(Path(sys.argv[1]), sys.argv[2], sys.argv[3])
    else:
        raise ValueError("unknown synthetic probe arguments")


def test_parent_tracing_context_is_disabled_inside_editorial_graph(tmp_path):
    from langsmith.run_helpers import tracing_context
    from langsmith.utils import tracing_is_enabled
    def operation(provider):
        assert tracing_is_enabled() is False
        return {"local": True}
    with tracing_context(enabled=True):
        assert run_editorial_graph(operation, Provider(), checkpoint_path=tmp_path / "graph.db", identity={}) == {"local": True}
