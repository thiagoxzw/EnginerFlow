"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { AppShell } from "@/components/app-shell";
import { ApiError, getDashboard } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

const MODULES = [
  {
    href: "/data-studio",
    title: "Data Studio",
    text: "Importe CSV e XLSX, cruze tabelas, compare chaves e exporte resultados. Nada é alterado sem prévia.",
  },
  {
    href: "/bom",
    title: "BOM Manager",
    text: "Estruturas de materiais com revisões imutáveis, explosão por veículo, kits e validação.",
  },
] as const;

export default function DashboardPage() {
  const router = useRouter();
  const query = useQuery({ queryKey: ["dashboard"], queryFn: getDashboard });

  useEffect(() => {
    if (query.error instanceof ApiError && query.error.status === 401) {
      router.replace("/login");
    }
  }, [query.error, router]);

  return (
    <AppShell>
      <div className="mx-auto max-w-6xl space-y-6 px-4 py-6 md:px-8 md:py-8">
        <header>
          <h1 className="text-2xl font-semibold tracking-tight">Visão geral</h1>
          <p className="mt-1 text-sm text-[var(--color-muted)]">Estado do sistema e atalhos para os módulos.</p>
        </header>

        {query.isPending ? (
          <p role="status" className="text-sm text-[var(--color-muted)]">
            Carregando…
          </p>
        ) : null}

        {query.isError && !(query.error instanceof ApiError && query.error.status === 401) ? (
          <div role="alert" className="card border-[var(--color-danger)] p-4">
            <p className="font-medium text-[var(--color-danger)]">Não foi possível carregar o painel.</p>
            <p className="mt-1 text-sm text-[var(--color-muted)]">
              {query.error instanceof Error ? query.error.message : "Erro desconhecido."}
            </p>
            <button
              type="button"
              onClick={() => query.refetch()}
              className="mt-3 rounded-md border border-[var(--color-border)] px-3 py-1.5 text-sm font-medium"
            >
              Tentar novamente
            </button>
          </div>
        ) : null}

        {query.data ? (
          <>
            <section aria-label="Indicadores" className="grid gap-4 sm:grid-cols-3">
              <Stat label="Versão" value={query.data.system.version} />
              <Stat
                label="Banco de dados"
                value={query.data.system.database === "up" ? "Operacional" : "Indisponível"}
                tone={query.data.system.database === "up" ? "success" : "danger"}
              />
              <Stat label="Atividades (7 dias)" value={String(query.data.activity_last_7_days)} />
            </section>

            <section aria-label="Módulos" className="grid gap-4 md:grid-cols-2">
              {MODULES.map((module) => (
                <Link
                  key={module.href}
                  href={module.href}
                  className="card group flex flex-col gap-2 p-5 transition-colors hover:border-[var(--color-accent)]"
                >
                  <span className="flex items-center justify-between">
                    <span className="font-semibold">{module.title}</span>
                    <span aria-hidden="true" className="text-[var(--color-muted)] transition-transform group-hover:translate-x-0.5">
                      →
                    </span>
                  </span>
                  <span className="text-sm text-[var(--color-muted)]">{module.text}</span>
                </Link>
              ))}
            </section>

            <section className="card overflow-hidden">
              <div className="flex items-center justify-between border-b border-[var(--color-border)] px-5 py-3">
                <h2 className="font-semibold">Histórico de atividades</h2>
                <span className="text-xs text-[var(--color-muted)]">Últimos registros</span>
              </div>
              {query.data.recent_activity.length === 0 ? (
                <p className="p-5 text-sm text-[var(--color-muted)]">Nenhuma atividade registrada.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-[var(--color-surface-2)] text-left text-xs uppercase tracking-wide text-[var(--color-muted)]">
                      <tr>
                        <th className="px-5 py-2.5 font-medium">Quando</th>
                        <th className="px-5 py-2.5 font-medium">Ação</th>
                        <th className="hidden px-5 py-2.5 font-medium lg:table-cell">Recurso</th>
                        <th className="px-5 py-2.5 font-medium">Resultado</th>
                      </tr>
                    </thead>
                    <tbody>
                      {query.data.recent_activity.map((entry, index) => (
                        <tr key={`${entry.occurred_at}-${index}`} className="border-t border-[var(--color-border)]">
                          <td className="whitespace-nowrap px-5 py-2.5 tabular-nums text-[var(--color-muted)]">
                            {formatDateTime(entry.occurred_at)}
                          </td>
                          <td className="px-5 py-2.5 font-mono text-xs">{entry.action}</td>
                          <td className="hidden max-w-[180px] truncate px-5 py-2.5 font-mono text-xs text-[var(--color-muted)] lg:table-cell">
                            {entry.resource}
                          </td>
                          <td className="px-5 py-2.5">
                            <Badge ok={entry.result === "ok"}>{entry.result}</Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <p className="text-xs text-[var(--color-muted)]">{query.data.note}</p>
          </>
        ) : null}
      </div>
    </AppShell>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: "success" | "danger" }) {
  const color =
    tone === "success" ? "text-[var(--color-success)]" : tone === "danger" ? "text-[var(--color-danger)]" : "";
  return (
    <div className="card p-5">
      <p className="text-sm text-[var(--color-muted)]">{label}</p>
      <p className={`mt-1 text-2xl font-semibold tabular-nums ${color}`}>{value}</p>
    </div>
  );
}

function Badge({ ok, children }: { ok: boolean; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
        ok ? "bg-[var(--color-success)]/10 text-[var(--color-success)]" : "bg-[var(--color-danger)]/10 text-[var(--color-danger)]"
      }`}
    >
      {children}
    </span>
  );
}
