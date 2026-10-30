"use client";

import { useEffect, useRef, useState } from "react";

type Entry = { id: string; title: string };

/** Navigation follows the rendered panels, including asynchronously loaded ones. */
export function PageOutline({ scope }: { scope: string }) {
  const nav = useRef<HTMLElement>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [active, setActive] = useState("");

  useEffect(() => {
    const root = nav.current?.closest("main");
    if (!root) return;
    let nodes: HTMLElement[] = [];
    let frame = 0;
    let sequence = 0;
    const assigned = new Map<HTMLElement, string>();
    const panels = new Set<HTMLElement>();
    const updatePosition = () => {
      frame = 0;
      const edge = (nav.current?.getBoundingClientRect().bottom ?? 0) + 48;
      const atBottom = window.scrollY > 0 && window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 2;
      const current = atBottom ? nodes.at(-1) : nodes.filter((node) => node.getBoundingClientRect().top <= edge).at(-1) ?? nodes[0];
      setActive(current?.id ?? "");
    };
    const schedulePosition = () => {
      if (!frame) frame = requestAnimationFrame(updatePosition);
    };
    const collect = () => {
      nodes = Array.from(root.querySelectorAll<HTMLElement>("h2, h3")).filter((node) =>
        !node.closest(".page-outline, .job-sidebar, .job-heading, [hidden], details:not([open]), [role=dialog]") &&
        node.getClientRects().length > 0 && Boolean(node.textContent?.trim()),
      );
      const next = nodes.map((node) => {
        if (!node.id) {
          const id = `office-section-${encodeURIComponent(scope)}-${++sequence}`;
          node.id = id;
          assigned.set(node, id);
        }
        node.classList.add("outline-target");
        const panel = node.closest<HTMLElement>("section:not(.job-content), .approval-panel, .editor-panel, .evidence-panel");
        if (panel && !panel.classList.contains("outline-panel")) {
          panel.classList.add("outline-panel");
          panels.add(panel);
        }
        return { id: node.id, title: node.textContent!.trim().replace(/\s+/g, " ") };
      });
      setEntries((previous) => JSON.stringify(previous) === JSON.stringify(next) ? previous : next);
      schedulePosition();
    };
    collect();
    const observer = new MutationObserver((records) => {
      if (records.some((record) => !nav.current?.contains(record.target))) collect();
    });
    observer.observe(root, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ["hidden", "open"] });
    window.addEventListener("scroll", schedulePosition, { passive: true });
    window.addEventListener("resize", collect);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", schedulePosition);
      window.removeEventListener("resize", collect);
      for (const [node, id] of assigned) { if (node.id === id) node.removeAttribute("id"); }
      for (const node of nodes) node.classList.remove("outline-target");
      for (const panel of panels) panel.classList.remove("outline-panel");
    };
  }, [scope]);

  function moveTo(id: string) {
    const target = document.getElementById(id);
    if (!target) return;
    target.setAttribute("tabindex", "-1");
    target.focus({ preventScroll: true });
    target.scrollIntoView({ block: "start", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
    history.replaceState(history.state, "", `#${id}`);
    setActive(id);
  }

  const current = entries.find((entry) => entry.id === active);
  return (
    <nav ref={nav} className="page-outline" aria-label="이 페이지 목차" hidden={entries.length < 2}>
      <div className="outline-topline">
        <strong>이 페이지 목차 <span>{entries.length}</span></strong>
        <a href="#main-content" className="outline-top">맨 위로 ↑</a>
      </div>
      <label className="outline-select">바로 이동
        <select aria-label="목차 바로 이동" value={active} onChange={(event) => moveTo(event.target.value)}>
          {!active && <option value="">구역 선택</option>}
          {entries.map((entry, index) => <option key={entry.id} value={entry.id}>{index + 1}. {entry.title}</option>)}
        </select>
      </label>
      <ol className="outline-links">
        {entries.map((entry, index) => <li key={entry.id}><a href={`#${entry.id}`} aria-current={active === entry.id ? "location" : undefined}
          onClick={(event) => { event.preventDefault(); moveTo(entry.id); }}><span>{String(index + 1).padStart(2, "0")}</span>{entry.title}</a></li>)}
      </ol>
      <p className="outline-location">현재 위치 · {current?.title ?? "구역을 선택하세요"}</p>
    </nav>
  );
}
