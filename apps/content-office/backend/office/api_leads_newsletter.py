"""리드마그넷 동의 장부 · 뉴스레터 회차(③) · 상품 오퍼 스냅샷 경로.

api.create_app이 `register(app, store)`를 한 번 부른다. 세션·CSRF·허용 출처 검사와 WorkflowError→409 변환은
api.py의 공통 미들웨어·예외 처리기가 하므로 여기서는 입력 모양 검증과 호출만 한다.
이메일은 leads 표 밖으로 나가지 않으며, 어떤 경로도 메일을 보내지 않는다(오너가 메일러에서 직접 보낸 뒤 기록만 남긴다).
"""
from __future__ import annotations

from typing import Literal

from fastapi import Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import leads as leads_module
from . import newsletter

ACTOR = "local-operator"


class LeadInput(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    magnet_key: str = Field(min_length=1, max_length=100)
    source: Literal["homepage", "youtube", "instagram", "threads", "blog", "newsletter", "other"]
    consent_version: str = Field(min_length=1, max_length=50)
    consent_text: str = Field(min_length=1, max_length=2000)
    consent_purpose: Literal["newsletter", "lead_magnet_delivery"] | None = None


class NewsletterInput(BaseModel):
    issue_key: str = Field(min_length=1, max_length=64)
    subject: str | None = Field(default=None, max_length=150)


class NewsletterReview(BaseModel):
    decision: Literal["approve", "reject"]
    expected_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    note: str | None = Field(default=None, max_length=500)


class NewsletterSent(BaseModel):
    expected_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class CouponInput(BaseModel):
    usage_limit: int | None = Field(default=None, ge=1, le=10**9, strict=True)
    user_usage_limit: int | None = Field(default=None, ge=1, le=10**9, strict=True)
    code: str | None = Field(default=None, max_length=64)
    discount_percent: int | None = Field(default=None, ge=1, le=100, strict=True)
    expires_at: str | None = Field(default=None, max_length=50)
    terms: str | None = Field(default=None, max_length=500)
    verified: bool = Field(default=False, strict=True)


class OfferInput(BaseModel):
    expected_offer_hash: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    product: str = Field(max_length=200)
    price_krw: int | None = Field(default=None, ge=0, le=10**9, strict=True)
    url: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=500)
    coupon: CouponInput | None = None


def dashboard_counts(store):
    """대시보드용 건수만. 이메일·수신자 ID는 나가지 않는다."""
    states = [issue["state"] for issue in newsletter.issues(store)]
    return {"leads": {"consented": leads_module.summary(store)["consented"]}, "newsletters": {"draft": states.count("draft"), "approved": states.count("approved")}}


def register(app, store):
    @app.post("/api/leads")
    def register_lead(body: LeadInput):
        record, created = leads_module.register_lead(store, email=body.email, magnet_key=body.magnet_key, source=body.source, consent_version=body.consent_version, consent_text=body.consent_text, consent_purpose=body.consent_purpose)
        return JSONResponse({"lead": record}, status_code=201 if created else 200)

    @app.get("/api/leads/summary")
    def lead_summary():
        return leads_module.summary(store)

    @app.get("/api/leads")
    def list_leads():
        return {"leads": leads_module.leads(store)}

    @app.post("/api/leads/{lead_id}/withdraw")
    def withdraw_lead(lead_id: str):
        return {"lead": leads_module.withdraw_lead(store, lead_id)}

    @app.post("/api/leads/{lead_id}/sent")
    def lead_sent(lead_id: str):
        # 오너가 자료를 직접 보냈다는 확인 기록. 여기서는 아무것도 보내지 않는다.
        return {"lead": leads_module.mark_sent(store, lead_id, ACTOR)}

    @app.post("/api/jobs/{job_id}/newsletter", status_code=201)
    def build_newsletter(job_id: str, body: NewsletterInput):
        return newsletter.build_issue(store, job_id, issue_key=body.issue_key, subject=body.subject, actor=ACTOR)

    @app.get("/api/newsletters")
    def list_newsletters():
        return {"issues": newsletter.issues(store)}

    @app.get("/api/newsletters/{issue_id}")
    def get_newsletter(issue_id: str):
        return newsletter.issue(store, issue_id)

    @app.get("/api/newsletters/{issue_id}/export")
    def export_newsletter(issue_id: str):
        record = newsletter.export_issue(store, issue_id)
        return Response(record["markdown"], media_type="text/markdown; charset=utf-8", headers={"Cache-Control": "no-store", "Content-Disposition": f'attachment; filename="newsletter-{record["issue_key"]}.md"'})

    @app.post("/api/newsletters/{issue_id}/review")
    def review_newsletter(issue_id: str, body: NewsletterReview):
        # 승인③은 세션의 사람 검토자가 기록한다. 승인해도 발송은 일어나지 않는다.
        return newsletter.review_issue(store, issue_id, body.decision, expected_hash=body.expected_hash, actor=ACTOR, note=body.note)

    @app.post("/api/newsletters/{issue_id}/rebuild")
    def rebuild_newsletter(issue_id: str):
        return newsletter.rebuild_issue(store, issue_id, actor=ACTOR)

    @app.post("/api/newsletters/{issue_id}/sent")
    def newsletter_sent(issue_id: str, body: NewsletterSent):
        return newsletter.mark_sent(store, issue_id, expected_hash=body.expected_hash, actor=ACTOR)

    @app.put("/api/jobs/{job_id}/offer")
    def set_offer(job_id: str, body: OfferInput):
        return store.set_offer(job_id, body.model_dump(exclude={"expected_offer_hash"}), ACTOR, expected_hash=body.expected_offer_hash)

    @app.delete("/api/jobs/{job_id}/offer")
    def clear_offer(job_id: str, expected_offer_hash: str = Query(pattern=r"^[0-9a-f]{64}$")):
        return store.clear_offer(job_id, ACTOR, expected_hash=expected_offer_hash)
