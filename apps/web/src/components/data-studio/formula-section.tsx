"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { errorText } from "@/components/data-studio/templates-section";
import { apiFetch } from "@/lib/api";
import { derivedNotice, newIdempotencyKey } from "@/lib/datasets";

const inputClass = "rounded-md border border-[var(--color-border)] bg-transparent px-2 py-1 text-sm";
const buttonClass =
  "rounded-md border border-[var(--color-border)] px-3 py-2 text-sm hover:bg-[var(--color-border)] disabled:opacity-50";
const FORMULA_PATH = "/api/v1/crossing/formula";

export const SYNTAX_HELP = [
  "[Coluna] referencia uma coluna; números com vírgula ou ponto: 2,5 ou 2.5",
  "+ - * / com parênteses. Ex.: ([Qtd]+[Extra])*[Preço]",
  "SOMA(a;b) · MEDIA(a;b) · MIN(a;b) · MAX(a;b) · CONTAR(a;b)",
  'SE([Qtd]>3; "grande"; "pequeno") · comparações = <> < > <= >=',
  'CONCAT(a;"-";b) · MAIUSC(t) · MINUSC(t) · ESQUERDA(t;3) · DIREITA(t;2)',
];

interface FormulaPreview {
  columns: string[];
  rows: (string | null)[][];
  counts: Record<string, number>;
}

interface FormulaDerived {
  dataset_id: string;
  name: string;
  run_id: string;
  row_count: number;
  result_sha256: string;
}

export function FormulaSection({
  datasetId,
  columns,
  onDerived,
}: {
  datasetId: string;
  columns: string[];
  onDerived: (id: string, message: string) => void;
}) {
  const queryClient = useQueryClient();
  const [formula, setFormula] = useState("");
  const [newColumn, setNewColumn] = useState("");
  const [preview, setPreview] = useState<FormulaPreview | null>(null);
  const [idem, setIdem] = useState(newIdempotencyKey);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const body = () => ({ dataset_id: datasetId, formula, new_column: newColumn.trim() });
  const ready = formula.trim() !== "" && newColumn.trim() !== "";

  async function runPreview() {
    setBusy("preview");
    setMessage(null);
    setIdem(newIdempotencyKey());
    try {
      setPreview(
        await apiFetch<FormulaPreview>(`${FORMULA_PATH}/preview`, { method: "POST", body: JSON.stringify(body()) }),
      );
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
      // Mesma chave numa nova tentativa: a coluna calculada não é duplicada se a resposta se perder.
      const result = await apiFetch<FormulaDerived>(`${FORMULA_PATH}/derive`, {
        method: "POST",
        headers: { "Idempotency-Key": idem },
        body: JSON.stringify(body()),
      });
      await queryClient.invalidateQueries({ queryKey: ["datasets"] });
      setPreview(null);
      setIdem(newIdempotencyKey());
      onDerived(result.dataset_id, derivedNotice(result));
    } catch (error) {
      setMessage(errorText(error));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-[var(--color-muted)]">
        Cria uma nova tabela com uma coluna calculada por linha. A tabela atual não muda. Erros aparecem na célula
        (ex.: #VAZIO!, #DIV/0!) e são contados; nunca viram zero em silêncio.
      </p>

      <div className="grid gap-3 md:grid-cols-[1fr_16rem]">
        <div className="space-y-1">
          <label htmlFor="fx-formula" className="block text-sm font-medium">
            Fórmula
          </label>
          <input
            id="fx-formula"
            value={formula}
            onChange={(e) => {
              setFormula(e.target.value);
              setPreview(null);
            }}
            placeholder="[Qtd]*[Preço]"
            className={`${inputClass} w-full font-mono`}
          />
        </div>
        <div className="space-y-1">
          <label htmlFor="fx-name" className="block text-sm font-medium">
            Nome da nova coluna
          </label>
          <input
            id="fx-name"
            value={newColumn}
            onChange={(e) => {
              setNewColumn(e.target.value);
              setPreview(null);
            }}
            placeholder="Total"
            className={`${inputClass} w-full`}
          />
        </div>
      </div>

      <details className="text-xs text-[var(--color-muted)]">
        <summary className="cursor-pointer">Sintaxe suportada e colunas disponíveis</summary>
        <ul className="mt-2 list-inside list-disc space-y-1">
          {SYNTAX_HELP.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        <p className="mt-2">Colunas: {columns.join(", ")}</p>
      </details>

      <div className="flex flex-wrap items-center gap-3">
        <button type="button" onClick={() => void runPreview()} disabled={!ready || busy !== null} className={buttonClass}>
          {busy === "preview" ? "Calculando…" : "Gerar prévia"}
        </button>
        <p role="status" className="text-sm text-[var(--color-muted)]">
          {busy === "preview" ? "Calculando a fórmula nas linhas da tabela…" : null}
          {busy === "derive" ? "Criando a tabela com a coluna calculada…" : null}
        </p>
      </div>

      {message ? (
        <p role="alert" className="text-sm text-[var(--color-danger)]">
          {message}
        </p>
      ) : null}

      {preview ? (
        <div className="space-y-3 rounded-md border border-[var(--color-border)] p-3">
          <p className="text-sm">
            Erros explícitos nas linhas: <strong>{preview.counts.erros ?? 0}</strong> de{" "}
            <strong>{preview.counts.linhas_lidas ?? 0}</strong>. Prévia das primeiras 50 linhas.
          </p>
          <div className="max-h-80 overflow-auto rounded-md border border-[var(--color-border)]">
            <table className="w-full text-xs">
              <caption className="sr-only">Prévia da coluna calculada</caption>
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
                {preview.rows.map((row, i) => (
                  <tr key={i} className="border-t border-[var(--color-border)]">
                    {row.map((v, j) => (
                      <td key={j} className={`whitespace-nowrap px-2 py-1 font-mono ${v?.startsWith("#") ? "text-[var(--color-danger)]" : ""}`}>
                        {v ?? ""}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button type="button" onClick={() => void createDerived()} disabled={busy !== null} className={buttonClass}>
            Criar tabela com a coluna calculada
          </button>
        </div>
      ) : null}
    </div>
  );
}
