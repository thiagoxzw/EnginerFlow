"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { errorText } from "@/components/data-studio/templates-section";
import { invalidateDataset } from "@/lib/invalidate";
import { applyOperation, previewOperation, type OperationPreview } from "@/lib/operations";
import { OP_LABELS, VALUE_OPS, type FilterOp } from "@/lib/rows";
import { getDatasetState } from "@/lib/templates";

const sectionClass =
  "card p-4 space-y-3";
const inputClass = "rounded-md border border-[var(--color-border)] bg-transparent px-2 py-1 text-sm";
const buttonClass =
  "rounded-md border border-[var(--color-border)] px-3 py-2 text-sm hover:bg-[var(--color-border)] disabled:opacity-50";

interface ReplaceForm {
  columns: string[];
  find: string;
  replace: string;
  matchCase: boolean;
  wholeCell: boolean;
  filterColumn: string;
  filterOp: FilterOp | "";
  filterValue: string;
}

/** Monta os parâmetros da operação. Filtro sem operador ou sem valor obrigatório é ignorado. */
export function buildReplaceParams(form: ReplaceForm): Record<string, unknown> {
  const params: Record<string, unknown> = {
    columns: form.columns,
    find: form.find,
    replace: form.replace,
    match_case: form.matchCase,
    whole_cell: form.wholeCell,
  };
  if (form.filterOp && form.filterColumn) {
    const needsValue = VALUE_OPS.includes(form.filterOp);
    if (!needsValue || form.filterValue.trim()) {
      params.filters = [
        {
          column: form.filterColumn,
          op: form.filterOp,
          ...(needsValue ? { value: form.filterValue } : {}),
        },
      ];
    }
  }
  return params;
}

export function ReplaceSection({ datasetId, columns }: { datasetId: string; columns: string[] }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<ReplaceForm>({
    columns: [],
    find: "",
    replace: "",
    matchCase: true,
    wholeCell: false,
    filterColumn: columns[0] ?? "",
    filterOp: "",
    filterValue: "",
  });
  const [preview, setPreview] = useState<{ result: OperationPreview; state: Awaited<ReturnType<typeof getDatasetState>> } | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function update(patch: Partial<ReplaceForm>) {
    setForm((prev) => ({ ...prev, ...patch }));
    setPreview(null); // qualquer mudança invalida a prévia
  }

  function toggleColumn(column: string) {
    const next = form.columns.includes(column)
      ? form.columns.filter((c) => c !== column)
      : [...form.columns, column];
    update({ columns: next });
  }

  async function makePreview() {
    setBusy(true);
    setMessage(null);
    try {
      const state = await getDatasetState(datasetId);
      const result = await previewOperation(datasetId, "replace_text", buildReplaceParams(form), state);
      setPreview({ result, state });
    } catch (error) {
      setMessage(errorText(error));
    } finally {
      setBusy(false);
    }
  }

  async function apply() {
    if (!preview) return;
    setBusy(true);
    setMessage(null);
    try {
      await applyOperation(datasetId, preview.result.preview_id, preview.state);
      setPreview(null);
      await invalidateDataset(queryClient, datasetId);
      setMessage("Substituição aplicada. A versão anterior continua no histórico.");
    } catch (error) {
      setPreview(null);
      setMessage(errorText(error));
    } finally {
      setBusy(false);
    }
  }

  const canPreview = form.columns.length > 0 && form.find.length > 0 && !busy;

  return (
    <section className={sectionClass} aria-labelledby="substituir">
      <h2 id="substituir" className="font-medium">
        Localizar e substituir
      </h2>
      <fieldset className="flex flex-wrap gap-3 text-sm">
        <legend className="mb-1 text-[var(--color-muted)]">Colunas</legend>
        {columns.map((c) => (
          <label key={c} className="flex items-center gap-1">
            <input
              type="checkbox"
              checked={form.columns.includes(c)}
              onChange={() => toggleColumn(c)}
            />
            {c}
          </label>
        ))}
      </fieldset>

      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1">
          <label htmlFor="sub-find" className="block text-sm">
            Localizar
          </label>
          <input
            id="sub-find"
            value={form.find}
            onChange={(e) => update({ find: e.target.value })}
            className={inputClass}
          />
        </div>
        <div className="space-y-1">
          <label htmlFor="sub-replace" className="block text-sm">
            Substituir por
          </label>
          <input
            id="sub-replace"
            value={form.replace}
            onChange={(e) => update({ replace: e.target.value })}
            className={inputClass}
          />
        </div>
        <label className="flex items-center gap-1 text-sm">
          <input
            type="checkbox"
            checked={form.matchCase}
            onChange={(e) => update({ matchCase: e.target.checked })}
          />
          Diferenciar maiúsculas
        </label>
        <label className="flex items-center gap-1 text-sm">
          <input
            type="checkbox"
            checked={form.wholeCell}
            onChange={(e) => update({ wholeCell: e.target.checked })}
          />
          Célula inteira
        </label>
      </div>

      <div className="flex flex-wrap items-end gap-2 text-sm">
        <span className="text-[var(--color-muted)]">Somente linhas em que</span>
        <select
          aria-label="Coluna do filtro da substituição"
          value={form.filterColumn}
          onChange={(e) => update({ filterColumn: e.target.value })}
          className={inputClass}
        >
          {columns.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <select
          aria-label="Operador do filtro da substituição"
          value={form.filterOp}
          onChange={(e) => update({ filterOp: e.target.value as FilterOp | "" })}
          className={inputClass}
        >
          <option value="">— sem filtro —</option>
          {(Object.keys(OP_LABELS) as FilterOp[]).map((op) => (
            <option key={op} value={op}>
              {OP_LABELS[op]}
            </option>
          ))}
        </select>
        {form.filterOp && VALUE_OPS.includes(form.filterOp) ? (
          <input
            aria-label="Valor do filtro da substituição"
            value={form.filterValue}
            onChange={(e) => update({ filterValue: e.target.value })}
            className={inputClass}
          />
        ) : null}
      </div>

      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={() => void makePreview()} disabled={!canPreview} className={buttonClass}>
          Gerar prévia
        </button>
        {preview ? (
          <button type="button" onClick={() => void apply()} disabled={busy} className={buttonClass}>
            Aplicar substituição
          </button>
        ) : null}
      </div>

      {preview ? (
        <p role="status" className="text-sm">
          {preview.result.rows_affected === 0
            ? "Nenhuma célula corresponde. Nada será alterado."
            : `${preview.result.rows_affected} linha(s) e ${preview.result.cells_changed} célula(s) serão alteradas.`}
        </p>
      ) : message ? (
        <p role="status" className="text-sm text-[var(--color-muted)]">
          {message}
        </p>
      ) : null}
    </section>
  );
}
