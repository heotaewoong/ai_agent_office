"""v2 검수 반복을 StateGraph로 옮긴 뒤에도 흐름과 결과가 그대로인지 확인한다."""
import pytest

from office.harness_trace import TraceRecorder, read_traces
from office.review_graph import NODES, build_review_graph, recursion_limit, route_after_validate, run_review_graph
from office.store import WorkflowError
from test_harness import Stub, good_body, packet, run, verdict


def test_graph_has_one_round_as_nodes_and_loops_back_from_refine():
    graph = build_review_graph({name: (lambda state: {}) for name in NODES}).get_graph()
    edges = {(edge.source, edge.target) for edge in graph.edges}
    assert edges == {("__start__", "validate"), ("validate", "judge"), ("validate", "skip_judge"), ("validate", "compare"),
                     ("skip_judge", "compare"), ("judge", "compare"), ("compare", "decide"), ("compare", "__end__"),
                     ("decide", "refine"), ("decide", "__end__"), ("refine", "validate")}
    assert "refine --> validate" in graph.draw_mermaid().replace(";", "")


def test_routing_matches_the_old_loop():
    state = {"round_no": 0, "refine_limit": 2}
    assert route_after_validate({**state, "validation": {"blocking": ["무결성"], "issues": ["x"]}}) == "compare"
    assert route_after_validate({**state, "validation": {"blocking": [], "issues": ["x"]}}) == "skip_judge"
    # 마지막 고치기 한 번은 판정 지적용으로 남긴다: 상한 직전 회차에서는 규칙에 걸려도 판정을 부른다.
    assert route_after_validate({**state, "round_no": 1, "validation": {"blocking": [], "issues": ["x"]}}) == "judge"
    assert route_after_validate({**state, "validation": {"blocking": [], "issues": []}}) == "judge"
    assert recursion_limit(2) > 5 * 3


def test_refine_limit_must_be_a_non_negative_integer():
    with pytest.raises(WorkflowError):
        run_review_graph({}, {"refine_limit": -1})


def test_review_runs_the_same_inside_the_editorial_entrypoint():
    # 원고 실행기는 @entrypoint 안에서 검수를 부른다. 검수 그래프는 부모 체크포인터를 물려받지 않고, 결과와 호출 순서가 같아야 한다.
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.func import entrypoint, task

    def stub():
        return Stub(judges=[verdict(completeness="비교축이 빠짐"), verdict()], refines=[good_body()])

    alone = stub()
    expected = run(alone, packet(), w_type="W3")

    nested = stub()

    @task
    def model_call(role, messages, schema, options):
        return nested.generate(role, messages, schema, options)

    class TaskProvider(Stub):
        def generate(self, role, messages, schema, options=None):
            return model_call(role, messages, schema, options).result()

    @entrypoint(checkpointer=InMemorySaver())
    def editorial_run(_):
        return run(TaskProvider(), packet(), w_type="W3")

    result = editorial_run.invoke({"job": "j"}, {"configurable": {"thread_id": "t"}})
    assert nested.calls == alone.calls == ["judge", "refine", "judge"]
    assert result["quality"]["harness"]["stop_reason"] == expected["quality"]["harness"]["stop_reason"] == "REPAIRED"
    assert result["quality"]["history"] == expected["quality"]["history"]
    assert result["body"] == expected["body"]


def test_failure_inside_the_graph_keeps_progress_in_the_trace(tmp_path):
    class RefineFails(Stub):
        def generate(self, role, messages, schema, options=None):
            if role == "refine":
                raise RuntimeError("전송 실패")
            return super().generate(role, messages, schema, options)

    trace = TraceRecorder(tmp_path, "run-f", w_type="W3")
    with pytest.raises(RuntimeError, match="전송 실패"):
        run(RefineFails(judges=[verdict(accuracy="숫자가 원문과 다름")]), packet(), w_type="W3", trace=trace)
    end = read_traces(tmp_path)[-1]
    assert end["step"] == "run:end" and end["status"] == "FAILED"
    assert end["meta"]["judge_calls"] == 1 and end["meta"]["rounds"] == 1 and end["meta"]["refine_calls"] == 0
