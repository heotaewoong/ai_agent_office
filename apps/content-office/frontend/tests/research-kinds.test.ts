import assert from "node:assert/strict";
import test from "node:test";
import { api } from "../lib/api.ts";
import { choiceLine, confirmedKind, kindNotice, researchKinds } from "../lib/source-library.ts";

test("글 유형은 W1부터 W5까지이고 사람이 고르지 않은 값에는 추측 표시가 붙는다", () => {
  assert.deepEqual(researchKinds.map((kind) => kind.id), ["W1", "W2", "W3", "W4", "W5"]);
  const plan = { kind: "W1" as const, kind_label: "비교·벤치마킹", kind_guessed: true, area_label: "AI 활용과 자동화", area_guessed: false };
  assert.equal(choiceLine(plan), "글 유형 비교·벤치마킹 (추측) · 분야 AI 활용과 자동화");
  assert.equal(confirmedKind(plan), undefined);
  assert.equal(confirmedKind({ ...plan, kind_guessed: false }), "W1");
  assert.equal(confirmedKind(undefined), undefined);
});

test("범위 밖과 내 경험 후기는 조사 방식이 달라진다고 알린다", () => {
  assert.equal(kindNotice({ blocked: false, needs_experience_source: false }), null);
  assert.match(kindNotice({ blocked: true, needs_experience_source: false }) ?? "", /밖으로 찾지 않아요/);
  assert.match(kindNotice({ blocked: false, needs_experience_source: true }) ?? "", /내 원고나 메모/);
});

test("글 유형 저장과 기준 다시 계산은 정한 주소와 본문만 보낸다", async (t) => {
  const original = globalThis.fetch;
  const requests: { url: string; method?: string; body?: unknown }[] = [];
  t.after(() => { globalThis.fetch = original; });
  globalThis.fetch = async (input, init) => {
    if (String(input) === "/api/session") return Response.json({ csrf: "fixture" });
    requests.push({ url: String(input), method: init?.method, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    return Response.json({ plans: [], choice: {} });
  };
  await api.saveResearchChoice("idea/1", { kind: "W2", area: "B" });
  await api.researchPlans([{ id: "idea-1", title: "새 기능 발표", kind: "W2", area: "B" }]);
  assert.deepEqual(requests, [
    { url: "/api/source-library/research/choices/idea%2F1", method: "PUT", body: { kind: "W2", area: "B" } },
    { url: "/api/source-library/research/plans", method: "POST", body: { topics: [{ id: "idea-1", title: "새 기능 발표", kind: "W2", area: "B" }] } },
  ]);
});
