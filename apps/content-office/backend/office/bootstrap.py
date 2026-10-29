from __future__ import annotations
import json
import os
from pathlib import Path
from .feeds import collect_feeds, normalize_url, deduplicate_events
from .store import Store, digest, now

BACKEND = Path(__file__).resolve().parents[1]
WORKSPACE = Path(__file__).resolve().parents[4]


def default_store():
    return Store(os.environ.get("OFFICE_STATE_DIR", str(Path.home() / ".local/state/heobrain-content-office")))


def enrich(articles):
    seed = json.loads((BACKEND / "config/editorial-seed.json").read_text(encoding="utf-8"))
    selected = {normalize_url(item["primary_url"]): item for item in seed["selected"]}
    candidates = {normalize_url(item["url"]): item for item in seed["candidates"]}
    for article in articles:
        candidate = candidates.get(normalize_url(article["url"]))
        if candidate:
            article["event_id"] = candidate.get("event_id") or candidate["id"]
        if any(part in article["url"] for part in ("chatgpt-ads-expands-26-new-countries", "building-chatgpt-ad-stack")):
            article["event_id"] = "chatgpt-ads-2026-10-21"
        item = selected.get(normalize_url(article["url"]))
        if not item:
            continue
        article.update(editorial_title=item["headline_ko"], selected=True, editorial_rank=item["rank"], score=100 - item["rank"], score_note="원문을 확인한 편집 선정. 객관적 성과 점수 아님", score_reasons=[item["reader_value_ko"], item["blog_angle_ko"]], evidence=[{"id": claim["id"], "url": claim["evidence_url"], "claim": claim["statement_ko"], "scope": claim["scope"], "numbers": claim["numbers"], "evidence_type": claim["evidence_type"]} for claim in item["claims"]], limitations=item["uncertainty_ko"], avoid=item["avoid_ko"], hook=item["hook_ko"], category=item["category"], evidence_checked_at=seed["retrieved_at"])
        for evidence in article["evidence"]:
            if evidence["id"] == "TB3":
                evidence["checks"] = [{"prohibited_pattern": r"(반복|전부|모두|항상)[^。.!?\n]{0,25}(87[.,]97|89[.,]35)", "message": "반복 신뢰성과 20회 중 한번 이상 성공을 혼동했는지 확인하세요"}]
            if evidence["id"] == "AD2":
                evidence["checks"] = [{"prohibited_pattern": r"누적\s*(집행\s*횟수|캠페인\s*횟수)", "message": "누적 광고주 수를 캠페인 집행 횟수로 바꾸지 마세요"}]
    return articles


def korean_cards(store, articles, provider=None, limit=None):
    """화면 앞쪽 기사부터 한국어 카드(제목·두 문장 요약·읽을 이유)를 만든다.

    원문이 같으면 이전 카드를 재사용한다. 키·예산·작업 시간 때문에 호출할 수 없으면 멈추고 기록만 남긴다.
    """
    from .korean import card_source_hash, korean_card
    from .store import WorkflowError
    limit = int(os.environ.get("OFFICE_CARD_KO_LIMIT", "9")) if limit is None else limit
    previous = {article["id"]: article.get("card_ko") for article in store.articles_list()}
    for article in articles:
        old = previous.get(article["id"])
        if old and old.get("source_hash") == card_source_hash(article):
            article["card_ko"] = old
    ordered = sorted(articles, key=lambda a: (a.get("score", 0), a.get("published_at") or ""), reverse=True)
    pending = [a for a in ordered[:limit] if not a.get("card_ko")]
    made, stopped = 0, None
    if pending:
        if provider is None:
            from .providers import Provider
            provider = Provider(store)
        for article in pending:
            try:
                article["card_ko"] = korean_card(article, provider)
                made += 1
            except WorkflowError as error:
                stopped = str(error)
                break
    store.event("korean_cards", {"role": "국어 검수", "made": made, "pending": len(pending), "stopped": stopped, "passed": sum(1 for a in articles if (a.get("card_ko") or {}).get("check", {}).get("passed"))})
    return articles


def refresh(store, provider=None):
    report = collect_feeds(store.root)
    articles = deduplicate_events(enrich(report.pop("articles")))
    report["active_article_ids"] = [article["id"] for article in articles]
    report["eligible_items"] = len(articles)
    articles = korean_cards(store, articles, provider=provider)
    store.save_articles(articles)
    store.set_setting("feed_report", report)
    store.event("rss_refreshed", {"role": "RSS 연구", "total_items": report["total_items"], "eligible_items": report["eligible_items"], "failed_feeds": [f["name"] for f in report["feeds"] if f["state"] != "ok"]})
    return report


def initialize(store, *, live=True, create_selected=False):
    window_path = WORKSPACE / "research/content-office-2026-10-26/work-window.json"
    if store.setting("work_window") is None and window_path.is_file():
        store.set_setting("work_window", json.loads(window_path.read_text(encoding="utf-8")))
    if live:
        refresh(store)
    if create_selected:
        selected = sorted([a for a in store.articles_list() if a.get("selected")], key=lambda a: a["editorial_rank"])
        for article in selected[:3]:
            job = store.create_job(article)
            if not job["source_packet"]:
                store.enqueue("draft", {"job_id": job["id"]}, key=f"draft:{job['id']}:initial")
    return {"articles": len(store.articles_list()), "jobs": len(store.jobs()), "budget": store.budget(), "at": now()}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--create-selected", action="store_true")
    args = parser.parse_args()
    print(json.dumps(initialize(default_store(), create_selected=args.create_selected), ensure_ascii=False, indent=2))
