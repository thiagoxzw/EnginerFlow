"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { CANONICAL_FIELDS, FIELD_LABELS, type CanonicalField } from "@/lib/datasets";
import { invalidateDataset } from "@/lib/invalidate";
import {
  applyPreview,
  createTemplate,
  getDatasetState,
  listTemplates,
  previewTemplate,
  type Template,
  type TemplateMapping,
  type TemplatePreview,
  updateTemplate,
} from "@/lib/templates";

const sectionClass =
  "rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4 space-y-3";
const inputClass = "rounded-md border border-[var(--color-border)] bg-transparent px-3 py-2";
const buttonClass =
  "rounded-md border border-[var(--color-border)] px-3 py-2 text-sm hover:bg-[var(--color-border)] disabled:opacity-50";

export function errorText(error: unknown): string {
  return error instanceof Error ? error.message : "Erro inesperado.";
}

/** Converte o formulário em mapeamento: campos vazios não são enviados. */
export function cleanTemplateMapping(form: Record<string, string>): TemplateMapping {
  const out: TemplateMapping = {};
  for (const field of CANONICAL_FIELDS) {
    const value = (form[field] ?? "").trim();
    if (value) {
      out[field] = value;
    }
  }
  return out;
}

export function TemplatesSection({
  datasetId,
  onApplied,
}: {
  datasetId: string;
  onApplied: () => void;
}) {
  const queryClient = useQueryClient();
  const templates = useQuery({ queryKey: ["templates"], queryFn: listTemplates });
  const [selectedId, setSelectedId] = useState<string>("");
  const [name, setName] = useState("");
  const [form, setForm] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<TemplatePreview | null>(null);
  const [previewState, setPreviewState] = useState<Awaited<ReturnType<typeof getDatasetState>> | null>(
    null,
  );
  const [confirmPartial, setConfirmPartial] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const selected: Template | undefined = templates.data?.find((t) => t.id === selectedId);

  function loadIntoForm(template: Template | undefined) {
    setName(template?.name ?? "");
    const next: Record<string, string> = {};
    for (const field of CANONICAL_FIELDS) {
      next[field] = template?.mapping[field] ?? "";
    }
    setForm(next);
    setPreview(null);
    setPreviewState(null);
    setConfirmPartial(false);
  }

  async function save() {
    setBusy(true);
    setMessage(null);
    try {
      const mapping = cleanTemplateMapping(form);
      const saved = selected
        ? await updateTemplate(selected.id, { name, mapping })
        : await createTemplate(name, mapping);
      await queryClient.invalidateQueries({ queryKey: ["templates"] });
      setSelectedId(saved.id);
      setMessage(
        selected
          ? `Modelo atualizado (definição v${saved.definition_version}).`
          : `Modelo criado (definição v${saved.definition_version}).`,
      );
    } catch (error) {
      setMessage(errorText(error));
    } finally {
      setBusy(false);
    }
  }

  async function runPreview(allowMissing: boolean) {
    if (!selected) return;
    setBusy(true);
    setMessage(null);
    try {
      const state = await getDatasetState(datasetId);
      const result = await previewTemplate(datasetId, selected.id, state, allowMissing);
      setPreview(result);
      setPreviewState(state);
      if (result.preview_id === null) {
        setMessage("Há colunas do modelo que não existem nesta tabela. Confirme para continuar.");
      }
    } catch (error) {
      setMessage(errorText(error));
      setPreview(null);
    } finally {
      setBusy(false);
    }
  }

  async function apply() {
    if (!preview?.preview_id || !previewState) return;
    setBusy(true);
    setMessage(null);
    try {
      await applyPreview(datasetId, preview.preview_id, previewState);
      setPreview(null);
      setPreviewState(null);
      setConfirmPartial(false);
      await invalidateDataset(queryClient, datasetId);
      setMessage("Modelo aplicado. O histórico anterior foi preservado.");
      onApplied();
    } catch (error) {
      setMessage(errorText(error));
      setPreview(null);
      setPreviewState(null);
    } finally {
      setBusy(false);
    }
  }

  const missing = preview ? Object.entries(preview.missing_fields) : [];

  return (
    <section className={sectionClass} aria-labelledby="modelos">
      <h2 id="modelos" className="font-medium">
        Modelos de mapeamento
      </h2>

      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1">
          <label htmlFor="tpl-select" className="block text-sm font-medium">
            Modelo
          </label>
          <select
            id="tpl-select"
            value={selectedId}
            onChange={(e) => {
              setSelectedId(e.target.value);
              loadIntoForm(templates.data?.find((t) => t.id === e.target.value));
            }}
            className={inputClass}
          >
            <option value="">— novo modelo —</option>
            {(templates.data ?? []).map((t) => (
              <option key={t.id} value={t.id}>
                {t.name} (v{t.definition_version})
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <label htmlFor="tpl-name" className="block text-sm font-medium">
            Nome
          </label>
          <input
            id="tpl-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={inputClass}
            maxLength={120}
          />
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {CANONICAL_FIELDS.map((field: CanonicalField) => (
          <div key={field} className="space-y-1">
            <label htmlFor={`tpl-${field}`} className="block text-sm font-medium">
              {FIELD_LABELS[field]}
            </label>
            <input
              id={`tpl-${field}`}
              value={form[field] ?? ""}
              placeholder="nome da coluna"
              onChange={(e) => setForm((prev) => ({ ...prev, [field]: e.target.value }))}
              className={`${inputClass} w-full`}
            />
          </div>
        ))}
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void save()}
          disabled={busy || name.trim() === ""}
          className={buttonClass}
        >
          {selected ? "Salvar alterações do modelo" : "Criar modelo"}
        </button>
        <button
          type="button"
          onClick={() => void runPreview(false)}
          disabled={busy || !selected}
          className={buttonClass}
        >
          Pré-visualizar aplicação
        </button>
      </div>

      {selected ? (
        <p className="text-sm text-[var(--color-muted)]">
          Definição atual: v{selected.definition_version}.
        </p>
      ) : null}

      {preview ? (
        <div className="space-y-2 rounded-md border border-[var(--color-border)] p-3">
          <p className="text-sm">
            Prévia do modelo “{selected?.name}” (definição v{preview.definition_version}).
          </p>
          {missing.length > 0 ? (
            <div className="space-y-2">
              <p role="alert" className="text-sm text-[var(--color-danger)]">
                Colunas ausentes nesta tabela:{" "}
                {missing.map(([field, column]) => `${FIELD_LABELS[field as CanonicalField]} → “${column}”`).join(", ")}
              </p>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={confirmPartial}
                  onChange={(e) => setConfirmPartial(e.target.checked)}
                />
                Confirmo a aplicação parcial: campos ausentes ficam sem mapeamento.
              </label>
              <button
                type="button"
                onClick={() => void runPreview(true)}
                disabled={busy || !confirmPartial}
                className={buttonClass}
              >
                Gerar prévia com confirmação
              </button>
            </div>
          ) : null}
          {preview.preview_id ? (
            <button type="button" onClick={() => void apply()} disabled={busy} className={buttonClass}>
              Aplicar modelo
            </button>
          ) : null}
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
