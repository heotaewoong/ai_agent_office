"use client";
import Link from "next/link";
import type { Dashboard } from "../lib/types";
import { officeHref } from "../lib/navigation";
import { statusInfo } from "../lib/workflow";
export function DecisionHome({ dashboard }: { dashboard: Dashboard }) {
  const source = dashboard.jobs.filter(job => job.state === "source_review");
  const release = dashboard.jobs.filter(job => ["release_review", "partial_release_review"].includes(job.state));
  const blocked = dashboard.jobs.filter(job => ["blocked", "source_rejected", "failed"].includes(job.state));
  return <div className="decision-home">
    <p className="notice">기획 선택⓪ → 원고① → 출력별 출고② → 회차③. 여기서는 검토 화면으로 이동해요. 승인이나 발송을 대신 실행하지 않아요.</p>
    <div className="decision-counts"><Link href="/plans"><span>⓪ 기획 선택</span><strong>후보 확인 →</strong></Link><Link href="/scripts"><span>① 원고 검토 대기</span><strong>{source.length}건</strong></Link><Link href="/publish"><span>② 출고 검토 대기</span><strong>{release.length}건</strong></Link><Link href="/runs"><span>③ 뉴스레터 초안</span><strong>{dashboard.newsletters?.draft ?? 0}건</strong><small>회차 내용과 동의를 확인하세요</small></Link></div>
    <section><h2>지금 살펴볼 작업</h2><p>원고·출고 검토 대기와 수정이 필요한 작업입니다. 승인 가능한지는 각 작업의 최신 판본과 검사 결과를 확인하세요.</p>
    {[...source, ...release, ...blocked].length ? <ul className="decision-list">{[...source, ...release, ...blocked].map(job => <li key={job.id}><Link href={officeHref(release.includes(job) ? "delivery" : "studio", job.id)}><span>{statusInfo(job.state).label}</span><strong>{job.title || job.id}</strong><span>검토하기 →</span></Link></li>)}</ul> : <p className="notice">검토를 기다리는 작업이 없어요. <Link href="/news">뉴스 고르기</Link> 또는 <Link href="/plans">직접 기획하기</Link>로 시작하세요.</p>}</section>
  </div>;
}
