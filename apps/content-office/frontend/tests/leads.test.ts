import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { changeLeadForm, emptyLeadForm, LEAD_SOURCES, leadFormAfterSave, leadInputFromForm, leadConsentPurposeLabel, validEmail, leadSourceLabel } from "../lib/leads.ts";

test("이메일 형식만 통과한다", () => {
  assert.equal(validEmail("reader@example.com"), true);
  assert.equal(validEmail("  reader@example.com  "), true);
  assert.equal(validEmail("reader@example"), false);
  assert.equal(validEmail("reader example@example.com"), false);
  assert.equal(validEmail("@example.com"), false);
  assert.equal(validEmail(""), false);
  assert.equal(validEmail(`${"a".repeat(250)}@example.com`), false);
  assert.equal(validEmail("reader+notes@example.co.kr"), true);
  assert.equal(validEmail("독자@example.com"), false);
  assert.equal(validEmail("reader'@example.com"), false);
});

test("리드 출처 이름", () => {
  assert.equal(leadSourceLabel("homepage"), "홈페이지");
  assert.equal(leadSourceLabel("instagram"), "Instagram");
  assert.equal(leadSourceLabel("threads"), "Threads");
  assert.equal(leadSourceLabel("other"), "기타 · 직접 등록");
  assert.equal(leadSourceLabel("x"), "x");
});

test("출처 선택과 직접 등록 기본값이 실제 서버 허용 목록과 같다", () => {
  const source = readFileSync(new URL("../../backend/office/leads.py", import.meta.url), "utf8");
  const route = readFileSync(new URL("../../backend/office/api_leads_newsletter.py", import.meta.url), "utf8");
  const values = (literal: string) => [...literal.matchAll(/"([^"]+)"/g)].map((match) => match[1]);
  const sourceValues = source.match(/^SOURCES = \(([^\n]+)\)/m);
  const inputValues = route.match(/source: Literal\[([^\]]+)\]/);
  assert.ok(sourceValues && inputValues);
  assert.deepEqual([...LEAD_SOURCES], values(sourceValues[1]));
  assert.deepEqual([...LEAD_SOURCES], values(inputValues[1]));
  const form = emptyLeadForm();
  assert.equal(form.source, "other");
  assert.ok(LEAD_SOURCES.some((source) => source === form.source));
  assert.equal(form.consent_version, "");
  assert.equal(form.consent_text, "");
  assert.equal(form.consent_confirmed, false);
  assert.equal(form.newsletter_consent_confirmed, false);
});

const completed = () => ({ ...emptyLeadForm(), email: " reader@example.com ", magnet_key: " exam-d30-planner ", consent_version: " 실제 표시한 버전 ", consent_text: " 독자가 실제로 본 문구를 옮긴 합성 검증 자료입니다. " });

test("실제 동의 확인 전에는 등록 입력을 만들지 않으며 체크 값은 서버에 보내지 않는다", () => {
  assert.ok("error" in leadInputFromForm(completed()));
  for (const source of LEAD_SOURCES) {
    const result = leadInputFromForm({ ...completed(), source, consent_confirmed: true });
    assert.ok("input" in result);
    assert.deepEqual(result.input, { email: "reader@example.com", magnet_key: "exam-d30-planner", source, consent_version: "실제 표시한 버전", consent_text: "독자가 실제로 본 문구를 옮긴 합성 검증 자료입니다.", consent_purpose: "lead_magnet_delivery" });
    assert.deepEqual(Object.keys(result.input).sort(), ["email", "magnet_key", "source", "consent_version", "consent_text", "consent_purpose"].sort());
  }
});

test("이메일·자료·동의 원문이나 버전 수정과 등록 성공은 운영자 확인을 초기화한다", () => {
  const checked = { ...completed(), consent_confirmed: true, newsletter_consent_confirmed: true };
  for (const field of ["email", "magnet_key", "consent_version", "consent_text"] as const) {
    const changed = changeLeadForm(checked, field, checked[field] + " 변경");
    assert.equal(changed.consent_confirmed, false, field);
    assert.equal(changed.newsletter_consent_confirmed, false, field);
    assert.equal(checked.consent_confirmed, true);
  }
  assert.equal(changeLeadForm(checked, "email", checked.email), checked);
  assert.equal(changeLeadForm(checked, "source", "youtube").consent_confirmed, true);
  const next = leadFormAfterSave(checked);
  assert.equal(next.email, "");
  assert.equal(next.consent_confirmed, false);
  assert.equal(next.newsletter_consent_confirmed, false);
  assert.equal(next.consent_text, checked.consent_text);
  assert.equal(next.magnet_key, checked.magnet_key);
});

test("뉴스레터 목적은 별도 명시 확인일 때만 보내고 출처·자유 문구에서 추정하지 않는다", () => {
  const form = { ...completed(), source: "newsletter", consent_text: "뉴스레터 수신에 동의합니다라는 자유 문구", consent_confirmed: true };
  const delivery = leadInputFromForm(form);
  assert.ok("input" in delivery);
  assert.equal(delivery.input.consent_purpose, "lead_magnet_delivery");
  const newsletter = leadInputFromForm({ ...form, newsletter_consent_confirmed: true });
  assert.ok("input" in newsletter);
  assert.equal(newsletter.input.consent_purpose, "newsletter");
  assert.equal(newsletter.input.consent_text, form.consent_text);
  assert.equal("newsletter_consent_confirmed" in newsletter.input, false);
  for (const value of [undefined, "true", 1]) {
    const parsed = leadInputFromForm({ ...form, newsletter_consent_confirmed: value } as never);
    assert.ok("input" in parsed);
    assert.equal(parsed.input.consent_purpose, "lead_magnet_delivery");
  }
  assert.ok("error" in leadInputFromForm({ ...form, consent_confirmed: false, newsletter_consent_confirmed: true }));
});

test("목적 없는 기존 기록과 자료 전달 기록은 뉴스레터 동의로 표시하지 않는다", () => {
  assert.equal(leadConsentPurposeLabel("newsletter"), "뉴스레터 수신 동의");
  assert.equal(leadConsentPurposeLabel("lead_magnet_delivery"), "신청 자료 전달 동의");
  for (const value of [undefined, null, "", "legacy"]) assert.equal(leadConsentPurposeLabel(value), "목적 미확인 · 뉴스레터 제외");
});

test("폼 검증은 서버의 출처·자료 키·동의 길이 계약을 지킨다", () => {
  const checked = { ...completed(), consent_confirmed: true };
  for (const source of ["manual", "tiktok", "Blog"]) assert.ok("error" in leadInputFromForm({ ...checked, source }));
  for (const magnet_key of ["", "-invalid", "with space", "../path", "a".repeat(101)]) assert.ok("error" in leadInputFromForm({ ...checked, magnet_key }));
  for (const patch of [{ consent_version: "" }, { consent_text: " " }, { consent_version: "v".repeat(51) }, { consent_text: "x".repeat(2001) }]) assert.ok("error" in leadInputFromForm({ ...checked, ...patch }));
  const boundary = leadInputFromForm({ ...checked, magnet_key: "a".repeat(100), consent_version: "v".repeat(50), consent_text: "x".repeat(2000) });
  assert.ok("input" in boundary);
});
