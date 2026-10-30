from urllib.parse import parse_qs, urlsplit

import pytest
from PIL import Image

from office.cards import plan_cards, render_slide
from office.offers import offer_card_cta, offer_text, offer_url
from office.store import Store, WorkflowError
from tests.test_cards import FakeCardsProvider, approved_job, good_slides
from tests.test_offer import coupon_offer


def test_selected_coupon_replaces_stale_link_code_and_preserves_product():
    offer = {**coupon_offer(), "url": "https://www.heobrain.kr/product/product-1?coupon=OLD&Coupon=OTHER&utm_source=instagram#details"}
    url = urlsplit(offer_url(offer))
    assert url.path == "/product/product-1" and url.fragment == "details"
    assert parse_qs(url.query) == {"utm_source": ["instagram"], "coupon": ["FIXTURE50"]}
    assert offer_url(offer) in offer_text(offer)
    assert "FIXTURE50" in offer_card_cta(offer)
    assert "coupon=OLD" in offer["url"]  # snapshot input is never mutated


def test_coupon_off_removes_stale_code_and_leaves_external_sites_unchanged():
    offer = {**coupon_offer(), "url": "https://heobrain.kr/checkout?product=p&coupon=OLD", "coupon": None}
    assert offer_url(offer) == "https://heobrain.kr/checkout?product=p"
    assert "쿠폰" not in offer_text(offer)
    external = {**coupon_offer(), "url": "https://other.example/product"}
    assert offer_url(external) == external["url"]


def test_unverified_coupon_cannot_be_exported_as_live_promotion():
    offer = {**coupon_offer(verified=False), "url": "https://heobrain.kr/product/p"}
    with pytest.raises(WorkflowError):
        offer_url(offer)


def test_cards_receive_campaign_context_and_render_last_card_cta(tmp_path):
    store = Store(tmp_path / "state")
    job = approved_job(store, approve=False)
    store.set_offer(job["id"], {**coupon_offer(), "url": "https://heobrain.kr/product/p"}, "fixture")
    from office.offers import campaign_packet
    job = store.job(job["id"])
    packet = campaign_packet(job["source_packet"], job["offer"])
    packet["quality"] = {"status": "passed", "critical": False}
    current = store.save_source(job["id"], packet, expected_hash=job["source_hash"])
    store.review_source(job["id"], current["source_hash"], "approved", "fixture")
    provider = FakeCardsProvider([good_slides(7)])
    cards = plan_cards(store, job["id"], provider=provider, images=False)
    assert '"campaign_offer"' in provider.calls[0]["user"]
    assert "FIXTURE50" in provider.calls[0]["user"]
    assert cards["slides"][-1]["cta"] == "heobrain.kr\n50% 할인 · 쿠폰 FIXTURE50"
    assert all(slide.get("cta") is None for slide in cards["slides"][:-1])
    with Image.open(store.artifacts / cards["slides"][-1]["artifact"]["path"]) as image:
        assert image.size == (1080, 1440)
    from tests.test_offer import api
    import io
    import zipfile
    client, _ = api(store)
    response = client.get(f"/api/jobs/{job['id']}/cards/archive", params={"version": cards["version"], "source_hash": cards["source_hash"]})
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.testzip() is None
        campaign = archive.read("campaign.txt").decode("utf-8")
        assert "coupon=FIXTURE50" in campaign and "프로필 링크" in campaign


def test_overlong_card_coupon_fails_instead_of_clipping(tmp_path):
    with pytest.raises(WorkflowError):
        render_slide({"title": "쿠폰 안내", "body": "조건은 본문에서 확인해요."}, 7, 7, tmp_path / "too-long.png", promotion="쿠폰 " + "가" * 500)


def test_usage_limits_are_validated_and_kept_in_content_and_hash():
    from office.offers import normalise_offer, offer_hash
    offer = coupon_offer(usage_limit=100, user_usage_limit=1)
    saved = normalise_offer(offer, "fixture")
    assert saved["coupon"]["usage_limit"] == 100
    assert "전체 100회" in offer_text(saved) and "1인 1회" in offer_text(saved)
    assert offer_hash(saved) != offer_hash(coupon_offer())
    with pytest.raises(WorkflowError):
        normalise_offer(coupon_offer(usage_limit=-1), "fixture")
