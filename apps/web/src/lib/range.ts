import type { PasteCell } from "@/lib/clipboard";

/** Posição de uma célula na página atual: índice da linha exibida e índice da coluna. */
export interface CellPos {
  rowIndex: number;
  colIndex: number;
}

/** Intervalo retangular de células. Anchor é onde começou a seleção; focus é a ponta móvel. */
export interface CellRange {
  anchor: CellPos;
  focus: CellPos;
}

/** Limites normalizados (menor e maior) do intervalo, independentemente da direção da seleção. */
export function normalizeRange(range: CellRange): { r0: number; r1: number; c0: number; c1: number } {
  return {
    r0: Math.min(range.anchor.rowIndex, range.focus.rowIndex),
    r1: Math.max(range.anchor.rowIndex, range.focus.rowIndex),
    c0: Math.min(range.anchor.colIndex, range.focus.colIndex),
    c1: Math.max(range.anchor.colIndex, range.focus.colIndex),
  };
}

export function rangeContains(range: CellRange | null, rowIndex: number, colIndex: number): boolean {
  if (!range) return false;
  const { r0, r1, c0, c1 } = normalizeRange(range);
  return rowIndex >= r0 && rowIndex <= r1 && colIndex >= c0 && colIndex <= c1;
}

/**
 * Move a ponta do intervalo (Shift+setas), mantendo a âncora. Fica dentro da página e das colunas
 * visíveis: nunca seleciona uma célula que não está na tela.
 */
export function extendRange(
  range: CellRange,
  rowDelta: number,
  colDelta: number,
  maxRowIndex: number,
  maxColIndex: number,
): CellRange {
  const focus: CellPos = {
    rowIndex: clamp(range.focus.rowIndex + rowDelta, 0, maxRowIndex),
    colIndex: clamp(range.focus.colIndex + colDelta, 0, maxColIndex),
  };
  return { anchor: range.anchor, focus };
}

/**
 * Atribuições para limpar o intervalo: uma por célula visível. Colunas ocultas ficam de fora, para
 * não alterar nada que o usuário não está vendo. Não grava nada fora da página exibida.
 */
export function clearRangeCells(
  range: CellRange,
  rows: { row_number: number }[],
  columns: string[],
  hidden: Set<string>,
): PasteCell[] {
  const { r0, r1, c0, c1 } = normalizeRange(range);
  const cells: PasteCell[] = [];
  for (let r = r0; r <= r1; r += 1) {
    const row = rows[r];
    if (!row) continue;
    for (let c = c0; c <= c1; c += 1) {
      const column = columns[c];
      if (column === undefined || hidden.has(column)) continue;
      cells.push({ row_number: row.row_number, column, value: "" });
    }
  }
  return cells;
}

/** Seleção de todas as células visíveis da página (Ctrl+A). */
export function pageRange(rowCount: number, colCount: number): CellRange | null {
  if (rowCount <= 0 || colCount <= 0) return null;
  return { anchor: { rowIndex: 0, colIndex: 0 }, focus: { rowIndex: rowCount - 1, colIndex: colCount - 1 } };
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
