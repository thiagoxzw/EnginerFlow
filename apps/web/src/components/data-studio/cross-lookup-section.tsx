"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { errorText } from "@/components/data-studio/templates-section";
import { apiFetch } from "@/lib/api";
import { downloadExport, type ExportFormat, type DatasetSummary } from "@/lib/datasets";

const inputClass = "rounded-md border border-[var(--color-border)] bg-transparent px-2 py-1 text-sm";
const buttonClass =
  "rounded-md border border-[var(--color-border)] px-3 py-2 text-sm hover:bg-[var(--color-border)] disabled:opacity-50";

const MAX_KEYS = 10;
const LOOKUP_PATH = "/api/v1/crossing/lookup";

type Duplicates = "first" | "all" | "error";
type Unmatched = "keep_empty" | "drop";
export interface KeyPair {
  left: string;
  right: string;
}

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
  run_id: string;
  row_count: number;
  counts: Record<string, number>;
  result_sha256: string;
}

const STATUS_LABELS: Record<string, string> = {
  encontrado: "Encontrados",
  "não encontrado": "Não encontrados",
  "múltiplas correspondências": "Com múltiplas correspondências",
  "chave inválida": "Chave inválida (vazia ou desconhecida)",
};

export interface LookupForm {
  leftId: string;
  rightId: string;
  keys: KeyPair[];
  returns: string[];
  duplicates: Duplicates;
  unmatched: Unmatched;
}

/** Monta o corpo do contrato da API a partir do formulário. */
export function buildLookupBody(form: LookupForm) {
  return {
    left_id: form.leftId,
    right_id: form.rightId,
    left_keys: form.keys.map((k) => k.left),
    right_keys: form.keys.map((k) => k.right),
    return_columns: form.returns,
    duplicates: form.duplicates,
    unmatched: form.unmatched,
  };
}

/** Chaves compostas chegam como "valor1|valor2"; na tela ficam como "valor1 + valor2". */
export function formatKeys(keys: string[], limit = 10): string {
  return keys.slice(0, limit).map((k) => k.split("|").join(" + ")).join(" · ");
}

/** Pares de chave só valem quando todos os lados estão preenchidos. */
export function keysComplete(keys: KeyPair[]): boolean {
  return keys.length > 0 && keys.every((k) => k.left !== "" && k.right !== "");
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
  const [keys, setKeys] = useState<KeyPair[]>([{ left: leftColumns[0] ?? "", right: "" }]);
  const [returns, setReturns] = useState<string[]>([]);
  const [duplicates, setDuplicates] = useState<Duplicates>("first");
  const [unmatched, setUnmatched] = useState<Unmatched>("keep_empty");
  const [preview, setPreview] = useState<LookupPreview | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [derived, setDerived] = useState<DerivedResult | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const right = others.find((d) => d.id === rightId);
  const rightColumns = right?.columns ?? [];
  const ready = Boolean(rightId) && keysComplete(keys);

  function form(): LookupForm {
    return { leftId, rightId, keys, returns, duplicates, unmatched };
  }

  function invalidatePreview() {
    setPreview(null);
    setDerived(null);
  }

  function updateKey(index: number, patch: Partial<KeyPair>) {
    setKeys((prev) => prev.map((k, i) => (i === index ? { ...k, ...patch } : k)));
    invalidatePreview();
  }

  async function runPreview() {
    setBusy("preview");
    setMessage(null);
    setDerived(null);
    try {
      const result = await apiFetch<LookupPreview>(`${LOOKUP_PATH}/preview`, {
        method: "POST",
        body: JSON.stringify(buildLookupBody(form())),
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
      const result = await apiFetch<DerivedResult>(`${LOOKUP_PATH}/derive`, {
        method: "POST",
        body: JSON.stringify(buildLookupBody(form())),
      });
      await queryClient.invalidateQueries({ queryKey: ["datasets"] });
      setPreview(null);
      setDerived(result);
      onDerived(result.dataset_id);
    } catch (error) {
      setMessage(errorText(error));
    } finally {
      setBusy(null);
    }
  }

  async function exportPreview(format: ExportFormat) {
    setBusy(`export-${format}`);
    setMessage(null);
    try {
      await downloadExport(`${LOOKUP_PATH}/export`, format, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildLookupBody(form())),
      });
    } catch (error) {
      setMessage(errorText(error));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-[var(--color-muted)]">
        Busca, para cada linha desta tabela, a correspondência exata na outra tabela pela chave escolhida.
        Nada é alterado nas tabelas de origem: o resultado vira uma tabela nova.
      </p>

      <div className="space-y-1">
        <label htmlFor="sp-right" className="block text-sm font-medium">
          Tabela de busca
        </label>
        <select
          id="sp-right"
          value={rightId}
          onChange={(e) => {
            setRightId(e.target.value);
            setKeys((prev) => prev.map((k) => ({ ...k, right: "" })));
            setReturns([]);
            invalidatePreview();
          }}
          className={`${inputClass} w-full md:w-96`}
        >
          <option value="">— escolher —</option>
          {others.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
      </div>

      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">
          Chaves de correspondência (todas precisam bater; máximo {MAX_KEYS})
        </legend>
        {keys.map((k, i) => (
          <div key={i} className="flex flex-wrap items-end gap-2">
            <div className="space-y-1">
              <label htmlFor={`sp-lk-${i}`} className="block text-xs text-[var(--color-muted)]">
                Coluna nesta tabela
              </label>
              <select
                id={`sp-lk-${i}`}
                value={k.left}
                onChange={(e) => updateKey(i, { left: e.target.value })}
                className={`${inputClass} min-w-40`}
              >
                {leftColumns.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
            <span aria-hidden="true" className="pb-2 text-[var(--color-muted)]">
              =
            </span>
            <div className="space-y-1">
              <label htmlFor={`sp-rk-${i}`} className="block text-xs text-[var(--color-muted)]">
                Coluna na tabela de busca
              </label>
              <select
                id={`sp-rk-${i}`}
                value={k.right}
                disabled={!rightId}
                onChange={(e) => updateKey(i, { right: e.target.value })}
                className={`${inputClass} min-w-40`}
              >
                <option value="">— escolher —</option>
                {rightColumns.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
            {keys.length > 1 ? (
              <button
                type="button"
                onClick={() => {
                  setKeys((prev) => prev.filter((_, j) => j !== i));
                  invalidatePreview();
                }}
                className={buttonClass}
              >
                Remover chave {i + 1}
              </button>
            ) : null}
          </div>
        ))}
        {keys.length < MAX_KEYS ? (
          <button
            type="button"
            onClick={() => {
              setKeys((prev) => [...prev, { left: leftColumns[0] ?? "", right: "" }]);
              invalidatePreview();
            }}
            className={buttonClass}
          >
            Adicionar chave
          </button>
        ) : null}
      </fieldset>

      {rightId ? (
        <fieldset className="space-y-1">
          <legend className="text-sm font-medium">Colunas a trazer da tabela de busca</legend>
          <div className="flex flex-wrap gap-3 text-sm">
            {rightColumns.map((c) => (
              <label key={c} className="flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={returns.includes(c)}
                  onChange={(e) => {
                    setReturns((prev) =>
                      e.target.checked ? [...prev, c] : prev.filter((x) => x !== c),
                    );
                    invalidatePreview();
                  }}
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
            onChange={(e) => {
              setDuplicates(e.target.value as Duplicates);
              invalidatePreview();
            }}
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
            onChange={(e) => {
              setUnmatched(e.target.value as Unmatched);
              invalidatePreview();
            }}
            className={inputClass}
          >
            <option value="keep_empty">Manter (com vazio)</option>
            <option value="drop">Remover do resultado</option>
          </select>
        </div>
        <button type="button" onClick={() => void runPreview()} disabled={!ready || busy !== null} className={buttonClass}>
          {busy === "preview" ? "Gerando prévia…" : "Gerar prévia"}
        </button>
      </div>

      <p role="status" className="text-sm text-[var(--color-muted)]">
        {busy === "preview" ? "Calculando a prévia; tabelas grandes podem levar alguns segundos." : null}
        {busy === "derive" ? "Criando a tabela derivada…" : null}
        {busy === "export-csv" || busy === "export-xlsx" ? "Preparando a exportação…" : null}
      </p>

      {message ? (
        <p role="alert" className="text-sm text-[var(--color-danger)]">
          {message}
        </p>
      ) : null}

      {derived ? (
        <div role="status" className="space-y-1 rounded-md border border-[var(--color-border)] p-3 text-sm">
          <p>
            Tabela derivada <strong>{derived.name}</strong> criada com {derived.row_count} linhas.
          </p>
          <p className="text-xs text-[var(--color-muted)]">
            Origem: esta tabela e a tabela de busca escolhida. Execução {derived.run_id.slice(0, 8)} · hash{" "}
            <span className="font-mono">{derived.result_sha256.slice(0, 12)}</span>. As tabelas de origem
            não foram alteradas.
          </p>
        </div>
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
              Chaves com múltiplas correspondências (amostra): {formatKeys(preview.duplicate_keys)}
            </p>
          ) : null}
          {preview.unmatched_keys.length > 0 ? (
            <p className="text-sm">
              Chaves não encontradas (amostra): {formatKeys(preview.unmatched_keys)}
            </p>
          ) : null}

          <div className="max-h-80 overflow-auto rounded-md border border-[var(--color-border)]">
            <table className="w-full text-xs">
              <caption className="sr-only">Prévia do resultado do PROCV</caption>
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
            <button type="button" onClick={() => void createDerived()} disabled={busy !== null} className={buttonClass}>
              Criar tabela derivada
            </button>
            <button
              type="button"
              onClick={() => void exportPreview("csv")}
              disabled={busy !== null}
              className={buttonClass}
            >
              Exportar CSV
            </button>
            <button
              type="button"
              onClick={() => void exportPreview("xlsx")}
              disabled={busy !== null}
              className={buttonClass}
            >
              Exportar XLSX
            </button>
            <span className="text-xs text-[var(--color-muted)]">
              A tabela derivada guarda a origem e o hash do resultado. Exportação usa o mesmo cálculo da prévia.
            </span>
          </div>
        </div>
      ) : null}
    </div>
  );
}
