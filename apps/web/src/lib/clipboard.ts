/**
 * Área de transferência tabular (TSV, o formato que o Excel usa). Funções puras, sem efeitos.
 *
 * - Quebras de linha "\r\n" (Excel no Windows) e "\n" são aceitas; a última linha vazia é descartada.
 * - Célula vazia colada vira texto vazio. Desconhecido não existe em texto: não é colado.
 * - Zeros à esquerda são preservados: o texto é copiado sem conversão numérica.
 */

export const MAX_PASTE_CELLS = 5000;

/**
 * Converte texto da área de transferência em matriz de células, como o Excel faz:
 * - Campo entre aspas pode conter tabulação, quebra de linha e aspas (escritas como "").
 * - Fora de aspas, tabulação separa células e CRLF ou LF separam linhas.
 * - A última linha vazia (quebra final) é descartada.
 */
export function parseTsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let quoted = false;
  let i = 0;
  let atFieldStart = true;
  while (i < text.length) {
    const ch = text[i] as string;
    if (quoted) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i += 2;
          continue;
        }
        quoted = false;
        i += 1;
        continue;
      }
      field += ch;
      i += 1;
      continue;
    }
    if (ch === '"' && atFieldStart && field === "") {
      quoted = true;
      atFieldStart = false;
      i += 1;
      continue;
    }
    if (ch === "\t") {
      row.push(field);
      field = "";
      atFieldStart = true;
      i += 1;
      continue;
    }
    if (ch === "\r" || ch === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
      atFieldStart = true;
      i += ch === "\r" && text[i + 1] === "\n" ? 2 : 1;
      continue;
    }
    field += ch;
    atFieldStart = false;
    i += 1;
  }
  // Fim do texto: fecha a última célula. Quebra final não gera linha vazia extra.
  if (field !== "" || row.length > 0 || atFieldStart === false) {
    row.push(field);
    rows.push(row);
  }
  return rows;
}

/** Célula em formato TSV: entre aspas (com aspas duplicadas) quando contém tabulação, quebra ou aspa. */
function tsvField(value: string): string {
  return /["\t\r\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

/** Converte uma matriz de texto em TSV, pronto para a área de transferência do Excel. */
export function serializeTsv(rows: string[][]): string {
  return rows.map((row) => row.map(tsvField).join("\t")).join("\n");
}

export interface CellTarget {
  rowNumber: number;
  rowIndex: number;
  colIndex: number;
}

export interface PasteCell {
  row_number: number;
  column: string;
  /** Texto, vazio ("") ou desconhecido (null). Colagens vindas do TSV são sempre texto. */
  value: string | null;
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
  // Célula única usa o mesmo formato TSV das demais: tabulação, quebra e aspa ficam entre aspas.
  return serializeTsv([[focusValue ?? ""]]);
}
