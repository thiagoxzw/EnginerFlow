"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { errorText } from "@/components/data-studio/templates-section";
import { apiFetch } from "@/lib/api";
import { derivedNotice } from "@/lib/datasets";

const inputClass = "rounded-md border border-[var(--color-border)] bg-transparent px-2 py-1 text-sm";
const buttonClass =
  "rounded-md border border-[var(--color-border)] px-3 py-2 text-sm hover:bg-[var(--color-border)] disabled:opacity-50";

const MAX_GROUP_COLUMNS = 5;
const MAX_MEASURES = 10;
const AGG_PATH = "/api/v1/crossing/aggregate";

export type MeasureOp = "count" | "count_distinct" | "sum" | "avg" | "min" | "max";

export const OP_LABELS: Record<MeasureOp, string> = {
  count: "Contagem (não vazios)",
  count_distinct: "Valores distintos",
  sum: "Soma (números)",
  avg: "Média (números)",
  min: "Mínimo (números)",
  max: "Máximo (números)",
};

export interface Measure {
  column: string;
  op: MeasureOp;
}

export interface AggregatePreview {
  columns: string[];
  rows: (string | null)[][];
  input_rows: number;
  groups: number;
}

interface AggregateDerived {
  dataset_id: string;
  name: string;
  run_id: string;
  row_count: number;
  result_sha256: string;
}

/** Corpo do contrato: só colunas escolhidas; medidas e agrupamento na ordem da tela. */
export function buildAggregateBody(form: { datasetId: string; groupBy: string[]; measures: Measure[] }) {
  return {
    dataset_id: form.datasetId,
    group_by: form.groupBy,
    measures: form.measures.map((m) => ({ column: m.column, op: m.op })),
  };
}

/** Não é possível agregar sem medida; agrupamento é opcional (sem agrupamento = total geral). */
export function aggregateReady(measures: Measure[]): boolean {
  return measures.length > 0 && measures.every((m) => m.column !== "");
}

export function AggregateSection({
  datasetId,
  columns,
  onDerived,
}: {
  datasetId: string;
  columns: string[];
  onDerived: (id: string, message: string) => void;
}) {
  const queryClient = useQueryClient();
  const [groupBy, setGroupBy] = useState<string[]>([]);
  const [measures, setMeasures] = useState<Measure[]>([{ column: columns[0] ?? "", op: "count" }]);
  const [preview, setPreview] = useState<AggregatePreview | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const body = () => buildAggregateBody({ datasetId, groupBy, measures });

  function changeMeasures(next: Measure[]) {
    setMeasures(next);
    setPreview(null);
  }

  async function runPreview() {
    setBusy("preview");
    setMessage(null);
    try {
      const result = await apiFetch<AggregatePreview>(`${AGG_PATH}/preview`, {
        method: "POST",
        body: JSON.stringify(body()),
      });
      setPreview(result);
    } catch (error) {
      setPreview(null);
      setMessage(errorText(error));
    } finally {
      setBusy(null);
    }
  }

  async function createDerived() {
    setBusy("derive");
    setMessage(null);
    try {
      const result = await apiFetch<AggregateDerived>(`${AGG_PATH}/derive`, {
        method: "POST",
        body: JSON.stringify(body()),
      });
      await queryClient.invalidateQueries({ queryKey: ["datasets"] });
      setPreview(null);
      onDerived(result.dataset_id, derivedNotice(result));
    } catch (error) {
      setMessage(errorText(error));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-[var(--color-muted)]">
        Agrupa esta tabela por colunas e calcula medidas. Números são somados com precisão decimal; texto que não é
        número é contado como inválido e fica fora da soma. Vazio e desconhecido formam grupos próprios.
      </p>

      <fieldset className="space-y-1">
        <legend className="text-sm font-medium">Agrupar por (opcional, até {MAX_GROUP_COLUMNS})</legend>
        <div className="flex flex-wrap gap-3 text-sm">
          {columns.map((c) => (
            <label key={c} className="flex items-center gap-1">
              <input
                type="checkbox"
                checked={groupBy.includes(c)}
                disabled={!groupBy.includes(c) && groupBy.length >= MAX_GROUP_COLUMNS}
                onChange={(e) => {
                  setGroupBy((prev) => (e.target.checked ? [...prev, c] : prev.filter((x) => x !== c)));
                  setPreview(null);
                }}
              />
              {c}
            </label>
          ))}
        </div>
        {groupBy.length === 0 ? (
          <p className="text-xs text-[var(--color-muted)]">Sem agrupamento: uma linha com o total geral.</p>
        ) : null}
      </fieldset>

      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Medidas (máximo {MAX_MEASURES})</legend>
        {measures.map((m, i) => (
          <div key={i} className="flex flex-wrap items-end gap-2">
            <div className="space-y-1">
              <label htmlFor={`ag-col-${i}`} className="block text-xs text-[var(--color-muted)]">
                Coluna
              </label>
              <select
                id={`ag-col-${i}`}
                value={m.column}
                onChange={(e) =>
                  changeMeasures(measures.map((x, j) => (j === i ? { ...x, column: e.target.value } : x)))
                }
                className={`${inputClass} min-w-40`}
              >
                {columns.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <label htmlFor={`ag-op-${i}`} className="block text-xs text-[var(--color-muted)]">
                Operação
              </label>
              <select
                id={`ag-op-${i}`}
                value={m.op}
                onChange={(e) =>
                  changeMeasures(
                    measures.map((x, j) => (j === i ? { ...x, op: e.target.value as MeasureOp } : x)),
                  )
                }
                className={inputClass}
              >
                {(Object.keys(OP_LABELS) as MeasureOp[]).map((op) => (
                  <option key={op} value={op}>
                    {OP_LABELS[op]}
                  </option>
                ))}
              </select>
            </div>
            {measures.length > 1 ? (
              <button
                type="button"
                onClick={() => changeMeasures(measures.filter((_, j) => j !== i))}
                className={buttonClass}
              >
                Remover medida {i + 1}
              </button>
            ) : null}
          </div>
        ))}
        {measures.length < MAX_MEASURES ? (
          <button
            type="button"
            onClick={() => changeMeasures([...measures, { column: columns[0] ?? "", op: "count" }])}
            className={buttonClass}
          >
            Adicionar medida
          </button>
        ) : null}
      </fieldset>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => void runPreview()}
          disabled={!aggregateReady(measures) || busy !== null}
          className={buttonClass}
        >
          {busy === "preview" ? "Calculando…" : "Gerar prévia"}
        </button>
        <p role="status" className="text-sm text-[var(--color-muted)]">
          {busy === "preview" ? "Agregando as linhas da tabela…" : null}
          {busy === "derive" ? "Criando a tabela derivada…" : null}
        </p>
      </div>

      {message ? (
        <p role="alert" className="text-sm text-[var(--color-danger)]">
          {message}
        </p>
      ) : null}

      {preview ? (
        <div className="space-y-3 rounded-md border border-[var(--color-border)] p-3">
          <p className="text-sm">
            <strong>{preview.groups}</strong> grupo(s) a partir de <strong>{preview.input_rows}</strong> linha(s).
          </p>
          <div className="max-h-80 overflow-auto rounded-md border border-[var(--color-border)]">
            <table className="w-full text-xs">
              <caption className="sr-only">Prévia da agregação</caption>
              <thead className="sticky top-0 bg-[var(--color-surface)] text-left text-[var(--color-muted)]">
                <tr>
                  {preview.columns.map((c) => (
                    <th key={c} scope="col" className="px-2 py-1 font-medium">
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((row, i) => (
                  <tr key={i} className="border-t border-[var(--color-border)]">
                    {row.map((v, j) => (
                      <td key={j} className="whitespace-nowrap px-2 py-1 font-mono">
                        {v ?? ""}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {preview.groups > preview.rows.length ? (
            <p className="text-xs text-[var(--color-muted)]">
              A prévia mostra {preview.rows.length} de {preview.groups} grupos; a tabela derivada terá todos.
            </p>
          ) : null}
          <button type="button" onClick={() => void createDerived()} disabled={busy !== null} className={buttonClass}>
            Criar tabela derivada
          </button>
        </div>
      ) : null}
    </div>
  );
}
