"""Operator-confirmed campaign snapshots, never coupon issuance or checkout verification."""
from __future__ import annotations

import copy
import re
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .store import WorkflowError, digest


def offer_snapshot(offer):
    if not offer:
        return None
    coupon = offer.get("coupon")
    coupon_keys = ("code", "discount_percent", "expires_at", "terms", "verified")
    if coupon:
        coupon_keys += tuple(key for key in ("usage_limit", "user_usage_limit") if coupon.get(key) is not None)
    snapshot = {"product": offer.get("product"), "price_krw": offer.get("price_krw"), "url": offer.get("url"), "note": offer.get("note"),
                "coupon": {key: coupon.get(key) for key in coupon_keys} if coupon else None}
    if offer.get("free_pdf"):
        snapshot["free_pdf"] = {key: offer["free_pdf"].get(key) for key in ("title", "url", "verified")}
    return snapshot


def offer_hash(offer):
    return digest(offer_snapshot(offer)) if offer else None


def require_campaign_packet(packet, offer):
    if (packet or {}).get("campaign_offer_hash") != offer_hash(offer):
        raise WorkflowError("상품·쿠폰 안내가 현재 원고·영상에 반영되지 않았습니다. 원고를 다시 검수하세요")


def source_version(packet, offer):
    return digest({"packet": packet, "offer": offer_snapshot(offer)}) if offer else digest(packet)


def _expiry(value):
    try:
        expiry = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        raise WorkflowError("쿠폰 만료 시각은 시간대가 포함된 ISO 날짜여야 합니다") from None
    if expiry.tzinfo is None:
        raise WorkflowError("쿠폰 만료 시각에 시간대가 필요합니다")
    return expiry


def require_offer_ready(offer):
    """Recheck before generation, approval and every external handoff; no remote verification."""
    if offer and offer.get("free_pdf") and offer["free_pdf"].get("verified") is not True:
        raise WorkflowError("무료 PDF의 Drive 링크 공개 열람을 확인한 뒤 제작하세요")
    if not offer or not offer.get("coupon"):
        return
    coupon = offer["coupon"]
    if coupon.get("verified") is not True:
        raise WorkflowError("쿠폰은 아직 미확인 기획입니다. 운영자가 스토어의 발급·조건을 직접 확인한 뒤 기록하세요")
    if not coupon.get("code") or not coupon.get("terms") or not offer.get("url"):
        raise WorkflowError("쿠폰 코드·조건·상품 URL 확인이 필요합니다")
    percent = coupon.get("discount_percent")
    if isinstance(percent, bool) or not isinstance(percent, int) or not 1 <= percent <= 100:
        raise WorkflowError("쿠폰 할인율은 1~100의 정수여야 합니다")
    if _expiry(coupon.get("expires_at")) <= datetime.now(timezone.utc):
        raise WorkflowError("쿠폰 사용 기간이 끝났습니다. 새 조건으로 원고·제작물과 승인을 다시 확인하세요")


def normalise_offer(offer, actor):
    if not str(actor or "").strip():
        raise WorkflowError("오퍼를 기록한 담당자가 필요합니다")
    product = str((offer or {}).get("product") or "").strip()
    if (not product and not (offer or {}).get("free_pdf")) or len(product) > 200:
        raise WorkflowError("상품 이름은 1~200자여야 합니다")
    price = (offer or {}).get("price_krw")
    if price is not None and (isinstance(price, bool) or not isinstance(price, int) or not 0 <= price <= 10**9):
        raise WorkflowError("가격은 0 이상의 정수(원) 또는 비워 둡니다")
    url = str((offer or {}).get("url") or "").strip() or None
    if url:
        try:
            parsed = urlsplit(url)
        except ValueError:
            raise WorkflowError("상품 주소는 https:// 로 시작하는 주소여야 합니다") from None
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or len(url) > 500 or any(ch.isspace() for ch in url):
            raise WorkflowError("상품 주소는 https:// 로 시작하는 주소여야 합니다")
    note = str((offer or {}).get("note") or "").strip() or None
    if note and len(note) > 500:
        raise WorkflowError("오퍼 메모는 500자 이하여야 합니다")
    coupon = (offer or {}).get("coupon")
    if coupon and not product:
        raise WorkflowError("구매 쿠폰에는 대상 상품이 필요합니다")
    if coupon is not None:
        if not isinstance(coupon, dict):
            raise WorkflowError("쿠폰 조건은 객체여야 합니다")
        code = str(coupon.get("code") or "").strip() or None
        terms = str(coupon.get("terms") or "").strip() or None
        expires = str(coupon.get("expires_at") or "").strip() or None
        percent = coupon.get("discount_percent")
        verified = coupon.get("verified", False)
        if code and (len(code) > 64 or any(ch.isspace() for ch in code)):
            raise WorkflowError("쿠폰 코드는 공백 없이 64자 이하여야 합니다")
        if terms and len(terms) > 500:
            raise WorkflowError("쿠폰 조건은 500자 이하여야 합니다")
        if percent is not None and (isinstance(percent, bool) or not isinstance(percent, int) or not 1 <= percent <= 100):
            raise WorkflowError("쿠폰 할인율은 1~100의 정수여야 합니다")
        if not isinstance(verified, bool):
            raise WorkflowError("쿠폰 확인 여부는 참 또는 거짓이어야 합니다")
        if expires:
            expires = _expiry(expires).isoformat()
        limits = {}
        for key in ("usage_limit", "user_usage_limit"):
            value = coupon.get(key)
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10**9:
                    raise WorkflowError("쿠폰 사용 횟수는 1~1,000,000,000의 정수여야 합니다. 전체 무제한은 비워 두세요")
                limits[key] = value
        coupon = {"code": code, "discount_percent": percent, "expires_at": expires, "terms": terms, "verified": verified, **limits}
    result = {"product": product, "price_krw": price, "url": url, "note": note, "coupon": coupon}
    pdf = (offer or {}).get("free_pdf")
    if pdf is not None:
        if not isinstance(pdf, dict) or not isinstance(pdf.get("verified", False), bool):
            raise WorkflowError("무료 PDF 정보와 확인 여부를 확인하세요")
        title = str(pdf.get("title") or "").strip()
        link = str(pdf.get("url") or "").strip()
        match = re.fullmatch(r"https://drive\.google\.com/file/d/([A-Za-z0-9_-]{10,200})/view(?:\?[^\s#]*)?", link)
        if not title or len(title) > 100 or not match:
            raise WorkflowError("무료 PDF 이름과 Google Drive 파일 공유 주소(/file/d/…/view)를 입력하세요")
        result["free_pdf"] = {"title": title, "url": f"https://drive.google.com/file/d/{match[1]}/view", "verified": pdf.get("verified", False)}
    if coupon and coupon["verified"]:
        require_offer_ready({key: value for key, value in result.items() if key != "free_pdf"})
    return result


def offer_url(offer):
    """HeoBrain 상품 링크의 쿠폰은 선택한 스냅샷만 사용한다. 할인 권한은 서버가 검증한다."""
    url = (offer or {}).get("url") or ""
    parsed = urlsplit(url)
    if parsed.hostname not in ("heobrain.kr", "www.heobrain.kr"):
        return url
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key.lower() != "coupon"]
    coupon = (offer or {}).get("coupon")
    if coupon:
        require_offer_ready(offer)
        query.append(("coupon", coupon["code"]))
    return urlunsplit(parsed._replace(query=urlencode(query)))


def offer_card_cta(offer):
    if not offer:
        return None
    require_offer_ready(offer)
    domain = urlsplit(offer_url(offer)).hostname or "상품 링크는 게시물 본문"
    coupon = offer.get("coupon")
    lines = ["무료 PDF · 프로필 링크"] if offer.get("free_pdf") else []
    if offer.get("product"):
        lines.append(domain)
        if coupon:
            lines.append(f"{coupon['discount_percent']}% 할인 · 쿠폰 {coupon['code']}")
    return "\n".join(lines) or None


def offer_text(offer):
    if not offer:
        return ""
    require_offer_ready(offer)
    parts = [str(offer["product"]).strip()] if offer.get("product") else []
    price = offer.get("price_krw")
    if price is not None and offer.get("product"):
        parts.append(f"기준가격 {price:,}원")
    coupon = offer.get("coupon")
    if coupon:
        percent = coupon["discount_percent"]
        parts.append(f"{percent}% 할인 쿠폰 {coupon['code']}")
        if price is not None:
            estimated = price - price * percent // 100
            parts.append(f"할인 예상 {estimated:,}원(실제 결제금액은 스토어 확인)")
        parts.append(f"사용기한 {coupon['expires_at']}")
        parts.append(f"조건: {coupon['terms']}")
        if coupon.get("user_usage_limit"):
            parts.append(f"1인 {coupon['user_usage_limit']}회")
        if coupon.get("usage_limit"):
            parts.append(f"전체 {coupon['usage_limit']}회 한정")
    if offer.get("url"):
        parts.append(offer_url(offer))
    if offer.get("note"):
        parts.append(offer["note"])
    lines = ["함께 보기: " + " · ".join(parts)] if parts else []
    if offer.get("free_pdf"):
        pdf = offer["free_pdf"]
        lines.append(f"무료 PDF: {pdf['title']} · {pdf['url']}\nInstagram·YouTube Shorts: 프로필 링크에서 자료와 구매 안내를 확인하세요.")
    return "\n\n".join(lines)


def campaign_packet(packet, offer):
    """Add an explicit CTA before critique/approval so voice and pixels use reviewed words."""
    if not offer and not packet.get("campaign_cta_scene"):
        return packet
    result = copy.deepcopy(packet)
    result["campaign_offer_hash"] = offer_hash(offer)
    result["campaign_offer"] = offer_snapshot(offer)
    video = result.get("video")
    if not video:
        return result
    scenes = list(video.get("scenes", []))
    # A previous campaign scene is replaced during reevaluation, never appended twice.
    if scenes and scenes[-1].get("narration") == result.get("campaign_cta_scene"):
        scenes.pop()
    if not offer:
        video["scenes"] = scenes
        result.pop("campaign_cta_scene", None)
        result.pop("campaign_offer_hash", None)
        result.pop("campaign_offer", None)
        return result
    require_offer_ready(offer)
    coupon = offer.get("coupon")
    domain = urlsplit(offer.get("url") or "").hostname or ""
    spoken_domain = "허브레인 점 케이알에서" if domain in ("heobrain.kr", "www.heobrain.kr") else "설명란의 상품 링크에서"
    narration = f"{offer['product']}은 {spoken_domain} 확인하세요." if offer.get("product") else ""
    caption = (offer["product"] + (" · " + domain.removeprefix("www.") if domain else "")) if offer.get("product") else ""
    if coupon:
        narration += f" 확인한 쿠폰은 {coupon['discount_percent']}퍼센트 할인입니다. 코드와 기간, 조건은 설명란을 확인하세요."
        caption += f" · {coupon['discount_percent']}% 할인 · 코드 {coupon['code']}"
    if offer.get("free_pdf"):
        narration += " 무료 PDF 자료는 프로필 링크에서 받으세요."
        caption = " · ".join(part for part in (caption, "무료 PDF · 프로필 링크") if part)
    scenes.append({"narration": narration, "caption": caption, "visual": "상품 안내 · 코드와 조건은 설명란 · 실제 상품 화면을 복제하지 않은 자체 도형"})
    video["scenes"] = scenes
    result["campaign_cta_scene"] = narration
    result["campaign_offer_hash"] = offer_hash(offer)
    result["campaign_offer"] = offer_snapshot(offer)
    return result
