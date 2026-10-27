"use strict";
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.HeoBrainCosts = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const scenarioFields = ["llm_input_tokens", "llm_output_tokens", "image_attempts", "image_input_tokens", "image_text_output_tokens", "tts_billable_characters", "video_takes", "native_seconds_per_take", "human_minutes", "resource_allowance_usd"];

  function finite(value) {
    return typeof value === "number" && Number.isFinite(value) && value >= 0;
  }

  function validModel(model) {
    if (!model || model.currency !== "USD" || !model.rates || !model.limits || !model.defaults) return false;
    const r = model.rates, l = model.limits;
    const prices = [r.llm && r.llm.input_per_million, r.llm && r.llm.output_per_million, r.image && r.image.output_per_image, r.image && r.image.input_per_million, r.image && r.image.text_output_per_million, r.tts && r.tts.per_thousand_characters];
    if (!prices.every(function (v) { return finite(v) && v <= 1000000; })) return false;
    if (!["max_started", "max_takes_per_started", "max_human_minutes_per_started", "max_hourly_value"].every(function (k) { return finite(l[k]) && l[k] > 0 && l[k] <= 1000000; })) return false;
    if (!Array.isArray(model.scenarios) || !model.scenarios.length || model.scenarios.length > 20) return false;
    if (!model.scenarios.every(function (s) { return s && typeof s.id === "string" && scenarioFields.every(function (k) { return finite(s[k]) && s[k] <= 10000000; }) && s.native_seconds_per_take > 0; })) return false;
    if (new Set(model.scenarios.map(function (s) { return s.id; })).size !== model.scenarios.length) return false;
    const videosValid = Array.isArray(model.video_models) && model.video_models.length > 0 && model.video_models.length <= 10 &&
      model.video_models.every(function (v) { return v && typeof v.id === "string" && finite(v.per_native_second) && v.per_native_second <= 1000000; }) &&
      new Set(model.video_models.map(function (v) { return v.id; })).size === model.video_models.length;
    if (!videosValid || !model.reference || !finite(model.reference.duration_seconds) || model.reference.duration_seconds <= 0 || model.reference.duration_seconds > 86400) return false;
    const d = model.defaults;
    return Number.isInteger(d.started) && d.started >= 1 && d.started <= l.max_started &&
      Number.isInteger(d.accepted) && d.accepted >= 1 && d.accepted <= d.started &&
      finite(d.hourly_value) && d.hourly_value <= l.max_hourly_value &&
      model.video_models.some(function (v) { return v.id === d.video_model; });
  }

  function defaults(model, scenarioId) {
    if (!validModel(model)) return null;
    const scenario = model.scenarios.find(function (s) { return s.id === scenarioId; }) || model.scenarios[0];
    return { scenario: scenario.id, started: model.defaults.started, accepted: model.defaults.accepted, video_model: model.defaults.video_model, video_takes: scenario.video_takes, human_minutes: scenario.human_minutes, hourly_value: model.defaults.hourly_value };
  }

  function calculate(model, input) {
    if (!validModel(model)) return { ok: false, errors: [{ field: "model", message: "원가 기준 자료를 불러오지 못했습니다. 원가 문서를 확인해 주세요." }] };
    input = input || {};
    const errors = [], values = {}, limits = model.limits;
    const scenario = model.scenarios.find(function (s) { return s.id === input.scenario; });
    const video = model.video_models.find(function (v) { return v.id === input.video_model; });
    if (!scenario) errors.push({ field: "scenario", message: "제작경로를 목록에서 선택해 주세요." });
    if (!video) errors.push({ field: "video_model", message: "영상 단가 모델을 목록에서 선택해 주세요." });
    [
      ["started", "시작 편수", 1, limits.max_started, true],
      ["accepted", "수용 편수", 1, limits.max_started, true],
      ["video_takes", "시작 1편당 생성 테이크 수", 0, limits.max_takes_per_started, true],
      ["human_minutes", "시작 1편당 사람 작업 분", 0, limits.max_human_minutes_per_started, false],
      ["hourly_value", "시간당 평가액", 0, limits.max_hourly_value, false]
    ].forEach(function (rule) {
      const raw = input[rule[0]];
      const value = typeof raw === "number" ? raw : typeof raw === "string" && raw.trim() ? Number(raw) : NaN;
      if (!Number.isFinite(value) || value < rule[2] || value > rule[3] || (rule[4] && !Number.isInteger(value))) {
        errors.push({ field: rule[0], message: rule[1] + " 값은 " + rule[2] + " 이상 " + rule[3] + " 이하" + (rule[4] ? " 정수" : " 숫자") + "로 입력해 주세요." });
      } else values[rule[0]] = value;
    });
    if (values.accepted !== undefined && values.started !== undefined && values.accepted > values.started) errors.push({ field: "accepted", message: "수용 편수는 시작 편수보다 클 수 없습니다." });
    if (errors.length) return { ok: false, errors: errors };
    const r = model.rates;
    const components = {
      llm: (scenario.llm_input_tokens * r.llm.input_per_million + scenario.llm_output_tokens * r.llm.output_per_million) / 1000000,
      image: scenario.image_attempts * r.image.output_per_image + (scenario.image_input_tokens * r.image.input_per_million + scenario.image_text_output_tokens * r.image.text_output_per_million) / 1000000,
      video: values.video_takes * scenario.native_seconds_per_take * video.per_native_second,
      tts: scenario.tts_billable_characters * r.tts.per_thousand_characters / 1000,
      resources: scenario.resource_allowance_usd
    };
    const usagePerStarted = Object.values(components).reduce(function (sum, value) { return sum + value; }, 0);
    const humanPerStarted = values.human_minutes / 60 * values.hourly_value;
    const scale = values.started / values.accepted;
    return {
      ok: true, scenario: scenario, video_model: video, inputs: values, components_per_started: components,
      usage_per_started: usagePerStarted, human_per_started: humanPerStarted,
      usage_per_accepted: usagePerStarted * scale, human_per_accepted: humanPerStarted * scale,
      total_per_accepted: (usagePerStarted + humanPerStarted) * scale,
      period_usage: usagePerStarted * values.started, period_human: humanPerStarted * values.started,
      billed_native_seconds: values.video_takes * scenario.native_seconds_per_take * values.started,
      comparison: model.video_models.map(function (candidate) {
        const videoCost = values.video_takes * scenario.native_seconds_per_take * candidate.per_native_second;
        return { id: candidate.id, name: candidate.name, video_per_started: videoCost, total_per_accepted: (usagePerStarted - components.video + videoCost + humanPerStarted) * scale };
      })
    };
  }

  return Object.freeze({ validModel: validModel, defaults: defaults, calculate: calculate });
});
