export type FlowStep =
  | { kind: "stage"; num: string; title: string; items: string[]; who: string; id?: string; input?: string; output?: string; entry?: string }
  | { kind: "gate"; mark: string; label: string; checks?: string }
  | { kind: "step" };
export type UnitCost = { task: string; role: string; unit: string; where: string };
export type UsageRow = { role: string; model: string; calls: number; krw: number; per_call: number };
export type TestCounts = { passed: number; failed: number; skipped?: number; errors?: number };
export type ArchitectureOverview = {
  doc: {
    headline: string;
    definition_version?: string;
    lanes?: { id: string; title: string; phase: string; label: string; state: "ok" | "warn" | "off"; steps: string[]; boundary: string }[];
    summary: string;
    flow: FlowStep[];
    unit_costs: UnitCost[];
    rails: { title: string; text: string }[];
    status: { state: "ok" | "warn" | "off"; label: string; text: string; note: string }[];
  };
  git: { commit: string | null; committed_at: string | null; subject: string | null; recent: { commit: string; at: string; author: string; subject: string }[] };
  build: { commit: string | null; deployed_at: string; tests: { backend: TestCounts; frontend: TestCounts } } | null;
  build_matches_running_code: boolean;
  keys: Record<"openai" | "gemini" | "runway" | "youtube", boolean>;
  profiles: { text: string; image: string };
  window: { status?: string | null; authorized_end?: string | null };
  worker: { state?: string | null; heartbeat?: string | null };
  budget: { cap_krw: number; spent_krw: number; reserved_krw: number; remaining_krw: number };
  usage: UsageRow[];
};

/** 문서의 작업 목록에 실측 사용량(모델·호출 수·평균 비용)을 붙인다. 아직 쓴 적 없는 작업은 "기록 없음". */
export function costRows(unitCosts: UnitCost[], usage: UsageRow[]) {
  return unitCosts.map((row) => {
    const used = usage.filter((u) => u.role === row.role);
    const calls = used.reduce((sum, u) => sum + u.calls, 0);
    const krw = used.reduce((sum, u) => sum + u.krw, 0);
    return {
      ...row,
      models: used.map((u) => u.model),
      calls,
      perCall: calls ? Math.round((krw / calls) * 10) / 10 : null,
      totalKrw: Math.round(krw * 10) / 10,
    };
  });
}

/** "백엔드 434 통과 · 화면 54 통과" 같은 한 줄 요약과 실패 여부. */
export function testSummary(build: ArchitectureOverview["build"]): { text: string; failed: boolean } {
  if (!build) return { text: "배포 기록 없음", failed: false };
  const b = build.tests.backend;
  const f = build.tests.frontend;
  const failed = (b.failed ?? 0) + (b.errors ?? 0) + (f.failed ?? 0) > 0;
  const part = (name: string, t: TestCounts) => `${name} ${t.passed} 통과${t.failed ? ` · ${t.failed} 실패` : ""}`;
  return { text: `${part("백엔드", b)} · ${part("화면", f)}`, failed };
}

export function shortCommit(commit: string | null | undefined) {
  return commit ? commit.slice(0, 7) : "확인 불가";
}


/** Keep every approval with its preceding stage, in source order. */
export function flowStages(flow: FlowStep[]) {
  const stages: { stage: Extract<FlowStep, { kind: "stage" }>; gates: Extract<FlowStep, { kind: "gate" }>[] }[] = [];
  for (const step of flow) {
    if (step.kind === "stage") stages.push({ stage: step, gates: [] });
    if (step.kind === "gate") {
      if (!stages.length) throw new Error("승인 앞에 공정이 필요합니다");
      stages[stages.length - 1].gates.push(step);
    }
  }
  return stages;
}

export function imageRoute(id: string) {
  return ({ "codex-subscription": "Codex 구독 로그인", "openai-gpt-image": "OpenAI 이미지 API", none: "생성 이미지 끔" } as Record<string, string>)[id] ?? id;
}

const xml = (value: string) => value.replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;" })[char]!);
function wrap(value: string, limit = 47) {
  const lines: string[] = []; let line = "", width = 0;
  for (const char of value) {
    const size = char.charCodeAt(0) > 255 ? 2 : 1;
    if (width + size > limit && line) { lines.push(line); line = ""; width = 0; }
    line += char; width += size;
  }
  if (line) lines.push(line);
  return lines;
}

/** Editable, self-contained vector map generated from the exact same document as the UI. */
export function pipelineSvg(doc: ArchitectureOverview["doc"]) {
  const stages = flowStages(doc.flow), parts: string[] = [];
  const text = (value: string, x: number, y: number, size = 20, fill = "#31473e", limit = 47, weight = 400) => {
    const lines = wrap(value, limit);
    parts.push(`<text x="${x}" y="${y}" fill="${fill}" font-size="${size}" font-weight="${weight}">${lines.map((line, i) => `<tspan x="${x}" dy="${i ? size * 1.5 : 0}">${xml(line)}</tspan>`).join("")}</text>`);
    return y + lines.length * size * 1.5;
  };
  text("HEOBRAIN · CONTENT PIPELINE", 60, 55, 18, "#426c58", 150, 700);
  let y = text(doc.headline, 60, 113, 36, "#193f32", 90, 700) + 16;
  y = text(doc.summary, 60, y, 22, "#526258", 145) + 30;
  y = text("⓪ 기획 선택 · ① 원고 승인 · ② 출력별 출고 승인 · ③ 회차 승인 — 모두 사람이 결정", 60, y, 20, "#865016", 160, 600) + 24;
  const width = 540, gap = 30, x0 = 60, points: { x: number; top: number; bottom: number }[] = [];
  for (let row = 0; row < Math.ceil(stages.length / 3); row++) {
    const slice = stages.slice(row * 3, row * 3 + 3), top = y;
    const ends: number[] = [];
    for (let col = 0; col < slice.length; col++) {
      const { stage, gates } = slice[col]; const x = x0 + (row % 2 ? 2 - col : col) * (width + gap);
      const begin = parts.length; parts.push("");
      parts.push(`<g data-node="stage-${row * 3 + col + 1}">`);
      let cy = text(stage.num, x + 24, top + 36, 18, "#426c58", 47, 700) + 8;
      cy = text(stage.title, x + 24, cy, 26, "#193f32", 36, 700) + 12;
      if (stage.input) cy = text("입력 · " + stage.input, x + 24, cy, 19, "#526258") + 12;
      for (const item of stage.items) cy = text("• " + item, x + 24, cy, 19) + 9;
      if (stage.output) cy = text("산출물 · " + stage.output, x + 24, cy + 6, 19, "#204e3d", 47, 600) + 12;
      cy = text(stage.who, x + 24, cy, 17, "#526258", 54) + 10;
      for (const gate of gates) cy = text(gate.mark + " " + gate.label + " · " + (gate.checks ?? "사람 확인"), x + 24, cy, 18, "#865016", 49, 600) + 12;
      const height = cy - top + 12;
      parts[begin] = `<rect data-card="stage-${row * 3 + col + 1}" x="${x}" y="${top}" width="${width}" height="${height}" rx="18" fill="#fffefa" stroke="#b9cfc0" stroke-width="2"/>`;
      parts.push("</g>");
      points.push({ x: x + width / 2, top, bottom: top + height }); ends.push(top + height);
    }
    y = Math.max(...ends) + 82;
  }
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1], b = points[i];
    const d = a.top === b.top ? `M${a.x + (b.x > a.x ? width / 2 : -width / 2)} ${a.top + 48} H${b.x + (b.x > a.x ? -width / 2 : width / 2)}` : `M${a.x} ${a.bottom} V${b.top}`;
    parts.push(`<path d="${d}" fill="none" stroke="#426c58" stroke-width="2.5" marker-end="url(#pipeline-arrow)"/>`);
  }
  y = text("병렬 제작과 별도 운영 흐름", 60, y, 28, "#193f32", 100, 700) + 20;
  for (const lane of doc.lanes ?? []) {
    const top = y, index = parts.length; parts.push("");
    parts.push(`<g data-node="lane-${xml(lane.id)}">`);
    y = text(lane.title + " · " + lane.label, 85, y + 34, 24, "#193f32", 120, 700) + 5;
    y = text(lane.phase, 85, y, 19, "#865016", 145) + 10;
    y = text(lane.steps.join(" → "), 85, y, 20, "#31473e", 145) + 8;
    y = text(lane.boundary, 85, y, 19, "#526258", 150) + 20;
    parts[index] = `<rect data-card="lane-${xml(lane.id)}" x="60" y="${top}" width="1680" height="${y - top}" rx="16" fill="#eef4ee" stroke="#c8d5ca"/>`;
    parts.push("</g>"); y += 24;
  }
  y = text("승인은 실행이 아닙니다. 외부 게시·발급·메일 발송과 실제 성과는 따로 확인합니다.", 60, y + 18, 20, "#865016", 150, 600) + 35;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1800 ${Math.ceil(y)}" width="1800" height="${Math.ceil(y)}" role="img" aria-labelledby="pipeline-title pipeline-desc"><title id="pipeline-title">${xml(doc.headline)}</title><desc id="pipeline-desc">${xml(doc.summary)} 모든 단계와 병렬 흐름은 화면과 같은 정의에서 생성합니다.</desc><defs><marker id="pipeline-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0 0L10 5L0 10Z" fill="#426c58"/></marker></defs><rect width="100%" height="100%" fill="#f8f7f3"/><g font-family="Malgun Gothic, Noto Sans KR, sans-serif">${parts.join("")}</g></svg>`;
}
