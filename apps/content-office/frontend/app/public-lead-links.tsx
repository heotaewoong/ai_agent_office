"use client";

import { useEffect, useId, useState } from "react";
import { api } from "../lib/api";
import { leadSourceLabel } from "../lib/leads";
import { publicLeadEmbed, publicLeadLink } from "../lib/public-lead";
import type { PublicLeadFormInfo } from "../lib/public-lead";

/** 공개 신청 링크: 독자가 직접 신청하는 /lead 주소와 홈페이지에 붙일 링크 버튼 HTML. */
export function PublicLeadLinks() {
  const uid = useId();
  const [info, setInfo] = useState<PublicLeadFormInfo | null>(null);
  const [error, setError] = useState("");
  const [source, setSource] = useState("homepage");
  const [copied, setCopied] = useState("");
  const [origin, setOrigin] = useState("");

  useEffect(() => {
    setOrigin(window.location.origin);
    api
      .publicLeadForm()
      .then(setInfo)
      .catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "공개 신청 링크 정보를 불러오지 못했습니다."));
  }, []);

  async function copy(id: string, text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(id);
    } catch {
      setCopied("");
      setError("클립보드에 복사하지 못했습니다. 글자를 직접 선택해 복사하세요.");
    }
  }

  const base = info?.public_origin || origin;
  return (
    <div className="settings-card public-lead-links" aria-label="공개 신청 링크">
      <h3>공개 신청 링크</h3>
      <p className="settings-help">
        독자가 이 링크에서 이메일과 동의를 직접 남기면 아래 장부에 출처와 함께 기록됩니다. 자료는 자동으로 보내지지 않습니다. 장부를 보고 직접 보낸 뒤 &quot;전달 완료&quot;로 표시하세요. 동의 문구는 서버 카탈로그(<code>config/lead_magnets.json</code>)의 초안이며 오너 확인이 필요합니다.
      </p>
      {info && !info.public_origin && (
        <p className="notice error">OFFICE_PUBLIC_ORIGIN이 설정되지 않아 지금 화면 주소로 링크를 만들었습니다. 외부 독자가 열 수 있는 주소인지 확인하세요.</p>
      )}
      {error && <p className="field-error">{error}</p>}
      {info && (
        <>
          <label htmlFor={`${uid}-source`}>링크를 붙일 곳(출처)</label>
          <select id={`${uid}-source`} value={source} onChange={(e) => { setSource(e.target.value); setCopied(""); }}>
            {info.sources.map((s) => (
              <option key={s} value={s}>
                {leadSourceLabel(s)}
              </option>
            ))}
          </select>
          {info.magnets.length === 0 && <p className="muted">공개로 표시한 자료가 없습니다.</p>}
          {base &&
            info.magnets.map((magnet) => {
              const link = publicLeadLink(base, magnet.key, source);
              const embed = publicLeadEmbed(link, magnet.title);
              return (
                <div key={magnet.key} className="public-lead-link" style={{ display: "grid", gap: 6, marginTop: 12 }}>
                  <p>
                    <strong>{magnet.title}</strong> <span className="muted">({magnet.key} · 동의 문구 {magnet.consent_version})</span>
                  </p>
                  <p>
                    <code style={{ wordBreak: "break-all" }}>{link}</code>{" "}
                    <button className="button secondary small" type="button" onClick={() => void copy(`${magnet.key}-link`, link)}>
                      {copied === `${magnet.key}-link` ? "복사했어요" : "링크 복사"}
                    </button>
                  </p>
                  <label htmlFor={`${uid}-${magnet.key}-embed`}>heobrain.kr에 붙일 링크 버튼 HTML (iframe 없음)</label>
                  <textarea id={`${uid}-${magnet.key}-embed`} readOnly rows={3} value={embed} style={{ width: "100%", fontFamily: "monospace", fontSize: 12 }} />
                  <button className="button secondary small" type="button" onClick={() => void copy(`${magnet.key}-embed`, embed)}>
                    {copied === `${magnet.key}-embed` ? "복사했어요" : "HTML 복사"}
                  </button>
                </div>
              );
            })}
        </>
      )}
    </div>
  );
}
