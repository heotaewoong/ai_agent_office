"use client";

import { useState } from "react";
import { api } from "../lib/api";
import type { Dashboard } from "../lib/types";
import { PROFILE_COST_GUIDANCE, PROFILE_OPTIONS, keyChips, settingsWarnings, validWindowMinutes, type ProfileKind } from "../lib/settings";
import { Icon } from "./icons";
import { ChannelsPanel } from "./channels-panel";
import { DailyCollectPanel } from "./daily-collect-panel";
import { LeadsPanel } from "./leads-panel";

type Action = (label: string, execute: () => Promise<unknown>, success: string) => Promise<true | string>;

const GROUPS: { kind: ProfileKind; title: string; description: string }[] = [
  { kind: "text", title: "글 모델", description: "원고 생성·비평·평가·국어 검수·퀴즈·카드뉴스 문구를 쓰는 모델. 실패해도 다른 제공자로 자동 전환하지 않습니다" },
  { kind: "voice", title: "음성", description: "영상 내레이션을 만드는 방식" },
  { kind: "image", title: "배경 이미지", description: "영상·카드 장면의 배경. 한국어 글자는 항상 로컬에서 얹습니다" },
  { kind: "clip", title: "생성 영상", description: "원고에서 clip: generated로 지정한 장면만 짧은 생성 영상으로" },
];

function money(value: number | undefined) {
  return new Intl.NumberFormat("ko-KR").format(Math.round(value ?? 0));
}

export function SettingsPanel({
  dashboard,
  windowLabel,
  busy,
  action,
}: {
  dashboard: Dashboard;
  windowLabel: string;
  busy: boolean;
  action: Action;
}) {
  const provider = dashboard.provider;
  const [minutes, setMinutes] = useState("120");
  const [servicesNote, setServicesNote] = useState("");
  const warnings = settingsWarnings(provider);
  const current: Record<ProfileKind, string | undefined> = {
    text: provider?.text?.id ?? provider?.model,
    voice: provider?.voice?.id,
    image: provider?.image?.id,
    clip: provider?.clip?.id,
  };
  const parsedMinutes = validWindowMinutes(minutes);
  const budget = dashboard.budget;
  const selectedProfiles = GROUPS.map(group => ({title: group.title, option: PROFILE_OPTIONS[group.kind].find(option => option.id === current[group.kind])}));

  async function choose(kind: ProfileKind, id: string) {
    const option = PROFILE_OPTIONS[kind].find((o) => o.id === id);
    if (!option || option.disabled) return;
    await action("제작 설정 변경", () => api.setProfile(kind, id), `${option?.label ?? id}(으)로 바꿨습니다. 새 제작 요청부터 적용됩니다.`);
  }

  async function openWindow() {
    if (parsedMinutes == null) return;
    let note = "";
    const ok = await action(
      "작업 시간 열기",
      async () => {
        const result = await api.startWindow(parsedMinutes);
        const started = result.services.started.length ? `작업자 시작: ${result.services.started.join(", ")}` : "";
        const running = result.services.running.length ? `이미 실행 중: ${result.services.running.join(", ")}` : "";
        note = [started, running, result.services.note].filter(Boolean).join(" · ");
      },
      `${parsedMinutes}분 작업 시간을 열었습니다. 기존 총예산 한도는 그대로입니다.`,
    );
    if (ok === true) setServicesNote(note);
  }

  return (
    <div className="settings-layout">
      <section className="settings-card" aria-label="키 연결 상태">
        <h2>연결·로그인 상태</h2>
        <p className="settings-help">키는 EC2의 환경 파일에만 있고 화면에는 연결 여부만 보입니다. 선택한 제공자와 기능에 필요한 키를 확인하세요. 키를 바꾸면 앱을 다시 시작해야 합니다.</p>
        <ul className="key-chips">
          {keyChips(provider).map((chip) => (
            <li key={chip.label} className={chip.ok ? "ok" : "missing"}>
              <Icon name={chip.ok ? "check" : "alert"} size={15} />
              <strong>{chip.label}</strong>
              <small>{chip.ok ? "연결됨" : `${chip.env} 없음`}</small>
            </li>
          ))}
        </ul>
        {warnings.length > 0 && (
          <ul className="settings-warnings" role="status">
            {warnings.map((warning) => (
              <li key={warning}>
                <Icon name="alert" size={14} />
                {warning}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="settings-card" aria-label="제작 프로필">
        <h2>어떤 방식으로 콘텐츠를 만들까요?</h2>
        <p className="settings-help">글·배경은 Codex 구독을 선택할 수 있습니다. 음성은 별도 합성 기능이며, 사진에 줌·자막을 붙이는 일반 영상은 생성 영상 모델 없이도 만듭니다. 선택 → 연결 상태 확인 → 원고 검토 → 제작 순서로 진행하세요.</p>
        {PROFILE_COST_GUIDANCE.map((note) => <p className="settings-help" key={note}>{note}</p>)}
        <div className="profile-summary" role="status" aria-label="선택한 제작 방식">
          {selectedProfiles.map(({title, option}) => <p key={title}><strong>{title}</strong> · {option?.label ?? "상태 확인 중"} · {option ? option.subscription ? "구독 한도 사용" : option.paid ? "별도 API 과금" : "추가 API 과금 없음" : "미확인"}</p>)}
          <p>선택을 바꾸면 새 요청부터 적용됩니다. 기존 제작물과 승인 기록은 바꾸지 않습니다. 이 PC의 로그인과 EC2 작업자의 로그인은 별개입니다.</p>
        </div>
        <div className="profile-groups">
          {GROUPS.map((group) => (
            <fieldset key={group.kind} className="profile-group" disabled={busy}>
              <legend>
                {group.title}
                <small>{group.description}</small>
              </legend>
              {PROFILE_OPTIONS[group.kind].map((option) => (
                <label key={option.id} className={`profile-option ${current[group.kind] === option.id ? "selected" : ""}`}>
                  <input
                    type="radio"
                    name={`profile-${group.kind}`}
                    value={option.id}
                    disabled={Boolean(option.disabled)}
                    checked={current[group.kind] === option.id}
                    onChange={() => void choose(group.kind, option.id)}
                  />
                  <span>
                    <strong>
                      {option.label}
                      {option.disabled ? <em className="paid-tag">미지원</em> : option.subscription ? <em className="free-tag">구독 한도</em> : option.paid ? <em className="paid-tag">API 과금</em> : <em className="free-tag">추가 과금 없음</em>}
                    </strong>
                    <small>{option.hint}</small>
                  </span>
                </label>
              ))}
            </fieldset>
          ))}
        </div>
      </section>

      <section className="settings-card" aria-label="작업 시간과 예산">
        <h2>작업 시간 · 예산</h2>
        <p className="settings-help">기사 수집·원고 작성·제작·업로드 요청은 작업 시간이 열려 있을 때만 실행됩니다. 여는 것은 운영자의 결정이며, 시간이 끝나면 작업자는 스스로 멈춥니다.</p>
        <div className="window-row">
          <span className="window-now">
            <Icon name="clock" size={16} />
            {windowLabel}
          </span>
          <label>
            열 시간(분)
            <input inputMode="numeric" value={minutes} onChange={(e) => setMinutes(e.target.value)} aria-invalid={parsedMinutes == null} />
          </label>
          <button className="button primary" disabled={busy || parsedMinutes == null} onClick={() => void openWindow()}>
            작업 시간 열기
          </button>
        </div>
        {parsedMinutes == null && <p className="field-error">1~360분 사이의 정수로 입력하세요.</p>}
        {servicesNote && <p className="settings-help">{servicesNote}</p>}
        <dl className="budget-grid">
          <div><dt>총 한도</dt><dd>{money(budget?.cap_krw)}원</dd></div>
          <div><dt>사용</dt><dd>{money(budget?.spent_krw)}원</dd></div>
          <div><dt>예약·불명</dt><dd>{money(budget?.reserved_krw)}원</dd></div>
          <div><dt>남음</dt><dd>{money(budget?.remaining_krw)}원</dd></div>
        </dl>
        {budget?.fx_note && <p className="settings-help">{budget.fx_note}</p>}
      </section>

      <DailyCollectPanel busy={busy} action={action} />
      <ChannelsPanel busy={busy} action={action} />
      <LeadsPanel busy={busy} action={action} />
    </div>
  );
}
