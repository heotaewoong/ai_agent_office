"""오피스 월드 공간 투영. 제목·상태·라벨·담당 이름만 담고 본문·근거·경로·비밀값은 넣지 않는다."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

STAGES = [
    {"id": "inbox", "name": "오늘의 뉴스", "approval": "⓪ 기획 선택", "color": "#f2a444", "view": "news"},
    {"id": "scripts", "name": "원고 작업실", "approval": "① 원고 승인", "color": "#4f8df7", "view": "studio"},
    {"id": "creative", "name": "제작 스튜디오", "approval": "영상 검토", "color": "#8b6cf0", "view": "delivery"},
    {"id": "outbox", "name": "제작·출고함", "approval": "② 출고 승인 · ③ 회차", "color": "#3ecfb2", "view": "delivery"},
    {"id": "ops", "name": "운영 기록", "approval": "교훈 승인", "color": "#e2c15a", "view": "activity"},
]
JOB_ROOM = {
    **{s: "scripts" for s in ("research_ready", "drafting", "source_review", "source_rejected", "blocked", "needs_reconciliation", "failed")},
    **{s: "creative" for s in ("source_approved", "production_queued", "producing")},
    **{s: "outbox" for s in ("release_review", "partial_release_review", "release_approved")},
}
STATE_LABELS = {
    "research_ready": "근거 준비", "drafting": "원고·검수 중", "source_review": "사람 승인 대기 ①",
    "source_approved": "원고 승인", "source_rejected": "원고 거절", "production_queued": "제작 대기",
    "producing": "제작 중", "release_review": "사람 승인 대기 ②", "partial_release_review": "일부 제작 완료",
    "release_approved": "출고 승인 ② 완료 · 수동 전달 대기", "blocked": "확인 필요",
    "needs_reconciliation": "호출 결과 확인 필요", "failed": "실패",
}
NEEDS_HUMAN = {"source_review", "release_review", "partial_release_review", "blocked", "needs_reconciliation", "failed"}
ROOM_AGENTS = {
    "inbox": ["research"], "scripts": ["editor", "critique", "eval"], "creative": ["video", "qa"],
    "outbox": ["release", "marketing"], "ops": ["director"],
}
TASK_AGENT = {"draft": "editor", "evaluate": "critique", "produce": "video", "refresh": "research"}
MODEL_AGENTS = {"editor", "critique", "eval"}
EVENT_TEXT = {
    "job_created": "작업 생성", "idea_saved": "기획 저장", "idea_selected": "⓪ 기획 선택", "packaging_selected": "패키지 확정",
    "source_saved": "원고 저장", "source_review_requested": "원고 검토 요청", "source_approved": "① 원고 승인",
    "source_rejected": "① 원고 거절", "release_approved": "② 출고 승인", "release_rejected": "② 출고 거절",
    "lesson_proposed": "교훈 후보", "lesson_reviewed": "교훈 검토", "model_started": "모델 호출",
    "model_completed": "모델 완료", "thumbnail_selected": "썸네일 선택",
    "production_completed": "제작 완료", "production_partial": "일부 제작 완료", "rss_refreshed": "RSS 새로 확인",
    "evidence_collected": "근거 수집", "source_input_saved": "근거 입력 저장", "operator_source_registered": "운영자 근거 등록",
    "draft_registered": "초안 등록", "task_result_unknown": "호출 결과 불명", "cost_unknown": "비용 불명",
    "cost_exceeded_reservation": "예약 초과", "model_cache_hit": "모델 캐시 적중", "speech_request_started": "음성 요청 시작",
    "operator_retry_requested": "재시도 요청",
}
FLOW = {
    "idea_selected": ("inbox", "scripts"), "job_created": ("inbox", "scripts"), "source_approved": ("scripts", "creative"),
    "production_partial": ("creative", "outbox"), "production_completed": ("creative", "outbox"), "release_approved": ("outbox", "ops"),
}
VIEW = {s["id"]: s["view"] for s in STAGES}


def _actions(state, job=None):
    if state in ("research_ready", "source_rejected"):
        article = (job or {}).get("article") or {}
        if article.get("origin") == "idea" and not (job or {}).get("packaging"):
            return []
        return [{"id": "draft", "label": "원고 생성"}]
    if state == "source_approved":
        return [{"id": "produce", "label": "제작 시작"}]
    return []


def _clock(created_at):
    try:
        dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(KST).strftime("%H:%M")
    except (ValueError, TypeError):
        return ""


def project_space(store, office_url: str = "http://localhost:3110", agents=()) -> dict:
    jobs = store.jobs()
    by_job = {j["id"]: j for j in jobs}
    items = {s["id"]: [] for s in STAGES}

    def item(room, id_, title, state, label, needs, actions=()):
        return {"id": id_, "title": title, "state": state, "stateLabel": label, "needsHuman": needs,
                "agentId": ROOM_AGENTS[room][0], "view": VIEW[room], "actions": list(actions)}

    for idea in store.ideas("candidate"):
        iid, ititle = str(idea.get("id", "")), str(idea.get("title", ""))
        if "blocked" not in idea:
            items["inbox"].append(item("inbox", iid, ititle, "pending", "점수 대기", False))
            continue
        blocked = idea.get("blocked")
        blocked = blocked if isinstance(blocked, list) else []
        if blocked:
            items["inbox"].append(item("inbox", iid, ititle, "blocked", "차단 · " + ", ".join(map(str, blocked)), False))
        else:
            score = idea.get("score")
            items["inbox"].append(item("inbox", iid, ititle, "candidate", f"후보 · 점수 {'—' if score is None else score}", True))
    for job in jobs:
        state = job.get("state", "")
        room = JOB_ROOM.get(state)
        if room:
            items[room].append(item(room, job.get("id", ""), job.get("title", ""), state, STATE_LABELS.get(state, state),
                                    state in NEEDS_HUMAN, _actions(state, job)))
    for lesson in store.lessons("proposed"):
        items["ops"].append(item("ops", str(lesson.get("id", "")), lesson.get("hypothesis", ""), "proposed", "사람 승인 대기", True))
    budget = store.budget()
    used = budget["reserved_krw"] + budget["spent_krw"]
    items["ops"].append(item("ops", "budget", f"외부 API 예산 {budget['cap_krw']:,}원 중 {used:,}원 사용·예약", "info", "추정 원가 · 청구 대사 전", False))

    tasks = store.task_activity(TASK_AGENT)
    model = store.setting("model") or ""
    status = {}
    for room, ids in ROOM_AGENTS.items():
        waiting = any(i["needsHuman"] for i in items[room])
        for aid in ids:
            kinds = [k for k, a in TASK_AGENT.items() if a == aid]
            mine = [t for t in tasks if t["kind"] in kinds]
            active = next((t for t in mine if t["state"] in ("claimed", "running")), None)
            if active:
                status[aid] = ("running", f"{active['kind']} 처리 중")
            elif mine and mine[0]["state"] == "failed":
                status[aid] = ("error", "마지막 작업 실패")
            elif mine and mine[0]["state"] == "unknown":
                status[aid] = ("unknown", "호출 결과 불명 · 대사 필요")
            elif waiting:
                status[aid] = ("waiting", "사람 답 대기")
            else:
                status[aid] = ("idle", "대기")
    room_of = {aid: room for room, ids in ROOM_AGENTS.items() for aid in ids}
    out_agents = []
    for a in agents:
        st, task = status.get(a["id"], ("idle", "대기"))
        out_agents.append({"id": a["id"], "name": a["name"], "description": a["description"], "engine": a["mode"],
                           "model": model if a["id"] in MODEL_AGENTS else "", "stageId": room_of.get(a["id"], "ops"),
                           "status": st, "task": task})

    events, flows = [], []
    for ev in store.events(limit=20):
        job = by_job.get(ev.get("job_id"))
        stage = JOB_ROOM.get(job.get("state", ""), "ops") if job else "ops"
        kind = ev.get("kind", "")
        text = EVENT_TEXT.get(kind, "작업 기록")
        title = job.get("title", "") if job else ""
        events.append({"time": _clock(ev.get("created_at", "")), "stageId": stage, "text": f"{text} · {title}" if title else text})
        if kind in FLOW and ev.get("job_id"):
            src, dst = FLOW[kind]
            flows.append({"from": src, "to": dst, "itemId": ev["job_id"]})

    summary = store.setting("knowledge_summary", {}) or {}
    # office/knowledge.py 요약 키: documents, unique_documents, sections
    notes = summary.get("notes") or summary.get("chunks") or summary.get("entries") or summary.get("sections") or 0
    sources = summary.get("sources") or summary.get("documents") or summary.get("files") or 0
    return {
        "version": 1, "generatedAt": datetime.now(KST).isoformat(timespec="seconds"),
        "office": {"name": "HeoBrain 오피스", "url": office_url},
        "brain": {"name": "HeoBrain", "notes": notes, "sources": sources, "label": "과거 기획·근거"},
        "stages": [{"id": s["id"], "name": s["name"], "approval": s["approval"], "color": s["color"], "url": office_url,
                    "view": s["view"], "items": items[s["id"]]} for s in STAGES],
        "agents": out_agents, "events": events, "flows": flows,
    }
