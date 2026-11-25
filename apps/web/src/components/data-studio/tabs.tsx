"use client";

import { useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

export interface TabItem {
  id: string;
  label: string;
  content: ReactNode;
}

/**
 * Abas acessíveis (WAI-ARIA): tablist/tab/tabpanel, setas, Home e End.
 * Todos os painéis ficam montados e só o ativo aparece: prévias e formulários não se perdem ao trocar de aba.
 */
export function Tabs({
  label,
  tabs,
  initial,
  size = "md",
}: {
  label: string;
  tabs: TabItem[];
  initial?: string;
  size?: "md" | "sm";
}) {
  const base = useId();
  const [active, setActive] = useState(initial ?? tabs[0]?.id ?? "");
  const buttons = useRef<Record<string, HTMLButtonElement | null>>({});

  function select(id: string) {
    setActive(id);
    buttons.current[id]?.focus();
  }

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next: number | null = null;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = tabs.length - 1;
    const target = next === null ? undefined : tabs[next];
    if (target) {
      event.preventDefault();
      select(target.id);
    }
  }

  const textSize = size === "sm" ? "text-xs" : "text-sm";

  return (
    <div className="space-y-3">
      <div
        role="tablist"
        aria-label={label}
        className="flex flex-wrap gap-1 border-b border-[var(--color-border)]"
      >
        {tabs.map((tab, index) => {
          const selected = tab.id === active;
          return (
            <button
              key={tab.id}
              ref={(el) => {
                buttons.current[tab.id] = el;
              }}
              type="button"
              role="tab"
              id={`${base}-tab-${tab.id}`}
              aria-selected={selected}
              aria-controls={`${base}-panel-${tab.id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => setActive(tab.id)}
              onKeyDown={(event) => onKeyDown(event, index)}
              className={`-mb-px rounded-t-md border border-b-0 px-3 py-2 ${textSize} ${
                selected
                  ? "border-[var(--color-border)] bg-[var(--color-surface)] font-medium"
                  : "border-transparent text-[var(--color-muted)] hover:text-[var(--color-foreground,inherit)]"
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      {tabs.map((tab) => (
        <div
          key={tab.id}
          role="tabpanel"
          id={`${base}-panel-${tab.id}`}
          aria-labelledby={`${base}-tab-${tab.id}`}
          hidden={tab.id !== active}
        >
          {tab.content}
        </div>
      ))}
    </div>
  );
}
