"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import { DataTable } from "@/components/data-studio/data-table";
import { HeaderSection } from "@/components/data-studio/header-section";
import { HistoryList, UndoRedoControls } from "@/components/data-studio/history-panel";
import { Tabs } from "@/components/data-studio/tabs";
import {
  DeletedTablesSection,
  TableAdminSection,
} from "@/components/data-studio/table-admin";
import { CrossLookupSection } from "@/components/data-studio/cross-lookup-section";
import { AggregateSection } from "@/components/data-studio/aggregate-section";
import { JoinSection } from "@/components/data-studio/join-section";
import { LineagePanel } from "@/components/data-studio/lineage-panel";
import { KeyCompareSection } from "@/components/data-studio/key-compare-section";
import { UploadSection } from "@/components/data-studio/upload-section";
import { ReplaceSection } from "@/components/data-studio/replace-section";
import { TemplatesSection } from "@/components/data-studio/templates-section";
import {
  CANONICAL_FIELDS,
  EXPORT_COMPARE_PATH,
  FIELD_LABELS,
  buildMappingPayload,
  compareDatasets,
  downloadExport,
  exportDatasetPath,
  exportDuplicatesPath,
  getDataset,
  getDuplicates,
  isDerived,
  listDatasets,
  saveMapping,
  type ExportFormat,
  type CanonicalField,
  type CompareOut,
  type DatasetSummary,
} from "@/lib/datasets";

function errorMessage(error: unknown): string {
  if (error instanceof ApiError && error.problem) {
    return error.problem.detail;
  }
  return error instanceof Error ? error.message : "Erro desconhecido.";
}

const sectionClass = "rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4 space-y-3";
const inputClass = "rounded-md border border-[var(--color-border)] bg-transparent px-3 py-2";
const buttonClass =
  "rounded-md bg-[var(--color-accent)] px-4 py-2 font-medium text-white disabled:opacity-60";

export function DataStudioView() {
  const queryClient = useQueryClient();
  const router = useRouter();
  const datasets = useQuery({ queryKey: ["datasets"], queryFn: listDatasets });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Aviso da última operação (ex.: tabela derivada criada). Fica na página, não no painel que é trocado.
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (datasets.error instanceof ApiError && datasets.error.status === 401) {
      router.replace("/login");
    }
  }, [datasets.error, router]);

  return (
    <div className="mx-auto max-w-[1600px] space-y-4 p-4 md:p-6">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-xl font-semibold">Data Studio</h1>
        <p className="text-xs text-[var(--color-muted)]">Nada é alterado automaticamente.</p>
      </header>

      <div className="grid gap-6 lg:grid-cols-[300px_minmax(0,1fr)]">
        <aside className="order-last min-w-0 space-y-4 lg:order-first lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:self-start lg:overflow-y-auto">
          <UploadSection
            onImported={(id) => {
              setSelectedId(id);
              void queryClient.invalidateQueries({ queryKey: ["datasets"] });
            }}
          />

          <section className={sectionClass} aria-labelledby="tabelas">
            <h2 id="tabelas" className="font-medium">
              Tabelas importadas
            </h2>
            {datasets.isPending ? (
              <p className="text-sm text-[var(--color-muted)]">Carregando…</p>
            ) : null}
            {datasets.isError ? (
              <p role="alert" className="text-sm text-[var(--color-danger)]">
                {errorMessage(datasets.error)}
              </p>
            ) : null}
            {datasets.data && datasets.data.length === 0 ? (
              <p className="text-sm text-[var(--color-muted)]">Nenhuma tabela importada ainda.</p>
            ) : null}
            {datasets.data && datasets.data.length > 0 ? (
              <ul className="divide-y divide-[var(--color-border)]">
                {datasets.data.map((d) => (
                  <li key={d.id} className="flex items-center justify-between gap-2 py-2">
                    <span className="min-w-0 text-sm">
                      <strong className="block truncate">{d.name}</strong>
                      <span className="text-xs text-[var(--color-muted)]">
                        {d.row_count} linhas · {d.columns.length} colunas
                        {d.sheet_name ? ` · aba ${d.sheet_name}` : ""}
                        {isDerived(d) ? " · derivada de cruzamento" : ""}
                      </span>
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedId(d.id);
                        setNotice(null);
                      }}
                      className="shrink-0 rounded-md border border-[var(--color-border)] px-3 py-1 text-sm"
                      aria-pressed={selectedId === d.id}
                    >
                      Abrir
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </section>

          <DeletedTablesSection />

          <CompareSection datasets={datasets.data ?? []} />
        </aside>

        <main className="order-first min-w-0 space-y-4 lg:order-none">
          {selectedId ? (
            <>
              {notice ? (
                <p role="status" className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-sm">
                  {notice}
                </p>
              ) : null}
              <DatasetPanel
                datasetId={selectedId}
                onDeleted={() => {
                  setSelectedId(null);
                  setNotice(null);
                }}
                onOpen={(id, message) => {
                  setSelectedId(id);
                  setNotice(message ?? null);
                  void queryClient.invalidateQueries({ queryKey: ["datasets"] });
                }}
              />
            </>
          ) : (
            <section className={sectionClass}>
              <h2 className="font-medium">Nenhuma tabela aberta</h2>
              <p className="text-sm text-[var(--color-muted)]">
                Importe um arquivo CSV ou XLSX, ou escolha uma tabela na lista à esquerda.
              </p>
            </section>
          )}
        </main>
      </div>
    </div>
  );
}

function DatasetPanel({
  datasetId,
  onDeleted,
  onOpen,
}: {
  datasetId: string;
  onDeleted: () => void;
  onOpen: (id: string, message?: string) => void;
}) {
  const queryClient = useQueryClient();
  const detail = useQuery({
    queryKey: ["dataset", datasetId],
    queryFn: () => getDataset(datasetId),
  });
  const allDatasets = useQuery({ queryKey: ["datasets"], queryFn: listDatasets });

  if (detail.isPending) {
    return <p className="text-sm text-[var(--color-muted)]">Carregando tabela…</p>;
  }
  if (detail.isError) {
    return (
      <p role="alert" className="text-sm text-[var(--color-danger)]">
        {errorMessage(detail.error)}
      </p>
    );
  }
  const data = detail.data;
  const onSaved = (updated: DatasetSummary) => {
    queryClient.setQueryData(["dataset", datasetId], (old: unknown) =>
      old && typeof old === "object" ? { ...old, mapping: updated.mapping } : old,
    );
  };

  const sheetInfo = data.sheet_name ? ` · aba ${data.sheet_name}` : "";
  const derived = isDerived(data);
  const openers = (allDatasets.data ?? []).filter((d) => d.id !== datasetId);

  // Ordem: cabeçalho (contexto e ações) -> tabela (central) -> ferramentas em abas.
  return (
    <div className="space-y-3">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-[var(--color-border)] pb-3">
        <div className="min-w-0 space-y-1">
          <h2 className="truncate text-lg font-semibold">{data.name}</h2>
          <p className="text-xs text-[var(--color-muted)]">
            {data.row_count} linhas · {data.columns.length} colunas{sheetInfo} ·{" "}
            {derived ? "Origem: cruzamento (derivada)" : "Origem: importação"}
          </p>
          {openers.length > 0 ? (
            <label className="flex items-center gap-2 text-xs">
              <span className="text-[var(--color-muted)]">Trocar tabela</span>
              <select
                value={datasetId}
                onChange={(e) => onOpen(e.target.value)}
                className="rounded-md border border-[var(--color-border)] bg-transparent px-2 py-1"
              >
                <option value={datasetId}>{data.name}</option>
                {openers.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <UndoRedoControls datasetId={datasetId} />
          <ExportButtons
            label="Exportar"
            onExport={(fmt) => downloadExport(exportDatasetPath(datasetId), fmt)}
          />
        </div>
      </header>

      {data.warnings.length > 0 ? (
        <details className="rounded-md border border-[var(--color-border)] p-2 text-sm">
          <summary className="cursor-pointer">{data.warnings.length} aviso(s) da importação</summary>
          <ul className="mt-2 list-inside list-disc">
            {data.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </details>
      ) : null}

      <DataTable datasetId={datasetId} columns={data.columns} />

      <Tabs
        label="Ferramentas da tabela"
        initial="transformar"
        tabs={[
          {
            id: "transformar",
            label: "Transformar",
            content: <ReplaceSection datasetId={datasetId} columns={data.columns} />,
          },
          {
            id: "cruzar",
            label: "Cruzar tabelas",
            content: (
              <Tabs
                label="Cruzamentos entre tabelas"
                size="sm"
                initial="procv"
                tabs={[
                  {
                    id: "procv",
                    label: "Super-PROCV",
                    content: (
                      <CrossLookupSection
                        leftId={datasetId}
                        leftColumns={data.columns}
                        datasets={allDatasets.data ?? []}
                        onDerived={onOpen}
                      />
                    ),
                  },
                  {
                    id: "juncao",
                    label: "Junção",
                    content: (
                      <JoinSection
                        leftId={datasetId}
                        leftColumns={data.columns}
                        datasets={allDatasets.data ?? []}
                        onDerived={onOpen}
                      />
                    ),
                  },
                  {
                    id: "comparar",
                    label: "Comparar",
                    content: (
                      <KeyCompareSection
                        leftId={datasetId}
                        leftColumns={data.columns}
                        datasets={allDatasets.data ?? []}
                        onDerived={onOpen}
                      />
                    ),
                  },
                  {
                    id: "agrupar",
                    label: "Agrupar",
                    content: (
                      <AggregateSection datasetId={datasetId} columns={data.columns} onDerived={onOpen} />
                    ),
                  },
                ]}
              />
            ),
          },
          {
            id: "mapeamento",
            label: "Mapeamento",
            content: (
              <div className="space-y-6">
                <MappingSection
                  key={datasetId}
                  datasetId={datasetId}
                  columns={data.columns}
                  initial={data.mapping}
                  onSaved={onSaved}
                />
                <HeaderSection datasetId={datasetId} />
                <TemplatesSection
                  datasetId={datasetId}
                  onApplied={() => void queryClient.invalidateQueries({ queryKey: ["dataset", datasetId] })}
                />
              </div>
            ),
          },
          {
            id: "historico",
            label: "Histórico",
            content: <HistoryList datasetId={datasetId} />,
          },
          {
            id: "gerenciar",
            label: "Gerenciar",
            content: <TableAdminSection datasetId={datasetId} name={data.name} onDeleted={onDeleted} />,
          },
          {
            id: "duplicatas",
            label: "Duplicatas",
            content: <DuplicatesSection datasetId={datasetId} hasCodeMapping={Boolean(data.mapping.code)} />,
          },
          ...(derived
            ? [
                {
                  id: "rastreabilidade",
                  label: "Rastreabilidade",
                  content: <LineagePanel datasetId={datasetId} />,
                },
              ]
            : []),
        ]}
      />
    </div>
  );
}

function MappingSection({
  datasetId,
  columns,
  initial,
  onSaved,
}: {
  datasetId: string;
  columns: string[];
  initial: DatasetSummary["mapping"];
  onSaved: (updated: DatasetSummary) => void;
}) {
  const [form, setForm] = useState<DatasetSummary["mapping"]>(initial);
  const [message, setMessage] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: () => saveMapping(datasetId, buildMappingPayload(form)),
    onSuccess: (updated) => {
      setMessage("Mapeamento salvo.");
      onSaved(updated);
    },
    onError: (error) => setMessage(errorMessage(error)),
  });

  return (
    <section className={sectionClass} aria-labelledby="mapeamento">
      <h2 id="mapeamento" className="font-medium">
        Mapeamento de colunas
      </h2>
      <p className="text-sm text-[var(--color-muted)]">
        Escolha qual coluna da origem corresponde a cada campo. Campos vazios não são usados.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        {CANONICAL_FIELDS.map((field: CanonicalField) => (
          <div key={field} className="space-y-1">
            <label htmlFor={`map-${field}`} className="block text-sm font-medium">
              {FIELD_LABELS[field]}
            </label>
            <select
              id={`map-${field}`}
              value={form[field] ?? ""}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, [field]: e.target.value || undefined }))
              }
              className={`${inputClass} w-full`}
            >
              <option value="">— não mapear —</option>
              {columns.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-3">
        <button type="button" onClick={() => save.mutate()} disabled={save.isPending} className={buttonClass}>
          {save.isPending ? "Salvando…" : "Salvar mapeamento"}
        </button>
        {message ? (
          <span role="status" className="text-sm text-[var(--color-muted)]">
            {message}
          </span>
        ) : null}
      </div>
    </section>
  );
}

function DuplicatesSection({
  datasetId,
  hasCodeMapping,
}: {
  datasetId: string;
  hasCodeMapping: boolean;
}) {
  const [threshold, setThreshold] = useState(0.85);
  const [requested, setRequested] = useState(false);
  const report = useQuery({
    queryKey: ["duplicates", datasetId, threshold],
    queryFn: () => getDuplicates(datasetId, threshold),
    enabled: requested && hasCodeMapping,
  });

  return (
    <section className={sectionClass} aria-labelledby="duplicatas">
      <h2 id="duplicatas" className="font-medium">
        Duplicatas e semelhanças
      </h2>
      {!hasCodeMapping ? (
        <p className="text-sm text-[var(--color-muted)]">Mapeie a coluna de código para analisar.</p>
      ) : (
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <label htmlFor="limite" className="block text-sm font-medium">
              Limite de semelhança
            </label>
            <select
              id="limite"
              value={threshold}
              onChange={(e) => setThreshold(Number(e.target.value))}
              className={inputClass}
            >
              <option value={0.75}>0,75</option>
              <option value={0.85}>0,85</option>
              <option value={0.95}>0,95</option>
            </select>
          </div>
          <button type="button" onClick={() => setRequested(true)} className={buttonClass}>
            Analisar
          </button>
        </div>
      )}

      {report.isFetching ? <p className="text-sm text-[var(--color-muted)]">Analisando…</p> : null}
      {report.isError ? (
        <p role="alert" className="text-sm text-[var(--color-danger)]">
          {errorMessage(report.error)}
        </p>
      ) : null}

      {report.data ? (
        <div className="space-y-4 text-sm">
          <p className="text-[var(--color-muted)]">{report.data.note}</p>
          <ExportButtons
            label="Exportar duplicatas"
            onExport={(fmt) => downloadExport(exportDuplicatesPath(datasetId, threshold), fmt)}
          />

          <div>
            <h3 className="font-medium">Códigos repetidos (mesma chave)</h3>
            {report.data.exact_codes.length === 0 ? (
              <p className="text-[var(--color-muted)]">Nenhum.</p>
            ) : (
              <ul className="list-inside list-disc">
                {report.data.exact_codes.map((g) => (
                  <li key={g.key}>
                    <span className="font-mono">{g.key}</span> nas linhas {g.row_numbers.join(", ")}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div>
            <h3 className="font-medium">Possíveis equivalências por zeros à esquerda</h3>
            {report.data.leading_zero_suspicions.length === 0 ? (
              <p className="text-[var(--color-muted)]">Nenhuma.</p>
            ) : (
              <ul className="list-inside list-disc">
                {report.data.leading_zero_suspicions.map((s) => (
                  <li key={`${s.key_a}|${s.key_b}`}>
                    <span className="font-mono">{s.key_a}</span> ×{" "}
                    <span className="font-mono">{s.key_b}</span> (revisar)
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div>
            <h3 className="font-medium">Descrições semelhantes</h3>
            {report.data.similar_descriptions.length === 0 ? (
              <p className="text-[var(--color-muted)]">Nenhuma acima do limite.</p>
            ) : (
              <table className="w-full">
                <thead className="text-left text-[var(--color-muted)]">
                  <tr>
                    <th className="py-1 font-medium">Linhas</th>
                    <th className="py-1 font-medium">Descrições</th>
                    <th className="py-1 font-medium">Score</th>
                    <th className="py-1 font-medium">Evidência</th>
                  </tr>
                </thead>
                <tbody>
                  {report.data.similar_descriptions.map((p) => (
                    <tr key={`${p.row_a}-${p.row_b}`} className="border-t border-[var(--color-border)]">
                      <td className="py-1 tabular-nums">
                        {p.row_a} × {p.row_b}
                      </td>
                      <td className="py-1">
                        {p.value_a} <span className="text-[var(--color-muted)]">/</span> {p.value_b}
                      </td>
                      <td className="py-1 tabular-nums">{p.score.toFixed(2).replace(".", ",")}</td>
                      <td className="py-1">{p.shared_tokens.join(", ") || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function CompareSection({ datasets }: { datasets: DatasetSummary[] }) {
  const [left, setLeft] = useState("");
  const [right, setRight] = useState("");
  const compare = useMutation<CompareOut, unknown, void>({
    mutationFn: () => compareDatasets(left, right),
  });

  return (
    <section className={sectionClass} aria-labelledby="comparar">
      <h2 id="comparar" className="font-medium">
        Comparar códigos entre tabelas
      </h2>
      <p className="text-sm text-[var(--color-muted)]">
        Ambas as tabelas precisam ter a coluna de código mapeada.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <DatasetSelect id="esq" label="Tabela A" value={left} onChange={setLeft} datasets={datasets} />
        <DatasetSelect id="dir" label="Tabela B" value={right} onChange={setRight} datasets={datasets} />
      </div>
      {[left, right]
        .map((id) => datasets.find((d) => d.id === id))
        .some((d) => d && !d.mapping.code) ? (
        <p role="status" className="text-sm text-[var(--color-danger)]">
          Falta mapear a coluna de código em uma das tabelas. Faça o mapeamento em &ldquo;Mapeamento, cabeçalho e
          modelos&rdquo;, dentro da tabela, antes de comparar.
        </p>
      ) : null}
      <button
        type="button"
        disabled={!left || !right || left === right || compare.isPending}
        onClick={() => compare.mutate()}
        className={buttonClass}
      >
        {compare.isPending ? "Comparando…" : "Comparar"}
      </button>

      {compare.isError ? (
        <p role="alert" className="text-sm text-[var(--color-danger)]">
          {errorMessage(compare.error)}
        </p>
      ) : null}

      {compare.data ? (
        <div className="space-y-3 text-sm">
          <p className="text-[var(--color-muted)]">{compare.data.note}</p>
          <ExportButtons
            label="Exportar comparação"
            onExport={(fmt) =>
              downloadExport(EXPORT_COMPARE_PATH, fmt, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ left_id: left, right_id: right }),
              })
            }
          />
          <ul className="list-inside list-disc">
            <li>Somente na tabela A: {compare.data.only_left_count}</li>
            <li>Somente na tabela B: {compare.data.only_right_count}</li>
            <li>Em ambas: {compare.data.in_both_count}</li>
          </ul>
          {compare.data.leading_zero_candidates.length > 0 ? (
            <div>
              <h3 className="font-medium">Candidatos por zeros à esquerda (revisar)</h3>
              <ul className="list-inside list-disc font-mono">
                {compare.data.leading_zero_candidates.map((c) => (
                  <li key={`${c.esquerda}|${c.direita}`}>
                    {c.esquerda} × {c.direita}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function DatasetSelect({
  id,
  label,
  value,
  onChange,
  datasets,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  datasets: DatasetSummary[];
}) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)} className={`${inputClass} w-full`}>
        <option value="">— escolher —</option>
        {datasets.map((d) => (
          <option key={d.id} value={d.id}>
            {d.name}
          </option>
        ))}
      </select>
    </div>
  );
}

function ExportButtons({
  label,
  onExport,
}: {
  label: string;
  onExport: (format: ExportFormat) => Promise<void>;
}) {
  const [error, setError] = useState<string | null>(null);
  const run = async (format: ExportFormat) => {
    setError(null);
    try {
      await onExport(format);
    } catch (err) {
      setError(errorMessage(err));
    }
  };
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-sm text-[var(--color-muted)]">{label}:</span>
      <button
        type="button"
        onClick={() => void run("csv")}
        className="rounded-md border border-[var(--color-border)] px-3 py-1 text-sm"
      >
        CSV
      </button>
      <button
        type="button"
        onClick={() => void run("xlsx")}
        className="rounded-md border border-[var(--color-border)] px-3 py-1 text-sm"
      >
        XLSX
      </button>
      {error ? (
        <span role="alert" className="text-sm text-[var(--color-danger)]">
          {error}
        </span>
      ) : null}
    </div>
  );
}
