"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { errorText } from "@/components/data-studio/templates-section";
import { apiFetch } from "@/lib/api";
import type { DatasetSummary } from "@/lib/datasets";

const inputClass = "rounded-md border border-[var(--color-border)] bg-transparent px-2 py-1 text-sm";
const buttonClass =
  "rounded-md border border-[var(--color-border)] px-3 py-2 text-sm hover:bg-[var(--color-border)] disabled:opacity-50";

type Duplicates = "first" | "all" | "error";
type Unmatched = "keep_empty" | "drop";

export interface LookupPreview {
  columns: string[];
  counts: Record<string, number>;
  left_rows_read: number;
  output_rows: number;
  unmatched_keys: string[];
  duplicate_keys: string[];
  sample: (string | null)[][];
}

export interface DerivedResult {
  dataset_id: string;
  name: string;
  row_count: number;
}

const STATUS_LABELS: Record<string, string> = {
  encontrado: "Encontrados",
  "não encontrado": "Não encontrados",
  "múltiplas correspondências": "Com múltiplas correspondências",
  "chave inválida": "Chave inválida (vazia ou desconhecida)",
};

/** Monta o corpo do contrato da API. Campos vazios não são enviados. */
export function buildLookupBody(form: {
  leftId: string;
  rightId: string;
  leftKey: string;
  rightKey: string;
  returns: string[];
  duplicates: Duplicates;
  unmatched: Unmatched;
}) {
  return {
    left_id: form.leftId,
    right_id: form.rightId,
    left_keys: [form.leftKey],
    right_keys: [form.rightKey],
    return_columns: form.returns,
    duplicates: form.duplicates,
    unmatched: form.unmatched,
  };
}

export function CrossLookupSection({
  leftId,
  leftColumns,
  datasets,
  onDerived,
}: {
  leftId: string;
  leftColumns: string[];
  datasets: DatasetSummary[];
  onDerived: (id: string) => void;
}) {
  const queryClient = useQueryClient();
  const others = datasets.filter((d) => d.id !== leftId);
  const [rightId, setRightId] = useState("");
  const [leftKey, setLeftKey] = useState(leftColumns[0] ?? "");
  const [rightKey, setRightKey] = useState("");
  const [returns, setReturns] = useState<string[]>([]);
  const [duplicates, setDuplicates] = useState<Duplicates>("first");
  const [unmatched, setUnmatched] = useState<Unmatched>("keep_empty");
  const [preview, setPreview] = useState<LookupPreview | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const right = others.find((d) => d.id === rightId);
  const rightColumns = right?.columns ?? [];
  const ready = Boolean(rightId && leftKey && rightKey);

  function body() {
    return buildLookupBody({ leftId, rightId, leftKey, rightKey, returns, duplicates, unmatched });
  }

  async function runPreview() {
    setBusy(true);
    setMessage(null);
    try {
      const result = await apiFetch<LookupPreview>("/api/v1/crossing/lookup/preview", {
        method: "POST",
        body: JSON.stringify(body()),
      });
      setPreview(result);
    } catch (error) {
      setPreview(null);
      setMessage(errorText(error));
    } finally {
      setBusy(false);
    }
  }

  async function createDerived() {
    setBusy(true);
    setMessage(null);
    try {
      const result = await apiFetch<DerivedResult>("/api/v1/crossing/lookup/derive", {
        method: "POST",
        body: JSON.stringify(body()),
      });
      await queryClient.invalidateQueries({ queryKey: ["datasets"] });
      setPreview(null);
      onDerived(result.dataset_id);
    } catch (error) {
      setMessage(errorText(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-[var(--color-muted)]">
        Busca, para cada linha desta tabela, a correspondência exata na outra tabela pela chave escolhida.
        Nada é alterado nas tabelas de origem: o resultado vira uma tabela nova.
      </p>

      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-1">
          <label htmlFor="sp-right" className="block text-sm font-medium">
            Tabela de busca
          </label>
          <select
            id="sp-right"
            value={rightId}
            onChange={(e) => {
              setRightId(e.target.value);
              setRightKey("");
              setReturns([]);
              setPreview(null);
            }}
            className={`${inputClass} w-full`}
          >
            <option value="">— escolher —</option>
            {others.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label htmlFor="sp-left-key" className="block text-sm font-medium">
              Chave nesta tabela
            </label>
            <select
              id="sp-left-key"
              value={leftKey}
              onChange={(e) => setLeftKey(e.target.value)}
              className={`${inputClass} w-full`}
            >
              {leftColumns.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <label htmlFor="sp-right-key" className="block text-sm font-medium">
              Chave na tabela de busca
            </label>
            <select
              id="sp-right-key"
              value={rightKey}
              onChange={(e) => setRightKey(e.target.value)}
              disabled={!rightId}
              className={`${inputClass} w-full`}
            >
              <option value="">— escolher —</option>
              {rightColumns.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {rightId ? (
        <fieldset className="space-y-1">
          <legend className="text-sm font-medium">Colunas a trazer da tabela de busca</legend>
          <div className="flex flex-wrap gap-3 text-sm">
            {rightColumns.map((c) => (
              <label key={c} className="flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={returns.includes(c)}
                  onChange={(e) =>
                    setReturns((prev) =>
                      e.target.checked ? [...prev, c] : prev.filter((x) => x !== c),
                    )
                  }
                />
                {c}
              </label>
            ))}
          </div>
        </fieldset>
      ) : null}

      <div className="flex flex-wrap items-end gap-3 text-sm">
        <div className="space-y-1">
          <label htmlFor="sp-dup" className="block font-medium">
            Correspondências múltiplas
          </label>
          <select
            id="sp-dup"
            value={duplicates}
            onChange={(e) => setDuplicates(e.target.value as Duplicates)}
            className={inputClass}
          >
            <option value="first">Usar a primeira</option>
            <option value="all">Uma linha por correspondência</option>
            <option value="error">Recusar a operação</option>
          </select>
        </div>
        <div className="space-y-1">
          <label htmlFor="sp-unm" className="block font-medium">
            Registros não encontrados
          </label>
          <select
            id="sp-unm"
            value={unmatched}
            onChange={(e) => setUnmatched(e.target.value as Unmatched)}
            className={inputClass}
          >
            <option value="keep_empty">Manter (com vazio)</option>
            <option value="drop">Remover do resultado</option>
          </select>
        </div>
        <button type="button" onClick={() => void runPreview()} disabled={!ready || busy} className={buttonClass}>
          {busy ? "Processando…" : "Gerar prévia"}
        </button>
      </div>

      {message ? (
        <p role="alert" className="text-sm text-[var(--color-danger)]">
          {message}
        </p>
      ) : null}

      {preview ? (
        <div className="space-y-3 rounded-md border border-[var(--color-border)] p-3">
          <ul className="flex flex-wrap gap-4 text-sm" aria-label="Contagens da prévia">
            <li>Linhas lidas na tabela: <strong>{preview.left_rows_read}</strong></li>
            {Object.entries(preview.counts).map(([status, n]) => (
              <li key={status}>
                {STATUS_LABELS[status] ?? status}: <strong>{n}</strong>
              </li>
            ))}
            <li>Linhas no resultado: <strong>{preview.output_rows}</strong></li>
          </ul>

          {preview.duplicate_keys.length > 0 ? (
            <p className="text-sm">
              Chaves com múltiplas correspondências (amostra): {preview.duplicate_keys.slice(0, 10).join(", ")}
            </p>
          ) : null}
          {preview.unmatched_keys.length > 0 ? (
            <p className="text-sm">
              Chaves não encontradas (amostra): {preview.unmatched_keys.slice(0, 10).join(", ")}
            </p>
          ) : null}

          <div className="max-h-80 overflow-auto rounded-md border border-[var(--color-border)]">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-[var(--color-surface)] text-left text-[var(--color-muted)]">
                <tr>
                  {preview.columns.map((c) => (
                    <th key={c} className="px-2 py-1 font-medium">
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.sample.map((row, i) => (
                  <tr key={i} className="border-t border-[var(--color-border)]">
                    {row.map((v, j) => (
                      <td key={j} className="px-2 py-1 font-mono">
                        {v ?? ""}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button type="button" onClick={() => void createDerived()} disabled={busy} className={buttonClass}>
              Criar tabela derivada
            </button>
            <span className="text-xs text-[var(--color-muted)]">
              Cria uma tabela nova com o resultado. As tabelas de origem não são alteradas.
            </span>
          </div>
        </div>
      ) : null}
    </div>
  );
}
