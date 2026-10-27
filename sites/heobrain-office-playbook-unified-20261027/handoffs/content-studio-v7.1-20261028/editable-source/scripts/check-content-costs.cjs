"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const base = path.resolve(__dirname, "..");
const cost = require(path.join(base, "dist/content-studio/costs.js"));
const model = JSON.parse(fs.readFileSync(path.join(base, "content-studio/cost-scenarios.json"), "utf8"));
let checks = 0;
function check(name, fn) { fn(); checks++; console.log("PASS " + name); }
function near(actual, expected) { assert.ok(Math.abs(actual - expected) < 1e-8, actual + " != " + expected); }
function calculate(id, changes) { return cost.calculate(model, Object.assign(cost.defaults(model, id), changes)); }
check("three routes reproduce documented hypothetical baseline", function () {
  [["education", 8.790033333333334], ["brand", 19.2404], ["story", 40.1869]].forEach(function (pair) {
    const result = calculate(pair[0]); assert.equal(result.ok, true); near(result.total_per_accepted, pair[1]);
  });
});
check("image input and text output charges are included", function () {
  near(calculate("education").components_per_started.image, .1407);
});
check("discarded projects stay in accepted denominator", function () {
  const r = calculate("story", { started: 10, accepted: 8 }); near(r.total_per_accepted, 50.233625);
  near(r.billed_native_seconds, 1200);
});
check("equal acceptance count scaling preserves unit cost", function () {
  near(calculate("brand", { started: 10, accepted: 10 }).total_per_accepted, calculate("brand").total_per_accepted);
});
check("one fewer 5-second take removes its native-second charge only", function () {
  near(calculate("brand").total_per_accepted - calculate("brand", { video_takes: 5 }).total_per_accepted, .6);
});
check("Turbo is a price substitution without quality inference", function () {
  const r = calculate("brand", { video_model: "turbo" }); near(r.components_per_started.video, 1.5);
  near(calculate("brand").total_per_accepted - r.total_per_accepted, 2.1);
  assert.equal(r.comparison.length, model.video_models.length);
});
check("hourly value affects human time and zero is valid", function () {
  near(calculate("education", { hourly_value: 0 }).total_per_accepted, .4567);
  near(calculate("education", { human_minutes: 0 }).human_per_accepted, 0);
});
check("30 more human minutes at 20 USD per hour adds 10 USD", function () {
  near(calculate("brand", { human_minutes: 75 }).total_per_accepted - calculate("brand").total_per_accepted, 10);
});
check("numeric UI strings parse without changing units", function () {
  near(calculate("brand", { started: "10", accepted: "8", human_minutes: "45", hourly_value: "20" }).total_per_accepted, 24.0505);
});
check("zero accepted and accepted above started return no result", function () {
  [{ accepted: 0 }, { started: 1, accepted: 2 }].forEach(function (input) {
    const r = calculate("education", input); assert.equal(r.ok, false); assert.ok(r.errors.some(function (e) { return e.field === "accepted"; }));
    assert.equal(r.total_per_accepted, undefined);
  });
});
check("negative nonfinite blank boolean and fractional counts reject", function () {
  [
    { started: -1 }, { accepted: NaN }, { human_minutes: Infinity }, { hourly_value: "NaN" },
    { started: "" }, { accepted: " " }, { video_takes: false }, { hourly_value: null }, { video_takes: 1.5 }, { started: 1.5 }
  ].forEach(function (input) { assert.equal(calculate("education", input).ok, false, JSON.stringify(input)); });
});
check("over-limit values reject rather than clamp silently", function () {
  [
    { started: model.limits.max_started + 1 }, { video_takes: model.limits.max_takes_per_started + 1 },
    { human_minutes: model.limits.max_human_minutes_per_started + 1 }, { hourly_value: model.limits.max_hourly_value + 1 }
  ].forEach(function (input) { assert.equal(calculate("brand", input).ok, false); });
});
check("upper boundaries stay finite", function () {
  const r = calculate("story", { started: model.limits.max_started, accepted: 1, video_takes: model.limits.max_takes_per_started, human_minutes: model.limits.max_human_minutes_per_started, hourly_value: model.limits.max_hourly_value });
  assert.equal(r.ok, true); assert.ok(Number.isFinite(r.total_per_accepted));
});
check("unknown IDs and broken rate data reject", function () {
  assert.equal(calculate("education", { scenario: "missing" }).ok, false);
  assert.equal(calculate("education", { video_model: "missing" }).ok, false);
  const broken = JSON.parse(JSON.stringify(model)); broken.rates.image.input_per_million = "not-number";
  assert.equal(cost.calculate(broken, {}).ok, false); assert.equal(cost.calculate(null, {}).ok, false);
});
check("calculation does not mutate input or source model", function () {
  const input = cost.defaults(model, "brand"), beforeModel = JSON.stringify(model), beforeInput = JSON.stringify(input);
  cost.calculate(model, input); assert.equal(JSON.stringify(model), beforeModel); assert.equal(JSON.stringify(input), beforeInput);
});
check("missing reference and invalid configured defaults fail safely", function () {
  [function(m){delete m.reference;}, function(m){m.reference.duration_seconds=0;},
   function(m){m.reference.duration_seconds=Infinity;}, function(m){m.defaults.started=0;},
   function(m){m.defaults.accepted=2;}, function(m){m.defaults.accepted="1";},
   function(m){m.defaults.hourly_value=-1;}, function(m){m.defaults.video_model="unknown";}
  ].forEach(function(change){
    const broken=JSON.parse(JSON.stringify(model)); change(broken);
    assert.equal(cost.validModel(broken),false);
    assert.equal(cost.defaults(broken,"education"),null);
    assert.equal(cost.calculate(broken,{}).ok,false);
  });
});
check("price change in single source changes output", function () {
  const changed = JSON.parse(JSON.stringify(model)); changed.video_models[0].per_native_second *= 2;
  near(cost.calculate(changed, cost.defaults(changed, "brand")).total_per_accepted - calculate("brand").total_per_accepted, 3.6);
});
check("browser module order and accessible calculator integration remain", function () {
  const html = fs.readFileSync(path.join(base, "dist/content-studio/index.html"), "utf8");
  const css = fs.readFileSync(path.join(base, "dist/content-studio/styles.css"), "utf8");
  const app = fs.readFileSync(path.join(base, "dist/content-studio/app.js"), "utf8");
  assert.ok(html.indexOf('src="./costs.js"') < html.indexOf('src="./app.js"'));
  assert.match(html, /id="cost-result"[^>]*aria-live="polite"/);
  assert.match(html, /id="cost-error"[^>]*role="alert"/);
  assert.match(css, /html\{scroll-behavior:auto/);
  assert.ok(app.includes("hub.cost_model")); assert.ok(app.includes("HeoBrainCosts"));
});
check("simulated DOM initializes from the single JSON source", function () {
  const vm = require("node:vm");
  const html = fs.readFileSync(path.join(base, "dist/content-studio/index.html"), "utf8");
  class Node {
    constructor(tag) { this.tagName = tag.toUpperCase(); this.children = []; this.attrs = {}; this.hidden = false; this.disabled = false; this._value = ""; this._text = ""; }
    set value(v) { this._value = String(v); }
    get value() { return this._value; }
    set textContent(v) { this._text = String(v); this.children = []; }
    get textContent() { return this._text + this.children.map(function (n) { return n.textContent || ""; }).join(" "); }
    get childElementCount() { return this.children.length; }
    append(...nodes) { this.children.push(...nodes); if (this.tagName === "SELECT" && !this.value && nodes.length) this.value = nodes[0].value; }
    replaceChildren(...nodes) { this.children = []; this._text = ""; if (this.tagName === "SELECT") this.value = ""; this.append(...nodes); }
    setAttribute(k, v) { this.attrs[k] = String(v); }
    removeAttribute(k) { delete this.attrs[k]; }
    focus() { this.focused = true; }
  }
  const nodes = {};
  for (const id of html.matchAll(/id="([^"]+)"/g)) { assert.equal(nodes[id[1]], undefined, "duplicate ID " + id[1]); nodes[id[1]] = new Node(id[1] === "cost-scenario" || id[1] === "cost-video-model" ? "select" : "div"); }
  const sandbox = {
    window: { HeoBrainCosts: cost }, testModel: model, URL, Intl, AbortController, setTimeout, clearTimeout,
    document: { getElementById: function (id) { assert.ok(nodes[id], "unknown ID " + id); return nodes[id]; }, createElement: function (tag) { return new Node(tag); }, addEventListener: function () {} }
  };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(base, "dist/content-studio/app.js"), "utf8"), sandbox);
  vm.runInContext("hub.cost_model = testModel; setupCostCalculator();", sandbox);
  assert.equal(nodes["cost-fields"].disabled, false);
  assert.match(nodes["cost-result"].textContent, /8\.79/);
  vm.runInContext('document.getElementById("cost-scenario").value = "story"; resetCostInputs(false);', sandbox);
  assert.equal(nodes["cost-takes"].value, "24");
  assert.match(nodes["cost-result"].textContent, /40\.19/);
  nodes["cost-accepted"].value = "0";
  vm.runInContext("updateCostResult(true);", sandbox);
  assert.equal(nodes["cost-result"].childElementCount, 0);
  assert.equal(nodes["cost-error"].hidden, false);
  assert.equal(nodes["cost-accepted"].attrs["aria-invalid"], "true");
  assert.equal(nodes["cost-accepted"].focused, true);
  nodes["cost-accepted"].value = "1";
  vm.runInContext("updateCostResult();", sandbox);
  assert.equal(nodes["cost-error"].hidden, true);
  assert.match(nodes["cost-result"].textContent, /40\.19/);
  vm.runInContext("hub.cost_model = null; setupCostCalculator();", sandbox);
  assert.equal(nodes["cost-fields"].disabled, true);
  assert.doesNotMatch(nodes["cost-result"].textContent, /40\.19/);
  sandbox.brokenModel=JSON.parse(JSON.stringify(model)); delete sandbox.brokenModel.reference;
  vm.runInContext("hub.cost_model = brokenModel; setupCostCalculator();", sandbox);
  assert.equal(nodes["cost-fields"].disabled,true);
  assert.match(nodes["cost-result"].textContent,/원가 기준 자료를 확인하지 못했습니다/);
});
console.log("All " + checks + " content cost checks passed. No paid calls or generation performed.");
