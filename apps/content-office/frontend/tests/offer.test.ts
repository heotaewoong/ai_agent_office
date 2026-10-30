import test from "node:test";
import assert from "node:assert/strict";
import { campaignUrl, couponRegistrationUrl } from "../lib/offer.ts";
import { changeOfferDraft, estimatedCouponPrice, offerDraftForJob, offerDraftFromJob, offerExpiryInput, offerFromForm, syncOfferDraft, updateOfferDrafts, type OfferDraft } from "../lib/offer.ts";

test("오퍼 폼은 상품·https URL·0 이상의 정수 가격만 받는다", () => {
  const ok = offerFromForm({ product: " 7일 복습 플래너 ", price_krw: "12,000", url: "https://heobrain.kr/p/1", note: "" });
  assert.ok("offer" in ok);
  assert.deepEqual(ok.offer, { product: "7일 복습 플래너", price_krw: 12000, url: "https://heobrain.kr/p/1", note: "" });
  const noProduct = offerFromForm({ product: "", price_krw: "0", url: "https://a.b", note: "" });
  assert.ok("error" in noProduct && noProduct.error.includes("상품"));
  const badUrl = offerFromForm({ product: "x", price_krw: "0", url: "http://a.b", note: "" });
  assert.ok("error" in badUrl && badUrl.error.includes("https"));
  const badPrice = offerFromForm({ product: "x", price_krw: "-1", url: "https://a.b", note: "" });
  assert.ok("error" in badPrice && badPrice.error.includes("가격"));
  const nan = offerFromForm({ product: "x", price_krw: "만원", url: "https://a.b", note: "" });
  assert.ok("error" in nan);
});

test("50% 쿠폰은 미확정 기획과 직접 확인된 조건을 구분하고 한국 시간을 기록한다", () => {
  const form = { product: "편입 영어 단어장", price_krw: "9,900", url: "https://www.heobrain.kr/p/1", coupon_enabled: "yes", discount_percent: "50" };
  const draft = offerFromForm(form);
  assert.ok("offer" in draft);
  assert.deepEqual(draft.offer.coupon, { code: null, discount_percent: 50, expires_at: null, terms: null, verified: false });
  const incomplete = offerFromForm({ ...form, coupon_verified: "yes" });
  assert.ok("error" in incomplete && incomplete.error.includes("모두 필요"));
  const ready = offerFromForm({ ...form, coupon_code: "FIXTURE50", expires_at: "2026-11-01T09:00", coupon_terms: "가상 상품 한정 1인 1회", coupon_verified: "yes" }, Date.parse("2026-10-30T00:00:00Z"));
  assert.ok("offer" in ready);
  assert.equal(ready.offer.coupon?.verified, true);
  assert.equal(ready.offer.coupon?.expires_at, "2026-11-01T00:00:00.000Z");
  assert.equal(estimatedCouponPrice(9900, 50), 4950);
  assert.equal(estimatedCouponPrice(9999, 50), 5000);
  assert.equal(offerExpiryInput("2026-11-01T00:00:00.000Z"), "2026-11-01T09:00");
});

test("쿠폰 확인은 지난 만료·이상 할인율·가격 정밀도·URL 인증정보를 거부한다", () => {
  const form = { product: "x", price_krw: "9900", url: "https://www.heobrain.kr/p/1", coupon_enabled: "yes", coupon_code: "FIXTURE50", discount_percent: "50", expires_at: "2026-11-01T09:00", coupon_terms: "가상 조건", coupon_verified: "yes" };
  assert.ok("error" in offerFromForm(form, Date.parse("2026-11-01T00:00:00Z")));
  for (const value of ["0", "101", "1.5", "NaN"]) assert.ok("error" in offerFromForm({ ...form, discount_percent: value }));
  assert.ok("error" in offerFromForm({ ...form, price_krw: "9007199254740993" }));
  assert.ok("error" in offerFromForm({ ...form, url: "https://user:secret@www.heobrain.kr/" }));
  assert.equal(offerExpiryInput("invalid"), "");
});

const originalOffer = { product: "가상 상품", price_krw: 9900, url: "https://www.heobrain.kr/p/fixture", note: "기존 메모", captured_at: "2026-10-30T00:00:00Z", actor: "fixture" };
const first = { id: "job-a", offer: originalOffer, offer_hash: "a".repeat(64) };
const second = { ...first, id: "job-b", offer_hash: "b".repeat(64) };

test("캠페인 A/B 작업·화면 왕복은 각 폼과 편집 시작 판본을 보존한다", () => {
  let drafts: Record<string, OfferDraft> = {};
  drafts = updateOfferDrafts(drafts, first, (draft) => changeOfferDraft(draft, "note", "A에 남길 메모"));
  const firstDraft = drafts[first.id];
  drafts = updateOfferDrafts(drafts, second, (draft) => changeOfferDraft(draft, "coupon_code", "FIXTURE50"));
  assert.equal(offerDraftForJob(drafts, first), firstDraft);
  assert.equal(offerDraftForJob(drafts, first).form.note, "A에 남길 메모");
  assert.equal(offerDraftForJob(drafts, second).form.coupon_code, "FIXTURE50");
  const external = { ...first, offer: { ...originalOffer, product: "외부에서 바뀐 상품" }, offer_hash: "c".repeat(64) };
  const restored = offerDraftForJob(drafts, external);
  assert.equal(restored, firstDraft);
  assert.notEqual(restored.baseHash, external.offer_hash);
  assert.equal(restored.form.note, "A에 남길 메모");
});

test("캠페인 명시적 다시 읽기는 해당 캐시만 지우고 미편집 폼은 새 판본을 따른다", () => {
  let drafts: Record<string, OfferDraft> = {};
  assert.equal(updateOfferDrafts(drafts, first, (draft) => draft), drafts);
  for (const job of [first, second]) drafts = updateOfferDrafts(drafts, job, (draft) => changeOfferDraft(draft, "note", job.id));
  const latest = { ...first, offer: { ...originalOffer, note: "서버의 최신 메모" }, offer_hash: "c".repeat(64) };
  drafts = updateOfferDrafts(drafts, latest, () => offerDraftFromJob(latest));
  assert.deepEqual(Object.keys(drafts), [second.id]);
  assert.equal(offerDraftForJob(drafts, latest).form.note, "서버의 최신 메모");
  const read = syncOfferDraft(offerDraftFromJob(first), latest);
  assert.equal(read.baseHash, latest.offer_hash);
  assert.equal(read.form.note, "서버의 최신 메모");
});

test("저장 성공은 제출한 캠페인만 비우며 늦은 완료가 새 입력이나 다른 작업을 지우지 않는다", () => {
  let drafts: Record<string, OfferDraft> = {};
  for (const job of [first, second]) drafts = updateOfferDrafts(drafts, job, (draft) => changeOfferDraft(draft, "note", job.id));
  const submitted = drafts[first.id];
  const saved = { ...first, offer: { ...originalOffer, note: first.id }, offer_hash: "d".repeat(64) };
  const cleared = updateOfferDrafts(drafts, first, (current) => current === submitted ? offerDraftFromJob(saved) : current);
  assert.deepEqual(Object.keys(cleared), [second.id]);
  assert.equal(offerDraftForJob(cleared, saved).form.note, first.id);
  drafts = updateOfferDrafts(drafts, first, (current) => changeOfferDraft(current, "note", "제출 후 추가 입력"));
  const latestDraft = drafts[first.id];
  drafts = updateOfferDrafts(drafts, first, (current) => current === submitted ? offerDraftFromJob(saved) : current);
  assert.equal(drafts[first.id], latestDraft);
  assert.equal(drafts[first.id].form.note, "제출 후 추가 입력");
  assert.equal(drafts[second.id].form.note, second.id);
});

test("쿠폰 확인을 캐시로 되살린 뒤에도 조건을 수정하면 확인 표시가 해제된다", () => {
  let draft = offerDraftFromJob(first);
  draft = changeOfferDraft(draft, "coupon_verified", "yes");
  assert.equal(draft.form.coupon_verified, "yes");
  for (const key of ["coupon_code", "discount_percent", "expires_at", "coupon_terms", "product", "price_krw", "url"])
    assert.equal(changeOfferDraft(draft, key, "changed").form.coupon_verified, "no", key);
});
test("선택한 쿠폰만 링크에 싣고 미선택하면 이전 코드를 제거한다", () => {
  const offer = { product: "합성상품", price_krw: 1000, url: "https://heobrain.kr/product/p?coupon=OLD&Coupon=OLD2", note: "", actor: "fixture", captured_at: "", coupon: { code: "FIXTURE20", discount_percent: 20, expires_at: "2099-01-01T00:00:00Z", terms: "합성", verified: true } };
  assert.equal(campaignUrl(offer), "https://heobrain.kr/product/p?coupon=FIXTURE20");
  assert.equal(campaignUrl({ ...offer, coupon: null }), "https://heobrain.kr/product/p");
  assert.equal(campaignUrl({ ...offer, url: "https://example.com/item" }), "https://example.com/item");
});

test("초기 선택의 상품·할인율·한국 종료일·사용 횟수를 등록 초안에 전달한다", () => {
  const form = { product: "합성 상품", price_krw: "9900", url: "https://heobrain.kr/product/p-1", coupon_enabled: "yes", coupon_code: "FIXTURE20", discount_percent: "20", expires_at: "2099-11-01", coupon_terms: "대상 상품 한정", user_usage_limit: "1", usage_limit: "100" };
  const ready = offerFromForm({ ...form, coupon_verified: "yes" });
  assert.ok("offer" in ready);
  assert.equal(ready.offer.coupon?.expires_at, "2099-11-01T14:59:59.999Z");
  assert.equal(ready.offer.coupon?.usage_limit, 100);
  const url = new URL(couponRegistrationUrl(form)!);
  assert.equal(url.searchParams.get("product"), "p-1");
  assert.equal(url.searchParams.get("valid_until"), "2099-11-01");
  assert.equal(url.searchParams.get("usage_limit"), "100");
  assert.equal(couponRegistrationUrl({ ...form, url: "https://example.com/item" }), null);
  assert.ok("error" in offerFromForm({ ...form, usage_limit: "-1" }));
});

test("무료 PDF와 상품/쿠폰 선택은 독립적이며 PDF만 제공할 수 있다", () => {
  const pdf = { free_pdf_enabled: "yes", free_pdf_title: "합성 무료 점검표", free_pdf_url: "https://drive.google.com/file/d/fixturePdf123456/view?usp=sharing", free_pdf_verified: "yes" };
  const onlyPdf = offerFromForm({ ...pdf, promotion_mode: "none", product: "이전 상품", url: "https://heobrain.kr/product/old?coupon=OLD", coupon_enabled: "yes", coupon_code: "OLD" });
  assert.ok("offer" in onlyPdf);
  assert.equal(onlyPdf.offer.product, "");
  assert.equal(onlyPdf.offer.url, "");
  assert.equal(onlyPdf.offer.coupon, undefined);
  assert.equal(onlyPdf.offer.free_pdf?.url, "https://drive.google.com/file/d/fixturePdf123456/view");
  const both = offerFromForm({ ...pdf, promotion_mode: "coupon", product: "합성 상품", price_krw: "9900", url: "https://heobrain.kr/product/p", coupon_enabled: "yes", coupon_code: "FIXTURE20", discount_percent: "20" });
  assert.ok("offer" in both && both.offer.free_pdf && both.offer.coupon);
  const productOnly = offerFromForm({ ...pdf, free_pdf_enabled: "no", promotion_mode: "product", product: "합성 상품", price_krw: "9900", url: "https://heobrain.kr/product/p" });
  assert.ok("offer" in productOnly && !productOnly.offer.free_pdf);
  assert.ok("error" in offerFromForm({ ...pdf, promotion_mode: "none", free_pdf_url: "https://example.com/file.pdf" }));
});

test("PDF 주소 수정은 이전 공개 확인을 해제하고 작업별 폼을 보존한다", () => {
  const original = { form: { free_pdf_enabled: "yes", free_pdf_title: "합성", free_pdf_url: "https://drive.google.com/file/d/fixturePdf123456/view", free_pdf_verified: "yes", coupon_verified: "yes" }, baseHash: null, dirty: false };
  const changed = changeOfferDraft(original, "free_pdf_url", "https://drive.google.com/file/d/fixturePdf987654/view");
  assert.equal(changed.form.free_pdf_verified, "no");
  assert.equal(original.form.free_pdf_verified, "yes");
});
