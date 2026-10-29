"""승인① 원고 → 4지선다 5문항 퀴즈 JSON. 문제만 만들고, 풀기·채점은 스토어의 기존 퀴즈 도구가 한다.

퀴즈 결과 공개를 뉴스레터 구독과 묶지 않는다(인계서 6장 11항).
"""
from __future__ import annotations

import re

from .brand import banned_claim_hits, brand_system_prompt, load_brand
from .briefs import brief_for_job
from .editorial import BASE, style_issues
from .media import artifact_record, write_json
from .providers import Provider
from .store import Store, WorkflowError, canonical, now

QUESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "question": {"type": "string"},
        "choices": {"type": "array", "minItems": 4, "maxItems": 4, "items": {"type": "string"}},
        "answer": {"type": "integer", "minimum": 0, "maximum": 3},
        "explanation": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["id", "question", "choices", "answer", "explanation", "evidence"],
    "additionalProperties": False,
}
QUIZ_SCHEMA = {"type": "object", "properties": {"questions": {"type": "array", "minItems": 5, "maxItems": 5, "items": QUESTION_SCHEMA}}, "required": ["questions"], "additionalProperties": False}
QUIZ_COUNT = 5
CHOICE_COUNT = 4

INSTRUCTIONS = "승인된 원고만 근거로 한국어 4지선다 5문항을 만든다. id는 Q1~Q5. 각 문항은 원고가 실제로 설명한 사실·판단 기준을 묻고, 보기 4개는 서로 다른 완결된 문구이며 정답은 하나다. 정답 번호(answer, 0~3)는 문항마다 고르게 섞는다. explanation은 해요체 한두 문장으로 왜 정답인지 원고 내용으로 설명한다. evidence에는 그 문항이 기대는 원고 근거 ID만 넣는다. 원고에 없는 수치·사실·개인 경험을 지어내지 않고, 과장·훈계 표현을 쓰지 않는다. 퀴즈를 풀거나 채점하지 않는다."


def packet_context(packet):
    """퀴즈·카드 프롬프트에 넣는 승인 원고 부분. 검수 기록·호출 로그는 뺀다."""
    evidence = [{key: item.get(key) for key in ("id", "claim", "url", "numbers") if item.get(key) is not None} for item in packet.get("evidence", []) if isinstance(item, dict)]
    return {"title": packet.get("title", ""), "body": packet.get("body", ""), "evidence": evidence, "limitations": packet.get("limitations", [])}


def text_issues(texts, brand):
    """금지 주장·문체 규칙을 임의의 문장 묶음에 적용한다(editorial.style_issues 재사용)."""
    joined = "\n".join(str(text or "") for text in texts)
    # style_issues가 brand.banned(금지 주장)도 함께 검사한다.
    return list(style_issues({"title": "", "body": joined}, brand))


def quiz_texts(quiz):
    texts = []
    for question in quiz.get("questions", []) or []:
        texts.append(question.get("question", ""))
        texts.extend(question.get("choices", []) or [])
        texts.append(question.get("explanation", ""))
    return [str(text or "") for text in texts]


def quiz_checks(quiz, packet, brand=None):
    """결정적 검사. 통과하지 못해도 결과는 저장하고 화면에서 문제점을 보여 준다."""
    brand = brand if brand is not None else load_brand()
    questions = [q for q in (quiz.get("questions") or []) if isinstance(q, dict)]
    issues = []
    if len(questions) != QUIZ_COUNT:
        issues.append(f"문항은 {QUIZ_COUNT}개여야 해요 (현재 {len(questions)}개)")
    known = {item.get("id") for item in packet.get("evidence", []) if isinstance(item, dict) and item.get("id")}
    answers = []
    for number, question in enumerate(questions, 1):
        label = str(question.get("id") or f"Q{number}")
        if not str(question.get("question", "")).strip():
            issues.append(f"{label}: 질문 문장이 비어 있어요")
        choices = [str(choice or "").strip() for choice in (question.get("choices") or [])]
        if len(choices) != CHOICE_COUNT or any(not choice for choice in choices):
            issues.append(f"{label}: 보기 {CHOICE_COUNT}개가 모두 비어 있지 않아야 해요")
        if len(set(choices)) != len(choices):
            issues.append(f"{label}: 보기 문구가 중복돼요")
        answer = question.get("answer")
        if not isinstance(answer, int) or isinstance(answer, bool) or not 0 <= answer < CHOICE_COUNT:
            issues.append(f"{label}: 정답 번호는 0~{CHOICE_COUNT - 1} 사이여야 해요")
        else:
            answers.append(answer)
        if not str(question.get("explanation", "")).strip():
            issues.append(f"{label}: 해설이 비어 있어요")
        cited = [str(item) for item in (question.get("evidence") or [])]
        unknown = [item for item in cited if item not in known]
        if unknown:
            issues.append(f"{label}: 원고에 없는 근거 ID {', '.join(unknown)}")
        if known and not cited:
            issues.append(f"{label}: 기대는 근거 ID를 하나 이상 적어야 해요")
    if len(answers) == QUIZ_COUNT and len(set(answers)) == 1:
        issues.append("모든 문항의 정답 번호가 같아요. 정답 위치를 섞으세요")
    issues.extend(text_issues(quiz_texts(quiz), brand))
    return {"passed": not issues, "issues": issues}


def output_folder(store, job, name):
    """작업 산출물 폴더 artifacts/<job>/<source_hash>/<name>. media.produce와 같은 경로 규칙."""
    job_id, source_hash = job["id"], job.get("source_hash") or ""
    if not re.fullmatch("job_[a-zA-Z0-9_-]+", job_id) or not re.fullmatch("[0-9a-f]{64}", source_hash) or not re.fullmatch("[a-z0-9-]+", name):
        raise WorkflowError("산출물 경로 식별자가 유효하지 않습니다")
    root = store.artifacts.resolve()
    folder = root / job_id / source_hash / name
    if not folder.resolve().is_relative_to(root):
        raise WorkflowError("산출물 경로가 허용 범위를 벗어났습니다")
    folder.mkdir(parents=True, exist_ok=True)
    return root, folder


def save_job_output(store, job_id, source_hash, key, record, event_kind, event_data):
    """원고 버전이 그대로일 때만 job[key]를 바꾼다. 승인①②와 제작물 manifest는 건드리지 않는다."""
    with store.connection(transaction=True) as db:
        job = store._job(db, job_id)
        if job.get("source_hash") != source_hash:
            raise WorkflowError("작업 도중 원고 버전이 변경되어 옛 결과를 저장하지 않았습니다")
        job[key] = record
        store._event(db, event_kind, event_data, job_id)
        return store._write_job(db, job)


def enqueue_output(store, job, kind, images=None):
    """quiz/cards 작업을 넣는다. 대기·실행 중이면 같은 작업을 돌려주고, 끝난 뒤(성공·실패)나 새 버전 뒤에는 새 작업을 만든다."""
    if kind not in ("quiz", "cards"):
        raise WorkflowError("퀴즈 또는 카드 작업만 넣을 수 있습니다")
    source_hash = job["source_hash"]
    version = int((job.get(kind) or {}).get("version", 0))
    finished = sum(1 for task in store.tasks(job["id"]) if task["kind"] == kind and task["payload"].get("source_hash") == source_hash and task["state"] not in ("queued", "running"))
    payload = {"job_id": job["id"], "source_hash": source_hash}
    if kind == "cards" and images is not None:
        payload["images"] = bool(images)
    suffix = "" if images is None else (":img" if images else ":noimg")
    return store.enqueue(kind, payload, key=f"{kind}:{job['id']}:{source_hash}:v{version}:{finished}{suffix}")


def enqueue_missing_outputs(store, job):
    """제작(produce) 때 자동으로 호출한다. 현재 원고 버전의 퀴즈·카드가 이미 있으면 건너뛴다(멱등)."""
    queued = {}
    for kind in ("quiz", "cards"):
        if (job.get(kind) or {}).get("source_hash") == job["source_hash"]:
            continue
        queued[kind] = enqueue_output(store, job, kind)["id"]
    return queued


def generate_quiz(store: Store, job_id, provider=None):
    job = store.require_source_approval(job_id)
    packet = job["source_packet"] or {}
    brand = load_brand()
    brief = brief_for_job(job)
    provider = provider or Provider(store)
    system = brand_system_prompt(BASE, brand)
    context = {"packet": packet_context(packet), "audience": brief, "instructions": INSTRUCTIONS}
    quiz = provider.generate("quiz", [{"role": "system", "content": system}, {"role": "user", "content": canonical(context)}], QUIZ_SCHEMA, {"max_tokens": 4096, "temperature": 0.4})
    checks = quiz_checks(quiz, packet, brand)
    refined = False
    if not checks["passed"]:
        # 한 번만 고친다. 그래도 걸리면 문제점을 그대로 저장해 사람이 본다.
        refine_context = {**context, "previous": quiz, "issues": checks["issues"], "instructions": INSTRUCTIONS + " 아래 issues를 모두 해결한 완전한 5문항을 다시 작성한다."}
        quiz = provider.generate("quiz", [{"role": "system", "content": system}, {"role": "user", "content": canonical(refine_context)}], QUIZ_SCHEMA, {"max_tokens": 4096, "temperature": 0.3})
        checks = quiz_checks(quiz, packet, brand)
        refined = True
    questions = [{"id": str(q.get("id") or f"Q{n}"), "question": str(q.get("question", "")), "choices": [str(c) for c in (q.get("choices") or [])], "answer": q.get("answer"), "explanation": str(q.get("explanation", "")), "evidence": [str(e) for e in (q.get("evidence") or [])]} for n, q in enumerate(quiz.get("questions") or [], 1)]
    version = int((job.get("quiz") or {}).get("version", 0)) + 1
    record = {"version": version, "generated_at": now(), "source_hash": job["source_hash"], "questions": questions, "checks": checks, "refined": refined, "note": "문제만 생성합니다. 풀기·채점은 스토어의 기존 퀴즈 도구를 쓰고, 퀴즈 결과 공개를 뉴스레터 구독과 묶지 않습니다", "artifact_id": None, "artifact": None}
    root, folder = output_folder(store, job, "quiz")
    path = folder / f"quiz-v{version}.json"
    write_json(path, {key: value for key, value in record.items() if key not in ("artifact_id", "artifact")})
    artifact = artifact_record(root, path)
    record.update(artifact_id=artifact["id"], artifact=artifact)
    save_job_output(store, job_id, job["source_hash"], "quiz", record, "quiz_generated", {"role": "편집", "version": version, "source_hash": job["source_hash"], "questions": len(questions), "passed": checks["passed"], "issues": len(checks["issues"]), "artifact_id": artifact["id"], "next_action": "문항·해설을 확인하고 스토어 퀴즈 도구로 옮깁니다"})
    return record
