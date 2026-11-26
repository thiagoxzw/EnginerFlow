"use client";

import { useQuery } from "@tanstack/react-query";

import { errorText } from "@/components/data-studio/templates-section";
import { getLineage, type Lineage } from "@/lib/datasets";

const sectionClass = "card p-4 space-y-3";

/** Rastreabilidade de uma tabela derivada: operação, execução, parâmetros, origens e hash. */
export function LineagePanel({ datasetId }: { datasetId: string }) {
  const lineage = useQuery({ queryKey: ["lineage", datasetId], queryFn: () => getLineage(datasetId) });

  return (
    <details className={sectionClass}>
      <summary className="cursor-pointer font-medium">Rastreabilidade desta tabela</summary>
      <div className="space-y-3 pt-3 text-sm">
        {lineage.isPending ? <p className="text-[var(--color-muted)]">Carregando…</p> : null}
        {lineage.isError ? (
          <p role="alert" className="text-[var(--color-danger)]">
            {errorText(lineage.error)}
          </p>
        ) : null}
        {lineage.data ? <LineageBody lineage={lineage.data} /> : null}
      </div>
    </details>
  );
}

function LineageBody({ lineage }: { lineage: Lineage }) {
  return (
    <>
      <p className="text-xs text-[var(--color-muted)]">
        Esta tabela é um resultado congelado. Alterações posteriores nas tabelas de origem não a modificam.
      </p>
      <dl className="grid gap-x-4 gap-y-1 sm:grid-cols-[max-content_1fr]">
        <dt className="font-medium">Operação</dt>
        <dd>
          {lineage.operation} (versão {lineage.operation_version})
        </dd>
        <dt className="font-medium">Execução</dt>
        <dd className="font-mono text-xs">{lineage.run_id}</dd>
        <dt className="font-medium">Criada em</dt>
        <dd>{new Date(lineage.created_at).toLocaleString("pt-BR")}</dd>
        <dt className="font-medium">Por</dt>
        <dd>{lineage.actor}</dd>
        <dt className="font-medium">Linhas</dt>
        <dd>{lineage.row_count}</dd>
        <dt className="font-medium">Hash do resultado</dt>
        <dd className="font-mono text-xs break-all">{lineage.result_sha256}</dd>
        <dt className="font-medium">Hash dos parâmetros</dt>
        <dd className="font-mono text-xs break-all">{lineage.params_sha256}</dd>
      </dl>

      <section aria-labelledby="origens-rastro" className="space-y-1">
        <h3 id="origens-rastro" className="font-medium">
          Origens
        </h3>
        <ul className="space-y-1">
          {lineage.sources.map((s) => (
            <li key={`${s.role}-${s.dataset_id}`}>
              <strong>{s.role === "left" ? "Esquerda" : "Direita"}:</strong> {s.dataset_name}{" "}
              <span className="text-xs text-[var(--color-muted)]">
                · versão de dados {s.version_id.slice(0, 8)} · metadados {s.metadata_version_id.slice(0, 8)} ·{" "}
                {s.still_active ? "ativa" : "excluída logicamente (resultado preservado)"}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="parametros-rastro" className="space-y-1">
        <h3 id="parametros-rastro" className="font-medium">
          Parâmetros e políticas
        </h3>
        <pre className="max-h-48 overflow-auto rounded-md bg-[var(--color-border)] p-2 text-xs">
          {JSON.stringify({ parametros: lineage.params, politica: lineage.policy }, null, 2)}
        </pre>
      </section>

      <section aria-labelledby="contagens-rastro" className="space-y-1">
        <h3 id="contagens-rastro" className="font-medium">
          Contagens
        </h3>
        <ul className="flex flex-wrap gap-x-4 gap-y-1">
          {Object.entries(lineage.counts).map(([k, v]) => (
            <li key={k}>
              {k}: <strong>{String(v)}</strong>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
