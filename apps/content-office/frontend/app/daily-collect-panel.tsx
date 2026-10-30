"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import { COLLECT_MAX_KRW, COLLECT_MINUTES, parseDailyCollectForm, runSummary, validCollectMaxKrw, validCollectMinutes, validTimeKst, type DailyCollectStatus } from "../lib/daily-collect";
import type { Action } from "../lib/types";
import { Icon } from "./icons";

/** 매일 아침 뉴스 자동 수집. 저장은 일정만 바꾸며, 실행은 서버 cron이 수집·한국어 요약만 합니다. */
export function DailyCollectPanel({ busy, action }: { busy: boolean; action: Action }) {
  const [status, setStatus] = useState<DailyCollectStatus | null>(null);
  const [loadError, setLoadError] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [time, setTime] = useState("07:00");
  const [minutes, setMinutes] = useState("15");
  const [maxKrw, setMaxKrw] = useState("100");

  const apply = useCallback((next: DailyCollectStatus) => {
    setStatus(next);
    setEnabled(next.settings.enabled);
    setTime(next.settings.time_kst);
    setMinutes(String(next.settings.minutes));
    setMaxKrw(String(next.settings.max_krw));
  }, []);

  const load = useCallback(async () => {
    try {
      apply(await api.dailyCollect());
      setLoadError("");
    } catch (cause) {
      setLoadError(cause instanceof Error ? cause.message : "자동 수집 설정을 불러오지 못했습니다.");
    }
  }, [apply]);

  useEffect(() => {
    void load();
  }, [load]);

  const parsed = parseDailyCollectForm({ enabled, time, minutes, maxKrw });
  const saved = status?.settings;
  const changed =
    parsed.ok && (!saved || saved.enabled !== parsed.patch.enabled || saved.time_kst !== parsed.patch.time_kst || saved.minutes !== parsed.patch.minutes || saved.max_krw !== parsed.patch.max_krw);

  async function save() {
    if (!parsed.ok) return;
    const patch = parsed.patch;
    let next: DailyCollectStatus | null = null;
    const ok = await action(
      "자동 수집 설정 저장",
      async () => {
        next = await api.updateDailyCollect(patch);
      },
      patch.enabled
        ? `매일 ${patch.time_kst}(한국 시간)에 ${patch.minutes}분 동안 뉴스만 수집·요약합니다. 1회 비용 상한 ${patch.max_krw}원.`
        : "매일 자동 수집을 껐습니다.",
    );
    if (ok === true && next) apply(next);
  }

  return (
    <section className="settings-card" aria-label="매일 자동 수집">
      <h2>매일 자동 수집</h2>
      <p className="settings-help">
        켜 두면 서버가 매일 정한 시각에 짧은 작업 시간을 스스로 열어 RSS 기사 수집과 한국어 카드 요약만 하고 닫습니다. 원고·제작·업로드와 ⓪①②③ 승인은 하지 않으며 작업자도 시작하지 않습니다. 그 시각에 운영자 작업 시간이 열려 있으면 그날은 건너뜁니다. 서버에 cron이 등록돼 있어야 실제로 돌아갑니다.
      </p>
      {loadError && <p className="field-error">{loadError}</p>}
      <label className="channel-toggle">
        <input type="checkbox" checked={enabled} disabled={busy} onChange={(e) => setEnabled(e.target.checked)} />
        {enabled ? "매일 자동 수집 켜짐" : "꺼짐"}
      </label>
      <div className="window-row">
        <label>
          시각(한국 시간)
          <input value={time} inputMode="numeric" placeholder="07:00" aria-invalid={validTimeKst(time) == null} disabled={busy} onChange={(e) => setTime(e.target.value)} />
        </label>
        <label>
          작업 시간(분, {COLLECT_MINUTES[0]}~{COLLECT_MINUTES[1]})
          <input value={minutes} inputMode="numeric" aria-invalid={validCollectMinutes(minutes) == null} disabled={busy} onChange={(e) => setMinutes(e.target.value)} />
        </label>
        <label>
          1회 비용 상한(원, {COLLECT_MAX_KRW[0]}~{COLLECT_MAX_KRW[1]})
          <input value={maxKrw} inputMode="numeric" aria-invalid={validCollectMaxKrw(maxKrw) == null} disabled={busy} onChange={(e) => setMaxKrw(e.target.value)} />
        </label>
        <button className="button primary" type="button" disabled={busy || !changed} onClick={() => void save()}>
          저장
        </button>
      </div>
      {!parsed.ok && parsed.errors.map((error) => <p className="field-error" key={error}>{error}</p>)}
      <p className="settings-help">
        <Icon name="clock" size={14} /> 마지막 실행: {runSummary(status?.last_run)}
        {saved?.updated_at && ` · 설정 변경 ${saved.updated_at.slice(0, 16).replace("T", " ")}`}
      </p>
    </section>
  );
}
