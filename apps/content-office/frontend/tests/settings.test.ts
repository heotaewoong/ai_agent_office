import test from "node:test";
import assert from "node:assert/strict";
import {
  PROFILE_OPTIONS,
  PROFILE_COST_GUIDANCE,
  textProfileConnection,
  settingsWarnings,
  keyChips,
  validWindowMinutes,
  uploadReadiness,
  deliveryStateLabel,
  canReconcile,
  studioUrl,
} from "../lib/settings.ts";

test("프로필 선택지는 서버 등록값과 같다", () => {
  assert.deepEqual(PROFILE_OPTIONS.voice.map((o) => o.id), ["windows-heami", "gemini-kore"]);
  assert.deepEqual(PROFILE_OPTIONS.image.map((o) => o.id), ["none", "openai-gpt-image", "codex-subscription"]);
  assert.deepEqual(PROFILE_OPTIONS.clip.map((o) => o.id), ["none", "runway-gen4-turbo", "runway-gen4.5"]);
  assert.ok(PROFILE_OPTIONS.image.find((o) => o.id === "openai-gpt-image")!.paid);
  assert.equal(PROFILE_OPTIONS.image.find((o) => o.id === "codex-subscription")!.paid, false);
});

test("Codex 구독 배경은 API 키가 아니라 codex 로그인을 경고한다", () => {
  const warnings = settingsWarnings({ configured: true, voice: { id: "gemini-kore" }, image: { id: "codex-subscription", configured: false }, clip: { id: "none" } });
  assert.equal(warnings.length, 1);
  assert.ok(warnings[0].includes("codex") && !warnings[0].includes("OPENAI_API_KEY"));
  const chips = keyChips({ configured: true, image: { id: "codex-subscription", configured: false, openai_configured: true }, clip: { configured: false } });
  assert.deepEqual(chips.find((c) => c.label === "OpenAI")!.ok, true);
});

test("켠 유료 프로필의 키가 없으면 경고, 생성 영상은 배경이 필요", () => {
  const warnings = settingsWarnings({
    configured: false,
    voice: { id: "gemini-kore" },
    image: { id: "none", configured: false },
    clip: { id: "runway-gen4-turbo", configured: false },
  });
  assert.ok(warnings.some((w) => w.includes("GEMINI_API_KEY")));
  assert.ok(warnings.some((w) => w.includes("RUNWAYML_API_SECRET")));
  assert.ok(warnings.some((w) => w.includes("배경 이미지")));
  assert.ok(!warnings.some((w) => w.includes("OPENAI_API_KEY")));
  assert.deepEqual(
    settingsWarnings({ configured: true, voice: { id: "gemini-kore" }, image: { id: "openai-gpt-image", configured: true }, clip: { id: "none" } }),
    [],
  );
});

test("키 연결 표시는 값이 아니라 연결 여부만", () => {
  const chips = keyChips({ configured: true, image: { configured: false }, clip: { configured: true }, youtube: { configured: false } });
  assert.deepEqual(chips.map((c) => [c.label, c.ok]), [["Gemini", true], ["OpenAI", false], ["Runway", true], ["YouTube", false]]);
});

test("작업 시간은 1~360분 정수만", () => {
  assert.equal(validWindowMinutes("90"), 90);
  assert.equal(validWindowMinutes(" 360 "), 360);
  for (const bad of ["0", "361", "1.5", "", "abc", "-5"]) assert.equal(validWindowMinutes(bad), null, bad);
});

const released = {
  selections: { video: true, blog: true, pdf: false, cards: false },
  manifest: { hash: "m1" },
  release_approval: { decision: "approved", version: "m1", outputs: ["video"] },
};

test("업로드는 영상 출고 승인②와 YouTube 자격이 있어야", () => {
  assert.equal(uploadReadiness(released as never, true).ok, true);
  assert.match(uploadReadiness(released as never, false).reason, /YOUTUBE_/);
  assert.match(uploadReadiness({ ...released, selections: { ...released.selections, video: false } } as never, true).reason, /영상 제작/);
  assert.match(uploadReadiness({ ...released, release_approval: { ...released.release_approval, outputs: ["blog"] } } as never, true).reason, /출고 승인②/);
  assert.match(uploadReadiness({ ...released, manifest: { hash: "m2" } } as never, true).reason, /출고 승인②/);
  assert.match(uploadReadiness({ ...released, release_approval: undefined } as never, true).reason, /출고 승인②/);
});

test("업로드 상태 문구와 대사 가능 여부", () => {
  assert.equal(deliveryStateLabel("private"), "비공개 업로드 완료");
  assert.equal(deliveryStateLabel("unknown"), "결과 불명 · 대사 필요");
  assert.equal(deliveryStateLabel("weird"), "weird");
  assert.equal(canReconcile({ state: "unknown", session_uri: "https://x" } as never), true);
  assert.equal(canReconcile({ state: "private", external_id: "vid" } as never), true);
  assert.equal(canReconcile({ state: "failed" } as never), false);
});

test("Studio 링크는 안전한 영상 ID만", () => {
  assert.equal(studioUrl("vid_ABC-123"), "https://studio.youtube.com/video/vid_ABC-123/edit");
  assert.equal(studioUrl("../evil"), null);
  assert.equal(studioUrl(undefined), null);
});


test("text model profile options and warnings follow the chosen provider", () => {
  assert.ok(PROFILE_OPTIONS.text.some((o) => o.id === "gpt-5.4-mini" && o.paid));
  assert.ok(PROFILE_OPTIONS.text.some((o) => o.id === "gemini-3.8-flash"));
  const openaiWithoutKey = settingsWarnings({ configured: true, text: { id: "gpt-5.4-mini", configured: false } });
  assert.ok(openaiWithoutKey.some((w) => w.includes("OPENAI_API_KEY")));
  const openaiNoGemini = settingsWarnings({ configured: false, text: { id: "gpt-5.4-mini", configured: true } });
  assert.ok(!openaiNoGemini.some((w) => w.includes("원고 작성이 동작하지")));
  const geminiNoKey = settingsWarnings({ configured: false, text: { id: "gemini-3.8-flash", configured: false } });
  assert.ok(geminiNoKey.some((w) => w.includes("GEMINI_API_KEY")));
});

test("글 모델의 연결 판정은 선택 프로필을 전역 Gemini 표시보다 우선한다", () => {
  for (const profile of PROFILE_OPTIONS.text) {
    const requiredKey = profile.id.startsWith("gpt-") ? "OPENAI_API_KEY" : "GEMINI_API_KEY";
    const ready = settingsWarnings({ configured: false, text: { id: profile.id, configured: true } });
    assert.ok(!ready.some((warning) => warning.includes("글 모델") || warning.includes("원고 작성")), profile.id);
    const missing = settingsWarnings({ configured: true, text: { id: profile.id, configured: false } });
    assert.ok(missing.some((warning) => warning.includes(requiredKey)), profile.id);
  }
});

test("선택 프로필이 없는 구판 OpenAI 응답도 해당 제공자의 키 상태로 안내한다", () => {
  const missing = settingsWarnings({ model: "gpt-5.4-mini", configured: true, image: { id: "none", openai_configured: false } });
  assert.ok(missing.some((warning) => warning.includes("OPENAI_API_KEY")));
  const ready = settingsWarnings({ model: "gpt-5.4-mini", configured: false, image: { id: "none", openai_configured: true } });
  assert.ok(!ready.some((warning) => warning.includes("GEMINI_API_KEY") || warning.includes("원고 작성")));
});

test("선택 프로필 키 표시는 글 모델 상태를 따르고 Codex 로그인과 API 키를 혼동하지 않는다", () => {
  const openai = { configured: false, text: { id: "gpt-5.4-mini", configured: true }, image: { id: "none", configured: false } };
  assert.deepEqual(textProfileConnection(openai), { model: "gpt-5.4-mini", env: "OPENAI_API_KEY", configured: true });
  assert.equal(keyChips(openai).find((chip) => chip.label === "OpenAI")?.ok, true);
  assert.equal(keyChips(openai).find((chip) => chip.label === "Gemini")?.ok, false);
  const gemini = { configured: false, text: { id: "gemini-3.8-flash", configured: true } };
  assert.equal(keyChips(gemini).find((chip) => chip.label === "Gemini")?.ok, true);
  assert.ok(!settingsWarnings({ ...gemini, voice: { id: "gemini-kore" } }).some((warning) => warning.includes("GEMINI_API_KEY")));
  const codex = { configured: true, image: { id: "codex-subscription", configured: true } };
  assert.equal(keyChips(codex).find((chip) => chip.label === "OpenAI")?.ok, false);
  assert.equal(textProfileConnection({ model: "gpt-5.4-mini", ...codex }).configured, undefined);
});

test("선택 글 모델의 연결 정보가 없으면 특정 키 누락으로 단정하지 않는다", () => {
  for (const provider of [{ model: "gpt-5.4-mini" }, { text: { id: "unsupported-profile", configured: true } }]) {
    const warnings = settingsWarnings(provider);
    assert.ok(warnings.some((warning) => warning.includes("연결 여부를 확인하지 못")));
    assert.ok(!warnings.some((warning) => warning.includes("연결이 없습니다")));
  }
});

test("비용 안내는 승인 전 글 호출과 승인 후 선택 제작을 구분한다", () => {
  assert.ok(PROFILE_COST_GUIDANCE.some((note) => note.includes("선택만으로는") && note.includes("호출하지 않습니다")));
  const before = PROFILE_COST_GUIDANCE.find((note) => note.includes("승인① 전에도")) ?? "";
  for (const role of ["근거 요약", "원고 생성", "비평", "평가", "국어 검수"]) assert.ok(before.includes(role), role);
  assert.ok(before.includes("작업 시간") && before.includes("예산"));
  const after = PROFILE_COST_GUIDANCE.find((note) => note.includes("승인① 후에는")) ?? "";
  for (const medium of ["음성", "배경 이미지", "생성 영상"]) assert.ok(after.includes(medium), medium);
  assert.ok(after.includes("승인 자체는") && after.includes("시작하지 않습니다"));
  assert.ok(!PROFILE_COST_GUIDANCE.join(" ").includes("승인① 뒤 실제 제작에서만"));
});
