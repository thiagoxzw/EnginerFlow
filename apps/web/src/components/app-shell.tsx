"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";

import { logout } from "@/lib/api";

const NAV = [
  { href: "/", label: "Início", icon: "M3 12l9-8 9 8M5 10v10h5v-6h4v6h5V10" },
  { href: "/data-studio", label: "Data Studio", icon: "M4 5h16v14H4zM4 10h16M10 5v14" },
  { href: "/bom", label: "BOM Manager", icon: "M6 4v16M6 8h6M6 16h6M12 8v8M12 8h6" },
] as const;

/** Estrutura comum às telas autenticadas: navegação entre módulos e área de conteúdo. */
export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();

  async function onLogout() {
    try {
      await logout();
    } finally {
      router.replace("/login");
    }
  }

  return (
    <div className="min-h-screen md:flex">
      <aside className="border-b border-[var(--color-border)] bg-[var(--color-surface)] md:sticky md:top-0 md:flex md:h-screen md:w-60 md:shrink-0 md:flex-col md:border-b-0 md:border-r">
        <div className="flex items-center gap-2 px-4 py-3 md:px-5 md:py-5">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-[var(--color-accent)] text-sm font-bold text-white" aria-hidden="true">
            E
          </span>
          <span className="font-semibold tracking-tight">EngiFlow</span>
        </div>

        <nav aria-label="Módulos" className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-1 md:flex-col md:overflow-visible md:pb-0">
          {NAV.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`flex shrink-0 items-center gap-3 rounded-md px-3 py-2 text-sm font-medium ${
                  active
                    ? "bg-[var(--color-accent-soft)] text-[var(--color-accent)]"
                    : "text-[var(--color-muted)] hover:text-[var(--color-fg)]"
                }`}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d={item.icon} />
                </svg>
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="hidden border-t border-[var(--color-border)] px-3 py-3 md:block">
          <button
            type="button"
            onClick={() => void onLogout()}
            className="w-full rounded-md px-3 py-2 text-left text-sm text-[var(--color-muted)] hover:text-[var(--color-fg)]"
          >
            Sair
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-end border-b border-[var(--color-border)] px-4 py-2 md:hidden">
          <button type="button" onClick={() => void onLogout()} className="text-sm text-[var(--color-muted)]">
            Sair
          </button>
        </div>
        <main className="min-w-0 flex-1">{children}</main>
      </div>
    </div>
  );
}
