"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { KeyPairsEditor, keysComplete, type KeyPair } from "@/components/data-studio/key-pairs";
import { errorText } from "@/components/data-studio/templates-section";
import { apiFetch } from "@/lib/api";
import { derivedNotice, newIdempotencyKey, type DatasetSummary } from "@/lib/datasets";

const inputClass = "rounded-md border border-[var(--color-border)] bg-transparent px-2 py-1 text-sm";
const buttonClass =
  "rounded-md border border-[var(--color-border)] px-3 py-2 text-sm hover:bg-[var(--color-border)] disabled:opacity-50";

const JOIN_PATH = "/api/v1/crossing/join";

export type JoinType = "inner" | "left" | "right" | "full";

export const JOIN_LABELS: Record<JoinType, string> = {
  inner: "Somente linhas com correspondência",
  left: "Todas as linhas desta tabela",
  right: "Todas as linhas da tabela de busca",
  full: "Todas as linhas das duas tabelas",
};

export const CARDINALITY_HELP: Record<string, string> = {
  "1:1": "Cada chave aparece no máximo uma vez nas duas tabelas.",
  "1:N": "Uma chave desta tabela aparece em várias linhas da tabela de busca.",
  "N:1": "Uma chave da tabela de busca aparece em várias linhas desta tabela.",
  "N:M": "A chave se repete nos dois lados: o resultado pode crescer muito.",
};

export interface JoinPreview {
  columns: string[];
  cardinality: string;
  left_rows: number;
  right_rows: number;
  matched_keys: number;
  matched_pairs: number;
  left_only_rows: number;
  right_only_rows: number;
  estimated_rows: number;
  notes: string[];
  sample: (string | null)[][];
}

export interface JoinDerived {
  dataset_id: string;
  name: string;
  run_id: string;
  row_count: number;
  result_sha256: string;
}

/** Corpo do contrato da API. */
export function buildJoinBody(form: {
  leftId: string;
  rightId: string;
  keys: KeyPair[];
  joinType: JoinType;
}) {
  return {
    left_id: form.leftId,
    right_id: form.rightId,
    left_keys: form.keys.map((k) => k.left),
    right_keys: form.keys.map((k) => k.right),
    join_type: form.joinType,
  };
}

/** Crescimento N:M exige confirmação explícita antes de criar a tabela. */
export function needsGrowthConfirmation(cardinality: string): boolean {
  return cardinality === "N:M";
}

export function JoinSection({
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
  const [joinType, setJoinType] = useState<JoinType>("inner");
  const [preview, setPreview] = useState<JoinPreview | null>(null);
  const [confirmGrowth, setConfirmGrowth] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  // Chave da derivação: nasce com a prévia e é reusada numa nova tentativa (sem duplicar).
  const [idem, setIdem] = useState(newIdempotencyKey);

  const right = others.find((d) => d.id === rightId);
  const rightColumns = right?.columns ?? [];
  const ready = Boolean(rightId) && keysComplete(keys);
  const growthBlocked = preview !== null && needsGrowthConfirmation(preview.cardinality) && !confirmGrowth;

  function invalidatePreview() {
    setPreview(null);
    setConfirmGrowth(false);
  }

  async function runPreview() {
    setBusy("preview");
    setIdem(newIdempotencyKey());
    setMessage(null);
    try {
      const result = await apiFetch<JoinPreview>(`${JOIN_PATH}/preview`, {
        method: "POST",
        body: JSON.stringify(buildJoinBody({ leftId, rightId, keys, joinType })),
      });
      setPreview(result);
      setConfirmGrowth(false);
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
      const result = await apiFetch<JoinDerived>(`${JOIN_PATH}/derive`, {
        method: "POST",
        headers: { "Idempotency-Key": idem },
        body: JSON.stringify(buildJoinBody({ leftId, rightId, keys, joinType })),
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
        Junta as duas tabelas pelas chaves escolhidas. A prévia mostra quantas linhas o resultado deve ter
        antes de criar a tabela. Nada é alterado nas tabelas de origem.
      </p>

      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-1">
          <label htmlFor="jn-right" className="block text-sm font-medium">
            Tabela de busca
          </label>
          <select
            id="jn-right"
            value={rightId}
            onChange={(e) => {
              setRightId(e.target.value);
              setKeys((prev) => prev.map((k) => ({ ...k, right: "" })));
              invalidatePreview();
            }}
            className={`${inputClass} w-full`}
          >
            <option value="">— escolher —</option>
            {others.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <label htmlFor="jn-type" className="block text-sm font-medium">
            Linhas no resultado
          </label>
          <select
            id="jn-type"
            value={joinType}
            onChange={(e) => {
              setJoinType(e.target.value as JoinType);
              invalidatePreview();
            }}
            className={`${inputClass} w-full`}
          >
            {(Object.keys(JOIN_LABELS) as JoinType[]).map((t) => (
              <option key={t} value={t}>
                {JOIN_LABELS[t]}
              </option>
            ))}
          </select>
        </div>
      </div>

      <KeyPairsEditor
        idPrefix="jn"
        legend="Chaves da junção"
        keys={keys}
        onChange={(next) => {
          setKeys(next);
          invalidatePreview();
        }}
        leftColumns={leftColumns}
        rightColumns={rightColumns}
        rightEnabled={Boolean(rightId)}
      />

      <div className="flex flex-wrap items-center gap-3">
        <button type="button" onClick={() => void runPreview()} disabled={!ready || busy !== null} className={buttonClass}>
          {busy === "preview" ? "Calculando…" : "Calcular prévia da junção"}
        </button>
      </div>

      <p role="status" className="text-sm text-[var(--color-muted)]">
        {busy === "preview" ? "Calculando a cardinalidade e as linhas estimadas…" : null}
        {busy === "derive" ? "Criando a tabela derivada…" : null}
      </p>

      {message ? (
        <p role="alert" className="text-sm text-[var(--color-danger)]">
          {message}
        </p>
      ) : null}

      {preview ? (
        <div className="space-y-3 rounded-md border border-[var(--color-border)] p-3">
          <section aria-label="Estimativas da junção" className="space-y-1 text-sm">
            <p>
              Cardinalidade: <strong>{preview.cardinality}</strong>{" "}
              <span className="text-[var(--color-muted)]">{CARDINALITY_HELP[preview.cardinality] ?? ""}</span>
            </p>
            <ul className="flex flex-wrap gap-x-4 gap-y-1">
              <li>Linhas nesta tabela: <strong>{preview.left_rows}</strong></li>
              <li>Linhas na tabela de busca: <strong>{preview.right_rows}</strong></li>
              <li>Chaves com correspondência: <strong>{preview.matched_keys}</strong></li>
              <li>Pares casados: <strong>{preview.matched_pairs}</strong></li>
              <li>Só nesta tabela: <strong>{preview.left_only_rows}</strong></li>
              <li>Só na tabela de busca: <strong>{preview.right_only_rows}</strong></li>
              <li>Linhas estimadas no resultado: <strong>{preview.estimated_rows}</strong></li>
            </ul>
            {preview.notes.map((note) => (
              <p key={note} className="text-xs text-[var(--color-muted)]">
                {note}
              </p>
            ))}
          </section>

          {needsGrowthConfirmation(preview.cardinality) ? (
            <label className="flex items-start gap-2 rounded-md bg-[var(--color-border)] p-2 text-sm">
              <input
                type="checkbox"
                checked={confirmGrowth}
                onChange={(e) => setConfirmGrowth(e.target.checked)}
                className="mt-1"
              />
              <span>
                Confirmo a junção N:M. O resultado pode ter cerca de <strong>{preview.estimated_rows}</strong> linhas.
              </span>
            </label>
          ) : null}

          <div className="max-h-80 overflow-auto rounded-md border border-[var(--color-border)]">
            <table className="w-full text-xs">
              <caption className="sr-only">Prévia da junção</caption>
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

          <button
            type="button"
            onClick={() => void createDerived()}
            disabled={busy !== null || growthBlocked}
            className={buttonClass}
          >
            Criar tabela derivada
          </button>
        </div>
      ) : null}
    </div>
  );
}
