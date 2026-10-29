import type { OfferInput } from "./types";

type Form = Record<string, string>;

/** 오퍼 스냅샷 폼 → 서버 입력. 상품명 필수, URL은 https만, 가격은 0 이상의 정수(쉼표 허용). */
export function offerFromForm(form: Form): { offer: OfferInput } | { error: string } {
  const product = (form.product ?? "").trim();
  if (!product) return { error: "상품 이름을 입력하세요." };
  const url = (form.url ?? "").trim();
  if (!/^https:\/\/\S+$/.test(url)) return { error: "상품 URL은 https로 시작해야 합니다." };
  const priceText = (form.price_krw ?? "").replace(/,/g, "").trim();
  if (!/^\d+$/.test(priceText)) return { error: "가격은 0 이상의 정수(원)로 입력하세요." };
  return { offer: { product, price_krw: Number(priceText), url, note: (form.note ?? "").trim() } };
}
