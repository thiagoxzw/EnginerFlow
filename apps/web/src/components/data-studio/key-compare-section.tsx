"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { KeyPairsEditor, keysComplete, type KeyPair } from "@/components/data-studio/key-pairs";
import { errorText } from "@/components/data-studio/templates-section";
import { apiFetch } from "@/lib/api";
import { derivedNotice, type DatasetSummary } from "@/lib/datasets";

const inputClass = "rounded-md border border-[var(--color-border)] bg-transparent px-2 py-1 text-sm";
const buttonClass =
  "rounded-md border border-[var(--color-border)] px-3 py-2 text-sm hover:bg-[var(--color-border)] disabled:opacity-50";

const COMPARE_PATH = "/api/v1/crossing/compare";

export const COUNT_LABELS: Record<string, string> = {
  adicionado: "Adicionados (só na tabela de busca)",
  removido: "Removidos (só nesta tabela)",
  alterado: "Alterados (chave igual, colunas diferentes)",
  idêntico: "Idênticos",
  chaves_duplicadas_busca: "Chaves repetidas na tabela de busca",
  chaves_invalidas_esquerda: "Chaves inválidas nesta tabela",
  chaves_invalidas_direita: "Chaves inválidas na tabela de busca",
};

export interface ComparePreview {
  columns: string[];
  counts: Record<string, number>;
  sample: (string | null)[][];
  difference_rows: number;
}

interface CompareDerived {
  dataset_id: string;
  name: string;
  run_id: string;
  row_count: number;
  result_sha256: string;
}

/** Corpo do contrato. */
export function buildCompareBody(form: { leftId: string; rightId: string; keys: KeyPair[] }) {
  return {
    left_id: form.leftId,
    right_id: form.rightId,
    left_keys: form.keys.map((k) => k.left),
    right_keys: form.keys.map((k) => k.right),
  };
}

export function KeyCompareSection({
  leftId,
  leftColumns,
  datasets,
  onDerived,
}: {
  leftId: string;
  leftColumns: string[];
  datasets: DatasetSummary[];
  onDerived: (id: string, message: string) => void;
}) {
  const queryClient = useQueryClient();
  const others = datasets.filter((d) => d.id !== leftId);
  const [rightId, setRightId] = useState("");
  const [keys, setKeys] = useState<KeyPair[]>([{ left: leftColumns[0] ?? "", right: "" }]);
  const [preview, setPreview] = useState<ComparePreview | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const right = others.find((d) => d.id === rightId);
  const rightColumns = right?.columns ?? [];
  const ready = Boolean(rightId) && keysComplete(keys);

  async function runPreview() {
    setBusy("preview");
    setMessage(null);
    try {
      const result = await apiFetch<ComparePreview>(`${COMPARE_PATH}/preview`, {
        method: "POST",
        body: JSON.stringify(buildCompareBody({ leftId, rightId, keys })),
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
      const result = await apiFetch<CompareDerived>(`${COMPARE_PATH}/derive`, {
        method: "POST",
        body: JSON.stringify(buildCompareBody({ leftId, rightId, keys })),
      });
      await queryClient.invalidateQueries({ queryKey: ["datasets"] });
      setPreview(null);
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
        Compara as linhas pelas chaves escolhidas e mostra o que foi adicionado, removido ou alterado coluna a
        coluna. Colunas com o mesmo nome são comparadas; valores numéricos são comparados como decimais (1,50 = 1.5).
      </p>

      <div className="space-y-1">
        <label htmlFor="cp-right" className="block text-sm font-medium">
          Tabela de comparação
        </label>
        <select
          id="cp-right"
          value={rightId}
          onChange={(e) => {
            setRightId(e.target.value);
            setKeys((prev) => prev.map((k) => ({ ...k, right: "" })));
            setPreview(null);
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

      <KeyPairsEditor
        idPrefix="cp"
        legend="Chaves de comparação"
        keys={keys}
        onChange={(next) => {
          setKeys(next);
          setPreview(null);
        }}
        leftColumns={leftColumns}
        rightColumns={rightColumns}
        rightEnabled={Boolean(rightId)}
      />

      <div className="flex flex-wrap items-center gap-3">
        <button type="button" onClick={() => void runPreview()} disabled={!ready || busy !== null} className={buttonClass}>
          {busy === "preview" ? "Comparando…" : "Comparar"}
        </button>
        <p role="status" className="text-sm text-[var(--color-muted)]">
          {busy === "preview" ? "Comparando as linhas das duas tabelas…" : null}
          {busy === "derive" ? "Criando a tabela derivada…" : null}
        </p>
      </div>

      {message ? (
        <p role="alert" className="text-sm text-[var(--color-danger)]">
          {message}
        </p>
      ) : null}

      {preview ? (
        <div className="space-y-3 rounded-md border border-[var(--color-border)] p-3">
          <ul aria-label="Contagens da comparação" className="grid gap-1 text-sm sm:grid-cols-2">
            {Object.entries(COUNT_LABELS).map(([key, label]) => (
              <li key={key}>
                {label}: <strong>{preview.counts[key] ?? 0}</strong>
              </li>
            ))}
          </ul>

          {preview.difference_rows === 0 ? (
            <p className="text-sm">As tabelas são idênticas pelas chaves e colunas comparadas.</p>
          ) : (
            <>
              <div className="max-h-80 overflow-auto rounded-md border border-[var(--color-border)]">
                <table className="w-full text-xs">
                  <caption className="sr-only">Diferenças encontradas</caption>
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
                          <td key={j} className="whitespace-nowrap px-2 py-1 font-mono">
                            {v ?? ""}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {preview.difference_rows > preview.sample.length ? (
                <p className="text-xs text-[var(--color-muted)]">
                  Mostrando {preview.sample.length} de {preview.difference_rows} diferenças; a tabela derivada terá todas.
                </p>
              ) : null}
            </>
          )}

          <button type="button" onClick={() => void createDerived()} disabled={busy !== null} className={buttonClass}>
            Criar tabela de diferenças
          </button>
        </div>
      ) : null}
    </div>
  );
}
