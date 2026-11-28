"""v2 검수 반복을 LangGraph StateGraph로 돌린다.

한 회차는 검사 → (판정 또는 판정 생략) → 비교 → 멈춤 판단 → 고치기 순서로 흐르고, 고치기는 다시 검사로 돌아간다.
노드가 하는 일(검사, 판정, 고치기)은 harness.review_until_ready_v2가 넘겨 주고, 이 모듈은 흐름만 정한다.

- 체크포인터는 붙이지 않는다(checkpointer=False). 원고 실행기(editorial_graph)의 @entrypoint 안에서 돌 때도
  부모 체크포인터를 물려받지 않게 하려는 것이다. 유료 호출의 재개 보장은 editorial_call_intents 표가 맡는다.
- 원격 추적은 바깥 설정을 따른다. 공개 샘플 실험(public_sample)에서만 켜지고, 그때는 노드가 LangSmith에 단계로 보인다.
- 반복 상한은 refine_limit로 정하고, recursion_limit은 그 상한을 넘는 폭주를 막는 안전장치다.
"""
from __future__ import annotations

import warnings
from typing import Any, TypedDict

from .store import WorkflowError

GRAPH_VERSION = "review-graph-v1"
NODES = ("validate", "skip_judge", "judge", "compare", "decide", "refine")
STEPS_PER_ROUND = 5  # validate, judge 또는 skip_judge, compare, decide, refine


class ReviewState(TypedDict, total=False):
    packet: dict
    round_no: int
    refine_limit: int
    best: Any
    history: list
    outcome: dict
    allowed_sentences: list
    judge_calls: int
    skipped: int
    refines: int
    stop_reason: Any
    validation: Any
    judge: Any
    korean_rules: Any
    compared: Any


def route_after_validate(state: ReviewState) -> str:
    validation = state["validation"]
    if validation["blocking"]:
        return "compare"  # 무결성 문제는 모델이 고칠 수 없다. 판정과 수정을 부르지 않는다.
    if validation["issues"] and state["round_no"] < state["refine_limit"] - 1:
        return "skip_judge"  # 0원 규칙에서 걸렸으니 유료 판정 없이 바로 고친다. 마지막 고치기 한 번은 판정 지적용으로 남긴다.
    return "judge"


def route_after_compare(state: ReviewState) -> str:
    return "end" if state.get("stop_reason") else "decide"  # 되돌리기가 일어나면 바로 끝


def route_after_decide(state: ReviewState) -> str:
    return "end" if state.get("stop_reason") else "refine"


def recursion_limit(refine_limit: int) -> int:
    return STEPS_PER_ROUND * (refine_limit + 1) + 5


def build_review_graph(nodes: dict):
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError:
        raise WorkflowError("v2 검수 그래프에 필요한 LangGraph를 설치하세요. 다른 실행기로 자동 전환하지 않습니다") from None
    missing = [name for name in NODES if name not in nodes]
    if missing:
        raise WorkflowError(f"검수 그래프 노드가 빠졌어요: {', '.join(missing)}")
    graph = StateGraph(ReviewState)
    for name in NODES:
        graph.add_node(name, nodes[name])
    graph.add_edge(START, "validate")
    graph.add_conditional_edges("validate", route_after_validate, {"judge": "judge", "skip_judge": "skip_judge", "compare": "compare"})
    graph.add_edge("skip_judge", "compare")
    graph.add_edge("judge", "compare")
    graph.add_conditional_edges("compare", route_after_compare, {"decide": "decide", "end": END})
    graph.add_conditional_edges("decide", route_after_decide, {"refine": "refine", "end": END})
    graph.add_edge("refine", "validate")
    return graph.compile(checkpointer=False)


def run_review_graph(nodes: dict, state: ReviewState) -> ReviewState:
    if not isinstance(state.get("refine_limit"), int) or state["refine_limit"] < 0:
        raise WorkflowError("고치기 상한은 0 이상의 정수여야 해요")
    graph = build_review_graph(nodes)
    # 추적 설정은 바깥을 그대로 따른다. 원격 추적은 assert_no_remote_tracing이 공개 샘플에만 허용한다.
    # durability는 바깥 @entrypoint의 "sync"를 물려받으면 체크포인터 없는 그래프가 저장을 기다리다 멈춘다(langgraph 1.2).
    # 저장하지 않는 그래프이니 "exit"으로 못 박는다.
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="`durability` has no effect when no checkpointer is present.")
        return graph.invoke(state, {"recursion_limit": recursion_limit(state["refine_limit"])}, durability="exit")
