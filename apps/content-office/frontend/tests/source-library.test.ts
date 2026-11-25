import assert from "node:assert/strict";
import test from "node:test";
import { api } from "../lib/api.ts";
import { officeHref, officeRoute } from "../lib/navigation.ts";
import { ownedSourceInput } from "../lib/owned-source.ts";
import {
  appendBody, areaForSegment, canPaste, candidateMeta, evidenceHint, fileToBase64, filterSources, importableSources, libraryLine, passagePlace,
  autoLine, researchBadge, safeOriginRef, savedCandidateNote, sourceDates, sourceSummary, splitCandidates, splitLinks, vectorSummary, verdictBadge,
  verdictLabels,
  type ResearchCandidate, type SourceItem,
} from "../lib/source-library.ts";

const item = (patch: Partial<SourceItem>): SourceItem => ({
  id: "a", kind: "link", area: "B", area_label: "AI 활용과 자동화", mine: false, title: "Hermes 공식 문서", url: "https://example.org/hermes",
  status: "done", note: "", passages: 6, use_as_evidence: false, pasted: false, origin: "manual", origin_ref: null, lane: "fact", lane_label: "사실 근거",
  file_name: null,
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

test("근거 연결 상태와 자료별 쓰임을 알려 준다", () => {
  assert.equal(vectorSummary({ passages: 0, ready: 0, pending: 0, available: true }), "");
  assert.match(vectorSummary({ passages: 1200, ready: 300, pending: 900, available: true }), /300\/1,200개 준비됨$/);
  assert.match(vectorSummary({ passages: 12, ready: 12, pending: 0, available: true }), /12개가 기획 근거 찾기에 연결돼 있어요/);
  assert.match(vectorSummary({ passages: 12, ready: 0, pending: 12, available: false }), /도구를 찾지 못해/);
  assert.match(evidenceHint({ kind: "link" }), /근거 찾기/);
  assert.match(evidenceHint({ kind: "memo" }), /내 글로 만들기/);
  assert.equal(canPaste({ kind: "link", status: "needs_check" }), true);
  assert.equal(canPaste({ kind: "file", status: "needs_check" }), true);
  assert.equal(canPaste({ kind: "memo", status: "needs_check" }), false);
  assert.equal(canPaste({ kind: "link", status: "done" }), false);
});

test("내 글로 만들기는 근거로 켠 메모·파일과 내 링크만 불러온다", () => {
  const rows = [
    item({ id: "link", use_as_evidence: true }),
    item({ id: "mine-link", use_as_evidence: true, mine: true }),
    item({ id: "memo", kind: "memo", url: null, use_as_evidence: true }),
    item({ id: "memo-off", kind: "memo", url: null }),
    item({ id: "broken", kind: "file", status: "needs_check", use_as_evidence: true }),
  ];
  assert.deepEqual(importableSources(rows).map((row) => row.id), ["mine-link", "memo"]);
  assert.deepEqual(appendBody("", "새 글"), { body: "새 글", cut: false });
  assert.deepEqual(appendBody("쓰던 글  ", "새 글"), { body: "쓰던 글\n\n새 글", cut: false });
  assert.deepEqual(appendBody("가".repeat(8), "나".repeat(8), 10), { body: "가".repeat(8) + "\n\n", cut: true });
});

test("내 경험 중심은 켰을 때만 요청에 들어간다", () => {
  const form = { title: "오픽", body: "본문", url: "", owned: true, preset: "exam-opic" };
  assert.deepEqual(ownedSourceInput({ ...form, experienceFirst: false }), { title: "오픽", body: "본문", source_url: "", owner_confirmed: true, brief_preset: "exam-opic" });
  assert.equal(ownedSourceInput({ ...form, experienceFirst: true }).experience_first, true);
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
  await api.fillSourceText("id/1", "붙인 본문", "제목");
  await api.fillSourceText("id/1", "붙인 본문");
  await api.setSourceEvidence(["a", "b"], false);
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
    { url: "/api/source-library/items/id%2F1/text", method: "POST", body: { text: "붙인 본문", title: "제목" } },
    { url: "/api/source-library/items/id%2F1/text", method: "POST", body: { text: "붙인 본문" } },
    { url: "/api/source-library/evidence", method: "POST", body: { ids: ["a", "b"], use_as_evidence: false } },
    { url: "/api/source-library/items/id%2F1/retry", method: "POST", body: undefined },
    { url: "/api/source-library/items/id%2F1", method: "DELETE", body: undefined },
    { url: "/api/source-library/items/id%2F1", method: "GET", body: undefined },
  ]);
});

const candidate = (patch: Partial<ResearchCandidate>): ResearchCandidate => ({
  key: "k1", lane: "fact", provider: "pubmed", provider_label: "PubMed 논문", title: "Spacing", url: "https://pubmed.ncbi.nlm.nih.gov/1/", snippet: "",
  year: 2021, needs_paste: false, in_library: false, ...patch,
});

test("외부 조사 기준은 필수, 권장, 안 함으로 보여 준다", () => {
  assert.deepEqual(researchBadge("required"), { label: "외부 조사 필수", tone: "red" });
  assert.deepEqual(researchBadge("recommended"), { label: "외부 조사 권장", tone: "orange" });
  assert.deepEqual(researchBadge("none"), { label: "외부 조사 안 함", tone: "neutral" });
});

test("후보는 사실 근거와 사례·참고 두 칸으로 나눈다", () => {
  const rows = [candidate({ key: "a" }), candidate({ key: "b", lane: "example", provider_label: "루틴 연구소", year: null })];
  const groups = splitCandidates(rows);
  assert.deepEqual([groups.fact.map((row) => row.key), groups.example.map((row) => row.key)], [["a"], ["b"]]);
  assert.equal(candidateMeta(rows[0]), "PubMed 논문 · 2021년");
  assert.equal(candidateMeta(rows[1]), "루틴 연구소");
});

test("창고 근거가 두 곳 이상이면 충분하다고 알려 준다", () => {
  assert.match(libraryLine({ fact_sources: null, sufficient: false }), /조회하지 못했어요/);
  assert.match(libraryLine({ fact_sources: 0, sufficient: false }), /아직 없어요/);
  assert.match(libraryLine({ fact_sources: 1, sufficient: false }), /후보 1곳/);
  assert.match(libraryLine({ fact_sources: 3, sufficient: true }), /후보 3곳.*직접 뒷받침/);
});

test("고른 후보를 창고에 넣은 결과를 한 줄로 알려 준다", () => {
  const on = item({ use_as_evidence: true, passages: 4 });
  assert.deepEqual(savedCandidateNote({ url: on.url!, result: "added", item: on }), { ok: true, text: "문단 4개를 넣고 근거로 켰어요." });
  assert.deepEqual(savedCandidateNote({ url: on.url!, result: "exists", item: on }), { ok: true, text: "이미 창고에 있던 자료를 근거로 켰어요." });
  const unread = savedCandidateNote({ url: "https://youtu.be/x", result: "added", item: item({ status: "needs_check", note: "자막을 붙여 넣어 주세요." }) });
  assert.equal(unread.ok, false);
  assert.match(unread.text, /확인 필요.*자막을 붙여 넣어 주세요/);
  assert.deepEqual(savedCandidateNote({ url: "http://x", result: "rejected", reason: "https만 됩니다." }), { ok: false, text: "https만 됩니다." });
  assert.equal(savedCandidateNote(undefined).ok, false);
});

test("사례·참고 자료는 따로 골라 보고, 근거 안내도 다르게 보여 준다", () => {
  const rows = [item({ id: "f" }), item({ id: "e", lane: "example", lane_label: "사례·참고" })];
  assert.deepEqual(filterSources(rows, "", "example").map((row) => row.id), ["e"]);
  assert.match(evidenceHint(rows[1]), /사례로만 소개돼요/);
  assert.equal(evidenceHint(rows[0]), "기획의 근거 찾기에 후보로 나와요");
});

test("발행일, 수정일, 읽은 날과 문단 위치를 보여 준다", () => {
  assert.equal(sourceDates(item({})), "");
  assert.equal(sourceDates(item({ published_at: "2026-10-03", modified_at: "2026-11-01", date_source: "json-ld", collected_at: "2026-11-25T00:16:03+00:00" })),
    "발행 2026-10-03 · 수정 2026-11-01 · 읽은 날 11월 25일");
  assert.equal(sourceDates(item({ published_at: "2026-04-09", date_source: "htmldate", collected_at: "2026-11-25T00:16:03+00:00" })),
    "발행 2026-04-09(추정) · 읽은 날 11월 25일");
  assert.equal(sourceDates(item({ collected_at: "2026-11-25T00:16:03+00:00" })), "발행일 모름 · 읽은 날 11월 25일");
  assert.equal(sourceDates(item({ status: "needs_check", published_at: "2026-10-03" })), "");
  assert.equal(passagePlace({ locator: "p.12", heading: null }), "PDF 12쪽");
  assert.equal(passagePlace({ locator: null, heading: "복습 간격 > 간격별 기억" }), "복습 간격 > 간격별 기억");
  assert.equal(passagePlace({ locator: null, heading: null }), "");
  assert.equal(passagePlace(undefined), "");
});

test("자료 창고 판정과 자동 조사 줄: 맞음은 초록, 애매는 주황, 틀림은 빨강이고 사람이 누른 조사에는 자동 줄이 없다", () => {
  assert.equal(verdictBadge(null), null);
  assert.deepEqual(verdictBadge({ verdict: "correct", label: "맞음", top_score: 0.7, reason: "" }), { label: "자료 창고 판정: 맞음", tone: "green" });
  assert.equal(verdictBadge({ verdict: "ambiguous", label: "애매", top_score: 0.5, reason: "" })?.tone, "orange");
  assert.equal(verdictBadge({ verdict: "incorrect", label: "틀림", top_score: 0.1, reason: "" })?.tone, "red");
  assert.equal(autoLine({}), null);
  assert.equal(autoLine({ auto: { ran: false, tavily: false, tavily_today: 0, tavily_daily_cap: 30 } }), "밖으로 찾지 않았어요.");
  assert.equal(autoLine({ auto: { ran: true, tavily: false, tavily_today: 3, tavily_daily_cap: 30 } }), "무료 공개 출처를 자동으로 찾아봤어요.");
  assert.equal(autoLine({ cached: true, auto: { ran: true, tavily: true, tavily_today: 4, tavily_daily_cap: 30 } }),
    "저장해 둔 자동 조사 결과예요. 무료 공개 출처와 Tavily를 자동으로 찾아봤어요(오늘 자동 4/30회).");
  assert.deepEqual(verdictLabels.map((choice) => choice.id), ["correct", "wrong", "practice"]);
});
