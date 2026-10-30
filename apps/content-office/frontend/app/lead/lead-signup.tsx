"use client";

import { useEffect, useId, useState } from "react";
import type { FormEvent } from "react";
import { validEmail } from "../../lib/leads";
import { fetchPublicMagnets, PUBLIC_LEAD_DONE, publicLeadLink, publicLeadPayload, submitPublicLead } from "../../lib/public-lead";
import type { PublicLeadSource, PublicMagnet } from "../../lib/public-lead";
import styles from "./lead.module.css";

type Load = { state: "loading" } | { state: "error"; message: string } | { state: "ready"; magnets: PublicMagnet[] };

export function LeadSignup({ magnetKey, source }: { magnetKey: string; source: PublicLeadSource }) {
  const uid = useId();
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [email, setEmail] = useState("");
  const [consent, setConsent] = useState(false);
  const [hp, setHp] = useState("");
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    let alive = true;
    fetchPublicMagnets()
      .then((magnets) => alive && setLoad({ state: "ready", magnets }))
      .catch((cause: unknown) => alive && setLoad({ state: "error", message: cause instanceof Error ? cause.message : "자료 정보를 불러오지 못했어요." }));
    return () => {
      alive = false;
    };
  }, []);

  const magnet = load.state === "ready" ? load.magnets.find((m) => m.key === magnetKey) : undefined;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!magnet || sending) return;
    const parsed = publicLeadPayload({ email, consent, hp }, magnet, source);
    if ("error" in parsed) {
      setError(parsed.error);
      return;
    }
    setError("");
    setSending(true);
    const result = await submitPublicLead(parsed.payload);
    setSending(false);
    if (result.ok) setDone(true);
    else setError(result.message);
  }

  return (
    <main className={styles.page}>
      <div className={styles.card}>
        <p className={styles.brand}>HeoBrain 무료 자료</p>
        {load.state === "loading" && <p className={styles.muted}>자료 정보를 불러오는 중이에요…</p>}
        {load.state === "error" && (
          <p className={styles.error} role="alert">
            {load.message}
          </p>
        )}
        {load.state === "ready" && !magnet && (
          <>
            <h1 className={styles.title}>신청할 자료를 골라 주세요</h1>
            {load.magnets.length === 0 ? (
              <p className={styles.muted}>지금은 신청할 수 있는 자료가 없어요.</p>
            ) : (
              <ul className={styles.choices}>
                {load.magnets.map((m) => (
                  <li key={m.key}>
                    <a href={publicLeadLink("", m.key, source)}>{m.title}</a>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
        {magnet && !done && (
          <>
            <h1 className={styles.title}>{magnet.title}</h1>
            <p className={styles.description}>{magnet.description}</p>
            <form className={styles.form} onSubmit={(e) => void submit(e)} noValidate>
              <label className={styles.label} htmlFor={`${uid}-email`}>
                자료를 받을 이메일
              </label>
              <input
                id={`${uid}-email`}
                className={styles.input}
                type="email"
                inputMode="email"
                autoComplete="email"
                maxLength={254}
                required
                value={email}
                aria-invalid={email.trim() !== "" && !validEmail(email)}
                placeholder="reader@example.com"
                onChange={(e) => {
                  setEmail(e.target.value);
                  setError("");
                }}
              />
              <div className={styles.consentBox}>
                <p className={styles.consentText}>{magnet.consent_text}</p>
                <p className={styles.version}>동의 문구 버전 {magnet.consent_version}</p>
              </div>
              <label className={styles.check} htmlFor={`${uid}-consent`}>
                <input
                  id={`${uid}-consent`}
                  type="checkbox"
                  checked={consent}
                  onChange={(e) => {
                    setConsent(e.target.checked);
                    setError("");
                  }}
                />
                <span>위 개인정보 수집·이용에 동의합니다. (필수)</span>
              </label>
              {/* 사람에게는 보이지 않는 함정 칸입니다. 자동 입력 프로그램만 채웁니다. */}
              <div className={styles.trap} aria-hidden="true">
                <label htmlFor={`${uid}-website`}>이 칸은 비워 두세요</label>
                <input id={`${uid}-website`} name="website" type="text" tabIndex={-1} autoComplete="off" value={hp} onChange={(e) => setHp(e.target.value)} />
              </div>
              {error && (
                <p className={styles.error} role="alert">
                  {error}
                </p>
              )}
              <button className={styles.submit} type="submit" disabled={sending}>
                {sending ? "보내는 중…" : "무료로 신청하기"}
              </button>
            </form>
            <p className={styles.note}>자료는 자동으로 발송되지 않아요. 운영자가 신청을 확인한 뒤 이메일로 직접 보내 드려요.</p>
          </>
        )}
        {magnet && done && (
          <div role="status">
            <h1 className={styles.title}>{PUBLIC_LEAD_DONE}</h1>
            <p className={styles.description}>신청한 자료: {magnet.title}</p>
          </div>
        )}
        {magnet && (
          <p className={styles.note}>
            동의를 철회하거나 문의하려면 자료를 받은 메일에 회신해 주세요. 운영자가 확인한 뒤 철회로 기록하고, 이후에는 안내를 보내지 않아요.
          </p>
        )}
      </div>
    </main>
  );
}
