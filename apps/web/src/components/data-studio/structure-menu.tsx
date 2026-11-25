"use client";

import { useEffect, useRef } from "react";

export interface MenuItem {
  label: string;
  run: () => void;
  /** Ação destrutiva (exclusão): aparece em destaque. A confirmação fica a cargo de quem chama. */
  danger?: boolean;
}

/**
 * Menu contextual da tabela (clique direito em número de linha ou cabeçalho de coluna).
 * Fecha com Escape ou com clique fora. Cada item executa uma operação versionada.
 */
export function StructureMenu({
  x,
  y,
  label,
  items,
  onClose,
}: {
  x: number;
  y: number;
  label: string;
  items: MenuItem[];
  onClose: () => void;
}) {
  const ref = useRef<HTMLUListElement>(null);

  useEffect(() => {
    const first = ref.current?.querySelector<HTMLButtonElement>("button");
    first?.focus();
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    function onPointer(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) onClose();
    }
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onPointer);
    };
  }, [onClose]);

  return (
    <ul
      ref={ref}
      role="menu"
      aria-label={label}
      style={{ position: "fixed", left: x, top: y, zIndex: 50 }}
      className="min-w-48 rounded border border-[var(--color-border)] bg-[var(--color-surface)] py-1 text-sm shadow-lg"
    >
      {items.map((item) => (
        <li key={item.label} role="none">
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              onClose();
              item.run();
            }}
            className={`w-full px-3 py-1.5 text-left hover:bg-[var(--color-border)] ${
              item.danger ? "text-[var(--color-danger)]" : ""
            }`}
          >
            {item.label}
          </button>
        </li>
      ))}
    </ul>
  );
}
