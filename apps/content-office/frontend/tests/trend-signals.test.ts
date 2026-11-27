import test from "node:test";
import assert from "node:assert/strict";
import { parseSeeds, trendLine, type TrendRow } from "../lib/trend-signals.ts";

const base = { seed: "편입", label: "구글 자동완성", checked_at: "2026-11-27T07:12:00+09:00", items: [] as TrendRow["items"] };

test("trendLine shows suggestions as read, marks only new ones and never invents rates", () => {
  assert.equal(trendLine({ ...base, source: "google", status: "ok", items: [{ text: "편입 영어" }, { text: "편입 일정", new: true }] } as TrendRow), "편입 영어, 편입 일정 (새로)");
  assert.equal(trendLine({ ...base, source: "wikipedia", status: "ok", items: [], views: { title: "편입학", last7: 1400, prev7: 1000, change_pct: 40 } } as TrendRow), "최근 7일 1,400회, 그 전 7일 1,000회, +40%");
  assert.equal(trendLine({ ...base, source: "wikipedia", status: "ok", items: [], views: { title: "편입학", last7: 30, prev7: 20, change_pct: null } } as TrendRow), "최근 7일 30회, 그 전 7일 20회");
  assert.match(trendLine({ ...base, source: "youtube", status: "blocked", note: "막혔어요(429)" } as TrendRow), /^막혔어요/);
});

test("parseSeeds trims, drops blanks and duplicates and caps the count", () => {
  assert.deepEqual(parseSeeds(" 편입 \n\n오픽\n편입\na\nb\nc\nd\ne\nf\ng", 8), ["편입", "오픽", "a", "b", "c", "d", "e", "f"]);
});
