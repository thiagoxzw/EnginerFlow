"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { errorText } from "@/components/data-studio/templates-section";
import { applyOperation, previewOperation, type OperationPreview } from "@/lib/operations";
import { getDatasetState, type DatasetState } from "@/lib/templates";

const sectionClass =
  "rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4 space-y-3";
const inputClass = "rounded-md border border-[var(--color-border)] bg-transparent px-2 py-1 text-sm";
const buttonClass =
  "rounded-md border border-[var(--color-border)] px-3 py-2 text-sm hover:bg-[var(--color-border)] disabled:opacity-50";

interface Pending {
  kind: "set" | "delete";
  preview: OperationPreview;
  state: DatasetState;
}

/** Valor para atualização em lote. "unknown" grava desconhecido (null); "empty" grava "". */
export function valueFromMode(mode: "text" | "empty" | "unknown", text: string): string | null {
  if (mode === "unknown") return null;
  if (mode === "empty") return "";
  return text;
}

export function RowActions({
  datasetId,
  columns,
  selected,
  scopeLabel,
  onApplied,
}: {
  datasetId: string;
  columns: string[];
  selected: number[];
  scopeLabel: string;
  onApplied?: () => void;
}) {
  const queryClient = useQueryClient();
  const [column, setColumn] = useState(columns[0] ?? "");
  const [mode, setMode] = useState<"text" | "empty" | "unknown">("text");
  const [text, setText] = useState("");
  const [pending, setPending] = useState<Pending | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(kind: Pending["kind"]) {
    if (selected.length === 0) return;
    setBusy(true);
    setMessage(null);
    try {
      const state = await getDatasetState(datasetId);
      const params =
        kind === "set"
          ? { row_numbers: selected, column, value: valueFromMode(mode, text) }
          : { row_numbers: selected };
      const preview = await previewOperation(
        datasetId,
        kind === "set" ? "set_rows_value" : "delete_rows",
        params,
        state,
      );
      setPending({ kind, preview, state });
    } catch (error) {
      setMessage(errorText(error));
    } finally {
      setBusy(false);
    }
  }

  async function apply() {
    if (!pending) return;
    setBusy(true);
    setMessage(null);
    try {
      await applyOperation(datasetId, pending.preview.preview_id, pending.state);
      const done = pending.kind === "delete" ? "Linhas excluídas logicamente." : "Valores atualizados.";
      setPending(null);
      await queryClient.invalidateQueries({ queryKey: ["rows", datasetId] });
      await queryClient.invalidateQueries({ queryKey: ["dataset", datasetId] });
      setMessage(`${done} Desfazer disponível no histórico.`);
      onApplied?.();
    } catch (error) {
      setPending(null);
      setMessage(errorText(error));
    } finally {
      setBusy(false);
    }
  }

  const hasSelection = selected.length > 0;

  return (
    <section className={sectionClass} aria-labelledby="acoes-linhas">
      <h2 id="acoes-linhas" className="font-medium">
        Ações nas linhas selecionadas
      </h2>
      <p className="text-sm text-[var(--color-muted)]">
        {hasSelection
          ? `${selected.length} linha(s) selecionada(s) — ${scopeLabel}.`
          : "Nenhuma linha selecionada."}
      </p>

      <div className="flex flex-wrap items-end gap-2 text-sm">
        <select
          aria-label="Coluna para atualizar"
          value={column}
          onChange={(e) => setColumn(e.target.value)}
          className={inputClass}
        >
          {columns.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <select
          aria-label="Tipo de valor"
          value={mode}
          onChange={(e) => setMode(e.target.value as "text" | "empty" | "unknown")}
          className={inputClass}
        >
          <option value="text">Texto</option>
          <option value="empty">Vazio</option>
          <option value="unknown">Desconhecido</option>
        </select>
        {mode === "text" ? (
          <input
            aria-label="Novo valor"
            value={text}
            onChange={(e) => setText(e.target.value)}
            className={inputClass}
          />
        ) : null}
        <button
          type="button"
          onClick={() => void run("set")}
          disabled={!hasSelection || busy || (mode === "text" && text === "")}
          className={buttonClass}
        >
          Atualizar valor
        </button>
        <button
          type="button"
          onClick={() => void run("delete")}
          disabled={!hasSelection || busy}
          className={buttonClass}
        >
          Excluir linhas
        </button>
      </div>

      {pending ? (
        <div className="space-y-2 rounded-md border border-[var(--color-border)] p-3">
          <p className="text-sm">
            {pending.kind === "delete"
              ? `Excluir ${pending.preview.rows_affected} linha(s)? Elas saem desta versão e continuam no histórico; pode ser desfeito.`
              : `Atualizar ${pending.preview.cells_changed} célula(s) em “${column}”?`}
          </p>
          <button type="button" onClick={() => void apply()} disabled={busy} className={buttonClass}>
            Confirmar
          </button>
          <button type="button" onClick={() => setPending(null)} className={buttonClass}>
            Cancelar
          </button>
        </div>
      ) : null}

      {message ? (
        <p role="status" className="text-sm text-[var(--color-muted)]">
          {message}
        </p>
      ) : null}
    </section>
  );
}
