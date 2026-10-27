"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import type { Lesson, SnapshotChannel, SnapshotPeriod } from "../lib/types";

const CHANNELS: { value: SnapshotChannel; label: string }[] = [
  { value: "youtube_long", label: "유튜브 롱폼" },
  { value: "shorts", label: "쇼츠" },
  { value: "blog_tistory", label: "티스토리" },
  { value: "blog_naver", label: "네이버" },
  { value: "newsletter", label: "뉴스레터" },
];
const PERIODS: SnapshotPeriod[] = ["24h", "7d", "28d"];
const STATE_LABEL: Record<Lesson["state"], string> = { proposed: "검토 대기", approved: "승인됨", rejected: "반려됨" };

function message(error: unknown) {
  return error instanceof Error ? error.message : "요청을 처리하지 못했습니다";
}

export function PerformancePanel() {
  const [channel, setChannel] = useState<SnapshotChannel>("youtube_long");
  const [period, setPeriod] = useState<SnapshotPeriod>("7d");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lessons, setLessons] = useState<Lesson[]>([]);
  const [reviewingId, setReviewingId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setLessons((await api.lessons()).lessons);
    } catch (e) {
      setError(message(e));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function upload(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const csv = await file.text();
      const saved = await api.uploadStudioCsv({ channel, period, csv });
      setResult(`스냅샷 ${saved.snapshots.length}건 저장 · 교훈 후보 ${saved.lessons.length}건`);
      await refresh();
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }

  async function review(id: string, decision: "approved" | "rejected") {
    setReviewingId(id);
    setError(null);
    try {
      await api.reviewLesson(id, decision);
      await refresh();
    } catch (e) {
      setError(message(e));
    } finally {
      setReviewingId(null);
    }
  }

  return (
    <section className="feed-panel v6-performance">
      <div className="section-heading">
        <div>
          <p className="eyebrow">성과 기록</p>
          <h2>성과 스냅샷 올리기</h2>
        </div>
        <span className="section-meta">Studio '콘텐츠' 표 CSV</span>
      </div>
      <div className="v6-performance-form">
        <label>
          채널
          <select value={channel} onChange={(e) => setChannel(e.target.value as SnapshotChannel)} disabled={busy}>
            {CHANNELS.map((c) => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>
        </label>
        <label>
          기간
          <select value={period} onChange={(e) => setPeriod(e.target.value as SnapshotPeriod)} disabled={busy}>
            {PERIODS.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </label>
        <label>
          CSV 파일
          <input
            type="file"
            accept=".csv,text/csv"
            disabled={busy}
            onChange={(e) => {
              const input = e.currentTarget;
              void upload(input.files?.[0]).finally(() => {
                input.value = "";
              });
            }}
          />
        </label>
      </div>
      {busy ? <p className="muted">올리는 중입니다</p> : null}
      {result ? <p className="muted">{result}</p> : null}
      {error ? <div className="notice error" role="alert">{error}</div> : null}

      <div className="section-heading">
        <div>
          <p className="eyebrow">교훈</p>
          <h2>교훈 후보</h2>
        </div>
        <span className="section-meta">{lessons.length}건</span>
      </div>
      {lessons.length === 0 ? (
        <p className="muted">아직 교훈 후보가 없습니다. 성과 CSV를 올리면 기준선과 비교해 후보가 만들어집니다.</p>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr><th>종류</th><th>가설</th><th>가중치</th><th>상태</th><th>검토</th></tr>
            </thead>
            <tbody>
              {lessons.map((lesson) => (
                <tr key={lesson.id}>
                  <td>{lesson.kind}</td>
                  <td>{lesson.hypothesis}</td>
                  <td>
                    {lesson.weight_change
                      ? `가중치 ${lesson.weight_change.factor} ${lesson.weight_change.delta > 0 ? "+" : ""}${lesson.weight_change.delta}`
                      : "-"}
                  </td>
                  <td><span className="badge">{STATE_LABEL[lesson.state]}</span></td>
                  <td>
                    {lesson.state === "proposed" ? (
                      <>
                        <button type="button" className="button primary" disabled={reviewingId === lesson.id} onClick={() => void review(lesson.id, "approved")}>승인</button>{" "}
                        <button type="button" className="button secondary" disabled={reviewingId === lesson.id} onClick={() => void review(lesson.id, "rejected")}>반려</button>
                      </>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
