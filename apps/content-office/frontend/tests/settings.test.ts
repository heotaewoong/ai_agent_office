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
  visibleProfileOptions,
  unavailableSelectionWarnings,
  paidProduceNotice,
  dailyClipUsage,
  PROFILE_CHANGE_NOTE,
} from "../lib/settings.ts";

test("프로필 선택지는 서버 등록값과 같다", () => {
  assert.deepEqual(PROFILE_OPTIONS.voice.filter((o) => !o.disabled).map((o) => o.id), ["windows-heami", "gemini-kore", "openai-tts"]);
  assert.deepEqual(PROFILE_OPTIONS.image.map((o) => o.id), ["none", "openai-gpt-image", "codex-subscription"]);
  assert.deepEqual(PROFILE_OPTIONS.clip.filter((o) => !o.disabled).map((o) => o.id), ["none", "pexels-stock", "runway-grok-lite", "runway-gen4-turbo", "runway-gen4.5"]);
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

test("OpenAI 음성은 OPENAI_API_KEY 연결을 경고하고 단가를 안내한다", () => {
  const openai = PROFILE_OPTIONS.voice.find((o) => o.id === "openai-tts")!;
  assert.ok(openai.paid && openai.hint.includes("$12") && openai.hint.includes("1,000원"));
  assert.ok(PROFILE_OPTIONS.voice.find((o) => o.id === "windows-heami")!.hint.includes("OpenAI"));
  const base = { configured: true, image: { id: "none", configured: false }, clip: { id: "none" } };
  const missing = settingsWarnings({ ...base, voice: { id: "openai-tts", configured: false } });
  assert.equal(missing.length, 1);
  assert.ok(missing[0].includes("OPENAI_API_KEY") && missing[0].includes("음성"));
  assert.deepEqual(settingsWarnings({ ...base, voice: { id: "openai-tts", configured: true } }), []);
});

test("키 연결 표시는 값이 아니라 연결 여부만", () => {
  const chips = keyChips({ configured: true, image: { configured: false }, clip: { configured: true }, youtube: { configured: false } });
  assert.deepEqual(chips.map((c) => [c.label, c.ok]), [["Gemini", true], ["OpenAI", false], ["Runway", true], ["Pexels", false], ["YouTube", false]]);
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
    const requiredKey = profile.subscription ? "ChatGPT 로그인" : profile.id.startsWith("gpt-") ? "OPENAI_API_KEY" : "GEMINI_API_KEY";
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


test("subscription text keeps API-key readiness separate and unsupported media disabled", () => {
 assert.ok(PROFILE_OPTIONS.text.some(o=>o.id==="codex-subscription-text" && o.subscription && !o.paid));
 for(const kind of ["voice","clip"] as const) assert.ok(PROFILE_OPTIONS[kind].some(o=>o.disabled && o.label.includes("Codex")));
 assert.deepEqual(settingsWarnings({configured:false,text:{id:"codex-subscription-text",configured:true}}),[]);
 assert.ok(settingsWarnings({configured:true,text:{id:"codex-subscription-text",configured:false}}).some(x=>x.includes("ChatGPT 로그인")));
});

test("Pexels 실사 영상은 무료이고 키·출처 표기를 안내하며, 키가 없으면 경고한다", () => {
  const pexels = PROFILE_OPTIONS.clip.find((o) => o.id === "pexels-stock")!;
  assert.equal(pexels.paid, false);
  for (const word of ["무료", "실제 촬영 영상", "PEXELS_API_KEY", "출처 표기"]) assert.ok(pexels.hint.includes(word), word);
  const grok = PROFILE_OPTIONS.clip.find((o) => o.id === "runway-grok-lite")!;
  assert.ok(grok.paid && grok.label.includes("추천") && PROFILE_OPTIONS.clip.filter((o) => o.paid)[0].id === "runway-grok-lite");
  const base = { configured: true, voice: { id: "gemini-kore" }, image: { id: "none" } };
  const missing = settingsWarnings({ ...base, clip: { id: "pexels-stock", configured: false, pexels_configured: false } });
  assert.ok(missing.some((w) => w.includes("PEXELS_API_KEY")));
  assert.ok(!missing.some((w) => w.includes("RUNWAYML_API_SECRET") || w.includes("배경 이미지 프로필")));
  assert.deepEqual(settingsWarnings({ ...base, clip: { id: "pexels-stock", configured: true, pexels_configured: true } }), []);
  const chips = keyChips({ configured: true, clip: { id: "pexels-stock", configured: true, pexels_configured: true, runway_configured: false } });
  assert.deepEqual(chips.filter((c) => ["Runway", "Pexels"].includes(c.label)).map((c) => [c.label, c.ok]), [["Runway", false], ["Pexels", true]]);
});

test("실행 불가 선택지도 표시하고 'none'은 항상 사용할 수 있다", () => {
  const availability = {
    image: { none: { available: true, reason: "" }, "openai-gpt-image": { available: true, reason: "" }, "codex-subscription": { available: false, reason: "codex 로그인이 없습니다" } },
    clip: { none: { available: false, reason: "x" }, "pexels-stock": { available: false, reason: "PEXELS_API_KEY가 서버에 없습니다" }, "runway-grok-lite": { available: true, reason: "" }, "runway-gen4-turbo": { available: true, reason: "" }, "runway-gen4.5": { available: true, reason: "" } },
  };
  assert.deepEqual(visibleProfileOptions({ availability }, "image").map((o) => o.id), ["none", "openai-gpt-image", "codex-subscription"]);
  assert.deepEqual(visibleProfileOptions({ availability }, "clip").map((o) => o.id), ["none", "pexels-stock", "runway-grok-lite", "runway-gen4-turbo", "runway-gen4.5"]);
  // An older server without availability data keeps every option visible.
  assert.deepEqual(visibleProfileOptions({}, "voice").map((o) => o.id), PROFILE_OPTIONS.voice.filter((o) => !o.disabled).map((o) => o.id));
  const saved = { availability, image: { id: "codex-subscription", configured: false }, clip: { id: "none" } };
  const lines = unavailableSelectionWarnings(saved);
  assert.equal(lines.length, 1);
  assert.ok(lines[0].includes("Codex 구독 배경") && lines[0].includes("codex 로그인이 없습니다") && lines[0].includes("실행 가능한 항목"));
  assert.ok(settingsWarnings(saved).includes(lines[0]));
  assert.deepEqual(unavailableSelectionWarnings({ availability, image: { id: "openai-gpt-image" }, clip: { id: "none" } }), []);
  assert.ok(PROFILE_CHANGE_NOTE.includes("다음 제작부터") && PROFILE_CHANGE_NOTE.includes("현재 설정으로 다시 제작"));
});

test("유료 클립 제작은 예상 항목을 먼저 보여 주고 하루 사용량을 표시한다", () => {
  assert.equal(paidProduceNotice(null), null);
  assert.equal(paidProduceNotice({ paid: false, clips: 0, credits: 0, reservation_krw: 0, label: "" }), null);
  const label = "유료: 영상 클립 1개 · 약 16크레딧($0.16, 예약 320원)";
  assert.equal(paidProduceNotice({ paid: true, clips: 1, credits: 16, reservation_krw: 320, label }), label);
  assert.equal(dailyClipUsage({ clip: { id: "none", paid: false } }), null);
  assert.equal(dailyClipUsage({ clip: { id: "runway-grok-lite", paid: true, paid_clips_today: 2, clip_limits: { daily_paid_clips: 3, max_clips_per_video: 1 } } }),
    "오늘 유료 클립 2/3개 사용 · 영상당 최대 1개");
});


test("키 연결이 사라져도 OpenAI·Runway 선택지를 숨기지 않고 실행 불가 이유를 표시한다", () => {
 const provider={availability:{text:{"gpt-5.4-mini":{available:false,reason:"OPENAI_API_KEY가 없습니다"}},clip:{"runway-grok-lite":{available:false,reason:"RUNWAYML_API_SECRET가 없습니다"}}}};
 const text=visibleProfileOptions(provider,"text").find(o=>o.id==="gpt-5.4-mini");
 assert.ok(text);assert.equal(text.disabled,true);assert.match(text.hint,/OPENAI_API_KEY/);
 const clip=visibleProfileOptions(provider,"clip").find(o=>o.id==="runway-grok-lite");
 assert.ok(clip);assert.equal(clip.disabled,true);assert.match(clip.hint,/RUNWAYML_API_SECRET/);
 assert.equal(visibleProfileOptions(provider,"clip").find(o=>o.id==="none")?.disabled,undefined);
});
