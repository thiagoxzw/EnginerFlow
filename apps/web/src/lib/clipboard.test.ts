import { describe, expect, it } from "vitest";

import { copyText, parseTsv, planPaste, serializeTsv, MAX_PASTE_CELLS } from "@/lib/clipboard";

const COLUMNS = ["SYN-Código", "SYN-Descrição", "Qtd"];
const ROWS = [2, 3, 5, 7];

describe("parseTsv", () => {
  it("aceita quebras de linha do Excel (CRLF) e descarta a última linha vazia", () => {
    expect(parseTsv("007\tPorca\r\n0010\tArruela\r\n")).toEqual([
      ["007", "Porca"],
      ["0010", "Arruela"],
    ]);
  });

  it("preserva zeros à esquerda e células vazias", () => {
    expect(parseTsv("00123\t\t0")).toEqual([["00123", "", "0"]]);
  });
});

describe("TSV compatível com o Excel", () => {
  it("lê campo entre aspas com tabulação, quebra de linha e aspas escapadas", () => {
    const text = 'a\t"x\ty"\t"linha 1\r\nlinha 2"\n"diz ""oi"""\tfim\n';
    expect(parseTsv(text)).toEqual([
      ["a", "x\ty", "linha 1\r\nlinha 2"],
      ['diz "oi"', "fim"],
    ]);
  });

  it("aspa no meio de um campo sem aspas de abertura é texto comum", () => {
    expect(parseTsv('ab"c\td')).toEqual([['ab"c', "d"]]);
  });

  it("ida e volta preserva tabulação, quebra, aspa e vazio", () => {
    const matrix = [
      ["com\ttab", 'com "aspas"', "com\nquebra"],
      ["", "007", "x\r\ny"],
    ];
    expect(parseTsv(serializeTsv(matrix))).toEqual(matrix);
  });

  it("célula sem caracteres especiais continua sem aspas", () => {
    expect(serializeTsv([["a", "b"]])).toBe("a\tb");
  });

  it("texto vazio não gera linhas e quebra final não gera linha extra", () => {
    expect(parseTsv("")).toEqual([]);
    expect(parseTsv("a\n")).toEqual([["a"]]);
  });
});

describe("serializeTsv", () => {
  it("gera TSV que volta igual ao ser lido", () => {
    const matrix = [
      ["00123", "SYN parafuso"],
      ["", "x"],
    ];
    expect(parseTsv(serializeTsv(matrix))).toEqual(matrix);
  });
});

describe("planPaste", () => {
  it("monta as atribuições a partir da célula de destino, na ordem da página", () => {
    const plan = planPaste([["A", "B"], ["C", "D"]], { rowNumber: 3, rowIndex: 1, colIndex: 1 }, COLUMNS, ROWS);
    expect(plan).toEqual({
      ok: true,
      rows: 2,
      columns: 2,
      cells: [
        { row_number: 3, column: "SYN-Descrição", value: "A" },
        { row_number: 3, column: "Qtd", value: "B" },
        { row_number: 5, column: "SYN-Descrição", value: "C" },
        { row_number: 5, column: "Qtd", value: "D" },
      ],
    });
  });

  it("recusa colagem que passa das colunas da tabela, sem gerar alterações", () => {
    const plan = planPaste([["a", "b"]], { rowNumber: 2, rowIndex: 0, colIndex: 2 }, COLUMNS, ROWS);
    expect(plan.ok).toBe(false);
  });

  it("recusa colagem que passa das linhas da página atual", () => {
    const plan = planPaste([["a"], ["b"], ["c"]], { rowNumber: 7, rowIndex: 3, colIndex: 0 }, COLUMNS, ROWS);
    expect(plan.ok).toBe(false);
  });

  it("recusa área de transferência sem dados", () => {
    expect(planPaste([], { rowNumber: 2, rowIndex: 0, colIndex: 0 }, COLUMNS, ROWS).ok).toBe(false);
  });

  it("recusa colagem acima do limite por operação", () => {
    const big = Array.from({ length: 1000 }, () => ["x", "x", "x", "x", "x", "x"]);
    const rowsList = Array.from({ length: 1000 }, (_, i) => i + 2);
    const columns = ["a", "b", "c", "d", "e", "f"];
    const plan = planPaste(big, { rowNumber: 2, rowIndex: 0, colIndex: 0 }, columns, rowsList);
    expect(MAX_PASTE_CELLS).toBe(5000);
    expect(plan.ok).toBe(false);
  });
});

describe("copyText", () => {
  it("copia a célula atual quando não há linhas selecionadas", () => {
    expect(copyText("00123", [])).toBe("00123");
    expect(copyText(null, [])).toBe("");
  });

  it("célula única com tabulação, quebra ou aspa sai entre aspas, como no Excel", () => {
    expect(copyText('diz "oi"\tali', [])).toBe('"diz ""oi""\tali"');
    expect(parseTsv(copyText("x\r\ny", []))).toEqual([["x\r\ny"]]);
  });

  it("copia as linhas selecionadas em TSV, mantendo o texto original", () => {
    expect(
      copyText("ignorado", [
        ["007", null, "Porca"],
        ["", "x", "0"],
      ]),
    ).toBe("007\t\tPorca\n\tx\t0");
  });
});
