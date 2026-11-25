"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState, type KeyboardEvent } from "react";

import { CellValue } from "@/components/data-studio/cell-value";
import type { PasteCell } from "@/lib/clipboard";
import { errorText } from "@/components/data-studio/templates-section";
import { invalidateDataset } from "@/lib/invalidate";
import { applyOperation, previewOperation } from "@/lib/operations";
import { getDatasetState } from "@/lib/templates";

/**
 * Grava um valor em UMA célula pelo mesmo mecanismo das demais alterações: prévia, aplicação e
 * registro no histórico. Por isso a alteração pode ser desfeita (Ctrl+Z) e não altera outras linhas.
 */
export async function commitCellValue(
  datasetId: string,
  rowNumber: number,
  column: string,
  value: string,
): Promise<void> {
  const state = await getDatasetState(datasetId);
  const preview = await previewOperation(
    datasetId,
    "set_rows_value",
    { row_numbers: [rowNumber], column, value },
    state,
  );
  await applyOperation(datasetId, preview.preview_id, state);
}

/** Grava várias células numa única operação (colagem): uma entrada no histórico, desfeita de uma vez. */
export async function commitCells(datasetId: string, cells: PasteCell[]): Promise<void> {
  const state = await getDatasetState(datasetId);
  const preview = await previewOperation(datasetId, "set_cells", { cells }, state);
  await applyOperation(datasetId, preview.preview_id, state);
}

/** Texto inicial da edição: vazio e desconhecido começam em branco (a diferença fica visível na exibição). */
export function editableText(value: string | null): string {
  return value ?? "";
}

/** Move o foco para a célula vizinha, dentro da mesma tabela. Retorna true se houve destino. */
export function focusNeighbor(cell: HTMLElement, rowDelta: number, colDelta: number): boolean {
  const table = cell.closest("table");
  if (!table) return false;
  const row = Number(cell.dataset.rowIndex);
  const col = Number(cell.dataset.colIndex);
  const target = table.querySelector<HTMLElement>(
    `[data-cell="1"][data-row-index="${row + rowDelta}"][data-col-index="${col + colDelta}"]`,
  );
  if (!target) return false;
  target.focus();
  return true;
}

export interface RangeHandlers {
  inRange: boolean;
  /** Clique: seleciona a célula; com Shift, estende o intervalo a partir da âncora. */
  onPointer: (rowIndex: number, colIndex: number, shift: boolean) => void;
  /** Shift+seta: move a ponta do intervalo. */
  onExtend: (rowDelta: number, colDelta: number) => void;
  /** Delete/Backspace: limpa o intervalo selecionado (uma operação, desfazível). */
  onClear: () => void;
}

export function EditableCell({
  datasetId,
  rowNumber,
  rowIndex,
  colIndex,
  column,
  value,
  range,
}: {
  datasetId: string;
  rowNumber: number;
  rowIndex: number;
  colIndex: number;
  column: string;
  value: string | null;
  range: RangeHandlers;
}) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function start() {
    setDraft(editableText(value));
    setError(null);
    setEditing(true);
  }

  async function commit(next: string) {
    setEditing(false);
    // Enter sem mudança não grava nada: nenhuma linha é alterada à toa.
    if (next === editableText(value)) return;
    setSaving(true);
    try {
      await commitCellValue(datasetId, rowNumber, column, next);
      await invalidateDataset(queryClient, datasetId);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setSaving(false);
    }
  }

  function onCellKey(event: KeyboardEvent<HTMLTableCellElement>) {
    if (editing) return;
    if (event.key === "Enter" || event.key === "F2") {
      event.preventDefault();
      start();
      return;
    }
    if (event.key === "Delete" || event.key === "Backspace") {
      event.preventDefault();
      range.onClear();
      return;
    }
    const moves: Record<string, [number, number]> = {
      ArrowUp: [-1, 0],
      ArrowDown: [1, 0],
      ArrowLeft: [0, -1],
      ArrowRight: [0, 1],
    };
    const move = moves[event.key];
    if (move) {
      event.preventDefault();
      if (event.shiftKey) {
        range.onExtend(move[0], move[1]);
        return;
      }
      // Seta sem Shift: a seleção volta a ser só esta célula e o foco anda para o vizinho.
      range.onPointer(rowIndex, colIndex, false);
      focusNeighbor(event.currentTarget, move[0], move[1]);
    }
  }

  function onInputKey(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") {
      event.preventDefault();
      void commit(draft);
    } else if (event.key === "Escape") {
      event.preventDefault();
      setEditing(false);
    } else if (event.key === "Tab") {
      event.preventDefault();
      void commit(draft).then(() => focusNeighbor(event.currentTarget.closest("td") as HTMLElement, 0, 1));
    }
  }

  return (
    <td
      data-cell="1"
      data-row-index={rowIndex}
      data-col-index={colIndex}
      tabIndex={0}
      aria-label={`${column}, linha ${rowNumber}`}
      onMouseDown={(e) => range.onPointer(rowIndex, colIndex, e.shiftKey)}
      onDoubleClick={() => !saving && start()}
      onKeyDown={onCellKey}
      data-in-range={range.inRange ? "1" : undefined}
      className={`px-2 py-1 text-xs focus:outline-2 focus:outline-[var(--color-accent)] ${
        range.inRange ? "bg-[var(--color-selection,rgba(59,130,246,0.18))]" : ""
      }`}
    >
      {editing ? (
        <input
          autoFocus
          aria-label={`Editar ${column} da linha ${rowNumber}`}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onInputKey}
          onBlur={() => setEditing(false)}
          className="w-full min-w-24 rounded border border-[var(--color-accent)] bg-transparent px-1 py-0.5 font-mono"
        />
      ) : (
        <CellValue value={value} />
      )}
      {saving ? <span className="ml-1 text-[var(--color-muted)]">gravando…</span> : null}
      {error ? (
        <span role="alert" className="ml-1 text-[var(--color-danger)]">
          {error}
        </span>
      ) : null}
    </td>
  );
}
