import assert from "node:assert/strict";
import test from "node:test";
import { api } from "../lib/api.ts";
import { bookCitation, bookDiscoveryLine, bookPage, bookPolicy, evidencePlace } from "../lib/book-evidence.ts";
import { mergeTavily, tavilyLabel, type ResearchResult, type TavilyResult } from "../lib/source-library.ts";

const book = { kind: "book" as const, title: "RAG의 모든 것", author: "정민제", printed_page: 93, file_page: 101, quote_policy: "quote_ok" as const };

test("책 근거는 서버와 같은 규칙으로 저자, 제목, 쪽을 보여 준다", () => {
  assert.equal(bookCitation(book), "『RAG의 모든 것』, 정민제, 93쪽");
  assert.equal(bookPage({ printed_page: null, file_page: 12 }), "PDF 12쪽(파일 기준)");
  assert.equal(bookCitation({ ...book, author: null, printed_page: null, file_page: null }), "『RAG의 모든 것』");
  assert.equal(bookCitation({ ...book, kind: "course", title: "교안.pdf" }), "강의 자료 「교안.pdf」");
  assert.equal(bookPolicy(book), "짧은 인용 가능(두 문장까지)");
  assert.equal(bookPolicy({ ...book, author: null, quote_policy: "paraphrase_only" }), "풀어 쓰기만 가능, 저자 미기록");
  assert.match(bookDiscoveryLine({ status: "ready", mode: "text" }), /키워드로만/);
  assert.equal(evidencePlace({ locator: "p.12", heading: "2장 > 간격" }), "PDF 12쪽 · 2장 > 간격");
  assert.equal(evidencePlace({}), "");
});

test("Tavily 결과는 지금 결과 뒤에 붙고 같은 주소는 한 번만 보인다", () => {
  const row = { key: "a", lane: "fact" as const, provider: "pubmed", provider_label: "PubMed 논문", title: "논문", url: "https://pubmed.ncbi.nlm.nih.gov/1/",
    snippet: "", year: null, needs_paste: false, in_library: false };
  const result = { plan: {} as ResearchResult["plan"], queries: { english: "spacing", terms: [], custom: false }, library: { fact_sources: 0, sufficient: false },
    candidates: [row], notes: ["처음 메모"], searched: true } satisfies ResearchResult;
  const found: TavilyResult = { queries: { tavily: "간격 복습" }, searched: true, notes: ["처음 메모", "Tavily 메모"],
    candidates: [row, { ...row, key: "b", lane: "example", provider: "tavily", idea_only: true, url: "https://blog.example.com/x" }],
    tavily: { month: "2026-11", calls: 1, cap: 900, remaining: 899, has_key: true } };
  const merged = mergeTavily(result, found);
  assert.deepEqual(merged.candidates.map((item) => item.key), ["a", "b"]);
  assert.deepEqual(merged.notes, ["처음 메모", "Tavily 메모"]);
  assert.equal(tavilyLabel(found.tavily), "Tavily로 한 번 더 찾기 (무료, 이번 달 1/900회)");
  assert.equal(tavilyLabel({ ...found.tavily, has_key: false }), "Tavily 키가 없어요");
  assert.match(tavilyLabel({ ...found.tavily, remaining: 0 }), /다 썼어요/);
});

test("책 근거와 Tavily 요청은 정해진 주소로만 간다", async (t) => {
  const original = globalThis.fetch;
  const calls: { url: string; body: unknown; method: string }[] = [];
  t.after(() => { globalThis.fetch = original; });
  globalThis.fetch = async (input, init) => {
    if (String(input) === "/api/session") return Response.json({ csrf: "fixture" });
    calls.push({ url: String(input), method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : null });
    return Response.json({});
  };
  await api.searchIdeaBookEvidence("idea/1", "a".repeat(64));
  await api.selectIdea("idea/1", "a".repeat(64), [], ["b".repeat(64)]);
  await api.approveIdeaPublicEvidence("idea/1", "a".repeat(64), ["c".repeat(64)], ["b".repeat(64)]);
  await api.tavilyUsage();
  await api.runTavily({ id: "idea-1", title: "간격 복습" });
  assert.deepEqual(calls.map((call) => [call.method, call.url]), [
    ["POST", "/api/ideas/idea%2F1/book-evidence"], ["POST", "/api/ideas/idea%2F1/select"], ["POST", "/api/ideas/idea%2F1/public-evidence/approve"],
    ["GET", "/api/source-library/research/tavily"], ["POST", "/api/source-library/research/tavily"],
  ]);
  assert.deepEqual(calls[1].body, { expected_hash: "a".repeat(64), book_evidence_ids: ["b".repeat(64)] });
  assert.deepEqual(calls[2].body, { expected_hash: "a".repeat(64), public_evidence_ids: ["c".repeat(64)], book_evidence_ids: ["b".repeat(64)] });
});
