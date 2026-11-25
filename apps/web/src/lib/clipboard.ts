/**
 * Área de transferência tabular (TSV, o formato que o Excel usa). Funções puras, sem efeitos.
 *
 * - Quebras de linha "\r\n" (Excel no Windows) e "\n" são aceitas; a última linha vazia é descartada.
 * - Célula vazia colada vira texto vazio. Desconhecido não existe em texto: não é colado.
 * - Zeros à esquerda são preservados: o texto é copiado sem conversão numérica.
 */

export const MAX_PASTE_CELLS = 5000;

/** Converte texto da área de transferência em matriz de células. */
export function parseTsv(text: string): string[][] {
  const lines = text.split(/\r?\n/);
  if (lines.length > 0 && lines[lines.length - 1] === "") lines.pop();
  return lines.map((line) => line.split("\t"));
}

/** Converte uma matriz de texto em TSV, pronto para a área de transferência. */
export function serializeTsv(rows: string[][]): string {
  return rows.map((row) => row.join("\t")).join("\n");
}

export interface CellTarget {
  rowNumber: number;
  rowIndex: number;
  colIndex: number;
}

export interface PasteCell {
  row_number: number;
  column: string;
  value: string;
}

export type PastePlan =
  | { ok: true; cells: PasteCell[]; rows: number; columns: number }
  | { ok: false; reason: string };

/**
 * Monta as atribuições de uma colagem a partir da célula de destino (canto superior esquerdo).
 * Só usa as linhas já carregadas na tela (`visibleRowNumbers`, na ordem exibida) e as colunas da tabela.
 * Nunca cola além dos limites: recusa antes de qualquer alteração e explica o motivo.
 */
export function planPaste(
  matrix: string[][],
  anchor: CellTarget,
  columns: string[],
  visibleRowNumbers: number[],
): PastePlan {
  if (matrix.length === 0) return { ok: false, reason: "A área de transferência não tem dados tabulares." };
  const width = Math.max(...matrix.map((row) => row.length));
  if (anchor.colIndex + width > columns.length) {
    return {
      ok: false,
      reason: `A colagem tem ${width} coluna(s), mas há só ${columns.length - anchor.colIndex} a partir da célula escolhida.`,
    };
  }
  const startRow = visibleRowNumbers.indexOf(anchor.rowNumber);
  if (startRow < 0 || startRow + matrix.length > visibleRowNumbers.length) {
    return {
      ok: false,
      reason: `A colagem tem ${matrix.length} linha(s), mas a página atual só tem ${visibleRowNumbers.length - startRow} a partir da célula escolhida. Mude a paginação e tente de novo.`,
    };
  }
  const cells: PasteCell[] = [];
  matrix.forEach((row, r) => {
    row.forEach((value, c) => {
      cells.push({
        row_number: visibleRowNumbers[startRow + r] ?? anchor.rowNumber,
        column: columns[anchor.colIndex + c] ?? "",
        value,
      });
    });
  });
  if (cells.length > MAX_PASTE_CELLS) {
    return {
      ok: false,
      reason: `A colagem tem ${cells.length} células. O limite por operação é ${MAX_PASTE_CELLS}.`,
    };
  }
  return { ok: true, cells, rows: matrix.length, columns: width };
}

/** Texto copiado: as linhas selecionadas (todas as colunas, na ordem exibida) ou a célula atual. */
export function copyText(
  focusValue: string | null,
  selectedRows: (string | null)[][],
): string {
  if (selectedRows.length > 0) {
    return serializeTsv(selectedRows.map((row) => row.map((v) => v ?? "")));
  }
  return focusValue ?? "";
}
