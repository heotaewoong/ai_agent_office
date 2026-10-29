import test from "node:test";
import assert from "node:assert/strict";
import { offerFromForm } from "../lib/offer.ts";

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
