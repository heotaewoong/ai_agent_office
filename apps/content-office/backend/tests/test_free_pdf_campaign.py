import pytest

from office.offers import campaign_packet, normalise_offer, offer_card_cta, offer_hash, offer_snapshot, offer_text, require_offer_ready
from office.store import Store, WorkflowError
from tests.test_offer import api, coupon_offer
from tests.test_cards import approved_job

PDF = {"title": "합성 무료 점검표", "url": "https://drive.google.com/file/d/fixturePdf123456/view", "verified": True}


@pytest.mark.parametrize("product,coupon,pdf", [(False, False, True), (True, False, False), (True, True, False), (True, False, True), (True, True, True)])
def test_resource_and_product_coupon_are_independent(product, coupon, pdf):
    offer = coupon_offer() if product else {"product": "", "price_krw": 0, "url": ""}
    if not coupon:
        offer.pop("coupon", None)
    if pdf:
        offer["free_pdf"] = PDF
    saved = normalise_offer(offer, "fixture")
    require_offer_ready(saved)
    text = offer_text(saved)
    cta = offer_card_cta(saved)
    assert ("fixturePdf123456" in text) is pdf
    assert ("FIXTURE50" in text) is coupon
    assert ("무료 PDF" in cta) is pdf
    packet = campaign_packet({"title": "합성", "body": "본문", "video": {"scenes": [{"narration": "본론", "caption": "본론"}]}}, saved)
    assert ("무료 PDF" in packet["video"]["scenes"][-1]["narration"]) is pdf
    assert len(campaign_packet(packet, saved)["video"]["scenes"]) == 2
    assert offer_snapshot(saved).get("free_pdf") == (PDF if pdf else None)


def test_none_and_deselecting_resource_never_leave_old_cta_or_link():
    assert offer_text(None) == "" and offer_card_cta(None) is None
    offer = {**coupon_offer(), "free_pdf": PDF}
    packet = campaign_packet({"video": {"scenes": [{"narration": "본론", "caption": "본론"}]}}, offer)
    product_only = coupon_offer()
    changed = campaign_packet(packet, product_only)
    assert "무료 PDF" not in changed["video"]["scenes"][-1]["narration"]
    assert PDF["url"] not in offer_text(product_only)
    cleared = campaign_packet(changed, None)
    assert len(cleared["video"]["scenes"]) == 1


def test_unchecked_drive_link_is_draft_only_and_wrong_hosts_are_rejected():
    offer = {"product": "", "free_pdf": {**PDF, "verified": False}}
    saved = normalise_offer(offer, "fixture")
    with pytest.raises(WorkflowError, match="공개 열람"):
        require_offer_ready(saved)
    for link in ("http://drive.google.com/file/d/fixturePdf123456/view", "https://drive.google.com.evil.test/file/d/fixturePdf123456/view", "https://drive.google.com/drive/folders/fixturePdf123456", "https://example.com/x.pdf"):
        with pytest.raises(WorkflowError):
            normalise_offer({"product": "", "free_pdf": {**PDF, "url": link}}, "fixture")


def test_api_resource_only_and_resource_edit_invalidate_prior_approval(tmp_path):
    store = Store(tmp_path)
    job = approved_job(store)
    client, headers = api(store)
    response = client.put(f"/api/jobs/{job['id']}/offer", headers=headers, json={"expected_offer_hash": None, "product": "", "price_krw": 0, "url": "", "free_pdf": PDF})
    assert response.status_code == 200
    saved = response.json()
    assert saved["offer"]["free_pdf"] == PDF
    assert saved["source_approval"] is None and saved["source_hash"] != job["source_hash"]
    assert offer_hash(saved["offer"]) == saved["offer_hash"]
    stale = client.put(f"/api/jobs/{job['id']}/offer", headers=headers, json={"expected_offer_hash": None, "product": "", "free_pdf": PDF})
    assert stale.status_code == 409


def test_pdf_and_coupon_are_present_in_all_channel_exports_and_shared_handoff(tmp_path):
    from office.exports import blog_markdown, write_video_exports, write_campaign_exports
    from office.channel_handoff import write_channel_handoffs
    packet = {"title": "합성 원고", "body": "첫 문단입니다.\n\n둘째 문단입니다.", "evidence": [], "video": {"title": "합성 영상", "description": "설명", "scenes": []}}
    offer = {**coupon_offer(), "free_pdf": PDF}
    assert PDF["url"] in blog_markdown(packet, offer)
    write_video_exports(packet, tmp_path, offer)
    assert PDF["url"] in (tmp_path / "description.txt").read_text(encoding="utf-8")
    write_channel_handoffs(packet, tmp_path, offer, source_hash="a" * 64, language="ko")
    caption = (tmp_path / "instagram-main-caption.txt").read_text(encoding="utf-8")
    assert PDF["url"] in caption and "FIXTURE50" in caption
    files = write_campaign_exports(offer, tmp_path)
    assert len(files) == 2
    import json
    metadata = json.loads((tmp_path / "campaign-delivery.json").read_text(encoding="utf-8"))
    assert metadata["free_pdf_selected"] and metadata["coupon_selected"]
    assert metadata["profile_links_updated"] is False and metadata["automatic_dm_enabled"] is False
