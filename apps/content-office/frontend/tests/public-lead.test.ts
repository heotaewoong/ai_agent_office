import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { LEAD_SOURCES } from "../lib/leads.ts";
import { leadSourceFromQuery, magnetKeyFromQuery, PUBLIC_LEAD_DONE, publicLeadEmbed, publicLeadLink, publicLeadPayload } from "../lib/public-lead.ts";

const magnet = { key: "exam-d30-planner", title: "시험 D-30 복습 플래너", description: "설명", consent_version: "2026-10-30-draft1", consent_text: "동의 문구" };

test("동의 체크와 이메일 형식이 맞아야 신청 본문을 만든다", () => {
  assert.deepEqual(publicLeadPayload({ email: "reader@example.com", consent: false, hp: "" }, magnet, "youtube"), { error: "개인정보 수집·이용 동의에 체크해 주세요." });
  assert.ok("error" in publicLeadPayload({ email: "reader@example", consent: true, hp: "" }, magnet, "youtube"));
  assert.ok("error" in publicLeadPayload({ email: "", consent: true, hp: "" }, magnet, "youtube"));
  const ok = publicLeadPayload({ email: "  reader@example.com ", consent: true, hp: "" }, magnet, "youtube");
  assert.ok("payload" in ok);
  assert.deepEqual(ok.payload, { email: "reader@example.com", magnet_key: "exam-d30-planner", source: "youtube", consent_version: "2026-10-30-draft1", consent_checked: true, hp: "" });
  // 동의 문구 원문은 보내지 않는다(서버 카탈로그가 정한다)
  assert.equal("consent_text" in ok.payload, false);
});

test("주소창 값은 허용 목록으로만 받아들인다", () => {
  assert.equal(leadSourceFromQuery("instagram"), "instagram");
  assert.equal(leadSourceFromQuery(["blog", "youtube"]), "blog");
  assert.equal(leadSourceFromQuery("tiktok"), "other");
  assert.equal(leadSourceFromQuery(undefined), "other");
  assert.equal(magnetKeyFromQuery("exam-d30-planner"), "exam-d30-planner");
  assert.equal(magnetKeyFromQuery("../etc"), "");
  assert.equal(magnetKeyFromQuery(undefined), "");
});

test("공개 신청 링크와 홈페이지 삽입 HTML", () => {
  assert.equal(publicLeadLink("https://office.example.kr/", "exam-d30-planner", "homepage"), "https://office.example.kr/lead?m=exam-d30-planner&src=homepage");
  assert.equal(publicLeadLink("https://office.example.kr", "a.b_c", "youtube"), "https://office.example.kr/lead?m=a.b_c&src=youtube");
  const embed = publicLeadEmbed("https://office.example.kr/lead?m=x&src=homepage", "<플래너> & \"표\"");
  assert.match(embed, /^<a href="https:\/\/office\.example\.kr\/lead\?m=x&amp;src=homepage" rel="noopener"/);
  assert.ok(embed.includes("&lt;플래너&gt; &amp; &quot;표&quot;"));
  assert.equal(/iframe|<script/i.test(embed), false);
});

test("공개 출처 목록과 완료 문구가 서버와 같다", () => {
  const route = readFileSync(new URL("../../backend/office/public_leads.py", import.meta.url), "utf8");
  const literal = route.match(/source: Literal\[([^\]]+)\]/);
  assert.ok(literal);
  assert.deepEqual([...LEAD_SOURCES], [...literal[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]));
  assert.ok(route.includes(PUBLIC_LEAD_DONE));
});
