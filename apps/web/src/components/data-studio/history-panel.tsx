"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { errorText } from "@/components/data-studio/templates-section";
import { ApiError } from "@/lib/api";
import { invalidateDataset } from "@/lib/invalidate";
import { listOperations, listVersions, moveHistory } from "@/lib/operations";
import { getDatasetState } from "@/lib/templates";

const sectionClass =
  "card p-4 space-y-3";
const buttonClass =
  "rounded-md border border-[var(--color-border)] px-3 py-2 text-sm hover:bg-[var(--color-border)] disabled:opacity-50";

const OP_LABELS: Record<string, string> = {
  rename_column: "Renomear coluna",
  set_mapping: "Mapeamento",
  apply_mapping_template: "Aplicar modelo",
  set_header_row: "Cabeçalho",
  replace_text: "Substituir texto",
  set_rows_value: "Atualizar valores",
  delete_rows: "Excluir linhas",
};

/** Atalhos ignorados quando o foco está em campo de edição (não desfazer o texto digitado). */
export function isEditingField(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || Boolean(target.isContentEditable);
}

/** Mapeia a tecla para desfazer/refazer. Retorna null se não for atalho de histórico. */
export function historyShortcut(event: KeyboardEvent): "undo" | "redo" | null {
  if (!(event.ctrlKey || event.metaKey)) return null;
  const key = event.key.toLowerCase();
  if (key === "z" && !event.shiftKey) return "undo";
  if (key === "y" || (key === "z" && event.shiftKey)) return "redo";
  return null;
}

/** Desfazer/refazer com atalho de teclado. Fica na barra de ferramentas, sempre visível. */
export function UndoRedoControls({ datasetId }: { datasetId: string }) {
  const queryClient = useQueryClient();
  const operations = useQuery({
    queryKey: ["operations", datasetId],
    queryFn: () => listOperations(datasetId),
  });
  const versions = useQuery({
    queryKey: ["versions", datasetId],
    queryFn: () => listVersions(datasetId),
  });
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const applied = operations.data?.filter((o) => o.status === "applied") ?? [];
  const undone = operations.data?.filter((o) => o.status === "undone") ?? [];
  const currentNumber = versions.data?.find((v) => v.is_current)?.number;

  async function refreshAll() {
    await invalidateDataset(queryClient, datasetId);
  }

  async function move(direction: "undo" | "redo") {
    if (busy) return;
    setBusy(true);
    setMessage(null);
    try {
      const state = await getDatasetState(datasetId);
      await moveHistory(datasetId, direction, state);
      await refreshAll();
      setMessage(direction === "undo" ? "Operação desfeita." : "Operação refeita.");
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setMessage("A tabela mudou em outra sessão. A visualização foi atualizada; tente de novo.");
        await refreshAll();
      } else {
        setMessage(errorText(error));
      }
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (isEditingField(event.target)) return;
      const action = historyShortcut(event);
      if (action) {
        event.preventDefault();
        void move(action);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // move depende de datasetId e busy; reanexar o ouvinte é barato e mantém o estado atual.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId, busy]);

  return (
    <div className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        onClick={() => void move("undo")}
        disabled={busy || applied.length === 0}
        className={buttonClass}
      >
        Desfazer (Ctrl+Z)
      </button>
      <button
        type="button"
        onClick={() => void move("redo")}
        disabled={busy || undone.length === 0}
        className={buttonClass}
      >
        Refazer (Ctrl+Y)
      </button>
      {currentNumber !== undefined ? (
        <span className="text-sm text-[var(--color-muted)]">Versão atual: {currentNumber}</span>
      ) : null}
      {message ? (
        <span role="status" className="text-sm text-[var(--color-muted)]">
          {message}
        </span>
      ) : null}
    </div>
  );
}

/** Lista de operações e versões. Os controles de desfazer ficam na barra de ferramentas. */
export function HistoryList({ datasetId }: { datasetId: string }) {
  const operations = useQuery({
    queryKey: ["operations", datasetId],
    queryFn: () => listOperations(datasetId),
  });
  const versions = useQuery({
    queryKey: ["versions", datasetId],
    queryFn: () => listVersions(datasetId),
  });

  return (
    <section aria-label="Operações e versões" className="space-y-3">
      {operations.data && operations.data.length === 0 ? (
        <p className="text-sm text-[var(--color-muted)]">Nenhuma operação aplicada ainda.</p>
      ) : null}
      {operations.data && operations.data.length > 0 ? (
        <ol className="space-y-1 text-sm" aria-label="Operações aplicadas">
          {operations.data.map((op) => (
            <li
              key={op.id}
              className={op.status === "undone" ? "text-[var(--color-muted)] line-through" : ""}
            >
              #{op.seq} {OP_LABELS[op.code] ?? op.code} v{op.code_version} —{" "}
              {op.status === "undone" ? "desfeita" : "aplicada"}
              {op.rows_affected > 0 ? ` (${op.rows_affected} linha(s))` : ""}
            </li>
          ))}
        </ol>
      ) : null}

      {versions.data && versions.data.length > 0 ? (
        <p className="text-xs text-[var(--color-muted)]">
          Versões de dados mantidas: {versions.data.length}. Nenhuma versão é apagada.
        </p>
      ) : null}
    </section>
  );
}

/** Painel completo (controles + lista), mantido para uso isolado. */
export function HistoryPanel({ datasetId }: { datasetId: string }) {
  return (
    <section className={sectionClass} aria-labelledby="historico">
      <h2 id="historico" className="font-medium">
        Histórico
      </h2>
      <UndoRedoControls datasetId={datasetId} />
      <HistoryList datasetId={datasetId} />
    </section>
  );
}
