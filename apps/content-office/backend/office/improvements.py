"""Human quality/learning feedback beside immutable source and production versions.

Uses the existing settings ledger; no startup migration or model/approval side effects.
"""
import json
import re
from .store import WorkflowError, canonical, digest, now

RUBRIC = {"accuracy": "근거 정확성", "clarity": "설명·가독성", "actionability": "따라 할 수 있음", "voice": "독자·브랜드 맥락", "visual": "시각적 설명력"}
REASONS = ("fact", "explanation", "style", "design", "rights", "format")
CASE_TOPICS = {
    "A": ["헷갈리는 개념 두 개 구별", "근거로 정답 설명", "틀린 보기의 이유", "단계별 풀이 예시", "일상 비유의 한계", "시험 공고 날짜 확인", "복습 후 다시 풀기", "암기 표현과 정확한 정의", "수험생의 현재 대안", "후기 없는 실제 학습 일지"],
    "B": ["연결됨과 동기화 완료 구별", "자동화의 사람 승인 위치", "입력·판단·출력 예시", "API 비용과 구독 구별", "실패 후 중복 실행 방지", "도구 비교의 같은 조건", "실제로 한 일과 계획 구별", "파일 생성과 외부 게시 구별", "출처 속 지시문 격리", "원문 변경과 파생물 갱신"],
}


def records(store, kind, job_id=None):
    # A bounded local ledger. Private text is never mirrored to public feeds.
    with store.connection() as db:
        rows = db.execute("SELECT value FROM settings WHERE key LIKE ? ORDER BY json_extract(value, '$.created_at') DESC, key LIMIT 500", (f'improvement:{kind}:%',)).fetchall()
    result = [json.loads(row[0]) for row in rows]
    return sorted((r for r in result if job_id is None or r.get('job_id') == job_id), key=lambda r: r['created_at'], reverse=True)


def save_record(store, kind, payload, *, job_id=None, source_hash=None):
    record_id = 'improve_' + digest({'kind': kind, 'job_id': job_id, 'source_hash': source_hash, 'data': payload})[:24]
    key = f'improvement:{kind}:{record_id}'
    if kind == 'learning':
        key = f'improvement:learning:{job_id}:{payload["observation_key"]}'
    with store.connection(transaction=True) as db:
        if job_id is not None:
            current = store._job(db, job_id)
            if current.get('source_hash') != source_hash:
                raise WorkflowError('원고 판본이 바뀌었습니다. 새로 확인한 뒤 기록하세요')
            if kind == 'learning' and digest(current.get('quiz') or {}) != payload['quiz_hash']:
                raise WorkflowError('기록 중 문항 판본이 변경되었습니다')
        old = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        if old:
            previous = json.loads(old[0])
            if any(previous.get(k) != v for k, v in payload.items()):
                raise WorkflowError('이미 기록된 식별자와 내용이 다릅니다. 최신 기록과 중복 여부를 확인하세요')
            return previous
        record = {**payload, 'id': record_id, 'job_id': job_id, 'source_hash': source_hash, 'created_at': now()}
        db.execute('INSERT INTO settings VALUES(?,?)', (key, canonical(record)))
        store._event(db, f'{kind}_recorded', {'record_id': record_id, 'source_hash': source_hash}, job_id)
        return record


def candidates(job, drafts):
    source = job.get('source_hash')
    result = []
    if source:
        result.append({'id': 'source', 'hash': source, 'label': '현재 원고'})
    manifest = job.get('manifest') or {}
    if manifest.get('hash') and manifest.get('source_hash') == source:
        result.append({'id': 'production', 'hash': manifest['hash'], 'label': '현재 제작물'})
    for draft in drafts:
        if draft.get('source_hash_snapshot') == source:
            result.append({'id': draft['id'], 'hash': digest({'body': draft['body'], 'assets': draft.get('assets', [])}), 'label': draft['title']})
    return result


def save_review(store, job_id, payload):
    job = store.job(job_id)
    case = payload.get('case_id', '')
    source_axis = (job.get('source_packet') or {}).get('audience', {}).get('axis')
    if case and source_axis in ('A', 'B') and case[0] != source_axis:
        raise WorkflowError('현재 원고의 축과 평가 사례의 축이 다릅니다')
    target = next((r for r in candidates(job, store.drafts(job_id)) if r['id'] == payload['target_id']), None)
    if not target or target['hash'] != payload['target_hash']:
        raise WorkflowError('평가 대상 파일/원고가 바뀌었습니다. 최신 판본을 다시 확인하세요')
    if set(payload['scores']) != set(RUBRIC) or any(type(n) is not int or not 1 <= n <= 5 for n in payload['scores'].values()):
        raise WorkflowError('다섯 평가 항목을 각각 1~5점으로 기록하세요')
    if not set(payload['reasons']).issubset(REASONS):
        raise WorkflowError('지원하지 않는 반려 사유입니다')
    if payload['critical'] and not payload['reasons']:
        raise WorkflowError('중대 오류의 반려 사유를 선택하세요')
    payload = {**payload, 'dataset_split': ('holdout' if int(case[1:]) > 7 else 'development') if case else 'unassigned', 'scope': 'human_observation_not_approval', 'quality_passed': not payload['critical'] and min(payload['scores'].values()) >= 4}
    # Verify artifact versions again under the same lock as the write.
    with store.connection(transaction=True) as db:
        current = store._job(db, job_id)
        current_drafts = [json.loads(r[0]) for r in db.execute('SELECT data FROM drafts WHERE job_id=?', (job_id,))]
        current_target = next((r for r in candidates(current, current_drafts) if r['id'] == payload['target_id']), None)
        if current.get('source_hash') != payload['source_hash'] or not current_target or current_target['hash'] != payload['target_hash']:
            raise WorkflowError('평가 중 원고/파일이 변경되었습니다')
        identity = digest({'job': job_id, 'payload': payload})[:24]
        key = 'improvement:review:' + identity
        old = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        if old:
            return json.loads(old[0])
        record = {**payload, 'id': identity, 'job_id': job_id, 'created_at': now()}
        db.execute('INSERT INTO settings VALUES(?,?)', (key, canonical(record)))
        store._event(db, 'quality_review_recorded', {'review_id': identity, 'target_id': payload['target_id'], 'critical': payload['critical']}, job_id)
        return record


def experience_context(store, job):
    brief = job.get('brief') or {}
    terms = set(re.findall(r'[\w가-힣]{2,}', ' '.join(str(brief.get(k, '')) for k in ('topic', 'problem', 'reader')) + ' ' + job.get('title', '') + ' ' + (job.get('article') or {}).get('title', '')))
    matches = []
    for card in records(store, 'experience'):
        if card.get('confirmed') is not True or card.get('use_in_content') is not True:
            continue
        if card.get('axis') not in (brief.get('axis'), 'both'):
            continue
        if terms.intersection(re.findall(r'[\w가-힣]{2,}', ' '.join(card.get('tags', [])) + ' ' + card['title'])):
            matches.append({k: card[k] for k in ('id', 'title', 'facts', 'evidence_note', 'checked_on')})
    return matches[:3]


def learning_contract(job):
    quiz = job.get('quiz') or {}
    if quiz.get('source_hash') != job.get('source_hash') or quiz.get('checks', {}).get('passed') is not True:
        return {'schema_version': 1, 'status': 'quiz_pending', 'items': [], 'note': '현재 원고의 검사 통과 퀴즈가 필요합니다. 스토어 연결/발송은 실행하지 않습니다.'}
    questions = quiz.get('questions', [])
    result = []
    for index, q in enumerate(questions):
        concept = 'concept_' + digest({'job': job['id'], 'evidence': sorted(q.get('evidence', [])) or [q['id']]})[:16]
        result.append({**q, 'concept_id': concept, 'learning_objective': (job.get('source_packet') or {}).get('audience', {}).get('outcome', ''), 'misconception_candidates': [v for n, v in enumerate(q.get('choices', [])) if n != q.get('answer')], 'concept_status': 'evidence_group_needs_human_validation'})
    return {'schema_version': 1, 'status': 'ready_for_store_review', 'quiz_hash': digest(quiz), 'job_id': job['id'], 'source_hash': job['source_hash'], 'items': result, 'note': '기존 스토어 퀴즈용 검토 계약입니다. 실제 스토어 동기화나 정답 공개의 구독 조건을 만들지 않습니다.'}


def storyboard(job):
    from .media import scene_content
    packet = job.get('source_packet') or {}
    evidence = {e.get('id'): e for e in packet.get('evidence', []) if isinstance(e, dict)}
    scenes = []
    for n, scene in enumerate((packet.get('video') or {}).get('scenes', [])):
        content = scene_content(scene, n)
        narration = str(scene.get('narration', ''))
        cited = re.findall(r'\[([A-Z]+\d+)\]', narration + ' ' + str(scene.get('visual', '')))
        scenes.append({'index': n+1, **content, 'evidence_ids': [e for e in cited if e in evidence], 'estimated_read_seconds': max(3, round(len(content['caption']) / 5, 1)), 'checks': (["장면별 근거를 직접 확인하세요"] if not cited else []) + (["비교·단계 등 설명할 관계를 구체화하세요"] if content['kind'] == 'explanation' and content['key_phrases'] == [content['caption']] else [])})
    return {'source_hash': job.get('source_hash'), 'scenes': scenes, 'note': '승인 원고의 설명 구조 점검입니다. 읽는 시간은 추정이며 실제 TTS 길이나 사람 검수를 대신하지 않습니다.'}


def workspace(store, job_id):
    job = store.job(job_id)
    return {'job_id': job_id, 'source_hash': job.get('source_hash'), 'rubric': RUBRIC, 'candidates': candidates(job, store.drafts(job_id)), 'reviews': records(store, 'review', job_id), 'storyboard': storyboard(job), 'learning': learning_contract(job), 'learning_observations': records(store, 'learning', job_id), 'experiences': [{**r, 'record_hash': digest(r)} for r in records(store, 'experience')], 'outcomes': records(store, 'outcome', job_id), 'casebook': [{'id': f'{axis}{n:02}', 'axis': axis, 'topic': topic, 'status': 'scenario_template_not_evaluated', 'split': 'holdout' if n > 7 else 'development'} for axis, topics in CASE_TOPICS.items() for n, topic in enumerate(topics, 1)], 'note': '평가·학습·성과 기록은 사람 승인①②③이나 실제 외부 게시를 대신하지 않습니다.'}
