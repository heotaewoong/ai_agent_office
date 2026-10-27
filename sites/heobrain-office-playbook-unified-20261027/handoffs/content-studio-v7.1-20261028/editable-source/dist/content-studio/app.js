"use strict";

const DEFAULT_DATA = {
  meta: {
    version: "v7.1 · 검토 보강판",
    date: "2026-10-28",
    verification: "문서 근거·계정 가용성·실제 생성 결과를 구분하는 기획 안내서입니다. 계정 연결·콘텐츠 생성·발행은 이 화면에서 실행하지 않습니다."
  },
  recommendations: [
    { id: "explain-first", title: "설명형 콘텐츠부터 시작", role: "블로그·뉴스레터·설명 영상", tools: ["검토한 원고", "도표·실제 데모", "음성과 자막"], rationale: "핵심 주장과 출처를 먼저 정리하고, 읽기와 이해에 필요한 장면을 고릅니다.", readiness: "기본 기획안", condition: "원고 검토 후 영상·이미지 제작 범위를 정합니다." },
    { id: "selective-video", title: "핵심 장면만 영상 생성", role: "짧은 영상·상품 소개", tools: ["이미지·영상 API 후보", "기존 장면", "최종 편집"], rationale: "영상 생성이 필요한 장면을 골라 비용과 수정량을 함께 비교합니다.", readiness: "기본 기획안", condition: "계정 가용성·이용 권리·유료 예산을 먼저 확인합니다." },
    { id: "channel-adapt", title: "원고 하나를 채널에 맞게", role: "멀티채널 콘텐츠", tools: ["공통 원고", "채널별 레이아웃", "검수·인계"], rationale: "블로그, 뉴스레터, 영상마다 길이와 읽는 순서, 행동 안내를 바꿉니다.", readiness: "기본 기획안", condition: "각 채널의 최종 발행은 별도 승인을 거칩니다." }
  ],
  tools: [],
  pipeline: [
    ["자료 찾기", "공식 발표·문서·허용된 자료에서 후보를 찾습니다.", "관심 주제와 허용된 소스", "자료 후보 목록", "수집 범위 확인"],
    ["자료 기록·중복 정리", "출처와 날짜를 남기고 같은 자료를 구분합니다.", "자료 후보", "중복을 구분한 자료 기록", "원문·버전 확인"],
    ["주장·권리 확인", "쓸 수 있는 사실과 자산의 이용 범위를 확인합니다.", "원문·자산", "주장과 출처·이용 범위", "근거·권리 검토"],
    ["주제 고르기", "독자의 질문과 만들 결과물을 정합니다.", "검토한 자료", "주제·독자·핵심 질문", "제작 범위 선택"],
    ["원고 초안", "근거를 연결하며 공통 원고를 씁니다.", "주제와 근거", "출처가 연결된 초안", "없는 사실·성과 추가 금지"],
    ["비평·수정", "사실, 구성, 문장을 검토해 고칩니다.", "초안과 기준", "수정 원고와 남은 쟁점", "독립 검토"],
    ["원고 승인", "영상·이미지로 바꿀 원고의 판본을 고정합니다.", "검토한 원고", "승인된 원고 판본", "사람의 원고 승인"],
    ["장면·음성 기획", "장면, 내레이션, 도표, 자막을 나눕니다.", "승인 원고", "장면 계획과 음성·자막 기준", "유료 생성·음성 이용 범위 확인"],
    ["시각 자산·썸네일", "선택한 장면과 썸네일을 검토합니다.", "장면 계획", "검토할 이미지·장면·썸네일", "비용·사실·이용 권리 확인"],
    ["렌더·품질 확인", "레이아웃과 음성·자막·파일을 확인합니다.", "승인 자산과 타임라인", "채널별 검수본", "내용·화면·파일 검증"],
    ["채널별 발행 승인", "채널의 조건과 최종 결과물을 함께 확인합니다.", "검수본과 메타데이터", "승인된 발행 또는 수동 인계", "외부 실행 별도 승인"],
    ["성과·다음 개선", "관찰한 결과와 수정할 점을 남깁니다.", "실제 발행·측정 기록", "개선 기록과 다음 검토", "실측과 추정 구분"]
  ].map(function (item, index) {
    return { id: "draft-step-" + (index + 1), name: item[0], description: item[1], input: item[2], output: item[3], gate: item[4], status: "기본 기획안 · 운영 검증 별도", acceptance: "단계별 기준을 실제 입력과 결과로 확인합니다.", tools: [] };
  }),
  ideas: [],
  sources: [],
  channels: [],
  resources: { pdfs: [] },
  gates: [
    { id: "G0", name: "⓪ 기획 선택", scope: "독자의 질문과 만들 결과물을 선택합니다. 데이터 로드에 실패했으므로 자세한 현행 상태는 통합 문서에서 확인하세요.", invalidation: "독자·문제·목표가 바뀌면 기획을 다시 검토합니다." },
    { id: "G1", name: "① 원고 승인", scope: "다음 제작에 사용할 원고 판본을 확인합니다. 예산·화자·자산 결속은 추가 설계와 구분합니다.", invalidation: "원고 판본과 영향을 받는 제작 조건을 다시 확인합니다." },
    { id: "G2", name: "② 출력별 출고", scope: "각 출력의 파일·내용·권리와 인계 조건을 검토합니다. 실제 외부 게시 연결은 별도 확인합니다.", invalidation: "파일·대상·공개 조건이 바뀌면 해당 출력을 재검토합니다." },
    { id: "G3", name: "③ 회차 승인", scope: "뉴스레터·홍보 회차의 대상·동의·빈도·조건을 검토하는 확장 단계입니다. 실제 발송은 미연결입니다.", invalidation: "회차·대상·동의·내용·예산이 바뀌면 재검토합니다." }
  ],
  handoff: { notes: ["README에서 읽을 순서와 현재 검증 상태를 확인하세요.", "다른 모델로 넘길 때 선택 이유, 남은 검증, 변경 기록도 함께 보관하세요.", "원고 승인·유료 생성·발행·쿠폰 실행의 범위를 각각 확인하세요."] }
};

let hub = DEFAULT_DATA;
const filters = { query: "", stage: "", automation: "", theme: "" };
const $ = function (id) { return document.getElementById(id); };
const items = function (value) { return Array.isArray(value) ? value : []; };
const rows = function (value) { return items(value).filter(function (item) { return item && typeof item === "object" && !Array.isArray(item); }); };

function text(value, fallback) {
  if (value === null || value === undefined || value === "") return fallback || "확인 중";
  if (Array.isArray(value)) return value.map(function (part) { return text(part, ""); }).filter(Boolean).join(" · ") || fallback || "확인 중";
  if (typeof value === "object") return Object.entries(value).map(function (entry) { return entry[0] + ": " + text(entry[1]); }).join(" · ");
  return String(value);
}

function normalize(value) {
  return String(value || "").normalize("NFKC").toLocaleLowerCase("ko-KR").replace(/\s+/g, " ").trim();
}

function matches(value, query) {
  return !normalize(query) || normalize(JSON.stringify(value)).includes(normalize(query));
}

function safeHref(value) {
  if (typeof value !== "string") return null;
  const raw = value.trim();
  if (!raw || /[\u0000-\u0020\u007f\\]/.test(raw)) return null;
  if (/^#[a-zA-Z][a-zA-Z0-9_-]*$/.test(raw)) return raw;
  const relative = raw.replace(/^\.\//, "");
  if (/^downloads\/[a-zA-Z0-9_-][a-zA-Z0-9_.-]*\.(md|json|zip|pdf)$/i.test(relative) && !relative.includes("..")) return relative;
  if (!/^https?:\/\//i.test(raw)) return null;
  try {
    const url = new URL(raw);
    return (url.protocol === "http:" || url.protocol === "https:") && !url.username && !url.password ? url.href : null;
  } catch (_) {
    return null;
  }
}

function el(tag, className, value) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (value !== undefined) node.textContent = text(value, "");
  return node;
}

function label(value) {
  const labels = {
    official_api: "공식 API", official_mcp: "공식 MCP", local_cli: "로컬 CLI",
    local: "로컬 실행", manual_handoff: "수동 인계", manual: "수동 제작",
    unsupported: "지원 확인 안 됨", unverified: "확인 필요", planned: "설계 제안",
    candidate: "비교 후보", verified: "기재된 근거 확인", ko: "한국어", en: "영어",
    phase1: "초기 검토", phase2: "확장 검토", phase3: "추가 검토"
  };
  return labels[value] || text(value);
}

function addTags(parent, values, amber) {
  const present = values.filter(function (value) { return value !== null && value !== undefined && value !== ""; });
  if (!present.length) return;
  const group = el("div", "tag-row");
  present.forEach(function (value, index) { group.append(el("span", "tag" + (amber && index === present.length - 1 ? " tag-amber" : ""), label(value))); });
  parent.append(group);
}

function addDefinitions(parent, pairs, className) {
  const dl = el("dl", "card-dl" + (className ? " " + className : ""));
  pairs.forEach(function (pair) { dl.append(el("dt", "", pair[0]), el("dd", "", pair[1])); });
  parent.append(dl);
}

function addLinks(parent, links) {
  const group = el("div", "card-links");
  rows(links).forEach(function (item) {
    const href = safeHref(item.url);
    if (!href) return;
    const link = el("a", "", item.label || "공식 자료");
    link.href = href;
    if (/^https?:/.test(href)) { link.target = "_blank"; link.rel = "noopener noreferrer"; }
    else if (href.startsWith("downloads/")) link.setAttribute("download", "");
    group.append(link);
  });
  if (group.childElementCount) parent.append(group);
}

function empty(parent, title, detail) {
  const box = el("div", "empty-state");
  box.append(el("p", "", title), el("p", "small-meta", detail || "검색어나 필터를 바꿔 보세요. 검색·필터 초기화로 전체 목록을 볼 수 있습니다."));
  parent.append(box);
}

function setOptions(id, values, firstLabel) {
  const select = $(id);
  select.replaceChildren();
  const first = el("option", "", firstLabel);
  first.value = "";
  select.append(first);
  Array.from(new Set(values.filter(function (value) { return typeof value === "string" && value.trim(); }))).sort(function (a, b) { return a.localeCompare(b, "ko"); }).forEach(function (value) {
    const option = el("option", "", label(value));
    option.value = value;
    select.append(option);
  });
}

function renderRecommendations() {
  const container = $("recommendations");
  container.replaceChildren();
  const provided = rows(hub.recommendations);
  const cards = provided.length ? provided.concat(DEFAULT_DATA.recommendations).slice(0, 3) : DEFAULT_DATA.recommendations;
  cards.forEach(function (item, index) {
    const card = el("article", "recommendation-card");
    card.append(el("span", "card-number", "0" + (index + 1)), el("h3", "", item.title));
    addTags(card, [item.role, item.readiness]);
    card.append(el("p", "", item.rationale));
    if (items(item.tools).length) card.append(el("p", "tool-names", items(item.tools)));
    card.append(el("p", "card-condition", item.condition));
    container.append(card);
  });
}

function routePreview() {
  const channel = $("route-channel").value;
  const visual = $("route-visual").value;
  const budget = $("route-budget").value;
  const preview = $("route-preview");
  const titles = { article: "블로그와 뉴스레터의 공통 원고", short: "짧은 영상의 핵심 장면", explain: "설명형 영상의 읽기 쉬운 구성", product: "검증한 상품 정보로 만드는 안내" };
  const paths = {
    article: ["출처·이용 범위 확인", "원고·주장 검토", "대표 이미지·도표 선택", "채널별 원고 인계", "발행 조건 승인"],
    short: ["주제·근거 확인", "짧은 대본 승인", "장면·음성·자막 계획", "세로 화면 검수", "채널 발행 승인"],
    explain: ["출처·주장 확인", "설명 대본 승인", "데모·도표·장면 구성", "음성·자막·렌더 검수", "채널 발행 승인"],
    product: ["상품·조건 확인", "소개 원고 승인", "이미지·장면 계획", "실제 화면·조건 검수", "발행·캠페인 각각 승인"]
  };
  const visualNotes = {
    diagram: "검토할 표현: 직접 만든 도표, 승인된 제품 데모, 이미지 모션과 읽기 쉬운 텍스트 레이어.",
    generated: budget === "draft" ? "생성 영상은 필요한 장면과 견적만 정리합니다. 초안은 기존 자산·도표로 검토합니다." : "영상 API의 계정 가용성·이용 권리·견적을 확인한 다음 승인된 예산 안의 핵심 장면을 선택합니다.",
    motion: "3D 장면은 필요한 구간만 선택합니다. Blender 등으로 만든 장면과 전체 영상 렌더를 나누고 장비 여유를 확인합니다."
  };
  preview.replaceChildren(el("h3", "", titles[channel]), el("p", "", visualNotes[visual]));
  const list = el("ol", "route-flow");
  paths[channel].forEach(function (step) { list.append(el("li", "", step)); });
  preview.append(list);
  preview.append(el("p", "route-note", "이 선택은 기획 안내를 바꿉니다. API 호출·렌더·결제·게시·쿠폰 발급은 실행하지 않습니다."));
}

function renderTools() {
  const container = $("tool-list");
  container.replaceChildren();
  const selected = rows(hub.tools).filter(function (item) {
    return matches(item, filters.query) && (!filters.stage || item.stage === filters.stage) && (!filters.automation || item.automation === filters.automation);
  });
  $("tool-count").textContent = selected.length + "개 도구 표시";
  selected.forEach(function (item) {
    const card = el("article", "tool-card");
    card.append(el("h3", "", item.name));
    addTags(card, [item.stage, item.choice]);
    card.append(el("p", "card-status", item.implemented === true ? "연동 구현 표시 · 실제 운영 검증은 상세 기록 확인" : "설계·선택 후보 · 실제 연결과 생성 검증은 별도"));
    addDefinitions(card, [
      ["연결 방식", label(item.automation)],
      ["확인 상태", item.status],
      ["선택 이유", item.reason],
      ["제약", item.limitations],
      ["비용", item.cost],
      ["권리 조건", item.license]
    ]);
    if (items(item.requestedNames).length) card.append(el("p", "small-meta", "요청한 이름: " + text(item.requestedNames)));
    addLinks(card, item.urls);
    if (item.verifiedAt) card.append(el("p", "verified-date", "기재된 근거 확인일 · " + text(item.verifiedAt)));
    container.append(card);
  });
  if (!selected.length) empty(container, rows(hub.tools).length ? "조건에 맞는 도구가 없습니다." : "도구 비교 자료를 확인 중입니다.", rows(hub.tools).length ? undefined : "통합 기획서와 도구·권리 문서에서 선택 조건을 확인할 수 있습니다.");
  return selected.length;
}

function renderPipeline() {
  const container = $("pipeline-list");
  container.replaceChildren();
  const pipeline = rows(hub.pipeline).length ? rows(hub.pipeline) : DEFAULT_DATA.pipeline;
  $("pipeline-title").textContent = "콘텐츠 제작의 " + pipeline.length + "단계";
  pipeline.forEach(function (item) {
    const card = el("li", "step-card");
    card.append(el("h3", "", item.name), el("p", "step-description", item.description));
    addTags(card, [item.status]);
    const detail = el("details");
    detail.append(el("summary", "", "입력·산출물·검수 조건"));
    const pairs = [["입력", item.input], ["산출물", item.output], ["승인", item.gate], ["통과 기준", item.acceptance]];
    if (items(item.tools).length) pairs.push(["검토 도구", item.tools]);
    addDefinitions(detail, pairs, "wide-label");
    card.append(detail);
    container.append(card);
  });
}

function renderIdeas() {
  const container = $("idea-list");
  container.replaceChildren();
  const selected = rows(hub.ideas).filter(function (item) { return matches(item, filters.query) && (!filters.theme || item.theme === filters.theme); });
  $("idea-count").textContent = selected.length + "개 아이디어 표시";
  selected.forEach(function (item) {
    const card = el("article", "idea-card");
    addTags(card, [item.theme, item.phase]);
    card.append(el("h3", "", item.title));
    addDefinitions(card, [["필요한 입력", item.input], ["만들 결과", item.output], ["검토 도구", item.tools], ["승인 조건", item.gate]], "wide-label");
    const check = el("p", "first-check");
    check.append(el("strong", "", "첫 확인"), document.createTextNode(text(item.firstCheck)));
    card.append(check);
    container.append(card);
  });
  if (!selected.length) empty(container, rows(hub.ideas).length ? "조건에 맞는 아이디어가 없습니다." : "아이디어 목록을 확인 중입니다.");
  return selected.length;
}

function renderSources() {
  const container = $("source-list");
  container.replaceChildren();
  const selected = rows(hub.sources).filter(function (item) { return matches(item, filters.query); });
  $("source-count").textContent = selected.length + "개 소스 표시";
  selected.forEach(function (item) {
    const card = el("article", "source-card");
    addTags(card, [item.type, item.confidence]);
    card.append(el("h3", "", item.name), el("p", "", item.why));
    addDefinitions(card, [["수집", item.collection], ["주기", item.frequency], ["이용 범위", item.rights]]);
    addLinks(card, [{ label: "소스 원문 ↗", url: item.url }]);
    container.append(card);
  });
  if (!selected.length) empty(container, rows(hub.sources).length ? "조건에 맞는 소스가 없습니다." : "소스 목록을 확인 중입니다.", rows(hub.sources).length ? undefined : "공식 소스·수집 경로·이용 범위는 소스와 벤치마킹 문서에서도 확인할 수 있습니다.");
  return selected.length;
}

function renderChannels() {
  const container = $("channel-list");
  container.replaceChildren();
  rows(hub.channels).forEach(function (item) {
    const card = el("article", "channel-card");
    card.append(el("h3", "", item.name));
    addTags(card, [item.mode]);
    addDefinitions(card, [["준비 상태", item.readiness], ["필요한 승인", item.approval], ["제약", item.limitations]], "wide-label");
    addLinks(card, [{ label: "채널 관련 근거 ↗", url: item.url }]);
    container.append(card);
  });
  if (!container.childElementCount) empty(container, "채널별 연결과 승인 조건을 확인 중입니다.", "음성과 멀티채널 문서에서 공식 연결·수동 인계·미확인 경로를 구분해 살펴보세요.");
  const gateContainer = $("gate-list");
  gateContainer.replaceChildren();
  const gates = rows(hub.gates).length ? rows(hub.gates) : DEFAULT_DATA.gates;
  gates.forEach(function (item) {
    const card = el("article", "gate-card");
    card.append(el("h4", "", item.name), el("p", "", item.scope), el("p", "", "다시 확인할 때 · " + text(item.invalidation)));
    gateContainer.append(card);
  });
}

function countLabel(value) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value.toLocaleString("ko-KR") : "확인 중";
}

function renderResourceStats() {
  const resources = hub.resources || {};
  if (typeof resources.scope === "string" && resources.scope.trim()) $("resource-scope").textContent = resources.scope;
  const container = $("resource-stats");
  container.replaceChildren();
  [["기존 보관 PDF", resources.existing_count], ["이번에 검증한 PDF", resources.verified_count], ["이번 신규 PDF", resources.new_count], ["구독 도서 새 변환", resources.subscription_new_count]].forEach(function (pair) {
    const box = el("div", "stat-box");
    box.append(el("dt", "", pair[0]), el("dd", "", countLabel(pair[1])));
    container.append(box);
  });
  $("resource-pages").textContent = "문서에 기재된 페이지 합계 · " + countLabel(resources.pages) + "쪽";
}

function renderResources() {
  const resources = hub.resources || {};
  const container = $("resource-list");
  container.replaceChildren();
  const selected = rows(resources.pdfs).filter(function (item) { return matches(item, filters.query); });
  selected.forEach(function (item) {
    const card = el("article", "resource-item");
    card.append(el("h3", "", item.title), el("p", "", label(item.language) + " · " + countLabel(item.pages) + "쪽"), el("p", "", "이용 범위 · " + text(item.license)));
    addLinks(card, [{ label: "PDF 또는 보관 위치 ↗", url: item.url }, { label: "공식 배포 근거 ↗", url: item.source_url }]);
    if (!safeHref(item.url)) card.append(el("p", "small-meta", "웹에서 열 수 있는 파일 링크는 확인 중입니다. 로컬 보관 경로는 인계 문서를 확인하세요."));
    container.append(card);
  });
  if (!selected.length) empty(container, rows(resources.pdfs).length ? "검색어에 맞는 PDF가 없습니다." : "파일별 확보 기록을 확인 중입니다.", rows(resources.pdfs).length ? undefined : "검증 수·신규 수·구독 도서 변환 상태는 인계 문서의 최신 기록과 함께 확인하세요.");
  return selected.length;
}

function renderHandoff() {
  const container = $("handoff-notes");
  container.replaceChildren();
  const notes = items(hub.handoff && hub.handoff.notes);
  (notes.length ? notes : DEFAULT_DATA.handoff.notes).forEach(function (note) { container.append(el("li", "", note)); });
}

function renderFiltered() {
  const counts = [renderTools(), renderIdeas(), renderSources(), renderResources()];
  $("filter-summary").textContent = "목록 표시 · 도구 " + counts[0] + "개 · 아이디어 " + counts[1] + "개 · 소스 " + counts[2] + "개 · PDF " + counts[3] + "개";
}

function renderAll() {
  const meta = hub.meta || {};
  if (typeof meta.title === "string" && meta.title.trim()) document.title = meta.title + " · HeoBrain";
  if (typeof meta.scope === "string" && meta.scope.trim()) $("page-scope").textContent = meta.scope;
  if (typeof meta.verification === "string" && meta.verification.trim()) $("verification-text").textContent = meta.verification;
  $("side-version").textContent = text(meta.version, "v7.1 · 검토 보강판");
  $("meta-date").textContent = text(meta.date, "2026-10-28");
  if (/^\d{4}-\d{2}-\d{2}$/.test(meta.date || "")) $("meta-date").dateTime = meta.date;
  setOptions("tool-stage", rows(hub.tools).map(function (item) { return item.stage; }), "모든 단계");
  setOptions("tool-automation", rows(hub.tools).map(function (item) { return item.automation; }), "모든 연결 방식");
  setOptions("idea-theme", rows(hub.ideas).map(function (item) { return item.theme; }), "모든 주제");
  renderRecommendations();
  renderPipeline();
  renderChannels();
  renderResourceStats();
  renderHandoff();
  routePreview();
  renderFiltered();
  setupCostCalculator();
}

let costModelReady = null;
const costFieldIds = { scenario: "cost-scenario", started: "cost-started", accepted: "cost-accepted", video_takes: "cost-takes", human_minutes: "cost-human", hourly_value: "cost-hourly", video_model: "cost-video-model" };

function costMoney(value) {
  return new Intl.NumberFormat("ko-KR", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
}

function resetCostInputs(all) {
  const initial = window.HeoBrainCosts.defaults(hub.cost_model, $("cost-scenario").value);
  if (!initial) return;
  Object.keys(costFieldIds).forEach(function (field) {
    if (all || field === "video_takes" || field === "human_minutes") $(costFieldIds[field]).value = initial[field];
  });
  updateCostResult();
}

function setupCostCalculator() {
  const api = window.HeoBrainCosts, model = hub.cost_model;
  if (!api || !api.validModel(model)) {
    $("cost-fields").disabled = true;
    $("cost-result").replaceChildren(el("p", "", "원가 기준 자료를 확인하지 못했습니다. 아래 인계 문서의 ‘제작경로와 수용 원가’를 읽어 주세요."));
    costModelReady = null;
    return;
  }
  if (costModelReady === model) return;
  costModelReady = model;
  $("cost-fields").disabled = false;
  [["cost-scenario", model.scenarios], ["cost-video-model", model.video_models]].forEach(function (pair) {
    $(pair[0]).replaceChildren();
    pair[1].forEach(function (item) { const option = el("option", "", item.name); option.value = item.id; $(pair[0]).append(option); });
  });
  [["cost-started", model.limits.max_started], ["cost-accepted", model.limits.max_started], ["cost-takes", model.limits.max_takes_per_started], ["cost-human", model.limits.max_human_minutes_per_started], ["cost-hourly", model.limits.max_hourly_value]].forEach(function (pair) { $(pair[0]).max = pair[1]; });
  $("cost-notes").replaceChildren();
  items(model.notes).forEach(function (note) { $("cost-notes").append(el("li", "", note)); });
  $("cost-rates").replaceChildren(el("h4", "", "공식 공개 단가 · 확인일 " + text(model.checked_at)));
  const r = model.rates;
  addDefinitions($("cost-rates"), [
    [r.llm.name, "입력 $" + r.llm.input_per_million + " / 출력 $" + r.llm.output_per_million + " (백만 토큰)"],
    [r.image.name, "출력 $" + r.image.output_per_image + "/장 + 입력 $" + r.image.input_per_million + " / 텍스트·생각 출력 $" + r.image.text_output_per_million + " (백만 토큰)"],
    [r.tts.name, "$" + r.tts.per_thousand_characters + "/천 문자"]
  ], "wide-label");
  model.video_models.forEach(function (item) { $("cost-rates").append(el("p", "small-meta", item.name + " $" + item.per_native_second + "/과금 원본 초")); });
  addLinks($("cost-rates"), [].concat(items(r.llm.urls), items(r.image.urls), items(r.tts.urls), ...model.video_models.map(function (item) { return items(item.urls); })));
  resetCostInputs(true);
}

function updateCostResult(focusError) {
  const api = window.HeoBrainCosts;
  if (!api || !costModelReady) return;
  const input = {};
  Object.keys(costFieldIds).forEach(function (field) { const node = $(costFieldIds[field]); input[field] = node.value; node.removeAttribute("aria-invalid"); node.setAttribute("aria-describedby", "cost-help cost-error"); });
  const result = api.calculate(hub.cost_model, input);
  const output = $("cost-result"), error = $("cost-error");
  output.replaceChildren();
  if (!result.ok) {
    error.hidden = false;
    error.textContent = result.errors.map(function (item) { return item.message; }).join(" ");
    result.errors.forEach(function (item) { if (costFieldIds[item.field]) $(costFieldIds[item.field]).setAttribute("aria-invalid", "true"); });
    if (focusError && result.errors[0] && costFieldIds[result.errors[0].field]) $(costFieldIds[result.errors[0].field]).focus();
    return;
  }
  error.hidden = true; error.textContent = "";
  output.append(el("p", "", result.scenario.name + " · " + result.inputs.started + "편 시작 / " + result.inputs.accepted + "편 수용 · " + text(hub.cost_model.reference.duration_seconds) + "초 편집 영상 기준 가정"));
  const stats = el("div", "cost-stats");
  [["사용량 환산 / 수용 1편", result.usage_per_accepted], ["사람 시간 평가 / 수용 1편", result.human_per_accepted], ["합계 / 수용 1편", result.total_per_accepted]].forEach(function (pair, index) {
    const card = el("dl", "cost-stat" + (index === 2 ? " total" : ""));
    card.append(el("dt", "", pair[0]), el("dd", "", costMoney(pair[1]))); stats.append(card);
  });
  output.append(stats);
  const breakdown = el("div", "cost-breakdown");
  const scale = result.inputs.started / result.inputs.accepted, c = result.components_per_started;
  addDefinitions(breakdown, [["글", costMoney(c.llm * scale)], ["이미지", costMoney(c.image * scale)], ["생성 영상", costMoney(c.video * scale)], ["TTS", costMoney(c.tts * scale)], ["자원 가정", costMoney(c.resources * scale)]]);
  output.append(breakdown, el("p", "", "기간 사용량 환산 " + costMoney(result.period_usage) + " + 사람 시간 평가 " + costMoney(result.period_human) + "를 수용 " + result.inputs.accepted + "편으로 나눕니다. 과금 원본 영상 합계 " + result.billed_native_seconds + "초. 고정 구독·세금 등 제외 항목은 아래를 확인하세요."));
  output.append(el("h3", "", "영상 단가만 바꿔 대입하면"));
  const compare = el("div", "cost-compare");
  result.comparison.forEach(function (item) { const card = el("p", "", item.name + " · 같은 입력 수량에 단가만 대입"); card.append(el("strong", "", costMoney(item.total_per_accepted) + " / 수용 1편")); compare.append(card); });
  output.append(compare, el("p", "", "두 모델의 품질·수용률·수정시간이 같다는 뜻이 아닙니다. 실제 결과로 테이크 수와 사람 작업 분을 각각 바꿔 비교해야 합니다. 실제 품질 비교는 아직 수행하지 않았습니다."));
  const baselines = hub.cost_model.scenarios.map(function (scenario) {
    const baseline = api.calculate(hub.cost_model, api.defaults(hub.cost_model, scenario.id));
    return baseline.ok ? scenario.name + " " + costMoney(baseline.total_per_accepted) : scenario.name + " 확인 필요";
  });
  output.append(el("p", "cost-baseline", "문서의 기본 가정 기준선: " + baselines.join(" · ") + ". 현재 입력과 별개인 설명용 기준이며 실제 제작비가 아닙니다."));
  $("cost-input-summary").replaceChildren(el("h4", "", result.scenario.name + " · 시작 1편당 고정한 입력 가정"), el("p", "small-meta", result.scenario.description));
  addDefinitions($("cost-input-summary"), [
    ["글 토큰", "입력 " + result.scenario.llm_input_tokens + " / 출력 " + result.scenario.llm_output_tokens],
    ["이미지", result.scenario.image_attempts + "회 · 입력 " + result.scenario.image_input_tokens + " / 텍스트·생각 출력 " + result.scenario.image_text_output_tokens + "토큰"],
    ["음성", result.scenario.tts_billable_characters + " 과금 문자"],
    ["영상", "테이크당 원본 " + result.scenario.native_seconds_per_take + "초 · 길이·모델 지원은 실제 호출 전 확인"],
    ["자원", costMoney(result.scenario.resource_allowance_usd) + " / 시작 1편, 실측 아님"]
  ]);
}

function setupNavigation() {
  if (!("IntersectionObserver" in window)) return;
  const links = Array.from(document.querySelectorAll(".toc a"));
  const observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (!entry.isIntersecting) return;
      links.forEach(function (link) {
        if (link.getAttribute("href") === "#" + entry.target.id) link.setAttribute("aria-current", "location");
        else link.removeAttribute("aria-current");
      });
    });
  }, { rootMargin: "-8% 0px -65% 0px", threshold: 0 });
  document.querySelectorAll("main > section[id]").forEach(function (section) { observer.observe(section); });
}

async function loadData() {
  const controller = new AbortController();
  const timer = setTimeout(function () { controller.abort(); }, 10000);
  try {
    const response = await fetch("./hub-data.json", { signal: controller.signal, cache: "no-store" });
    if (!response.ok) throw new Error("Hub data unavailable");
    const incoming = await response.json();
    if (!incoming || typeof incoming !== "object" || Array.isArray(incoming)) throw new Error("Invalid hub data");
    hub = Object.assign({}, DEFAULT_DATA, incoming);
    hub.meta = Object.assign({}, DEFAULT_DATA.meta, incoming.meta && typeof incoming.meta === "object" ? incoming.meta : {});
    hub.resources = incoming.resources && typeof incoming.resources === "object" ? incoming.resources : DEFAULT_DATA.resources;
    $("data-error").hidden = true;
    renderAll();
  } catch (_) {
    $("data-error").hidden = false;
  } finally {
    clearTimeout(timer);
  }
}

function boot() {
  renderAll();
  $("global-search").addEventListener("input", function (event) { filters.query = event.target.value; renderFiltered(); });
  [["tool-stage", "stage"], ["tool-automation", "automation"], ["idea-theme", "theme"]].forEach(function (pair) {
    $(pair[0]).addEventListener("change", function (event) { filters[pair[1]] = event.target.value; renderFiltered(); });
  });
  ["route-channel", "route-visual", "route-budget"].forEach(function (id) { $(id).addEventListener("change", routePreview); });
  $("reset-filters").addEventListener("click", function () {
    filters.query = ""; filters.stage = ""; filters.automation = ""; filters.theme = "";
    $("global-search").value = "";
    ["tool-stage", "tool-automation", "idea-theme"].forEach(function (id) { $(id).value = ""; });
    renderFiltered();
    $("global-search").focus();
  });
  $("cost-form").addEventListener("submit", function (event) { event.preventDefault(); updateCostResult(true); });
  Object.keys(costFieldIds).forEach(function (field) {
    $(costFieldIds[field]).addEventListener(field === "scenario" || field === "video_model" ? "change" : "input", function () {
      if (field === "scenario") resetCostInputs(false); else updateCostResult();
    });
  });
  $("cost-reset").addEventListener("click", function () { resetCostInputs(true); });
  setupNavigation();
  loadData();
}

document.addEventListener("DOMContentLoaded", boot, { once: true });
