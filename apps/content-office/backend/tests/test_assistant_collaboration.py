import copy

import pytest

from office.assistant_requests import BridgeError, project_collaboration
from office.assistant_request_protocol import TENANT

RID = "aa3a151d-72e8-4abf-b09d-10d416279c41"
KEY = "office-world:" + RID


def node(ident, suffix, actor, run_id, base_key=KEY):
    return {"task": {"id": ident, "idempotency_key": base_key + suffix, "status": "done", "tenant": TENANT,
                     "assignee": actor, "title": "내부 단계", "created_at": 1, "current_run_id": None},
            "runs": [{"id": run_id, "task_id": ident, "profile": actor, "status": "done",
                      "outcome": "completed", "ended_at": run_id * 10, "summary": actor + " 실행 결과"}],
            "events": [{"id": run_id * 10, "task_id": ident, "run_id": run_id,
                        "kind": "completed", "created_at": run_id * 10}],
            "links": {"parents": [], "children": []}}


def edges(nodes, links):
    for data in nodes.values():
        data["links"] = {"parents": [], "children": []}
    for parent, child in links:
        nodes[parent]["links"]["children"].append(child)
        nodes[child]["links"]["parents"].append(parent)


def collaboration(parallel=False, request_id=RID, root_id="t_root"):
    key = "office-world:" + request_id
    nodes = {root_id: node(root_id, "", "lumi", 1, key)}
    works = [("t_worka", ":work-a", "ethan"), ("t_workb", ":work-b", "noah")] if parallel else [("t_work", ":work", "ethan")]
    for index, (ident, suffix, actor) in enumerate(works, 2):
        nodes[ident] = node(ident, suffix, actor, index, key)
    nodes["t_verify"] = node("t_verify", ":verify", "ada", 4, key)
    nodes["t_final"] = node("t_final", ":final", "lumi", 5, key)
    links = [(root_id, ident) for ident, _, _ in works]
    links += [(ident, "t_verify") for ident, _, _ in works]
    links += [(ident, "t_final") for ident, _, _ in works] + [("t_verify", "t_final")]
    edges(nodes, links)
    return nodes


def render(nodes):
    class Native:
        def task(self, ident): return copy.deepcopy(nodes[ident])
    return project_collaboration(Native(), {"request_id": RID, "native_task_id": "t_root", "native_key": KEY},
                                 copy.deepcopy(nodes["t_root"]))


@pytest.mark.parametrize("parallel", [False, True])
def test_only_exact_completed_four_or_five_card_team_has_a_verified_final_report(parallel):
    result = render(collaboration(parallel))
    assert result["status"] == "completed"
    assert result["report"] == {"summary": "lumi 실행 결과", "verified": True,
                                 "task_id": "t_final", "run_id": 5, "event_id": 50}
    assert {event["assignee"] for event in result["events"]} == ({"lumi", "ethan", "ada", "noah"} if parallel else {"lumi", "ethan", "ada"})


def test_intake_done_alone_never_becomes_a_collaboration_report():
    result = render({"t_root": node("t_root", "", "lumi", 1)})
    assert result["status"] == "blocked"
    assert result["error"]["code"] == "collaboration_incomplete"
    assert result["report"] is None


@pytest.mark.parametrize("actor", ["lumi", "ethan"])
def test_verifier_must_be_a_different_actual_role_from_lumi_and_all_workers(actor):
    nodes = collaboration()
    nodes["t_verify"]["task"]["assignee"] = actor
    nodes["t_verify"]["runs"][0]["profile"] = actor
    result = render(nodes)
    assert result["status"] == "blocked" and result["report"] is None
    assert result["error"]["code"] == "native_collaboration_invalid"


def test_missing_final_or_an_orphan_work_cannot_be_inferred_from_other_done_cards():
    nodes = collaboration()
    del nodes["t_final"]
    for data in nodes.values():
        data["links"]["children"] = [ident for ident in data["links"]["children"] if ident != "t_final"]
    result = render(nodes)
    assert result["report"] is None and result["status"] == "blocked"
    assert result["error"]["code"] == "collaboration_incomplete"
    nodes = collaboration(True)
    nodes["t_root"]["links"]["children"].remove("t_workb")
    result = render(nodes)
    assert result["report"] is None and result["status"] == "blocked"


@pytest.mark.parametrize("change", ["cross_key", "wrong_final", "duplicate_key", "wrong_parent"])
def test_noncanonical_keys_duplicates_and_parent_sets_are_not_verified(change):
    nodes = collaboration()
    if change == "cross_key": nodes["t_work"]["task"]["idempotency_key"] = "office-world:another:work"
    if change == "wrong_final": nodes["t_final"]["task"]["idempotency_key"] = KEY + ":latest-lumi"
    if change == "duplicate_key":
        nodes["t_duplicate"] = node("t_duplicate", ":verify", "ada", 6)
        nodes["t_root"]["links"]["children"].append("t_duplicate")
        nodes["t_duplicate"]["links"]["parents"] = ["t_root"]
    if change == "wrong_parent":
        nodes["t_final"]["links"]["parents"].remove("t_work")
        nodes["t_work"]["links"]["children"].remove("t_final")
    result = render(nodes)
    assert result["report"] is None and result["status"] == "blocked"
    assert result["error"]["code"] == "native_collaboration_invalid"


def test_every_role_needs_its_native_run_event_but_only_final_summary_is_displayed():
    nodes = collaboration()
    nodes["t_work"]["runs"][0]["summary"] = "내부 /home/private/work.md"
    assert render(nodes)["status"] == "completed"
    nodes["t_work"]["events"] = []
    assert render(nodes)["report"] is None
    nodes = collaboration()
    nodes["t_final"]["runs"][0]["summary"] = "내부 /home/private/final.md"
    result = render(nodes)
    assert result["status"] == "blocked" and result["report"] is None
    assert result["error"]["code"] == "report_redaction_required"


def test_stale_final_receipt_before_another_role_completion_is_not_a_final_report():
    nodes = collaboration()
    nodes["t_final"]["events"][0]["id"] = 35
    result = render(nodes)
    assert result["report"] is None and result["status"] == "blocked"
    assert result["error"]["code"] == "native_collaboration_invalid"


def test_full_graph_detects_a_cycle_hidden_by_shared_node_visitation():
    nodes = {ident: node(ident, ":" + ident, "lumi", index) for index, ident in enumerate(["t_root", "t_b", "t_c", "t_d"], 1)}
    nodes["t_root"]["task"]["idempotency_key"] = KEY
    edges(nodes, [("t_root", "t_b"), ("t_root", "t_c"), ("t_b", "t_d"), ("t_c", "t_d"), ("t_d", "t_c")])
    with pytest.raises(BridgeError) as caught: render(nodes)
    assert caught.value.code == "native_graph_invalid"


def test_full_graph_longest_path_is_checked_after_a_shorter_shared_path():
    nodes = {ident: node(ident, ":" + ident, "lumi", index) for index, ident in enumerate(["t_root", "t_a", "t_b", "t_c", "t_d"], 1)}
    nodes["t_root"]["task"]["idempotency_key"] = KEY
    edges(nodes, [("t_root", "t_a"), ("t_root", "t_c"), ("t_a", "t_b"), ("t_b", "t_c"), ("t_c", "t_d")])
    with pytest.raises(BridgeError) as caught: render(nodes)
    assert caught.value.code == "native_graph_limit"
