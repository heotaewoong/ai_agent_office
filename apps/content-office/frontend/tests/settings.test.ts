import test from "node:test";
import assert from "node:assert/strict";
import {
  PROFILE_OPTIONS,
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
