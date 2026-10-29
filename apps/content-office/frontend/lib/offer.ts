import type { Job, Offer, OfferInput } from "./types";

type Form = Record<string, string>;
type FormOffer = Omit<OfferInput, "expected_offer_hash">;
type OfferJob = Pick<Job, "id" | "offer" | "offer_hash">;
export type OfferDraft = { form: Form; baseHash: string | null; dirty: boolean };
export type OfferDraftUpdate = (current: OfferDraft) => OfferDraft;

export function offerFormFromOffer(offer?: Offer | null): Form {
  return {
    product: offer?.product ?? "",
    price_krw: offer ? String(offer.price_krw) : "",
    url: offer?.url ?? "",
    note: offer?.note ?? "",
    coupon_enabled: offer?.coupon ? "yes" : "no",
    coupon_code: offer?.coupon?.code ?? "",
    discount_percent: offer?.coupon?.discount_percent == null ? "" : String(offer.coupon.discount_percent),
    expires_at: offerExpiryInput(offer?.coupon?.expires_at),
    coupon_terms: offer?.coupon?.terms ?? "",
    coupon_verified: offer?.coupon?.verified ? "yes" : "no",
  };
}

export function offerDraftFromJob(job: OfferJob): OfferDraft {
  return { form: offerFormFromOffer(job.offer), baseHash: job.offer_hash ?? null, dirty: false };
}

export function syncOfferDraft(draft: OfferDraft, job: OfferJob): OfferDraft {
  return draft.dirty || draft.baseHash === (job.offer_hash ?? null) ? draft : offerDraftFromJob(job);
}

export function changeOfferDraft(draft: OfferDraft, key: string, value: string): OfferDraft {
  return { ...draft, form: { ...draft.form, [key]: value, coupon_verified: key === "coupon_verified" ? value : "no" }, dirty: true };
}

export function offerDraftForJob(drafts: Record<string, OfferDraft>, job: OfferJob): OfferDraft {
  return syncOfferDraft(drafts[job.id] ?? offerDraftFromJob(job), job);
}

/** 브리프와 같은 작업별 임시 캐시 패턴. 저장 성공·명시 초기화는 해당 작업만 비운다. */
export function updateOfferDrafts(drafts: Record<string, OfferDraft>, job: OfferJob, update: OfferDraftUpdate): Record<string, OfferDraft> {
  const next = update(offerDraftForJob(drafts, job));
  if (next.dirty) return drafts[job.id] === next ? drafts : { ...drafts, [job.id]: next };
  if (!drafts[job.id]) return drafts;
  const result = { ...drafts };
  delete result[job.id];
  return result;
}

/** 실제 발급과 분리한 캠페인 기록. 시간대 없는 입력은 명시적으로 한국 시간으로 해석한다. */
export function offerFromForm(form: Form, now = Date.now()): { offer: FormOffer } | { error: string } {
  const product = (form.product ?? "").trim();
  if (!product || product.length > 200) return { error: "상품 이름은 1~200자로 입력하세요." };
  const url = (form.url ?? "").trim();
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "https:" || !parsed.hostname || parsed.username || parsed.password || url.length > 500 || /\s/.test(url)) throw new Error();
  } catch {
    return { error: "상품 URL은 사용자명·비밀번호 없는 https 주소로 입력하세요." };
  }
  const priceText = (form.price_krw ?? "").replace(/,/g, "").trim();
  const price = Number(priceText);
  if (!/^\d+$/.test(priceText) || !Number.isSafeInteger(price) || price > 1_000_000_000) return { error: "가격은 0~1,000,000,000 사이 정수(원)로 입력하세요." };
  const note = (form.note ?? "").trim();
  if (note.length > 500) return { error: "메모는 500자 이내로 입력하세요." };
  const offer: FormOffer = { product, price_krw: price, url, note };
  if (form.coupon_enabled !== "yes") return { offer };
  const percentText = (form.discount_percent ?? "").trim();
  const percent = percentText ? Number(percentText) : null;
  if (percent !== null && (!/^\d+$/.test(percentText) || percent < 1 || percent > 100))
    return { error: "할인율은 1~100 사이 정수로 입력하세요. 미정이면 비워 두세요." };
  const expires = (form.expires_at ?? "").trim();
  const date = expires ? new Date(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(expires) ? `${expires}:00+09:00` : expires) : null;
  if (date && !Number.isFinite(date.getTime())) return { error: "쿠폰 만료 시각을 확인하세요." };
  const code = (form.coupon_code ?? "").trim();
  const terms = (form.coupon_terms ?? "").trim();
  if (code.length > 64 || /\s/.test(code)) return { error: "쿠폰 코드는 공백 없이 64자 이내로 입력하세요." };
  if (terms.length > 500) return { error: "쿠폰 조건은 500자 이내로 입력하세요." };
  const verified = form.coupon_verified === "yes";
  if (verified && (!code || percent === null || !date || date.getTime() <= now || !terms))
    return { error: "확인 완료로 기록하려면 실제 코드·할인율·미래 만료 시각·적용 조건이 모두 필요합니다." };
  offer.coupon = { code: code || null, discount_percent: percent, expires_at: date?.toISOString() ?? null, terms: terms || null, verified };
  return { offer };
}

export function estimatedCouponPrice(price: number, percent: number): number {
  return price - Math.floor(price * percent / 100);
}

/** 입력칸은 한국 시간, 서버 기록은 시간대 있는 ISO 문자열로 유지한다. */
export function offerExpiryInput(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "";
  return new Date(date.getTime() + 9 * 60 * 60 * 1000).toISOString().slice(0, 16);
}
