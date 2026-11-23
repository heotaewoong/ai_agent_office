import assert from "node:assert/strict";
import test from "node:test";
import { api } from "../lib/api.ts";
import { officeHref, officeRoute } from "../lib/navigation.ts";
import { areaForSegment, fileToBase64, filterSources, safeOriginRef, sourceSummary, splitLinks, type SourceItem } from "../lib/source-library.ts";

const item = (patch: Partial<SourceItem>): SourceItem => ({
  id: "a", kind: "link", area: "B", area_label: "AI 활용과 자동화", mine: false, title: "Hermes 공식 문서", url: "https://example.org/hermes",
  status: "done", note: "", passages: 6, use_as_evidence: false, origin: "manual", origin_ref: null, file_name: null,
  created_at: "2026-11-23T12:00:00+00:00", updated_at: "2026-11-23T12:00:00+00:00", ...patch,
});

test("자료 창고 주소는 화면과 서로 바뀐다", () => {
  assert.equal(officeHref("sources"), "/sources");
  assert.deepEqual(officeRoute("/sources"), { view: "sources" });
});

test("붙여 넣은 글에서 주소만 한 번씩 고른다", () => {
  assert.deepEqual(splitLinks("https://a.example/1\n메모 https://b.example/2, https://a.example/1 ftp://x"), ["https://a.example/1", "https://b.example/2"]);
  assert.deepEqual(splitLinks("주소 없음"), []);
});

test("분야·근거·내 자료·확인 필요와 낱말로 목록을 거른다", () => {
  const rows = [
    item({ id: "a" }),
    item({ id: "b", area: "C", use_as_evidence: true, title: "간격 복습 논문" }),
    item({ id: "c", mine: true, kind: "memo", url: null, title: "편입 경험" }),
    item({ id: "d", status: "needs_check", title: "막힌 글" }),
  ];
  assert.deepEqual(filterSources(rows, "", "all").map((row) => row.id), ["a", "b", "c", "d"]);
  assert.deepEqual(filterSources(rows, "C", "all").map((row) => row.id), ["b"]);
  assert.deepEqual(filterSources(rows, "", "evidence").map((row) => row.id), ["b"]);
  assert.deepEqual(filterSources(rows, "", "mine").map((row) => row.id), ["c"]);
  assert.deepEqual(filterSources(rows, "", "check").map((row) => row.id), ["d"]);
  assert.deepEqual(filterSources(rows, "", "all", "hermes 문서").map((row) => row.id), ["a"]);
});

test("연결 항목 ID와 기본 분야, 요약 문장", () => {
  assert.equal(safeOriginRef("idea_1.a:b-c"), "idea_1.a:b-c");
  assert.equal(safeOriginRef("a b"), undefined);
  assert.equal(safeOriginRef(3), undefined);
  assert.equal(areaForSegment("exam"), "A");
  assert.equal(areaForSegment("ai"), "B");
  assert.equal(areaForSegment(), "B");
  assert.equal(sourceSummary({ items: 3, ready: 2, passages: 1638, evidence: 1, needs_check: 0 }), "자료 3건 · 문단 1,638개 · 근거로 사용 1건");
  assert.match(sourceSummary({ items: 3, ready: 2, passages: 10, evidence: 0, needs_check: 2 }), /확인 필요 2건$/);
});

test("파일은 base64로 바꿔 보낸다", async () => {
  assert.equal(await fileToBase64(new Blob(["자료 창고"])), Buffer.from("자료 창고").toString("base64"));
});

test("자료 창고 요청은 정한 주소와 본문만 보낸다", async (t) => {
  const original = globalThis.fetch;
  const requests: { url: string; method?: string; body?: unknown }[] = [];
  t.after(() => { globalThis.fetch = original; });
  globalThis.fetch = async (input, init) => {
    if (String(input) === "/api/session") return Response.json({ csrf: "fixture" });
    requests.push({ url: String(input), method: init?.method, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    return Response.json({ results: [], items: [], areas: [], stats: {}, limits: {} });
  };
  await api.sourceLibrary();
  await api.searchSourceLibrary("간격 복습", "C", true);
  await api.addSourceLinks(["https://example.org/a"], { area: "B", origin: "news", origin_ref: "n1" }, "제목");
  await api.addSourceMemo("경험", "본문", { area: "A", mine: true });
  await api.addSourceFile("a.md", "YQ==", { area: "B" });
  await api.updateSourceItem("id/1", { use_as_evidence: true });
  await api.retrySourceItem("id/1");
  await api.deleteSourceItem("id/1");
  await api.sourceItem("id/1");
  assert.deepEqual(requests, [
    { url: "/api/source-library", method: "GET", body: undefined },
    { url: "/api/source-library/search?q=%EA%B0%84%EA%B2%A9+%EB%B3%B5%EC%8A%B5&area=C&evidence_only=true", method: "GET", body: undefined },
    { url: "/api/source-library/links", method: "POST", body: { urls: ["https://example.org/a"], title: "제목", area: "B", origin: "news", origin_ref: "n1" } },
    { url: "/api/source-library/memos", method: "POST", body: { title: "경험", text: "본문", area: "A", mine: true } },
    { url: "/api/source-library/files", method: "POST", body: { name: "a.md", content_base64: "YQ==", area: "B" } },
    { url: "/api/source-library/items/id%2F1", method: "PATCH", body: { use_as_evidence: true } },
    { url: "/api/source-library/items/id%2F1/retry", method: "POST", body: undefined },
    { url: "/api/source-library/items/id%2F1", method: "DELETE", body: undefined },
    { url: "/api/source-library/items/id%2F1", method: "GET", body: undefined },
  ]);
});
