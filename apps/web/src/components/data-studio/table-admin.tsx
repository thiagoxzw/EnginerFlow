"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { errorText } from "@/components/data-studio/templates-section";
import { apiFetch } from "@/lib/api";
import type { DatasetSummary } from "@/lib/datasets";

const sectionClass =
  "card p-4 space-y-3";
const inputClass = "rounded-md border border-[var(--color-border)] bg-transparent px-3 py-2";
const buttonClass =
  "rounded-md border border-[var(--color-border)] px-3 py-2 text-sm hover:bg-[var(--color-border)] disabled:opacity-50";

export function renameTable(id: string, name: string): Promise<DatasetSummary> {
  return apiFetch<DatasetSummary>(`/api/v1/datasets/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

export function deleteTable(id: string, confirmName: string): Promise<DatasetSummary> {
  return apiFetch<DatasetSummary>(`/api/v1/datasets/${id}`, {
    method: "DELETE",
    body: JSON.stringify({ confirm_name: confirmName }),
  });
}

export function restoreTable(id: string): Promise<DatasetSummary> {
  return apiFetch<DatasetSummary>(`/api/v1/datasets/${id}/restore`, { method: "POST" });
}

export function listDeletedDatasets(): Promise<DatasetSummary[]> {
  return apiFetch<DatasetSummary[]>("/api/v1/datasets?deleted=true");
}

/** Renomear e excluir logicamente. A exclusão exige digitar o nome exato da tabela. */
export function TableAdminSection({
  datasetId,
  name,
  onDeleted,
}: {
  datasetId: string;
  name: string;
  onDeleted: () => void;
}) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState(name);
  const [confirm, setConfirm] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function rename() {
    setBusy(true);
    setMessage(null);
    try {
      await renameTable(datasetId, draft);
      await queryClient.invalidateQueries({ queryKey: ["datasets"] });
      await queryClient.invalidateQueries({ queryKey: ["dataset", datasetId] });
      setMessage("Nome atualizado.");
    } catch (error) {
      setMessage(errorText(error));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    setMessage(null);
    try {
      await deleteTable(datasetId, confirm);
      await queryClient.invalidateQueries({ queryKey: ["datasets"] });
      await queryClient.invalidateQueries({ queryKey: ["deleted-datasets"] });
      onDeleted();
    } catch (error) {
      setMessage(errorText(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={sectionClass} aria-labelledby="gerenciar">
      <h2 id="gerenciar" className="font-medium">
        Gerenciar tabela
      </h2>
      <div className="flex flex-wrap items-end gap-2">
        <div className="space-y-1">
          <label htmlFor="renomear" className="block text-sm">
            Nome
          </label>
          <input
            id="renomear"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            maxLength={255}
            className={inputClass}
          />
        </div>
        <button type="button" onClick={() => void rename()} disabled={busy || draft.trim() === ""} className={buttonClass}>
          Renomear
        </button>
      </div>

      <div className="space-y-2 rounded-md border border-[var(--color-border)] p-3">
        <p className="text-sm text-[var(--color-muted)]">
          Excluir ocultará a tabela e bloqueará operações nela. Nada é apagado: a tabela pode ser
          restaurada. Para confirmar, digite o nome exato: <strong>{name}</strong>
        </p>
        <div className="flex flex-wrap items-end gap-2">
          <input
            aria-label="Confirmar nome para excluir"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            className={inputClass}
          />
          <button
            type="button"
            onClick={() => void remove()}
            disabled={busy || confirm !== name}
            className={buttonClass}
          >
            Excluir tabela
          </button>
        </div>
      </div>

      {message ? (
        <p role="status" className="text-sm text-[var(--color-muted)]">
          {message}
        </p>
      ) : null}
    </section>
  );
}

/** Tabelas excluídas logicamente, com restauração. */
export function DeletedTablesSection() {
  const queryClient = useQueryClient();
  const deleted = useQuery({ queryKey: ["deleted-datasets"], queryFn: listDeletedDatasets });
  const [message, setMessage] = useState<string | null>(null);

  async function restore(id: string) {
    setMessage(null);
    try {
      await restoreTable(id);
      await queryClient.invalidateQueries({ queryKey: ["datasets"] });
      await queryClient.invalidateQueries({ queryKey: ["deleted-datasets"] });
      setMessage("Tabela restaurada.");
    } catch (error) {
      setMessage(errorText(error));
    }
  }

  return (
    <section className={sectionClass} aria-labelledby="excluidas">
      <h2 id="excluidas" className="font-medium">
        Tabelas excluídas
      </h2>
      {deleted.data && deleted.data.length === 0 ? (
        <p className="text-sm text-[var(--color-muted)]">Nenhuma tabela excluída.</p>
      ) : null}
      {deleted.data && deleted.data.length > 0 ? (
        <ul className="divide-y divide-[var(--color-border)]">
          {deleted.data.map((d) => (
            <li key={d.id} className="flex items-center justify-between gap-2 py-2">
              <span className="text-sm">{d.name}</span>
              <button type="button" onClick={() => void restore(d.id)} className={buttonClass}>
                Restaurar {d.name}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {message ? (
        <p role="status" className="text-sm text-[var(--color-muted)]">
          {message}
        </p>
      ) : null}
    </section>
  );
}
