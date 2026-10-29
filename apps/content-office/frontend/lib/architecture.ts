export type FlowStep =
  | { kind: "stage"; num: string; title: string; items: string[]; who: string }
  | { kind: "gate"; mark: string; label: string }
  | { kind: "step" };
export type UnitCost = { task: string; role: string; unit: string; where: string };
export type UsageRow = { role: string; model: string; calls: number; krw: number; per_call: number };
export type TestCounts = { passed: number; failed: number; skipped?: number; errors?: number };
export type ArchitectureOverview = {
  doc: {
    headline: string;
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
