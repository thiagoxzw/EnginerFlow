"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { ApiError, getDashboard, logout } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

export default function DashboardPage() {
  const router = useRouter();
  const query = useQuery({ queryKey: ["dashboard"], queryFn: getDashboard });

  useEffect(() => {
    if (query.error instanceof ApiError && query.error.status === 401) {
      router.replace("/login");
    }
  }, [query.error, router]);

  const onLogout = async () => {
    try {
      await logout();
    } finally {
      router.replace("/login");
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-4 md:p-8">
      <header className="flex items-center justify-between">
        <div>
          <p className="text-sm text-[var(--color-muted)]">EngiFlow</p>
          <h1 className="text-2xl font-semibold">Dashboard</h1>
        </div>
        <button
          type="button"
          onClick={onLogout}
          className="rounded-md border border-[var(--color-border)] px-3 py-2 text-sm"
        >
          Sair
        </button>
      </header>

      {query.isPending ? (
        <p role="status" className="text-[var(--color-muted)]">
          Carregando…
        </p>
      ) : null}

      {query.isError && !(query.error instanceof ApiError && query.error.status === 401) ? (
        <div role="alert" className="rounded-md border border-[var(--color-danger)] p-4">
          <p className="font-medium text-[var(--color-danger)]">Não foi possível carregar o dashboard.</p>
          <p className="text-sm text-[var(--color-muted)]">
            {query.error instanceof Error ? query.error.message : "Erro desconhecido."}
          </p>
          <button
            type="button"
            onClick={() => query.refetch()}
            className="mt-3 rounded-md border border-[var(--color-border)] px-3 py-1 text-sm"
          >
            Tentar novamente
          </button>
        </div>
      ) : null}

      {query.data ? (
        <>
          <section className="grid gap-4 sm:grid-cols-3" aria-label="Indicadores">
            <Stat label="Versão" value={query.data.system.version} />
            <Stat label="Banco de dados" value={query.data.system.database === "up" ? "Operacional" : "Indisponível"} />
            <Stat label="Atividades (7 dias)" value={String(query.data.activity_last_7_days)} />
          </section>

          <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
            <h2 className="border-b border-[var(--color-border)] px-4 py-3 font-medium">
              Histórico de atividades
            </h2>
            {query.data.recent_activity.length === 0 ? (
              <p className="p-4 text-sm text-[var(--color-muted)]">Nenhuma atividade registrada.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-[var(--color-muted)]">
                    <tr>
                      <th className="px-4 py-2 font-medium">Quando</th>
                      <th className="px-4 py-2 font-medium">Ação</th>
                      <th className="px-4 py-2 font-medium">Recurso</th>
                      <th className="px-4 py-2 font-medium">Resultado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {query.data.recent_activity.map((entry, index) => (
                      <tr key={`${entry.occurred_at}-${index}`} className="border-t border-[var(--color-border)]">
                        <td className="px-4 py-2 tabular-nums">{formatDateTime(entry.occurred_at)}</td>
                        <td className="px-4 py-2">{entry.action}</td>
                        <td className="px-4 py-2">{entry.resource}</td>
                        <td className="px-4 py-2">{entry.result}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <p className="text-sm text-[var(--color-muted)]">{query.data.note}</p>
        </>
      ) : null}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <p className="text-sm text-[var(--color-muted)]">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
    </div>
  );
}
