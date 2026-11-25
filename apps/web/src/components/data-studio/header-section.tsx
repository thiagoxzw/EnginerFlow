"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { errorText } from "@/components/data-studio/templates-section";
import { invalidateDataset } from "@/lib/invalidate";
import {
  applyOperation,
  metadataVersions,
  previewOperation,
  rawHead,
  type OperationPreview,
} from "@/lib/operations";
import { getDatasetState, type DatasetState } from "@/lib/templates";

const sectionClass =
  "rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4 space-y-3";
const buttonClass =
  "rounded-md border border-[var(--color-border)] px-3 py-2 text-sm hover:bg-[var(--color-border)] disabled:opacity-50";

export function HeaderSection({ datasetId }: { datasetId: string }) {
  const queryClient = useQueryClient();
  const raw = useQuery({
    queryKey: ["raw-head", datasetId],
    queryFn: () => rawHead(datasetId, 30),
  });
  const metas = useQuery({
    queryKey: ["metadata-versions", datasetId],
    queryFn: () => metadataVersions(datasetId),
  });
  const [pending, setPending] = useState<number | null>(null);
  const [preview, setPreview] = useState<{ row: number; result: OperationPreview; state: DatasetState } | null>(
    null,
  );
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const current = metas.data?.find((m) => m.is_current);
  const currentHeader = current?.header_row ?? null;

  async function makePreview(row: number) {
    setBusy(true);
    setMessage(null);
    try {
      const state = await getDatasetState(datasetId);
      const result = await previewOperation(datasetId, "set_header_row", { header_row: row }, state);
      setPreview({ row, result, state });
      setPending(null);
    } catch (error) {
      setMessage(errorText(error));
    } finally {
      setBusy(false);
    }
  }

  async function apply() {
    if (!preview) return;
    setBusy(true);
    setMessage(null);
    try {
      await applyOperation(datasetId, preview.result.preview_id, preview.state);
      setPreview(null);
      await invalidateDataset(queryClient, datasetId);
      setMessage(`Cabeçalho definido na linha ${preview.row}. Versões anteriores preservadas.`);
    } catch (error) {
      setPreview(null);
      setMessage(errorText(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={sectionClass} aria-labelledby="cabecalho">
      <h2 id="cabecalho" className="font-medium">
        Cabeçalho
      </h2>
      <p className="text-sm text-[var(--color-muted)]">
        {currentHeader === null
          ? "Cabeçalho detectado automaticamente."
          : `Cabeçalho atual: linha ${currentHeader}.`}{" "}
        Escolha a linha real do cabeçalho. A tabela é reconstruída do arquivo original.
      </p>

      {raw.isPending ? <p className="text-sm text-[var(--color-muted)]">Carregando linhas…</p> : null}
      {raw.isError ? (
        <p role="alert" className="text-sm text-[var(--color-danger)]">
          {errorText(raw.error)}
        </p>
      ) : null}

      {raw.data ? (
        <div className="max-h-80 overflow-auto rounded-md border border-[var(--color-border)]">
          <table className="w-full text-xs">
            <tbody>
              {raw.data.map((row) => (
                <tr
                  key={row.row_number}
                  className={`border-t border-[var(--color-border)] ${
                    row.row_number === currentHeader ? "bg-[var(--color-border)]" : ""
                  }`}
                >
                  <td className="px-2 py-1 text-[var(--color-muted)]">{row.row_number}</td>
                  {row.values.map((v, j) => (
                    <td key={j} className="whitespace-nowrap px-2 py-1 font-mono">
                      {v ?? ""}
                    </td>
                  ))}
                  <td className="px-2 py-1 text-right">
                    <button
                      type="button"
                      onClick={() => setPending(row.row_number)}
                      disabled={busy}
                      className={buttonClass}
                      aria-label={`Usar a linha ${row.row_number} como cabeçalho`}
                    >
                      Usar como cabeçalho
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {pending !== null ? (
        <div className="space-y-2 rounded-md border border-[var(--color-border)] p-3">
          <p className="text-sm">
            Reconstruir a tabela usando a linha {pending} como cabeçalho? Uma nova versão de dados é
            criada a partir do arquivo original. As versões anteriores continuam no histórico e podem
            ser desfeitas.
          </p>
          <div className="flex gap-2">
            <button type="button" onClick={() => void makePreview(pending)} disabled={busy} className={buttonClass}>
              Gerar prévia
            </button>
            <button type="button" onClick={() => setPending(null)} className={buttonClass}>
              Cancelar
            </button>
          </div>
        </div>
      ) : null}

      {preview ? (
        <div className="space-y-2 rounded-md border border-[var(--color-border)] p-3">
          <p className="text-sm">
            Prévia: {preview.result.rows_affected} linha(s) de dados com cabeçalho na linha {preview.row}.
          </p>
          <button type="button" onClick={() => void apply()} disabled={busy} className={buttonClass}>
            Aplicar cabeçalho
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
