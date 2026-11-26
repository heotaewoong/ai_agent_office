"""기획 은행: 신호를 점수화해 사람이 고를 후보를 정렬한다. 점수는 판단 보조이며 성과 예측이 아니다.

demand는 요청마다 최대값을 100으로 맞춘 상대값(네이버 데이터랩 등)이므로 같은 요청 안에서만 비교한다.
"""
from __future__ import annotations

import hashlib
import json
import math
import re

from .calendar import enrich_idea
from .evidence import reference_url
from .store import WorkflowError, canonical, digest, now

# timeliness는 기본 다섯 요소를 100점으로 정규화한 뒤 가산점(최대 10점, 합계 100점 상한)으로 더한다.
# 캘린더가 있는 프리셋(brief.preset)의 카드만 0보다 큰 값을 받으므로 기존 카드 점수는 그대로다.
WEIGHTS = {"outlier": 30, "demand": 20, "evidence": 20, "fit": 20, "novelty": 10, "timeliness": 10}
BASE_FACTORS = ("outlier", "demand", "evidence", "fit", "novelty")
BAND_POINTS = {"10x+": 1.0, "5-10x": 0.8, "2-5x": 0.55, "under-2x": 0.2, "unknown": 0.0}
BLOCKING_FLAGS = {
    "ai_persona_real_person_ymyl": "실존 인물 AI 페르소나의 금융·법률·건강 발언(YouTube 2026-07 수익화 제외 유형)",
    "templated_series": "같은 템플릿 반복 위험(YouTube 비진정성 콘텐츠)",
    "no_primary_source": "1차 출처 없음",
}


def outlier_ratio(views, channel_avg_views):
    if not views or not channel_avg_views or channel_avg_views <= 0:
        return None
    return views / channel_avg_views


def outlier_band(ratio):
    if ratio is None:
        return "unknown"
    if ratio >= 10:
        return "10x+"
    if ratio >= 5:
        return "5-10x"
    if ratio >= 2:
        return "2-5x"
    return "under-2x"


def _number(value, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def effective_weights(weights=None, lessons=()):
    result = dict(weights or WEIGHTS)
    for lesson in lessons:
        change = lesson.get("weight_change") or {}
        if lesson.get("state") == "approved" and change.get("factor") in result:
            result[change["factor"]] = max(0, result[change["factor"]] + int(_number(change.get("delta"))))
    return result


def score_idea(card, weights=None, lessons=(), today=None, calendar=None):
    w = effective_weights(weights, lessons)
    card = enrich_idea(card, today, calendar)
    band = outlier_band(outlier_ratio(card.get("views"), card.get("channel_avg_views")))
    sources = int(_number(card.get("primary_sources")))
    parts = {
        "outlier": BAND_POINTS[band],
        "demand": min(max(_number(card.get("demand")), 0.0), 100.0) / 100,
        "evidence": min(sources, 3) / 3,
        "fit": min(max(_number(card.get("fit")), 0.0), 1.0),
        "novelty": 0.0 if card.get("covered_before") else 1.0,
        "timeliness": min(max(_number(card.get("timeliness")), 0.0), 1.0),
    }
    base = 100 * sum(w[k] * parts[k] for k in BASE_FACTORS) / (sum(w[k] for k in BASE_FACTORS) or 1)
    score = round(min(100.0, base + w.get("timeliness", 0) * parts["timeliness"]), 1)
    raw_flags = card.get("policy_flags")
    raw_flags = raw_flags if isinstance(raw_flags, (list, tuple, set)) else []
    flags = [f for f in raw_flags if f in BLOCKING_FLAGS] + ([] if sources else ["no_primary_source"])
    blocked = [BLOCKING_FLAGS[f] for f in dict.fromkeys(flags)]
    reasons = [f"이상치 {band}", f"수요 {_number(card.get('demand')):g}(상대값)", f"1차 출처 {sources}개"]
    return {**card, "score": 0.0 if blocked else score, "outlier_band": band, "parts": parts, "reasons": reasons, "blocked": blocked}


def rank_ideas(cards, weights=None, lessons=(), today=None, calendar=None):
    scored = [score_idea(card, weights, lessons, today, calendar) for card in cards]
    return sorted(scored, key=lambda c: (not c["blocked"], c["score"]), reverse=True)


def with_edit_hash(card):
    """읽은 저장 판본의 토큰. 시간에 따라 재계산하는 점수와 구분하고 DB에는 넣지 않는다."""
    return {**card, "edit_hash": digest(card)}



PUBLIC_EVIDENCE_LIMIT = 4
_PUBLIC_ID = re.compile(r"[0-9a-f]{64}")
_PUBLIC_FIELDS = ("id", "url", "title", "paragraph", "quote", "source_sha256", "quote_sha256")
# 자료 창고 문단의 위치 정보(PDF 쪽, 소제목 경로). 있으면 그대로 넘기고 승인 판본 해시에도 들어간다. 근거 ID와는 무관하다.
_PUBLIC_PLACE_FIELDS = {"locator": 40, "heading": 200}


def _checked_public_references(references):
    from .public_evidence import public_evidence_id

    if not isinstance(references, list) or len(references) > PUBLIC_EVIDENCE_LIMIT:
        raise WorkflowError("공개 근거 목록의 판본을 다시 확인하세요")
    checked, seen = [], set()
    for entry in references:
        if not isinstance(entry, dict) or any(key not in entry for key in _PUBLIC_FIELDS):
            raise WorkflowError("공개 근거의 출처와 문단을 다시 확인하세요")
        item = {key: entry[key] for key in _PUBLIC_FIELDS}
        for key, limit in _PUBLIC_PLACE_FIELDS.items():
            if key in entry:
                value = entry[key]
                if not isinstance(value, str) or not value.strip() or len(value) > limit or re.search(r"[\x00-\x1f]", value):
                    raise WorkflowError("공개 근거의 쪽이나 소제목 정보가 올바르지 않습니다")
                item[key] = value
        if any(not isinstance(item[key], str) or not _PUBLIC_ID.fullmatch(item[key])
               for key in ("id", "source_sha256", "quote_sha256")):
            raise WorkflowError("공개 근거의 해시가 올바르지 않습니다")
        url, title, paragraph, quote = (item[key] for key in ("url", "title", "paragraph", "quote"))
        if (not isinstance(url, str) or len(url) > 2000 or url in seen
                or not isinstance(title, str) or not title.strip() or len(title) > 500
                or type(paragraph) is not int or not 1 <= paragraph <= 100_000
                or not isinstance(quote, str) or not quote.strip() or len(quote) > 2400):
            raise WorkflowError("공개 근거의 출처와 문단을 다시 확인하세요")
        try:
            reference_url(url)
        except ValueError as error:
            raise WorkflowError("공개 근거의 HTTPS 주소가 올바르지 않습니다") from error
        quote_hash = hashlib.sha256(quote.encode()).hexdigest()
        if quote_hash != item["quote_sha256"] or item["id"] != public_evidence_id(url, item["source_sha256"], paragraph, quote_hash):
            raise WorkflowError("공개 근거의 원문 판본이 일치하지 않습니다")
        if "published" in entry:
            if not isinstance(entry["published"], str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", entry["published"]):
                raise WorkflowError("공개 근거의 발행일 형식이 올바르지 않습니다")
            item["published"] = entry["published"]
        if "highlight" in entry:
            value = entry["highlight"]
            if not isinstance(value, str) or not value.strip() or len(value) > 400 or value not in quote:
                raise WorkflowError("공개 근거의 표시 문장이 원문 문단과 맞지 않습니다")
            item["highlight"] = value
        if "flags" in entry:
            value = entry["flags"]
            if (not isinstance(value, list) or len(value) > 3
                    or any(not isinstance(flag, str) or not flag.strip() or len(flag) > 120 for flag in value)):
                raise WorkflowError("공개 근거의 주의 표시 형식이 올바르지 않습니다")
            item["flags"] = list(value)
        checked.append(item)
        seen.add(url)
    return checked


def _evidence_review_jobs(db, idea_id=None):
    # Selection can be supplemented only before any manuscript or later approval exists.
    return {
        job["article"]["id"]: job
        for row in db.execute("""
            SELECT j.data FROM jobs j
            WHERE json_extract(j.data, '$.article.origin') = 'idea'
              AND (? IS NULL OR json_extract(j.data, '$.article.id') = ?)
              AND json_extract(j.data, '$.state') = 'research_ready'
              AND json_extract(j.data, '$.deleted_at') IS NULL
              AND json_extract(j.data, '$.source_hash') IS NULL
              AND json_extract(j.data, '$.source_packet') IS NULL
              AND json_extract(j.data, '$.source_approval') IS NULL
              AND json_extract(j.data, '$.release_approval') IS NULL
              AND json_extract(j.data, '$.manifest') IS NULL
              AND NOT EXISTS (SELECT 1 FROM approvals a WHERE a.job_id = j.id)
              AND NOT EXISTS (
                  SELECT 1 FROM tasks t
                  WHERE json_extract(t.payload, '$.job_id') = j.id
                    AND t.state IN ('queued', 'running', 'unknown')
              )
        """, (idea_id, idea_id))
        for job in (json.loads(row[0]),)
    }


def _visible_evidence(card):
    from .evidence_relevance import is_topic_candidate

    references = card.get("public_evidence")
    if references is None:
        return card
    allowed = [item for item in references if is_topic_candidate(card["title"], item["title"], item["quote"])]
    result = {**card, "public_evidence": allowed}
    discovery = card.get("public_discovery")
    if not allowed and discovery and discovery.get("status") == "ready":
        result["public_discovery"] = {**discovery, "status": "insufficient"}
    return result


def reviewable_ideas(store, *, lessons=()):
    with store.connection() as db:
        eligible = _evidence_review_jobs(db)
        cards = [json.loads(row[0]) for row in db.execute("SELECT data FROM ideas ORDER BY created_at")]
    return rank_ideas([
        {**_visible_evidence(with_edit_hash(card)), "public_evidence_reviewable": card["id"] in eligible}
        if card.get("state") == "selected" else _visible_evidence(with_edit_hash(card))
        for card in cards
    ], lessons=lessons)


def _reviewable_idea(db, idea_id, expected_hash, *, allow_selected=False):
    row = db.execute("SELECT state,data FROM ideas WHERE id=?", (idea_id,)).fetchone()
    if not row:
        raise WorkflowError("기획을 찾을 수 없습니다")
    stored = json.loads(row["data"])
    state = stored.get("state")
    if row["state"] != state or state not in ("candidate", "selected") or (state == "selected" and not allow_selected):
        raise WorkflowError("이미 선택한 기획입니다. 기존 작업을 확인하세요")
    if digest(stored) != expected_hash:
        raise WorkflowError("기획이 변경되었습니다. 출처와 내용을 다시 확인한 뒤 선택하세요")
    job = None
    if state == "selected":
        job = _evidence_review_jobs(db, idea_id).get(idea_id)
        if job is None:
            raise WorkflowError("원고가 없고 진행 중인 작업이 없는 기획에서만 근거를 다시 승인할 수 있습니다")
    return stored, job


def _with_library_references(store, title, references, claims):
    """플랫폼에서 온 기획도 자료 창고에서 운영자가 근거로 켠 문단을 남은 자리에 함께 보여 준다."""
    references, claims = _checked_public_references(references), list(claims)
    room = PUBLIC_EVIDENCE_LIMIT - len(references)
    if room <= 0:
        return references, claims
    try:
        from .public_evidence import PublicEvidenceUnavailable, find_library_evidence
    except ImportError:
        return references, claims
    try:
        extra = find_library_evidence(title, root=store.root, exclude_urls=tuple(item["url"] for item in references), limit=room)
    except PublicEvidenceUnavailable:
        return references, claims
    used = {item["url"] for item in references}
    extra = [item for item in extra if isinstance(item, dict) and item.get("url") not in used][:room]
    merged = _checked_public_references(references + extra)
    from .source_library import example_urls
    examples = example_urls(store.root)
    claims += [{"label": "자료 창고의 사례·참고 문단(사실 근거로는 쓰지 않음)" if item["url"] in examples else "자료 창고에서 근거로 고른 문단",
                "evidence_ids": [item["id"]]} for item in merged[len(references):]]
    return merged, claims


def refresh_idea_public_evidence(store, idea_id, *, expected_hash, lessons=()):
    from .public_evidence import PublicEvidenceUnavailable, find_public_evidence

    with store.connection() as db:
        candidate, job = _reviewable_idea(db, idea_id, expected_hash, allow_selected=True)
    public_discovery = None
    try:
        origin = candidate.get("platform_origin")
        if origin:
            from .public_discovery import discover_public_evidence

            cited_links = [word.rstrip(".,);]") for word in origin["summary"].split()
                           if word.startswith("https://")][:2]
            seeds = tuple(dict.fromkeys([*origin.get("original_urls", []), candidate["source_url"],
                                        *candidate.get("source_urls", [])[:3], *cited_links, origin["url"]]))
            result = discover_public_evidence(candidate["title"], seed_urls=seeds,
                                              context=origin["summary"], limit=PUBLIC_EVIDENCE_LIMIT)
            if result["status"] == "unavailable":
                with store.connection() as db:
                    current, job = _reviewable_idea(db, idea_id, expected_hash, allow_selected=True)
                response = score_idea(_visible_evidence(with_edit_hash(current)), lessons=lessons)
                if job:
                    response["public_evidence_reviewable"] = True
                response.setdefault("public_discovery", {"status": "unavailable", "claims": [],
                                                         "checked_at": now(), "paid_calls": 0})
                return response
            references, claims = _with_library_references(store, candidate["title"], result["references"], result["claims"])
            public_discovery = {"status": "ready" if references else "insufficient",
                                "claims": claims, "checked_at": now(), "paid_calls": 0}
        else:
            from .external_research import guess_area
            from .research_choices import load_choice
            # 사람이 고른 분야가 있으면 그 값을, 없으면 제목으로 추측한 분야를 쓴다. 시험 분야일 때만 시험 자료로 좁힌다.
            area = (load_choice(store.root, idea_id) or {}).get("area") or guess_area(candidate["title"])
            scope = {"area": area} if area == "A" else {}
            references = _checked_public_references(find_public_evidence(candidate["title"], limit=PUBLIC_EVIDENCE_LIMIT, **scope))
        references = _visible_evidence({**candidate, "public_evidence": references})["public_evidence"]
        if public_discovery is not None and not references:
            public_discovery["status"] = "insufficient"
    except PublicEvidenceUnavailable as error:
        raise WorkflowError(str(error) or "공개 근거 검색을 실행할 수 없습니다. 잠시 후 다시 확인하세요") from error
    # External reads happen outside the write transaction. Re-check the candidate version on save.
    with store.connection(transaction=True) as db:
        stored, job = _reviewable_idea(db, idea_id, expected_hash, allow_selected=True)
        if stored.get("public_evidence") != references or public_discovery is not None:
            stored = {**stored, "public_evidence": references}
            if public_discovery is not None:
                stored["public_discovery"] = public_discovery
            db.execute("UPDATE ideas SET data=?,updated_at=? WHERE id=?", (canonical(stored), now(), idea_id))
            store._event(db, "idea_public_evidence_refreshed", {"idea_id": idea_id, "matches": len(references)})
    response = score_idea(with_edit_hash(stored), lessons=lessons)
    if job:
        response["public_evidence_reviewable"] = True
    return response


def refresh_idea_book_evidence(store, idea_id, *, expected_hash, lessons=()):
    """개인 DB(책, 강의 자료)에서 기획 제목과 맞는 문단 후보를 찾는다. 사람이 누를 때만 돈다. 외부로 나가는 요청은 없다."""
    from .private_books import BOOK_EVIDENCE_LIMIT, BookEvidenceUnavailable, find_book_evidence

    with store.connection() as db:
        candidate, job = _reviewable_idea(db, idea_id, expected_hash, allow_selected=True)
    try:
        references, mode = find_book_evidence(candidate["title"], limit=BOOK_EVIDENCE_LIMIT)
    except BookEvidenceUnavailable as error:
        raise WorkflowError(str(error) or "개인 DB 검색을 지금 쓸 수 없어요. 잠시 뒤 다시 찾아 주세요") from error
    discovery = {"status": "ready" if references else "insufficient", "checked_at": now(), "mode": mode, "paid_calls": 0}
    with store.connection(transaction=True) as db:
        stored, job = _reviewable_idea(db, idea_id, expected_hash, allow_selected=True)
        stored = {**stored, "book_evidence": references, "book_discovery": discovery}
        db.execute("UPDATE ideas SET data=?,updated_at=? WHERE id=?", (canonical(stored), now(), idea_id))
        store._event(db, "idea_book_evidence_refreshed", {"idea_id": idea_id, "matches": len(references), "mode": mode})
    response = score_idea(with_edit_hash(stored), lessons=lessons)
    if job:
        response["public_evidence_reviewable"] = True
    return response


def _selected_book_references(card, book_evidence_ids):
    from .private_books import BOOK_EVIDENCE_LIMIT, checked_book_references

    if book_evidence_ids is None:
        return []
    if (not isinstance(book_evidence_ids, list) or len(book_evidence_ids) > BOOK_EVIDENCE_LIMIT
            or any(not isinstance(key, str) or not _PUBLIC_ID.fullmatch(key) for key in book_evidence_ids)
            or len(set(book_evidence_ids)) != len(book_evidence_ids)):
        raise WorkflowError("책 근거는 화면에서 중복 없이 최대 4개를 고르세요")
    if not book_evidence_ids:
        return []
    latest = {item["id"]: item for item in checked_book_references(card.get("book_evidence", []))}
    if any(key not in latest for key in book_evidence_ids):
        raise WorkflowError("기획의 책 근거 후보가 바뀌었습니다. 다시 확인한 뒤 선택하세요")
    return [latest[key] for key in book_evidence_ids]


def approved_book_references(article):
    from .private_books import checked_book_references

    if "approved_book_evidence" not in article and "approved_book_evidence_hash" not in article:
        return []
    references = checked_book_references(article.get("approved_book_evidence"))
    if not references or digest(references) != article.get("approved_book_evidence_hash"):
        raise WorkflowError("기획 승인⓪의 책 근거 판본이 일치하지 않습니다")
    return references


def _selected_public_references(card, public_evidence_ids):
    if public_evidence_ids is None:
        return []
    if (not isinstance(public_evidence_ids, list) or len(public_evidence_ids) > PUBLIC_EVIDENCE_LIMIT
            or any(not isinstance(key, str) or not _PUBLIC_ID.fullmatch(key) for key in public_evidence_ids)
            or len(set(public_evidence_ids)) != len(public_evidence_ids)):
        raise WorkflowError("공개 근거는 화면에서 중복 없이 최대 4개를 고르세요")
    if not public_evidence_ids:
        return []
    from .evidence_relevance import is_topic_candidate
    latest = {item["id"]: item for item in _checked_public_references(card.get("public_evidence", []))
              if is_topic_candidate(card["title"], item["title"], item["quote"])}
    if any(key not in latest for key in public_evidence_ids):
        raise WorkflowError("기획의 공개 근거가 변경되었습니다. 다시 확인한 뒤 선택하세요")
    return [latest[key] for key in public_evidence_ids]


def approved_public_references(article):
    if "approved_public_evidence" not in article and "approved_public_evidence_hash" not in article:
        return []
    references = _checked_public_references(article.get("approved_public_evidence"))
    if not references or digest(references) != article.get("approved_public_evidence_hash"):
        raise WorkflowError("기획 승인⓪의 공개 근거 판본이 일치하지 않습니다")
    return references


def set_idea_sources(store, idea_id, source_urls, *, expected_hash, operator_verified, lessons=()):
    """선택 전 출처를 운영자 확인으로 보완한다. 본문 열람·독립 검증·기획 선택은 수행하지 않는다."""
    if operator_verified is not True:
        raise WorkflowError("각 출처의 본문과 기획 관련성을 직접 확인한 뒤 체크하세요")
    if not isinstance(source_urls, list) or not 1 <= len(source_urls) <= 10:
        raise WorkflowError("출처 URL을 1~10개 입력하세요")
    urls = []
    for raw in source_urls:
        if not isinstance(raw, str) or not raw.strip() or len(raw) > 2000:
            raise WorkflowError("출처 URL은 2000자 이내의 공개 HTTPS 주소여야 합니다")
        try:
            url = reference_url(raw.strip())
        except ValueError as error:
            raise WorkflowError("공개 HTTPS 원출처 주소를 확인하세요") from error
        if url not in urls:
            urls.append(url)
    with store.connection(transaction=True) as db:
        row = db.execute("SELECT state,data FROM ideas WHERE id=?", (idea_id,)).fetchone()
        if not row:
            raise WorkflowError("기획을 찾을 수 없습니다")
        stored = json.loads(row["data"])
        if row["state"] != "candidate" or stored.get("state") != "candidate":
            raise WorkflowError("이미 선택한 기획의 출처는 바꿀 수 없습니다")
        if digest(stored) != expected_hash:
            raise WorkflowError("기획이 변경되었습니다. 현재 기획을 다시 불러온 뒤 출처를 확인하세요")
        updated = score_idea({**stored, "source_url": urls[0], "source_urls": urls,
                              "primary_sources": len(urls), "operator_verified_sources": len(urls)}, lessons=lessons)
        # A representative URL is separate from already verified, topic-bound excerpts.
        if "public_evidence" in updated:
            try:
                _checked_public_references(updated["public_evidence"])
            except WorkflowError:
                updated.pop("public_evidence")
                updated.pop("public_discovery", None)
        key = store._idea_key(updated)
        if db.execute("SELECT id FROM ideas WHERE dedup_key=? AND id<>?", (key, idea_id)).fetchone():
            raise WorkflowError("같은 제목과 대표 출처의 기획이 이미 있습니다. 기존 기획을 확인하세요")
        db.execute("UPDATE ideas SET dedup_key=?,data=?,updated_at=? WHERE id=?", (key, canonical(updated), now(), idea_id))
        store._event(db, "idea_sources_updated", {"idea_id": idea_id, "operator_verified_sources": len(urls), "source_urls_hash": digest(urls)})
    return _visible_evidence(with_edit_hash(updated))


def select_reviewed_idea(store, idea_id, *, expected_hash, actor, lessons=(), public_evidence_ids=None, book_evidence_ids=None):
    """읽은 기획 판본의 선택과 작업 생성을 한 번에 저장한다. 출처 편집과 같은 DB 잠금을 쓴다."""
    with store.connection(transaction=True) as db:
        stored, _ = _reviewable_idea(db, idea_id, expected_hash)
        refreshed = score_idea(stored, lessons=lessons)
        if refreshed.get("blocked"):
            raise WorkflowError("정책·근거 검사에서 막힌 기획은 선택할 수 없습니다")
        try:
            reference_url(refreshed.get("source_url") or "")
        except ValueError as error:
            raise WorkflowError("기획을 선택하려면 공개 https 출처 URL이 필요합니다") from error
        selected = {**refreshed, "state": "selected", "selected_by": actor, "selected_at": now()}
        article = {"id": idea_id, "title": selected["title"], "url": selected["source_url"], "origin": "idea", "evidence": []}
        event = {"idea_id": idea_id, "actor": actor}
        references = _selected_public_references(stored, public_evidence_ids)
        if references:
            reference_hash = digest(references)
            article.update(approved_public_evidence=references, approved_public_evidence_hash=reference_hash)
            selected.update(approved_public_evidence_ids=public_evidence_ids, approved_public_evidence_hash=reference_hash)
            event.update(approved_public_evidence_count=len(references), approved_public_evidence_hash=reference_hash)
        books = _selected_book_references(stored, book_evidence_ids)
        if books:
            book_hash = digest(books)
            article.update(approved_book_evidence=books, approved_book_evidence_hash=book_hash)
            selected.update(approved_book_evidence_ids=book_evidence_ids, approved_book_evidence_hash=book_hash)
            event.update(approved_book_evidence_count=len(books), approved_book_evidence_hash=book_hash)
        db.execute("UPDATE ideas SET state='selected',data=?,updated_at=? WHERE id=?", (canonical(selected), now(), idea_id))
        store._event(db, "idea_selected", event)
        job = store._create_job(db, article, brief=selected.get("brief"))
        if references and approved_public_references(job["article"]) != references:
            raise WorkflowError("기존 작업과 기획의 승인 근거가 다릅니다. 기존 작업을 확인하세요")
        if books and approved_book_references(job["article"]) != books:
            raise WorkflowError("기존 작업과 기획의 승인 책 근거가 다릅니다. 기존 작업을 확인하세요")
    return {"idea": _visible_evidence(selected), "job": job}


def approve_existing_idea_evidence(store, idea_id, *, expected_hash, actor, public_evidence_ids, lessons=(), book_evidence_ids=None):
    """원고가 없는 기존 작업의 근거 선택을 화면에서 고른 그대로 바꾼다(공개 원문 문단과 책 문단)."""
    with store.connection(transaction=True) as db:
        idea, job = _reviewable_idea(db, idea_id, expected_hash, allow_selected=True)
        if job is None or score_idea(idea, lessons=lessons)["blocked"]:
            raise WorkflowError("기존 작업의 기획 및 대표 출처를 확인하세요")
        references = _selected_public_references(idea, public_evidence_ids)
        books = _selected_book_references(idea, book_evidence_ids)
        if not references and not books:
            raise WorkflowError("기존 작업에 넘길 원문 문단이나 책 문단을 한 개 이상 체크하세요")
        article = dict(job["article"])
        previous = approved_public_references(article)
        previous_books = approved_book_references(article)
        if previous != references or previous_books != books:
            event = {"idea_id": idea_id, "actor": actor}
            if references:
                version = digest(references)
                idea.update(approved_public_evidence_ids=public_evidence_ids, approved_public_evidence_hash=version)
                article.update(approved_public_evidence=references, approved_public_evidence_hash=version)
                event.update(approved_public_evidence_hash=version, approved_public_evidence_ids=public_evidence_ids)
            else:
                for key in ("approved_public_evidence_ids", "approved_public_evidence_hash"):
                    idea.pop(key, None)
                for key in ("approved_public_evidence", "approved_public_evidence_hash"):
                    article.pop(key, None)
            if books:
                book_version = digest(books)
                idea.update(approved_book_evidence_ids=book_evidence_ids, approved_book_evidence_hash=book_version)
                article.update(approved_book_evidence=books, approved_book_evidence_hash=book_version)
                event.update(approved_book_evidence_hash=book_version, approved_book_evidence_ids=book_evidence_ids)
            else:
                for key in ("approved_book_evidence_ids", "approved_book_evidence_hash"):
                    idea.pop(key, None)
                for key in ("approved_book_evidence", "approved_book_evidence_hash"):
                    article.pop(key, None)
            event.update(previous_approved_public_evidence=previous,
                         previous_approved_book_evidence_ids=[item["id"] for item in previous_books])
            job["article"] = article
            db.execute("UPDATE ideas SET data=?,updated_at=? WHERE id=?", (canonical(idea), now(), idea_id))
            store._write_job(db, job)
            store._event(db, "idea_public_evidence_approved", event, job["id"])
    return {"idea": {**_visible_evidence(with_edit_hash(idea)), "public_evidence_reviewable": True}, "job": job}
