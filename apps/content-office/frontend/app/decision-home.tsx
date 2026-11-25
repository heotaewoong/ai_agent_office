"use client";
import Link from "next/link";
import type { Dashboard } from "../lib/types";
import { officeHref } from "../lib/navigation";
import { statusInfo } from "../lib/workflow";
import { Icon } from "./icons";

export function DecisionHome({ dashboard }: { dashboard: Dashboard }) {
  const source = dashboard.jobs.filter(job => job.state === "source_review");
  const release = dashboard.jobs.filter(job => ["release_review", "partial_release_review"].includes(job.state));
  const blocked = dashboard.jobs.filter(job => ["blocked", "source_rejected", "failed"].includes(job.state));
  const drafts = dashboard.newsletters?.draft ?? 0;
  const steps = [
    { href: "/plans", step: "⓪", title: "기획 선택", count: null as number | null, hint: "근거가 갖춰진 기획을 골라요" },
    { href: "/scripts", step: "①", title: "원고 검토", count: source.length, hint: "원고를 읽고 승인해요" },
    { href: "/publish", step: "②", title: "출고 검토", count: release.length, hint: "완성본을 확인하고 내보내요" },
    { href: "/runs", step: "③", title: "뉴스레터 초안", count: drafts, hint: "회차 내용과 동의를 확인해요" },
  ];
  const focus = steps.findIndex(item => (item.count ?? 0) > 0);
  const queue = [...source, ...release, ...blocked];
  return <div className="decision-home">
    <ol className="decision-steps" aria-label="콘텐츠가 나가는 순서">
      {steps.map((item, index) => <li key={item.href} className={index === focus ? "is-focus" : ""}>
        <Link href={item.href}>
          <span className="decision-step-top"><span className="decision-step-no" aria-hidden="true">{item.step}</span>{item.title}</span>
          <strong>{item.count === null ? "후보 보기" : `${item.count}건`}</strong>
          <small>{index === focus ? "지금 먼저 볼 곳이에요" : item.hint}</small>
        </Link>
      </li>)}
    </ol>
    <p className="decision-note">여기서는 검토 화면으로 이동만 해요. 승인이나 발송은 각 화면에서 직접 눌러야 실행돼요.</p>
    <section className="decision-queue" aria-labelledby="decision-queue-heading">
      <div className="section-heading"><div className="section-title"><h2 id="decision-queue-heading">지금 살펴볼 작업</h2><span className="count-pill">{queue.length}</span></div></div>
      {queue.length ? <ul className="decision-list">{queue.map(job => {
        const info = statusInfo(job.state);
        const tone = blocked.includes(job) ? "red" : release.includes(job) ? "orange" : "blue";
        return <li key={job.id}><Link href={officeHref(release.includes(job) ? "delivery" : "studio", job.id)}>
          <span className={`badge ${tone}`}>{info.label}</span>
          <strong>{job.title || job.id}</strong>
          <span className="decision-open">열기<Icon name="chevron" size={16} /></span>
        </Link></li>;
      })}</ul> : <p className="decision-empty">검토를 기다리는 작업이 없어요. <Link href="/news">오늘의 뉴스</Link>에서 고르거나 <Link href="/plans">직접 기획</Link>해서 시작하세요.</p>}
    </section>
  </div>;
}
