"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Icon } from "./icons";
import { officeHref, type View } from "../lib/navigation";
import { statusInfo } from "../lib/workflow";

export type PaletteView = { id: View; title: string; icon: string; hint?: string };
export type PaletteJob = { id: string; title: string; state: string };

type Entry = { key: string; group: string; label: string; icon: string; meta?: string; href: string; external?: boolean };

/** 화면과 작업을 이름으로 바로 여는 빠른 이동 창. 아무것도 실행하지 않고 이동만 한다. */
export function CommandPalette({ views, jobs }: { views: PaletteView[]; jobs: PaletteJob[] }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const listId = useId();
  const titleId = useId();

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((value) => !value);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) {
      opener.current = document.activeElement as HTMLElement | null;
      setQuery("");
      setCursor(0);
      requestAnimationFrame(() => input.current?.focus());
    } else {
      opener.current?.focus?.();
    }
  }, [open]);

  const entries = useMemo<Entry[]>(() => {
    const pages: Entry[] = views.map((view) => ({
      key: `view-${view.id}`,
      group: "화면",
      label: view.title,
      icon: view.icon,
      meta: view.hint,
      href: officeHref(view.id),
    }));
    pages.push({ key: "detail-lab", group: "화면", label: "상세페이지 제작실", icon: "grid", meta: "새 탭", href: "/detail-lab/", external: true });
    const work: Entry[] = jobs.map((job) => ({
      key: `job-${job.id}`,
      group: "작업",
      label: job.title || "제목 없는 작업",
      icon: "studio",
      meta: statusInfo(job.state).label,
      href: officeHref("studio", job.id),
    }));
    return [...pages, ...work];
  }, [views, jobs]);

  const results = useMemo(() => {
    const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const found = words.length
      ? entries.filter((entry) => words.every((word) => `${entry.label} ${entry.meta ?? ""}`.toLowerCase().includes(word)))
      : entries.filter((entry) => entry.group === "화면").concat(entries.filter((entry) => entry.group === "작업").slice(0, 6));
    return found.slice(0, 40);
  }, [entries, query]);

  useEffect(() => { setCursor(0); }, [query]);

  function go(entry: Entry | undefined) {
    if (!entry) return;
    setOpen(false);
    if (entry.external) window.open(entry.href, "_blank", "noopener,noreferrer");
    else router.push(entry.href);
  }

  function onInputKey(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") { event.preventDefault(); setCursor((c) => Math.min(results.length - 1, c + 1)); }
    else if (event.key === "ArrowUp") { event.preventDefault(); setCursor((c) => Math.max(0, c - 1)); }
    else if (event.key === "Enter") { event.preventDefault(); go(results[cursor]); }
    else if (event.key === "Escape") { event.preventDefault(); setOpen(false); }
  }

  useEffect(() => {
    if (!open) return;
    document.getElementById(`${listId}-${cursor}`)?.scrollIntoView({ block: "nearest" });
  }, [cursor, open, listId]);

  let lastGroup = "";
  return (
    <>
      <button type="button" className="palette-trigger" onClick={() => setOpen(true)} aria-keyshortcuts="Control+K Meta+K" aria-label="화면이나 작업으로 이동 (Ctrl K)">
        <Icon name="search" size={16} />
        <span>화면·작업으로 이동</span>
        <kbd>Ctrl K</kbd>
      </button>
      {open && (
        <div className="palette-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setOpen(false); }}>
          <div className="palette" role="dialog" aria-modal="true" aria-labelledby={titleId}>
            <h2 id={titleId} className="visually-hidden">빠른 이동</h2>
            <div className="palette-input">
              <Icon name="search" size={18} />
              <input
                ref={input}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={onInputKey}
                placeholder="화면 이름이나 작업 제목을 입력하세요"
                role="combobox"
                aria-expanded="true"
                aria-controls={listId}
                aria-activedescendant={results[cursor] ? `${listId}-${cursor}` : undefined}
                aria-label="이동할 곳 검색"
                autoComplete="off"
                spellCheck={false}
              />
              <kbd>Esc</kbd>
            </div>
            {results.length === 0 ? (
              <p className="palette-empty">“{query}”와 맞는 화면이나 작업이 없어요. 다른 단어로 찾아보세요.</p>
            ) : (
              <ul className="palette-list" id={listId} role="listbox" aria-label="이동할 곳">
                {results.map((entry, index) => {
                  const heading = entry.group !== lastGroup ? entry.group : "";
                  lastGroup = entry.group;
                  return (
                    <li key={entry.key} role="presentation">
                      {heading && <div className="palette-group" aria-hidden="true">{heading}</div>}
                      <div
                        id={`${listId}-${index}`}
                        role="option"
                        aria-selected={index === cursor}
                        className="palette-option"
                        onMouseMove={() => setCursor(index)}
                        onClick={() => go(entry)}
                      >
                        <Icon name={entry.icon} size={18} />
                        <span>{entry.label}</span>
                        {entry.meta && <small>{entry.meta}</small>}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
            <div className="palette-foot" aria-hidden="true">
              <span><kbd>↑</kbd><kbd>↓</kbd> 고르기</span>
              <span><kbd>Enter</kbd> 열기</span>
              <span><kbd>Esc</kbd> 닫기</span>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

type ThemeChoice = "system" | "light" | "dark";
const themeLabels: Record<ThemeChoice, string> = { system: "시스템 설정", light: "밝은 화면", dark: "어두운 화면" };
const themeIcons: Record<ThemeChoice, string> = { system: "monitor", light: "sun", dark: "moon" };

/** 밝은 화면, 어두운 화면, 시스템 설정을 차례로 바꾼다. 선택은 이 브라우저에만 저장된다. */
export function ThemeSwitch() {
  const [choice, setChoice] = useState<ThemeChoice>("system");
  useEffect(() => {
    try {
      const saved = localStorage.getItem("office-theme");
      if (saved === "light" || saved === "dark") setChoice(saved);
    } catch { /* storage blocked: keep the system setting */ }
  }, []);
  function next() {
    const order: ThemeChoice[] = ["system", "light", "dark"];
    const value = order[(order.indexOf(choice) + 1) % order.length];
    setChoice(value);
    if (value === "system") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = value;
    try {
      if (value === "system") localStorage.removeItem("office-theme");
      else localStorage.setItem("office-theme", value);
    } catch { /* storage blocked: the choice still applies to this tab */ }
  }
  return (
    <button type="button" className="theme-switch" onClick={next} aria-label={`화면 밝기: ${themeLabels[choice]}. 눌러서 바꾸기`}>
      <Icon name={themeIcons[choice]} size={16} />
      <span>{themeLabels[choice]}</span>
      <small>바꾸기</small>
    </button>
  );
}
