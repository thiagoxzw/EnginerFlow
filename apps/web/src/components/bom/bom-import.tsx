"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { BOM_FIELDS, createBomStructure, previewBom, type BomMode, type BomPreview } from "@/lib/bom";
import { listDatasets, type DatasetSummary } from "@/lib/datasets";
import { errorText } from "@/components/data-studio/templates-section";

const inputClass = "rounded-md border border-[var(--color-border)] bg-transparent px-2 py-1 text-sm";
const buttonClass = "rounded-md border border-[var(--color-border)] px-3 py-1 text-sm disabled:opacity-50";

/** Palavras-chave para sugerir a coluna de cada campo. A sugestão é editável; nada é gravado sem confirmação. */
const HINTS: Record<string, string[]> = {
  child_code: ["codigo", "cod", "component", "item", "part"],
  parent_code: ["pai", "parent", "conjunto", "assembly"],
  level: ["nivel", "level"],
  qty: ["qtd", "quant", "qty", "quantity"],
  unit: ["unid", "un.", "uom", "unit"],
  description: ["descr", "desc", "nome"],
  rev: ["rev"],
  position: ["posi", "pos", "item no"],
  alt_code: ["alternativ", "alt"],
  manufacturer: ["fabric", "manufact", "fornec"],
  part_number: ["part", "pn"],
  notes: ["obs", "nota", "note"],
  category: ["categ", "tipo", "type"],
};

function norm(text: string): string {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLocaleLowerCase("pt-BR");
}

/** Campos na ordem de prioridade: pai e nível antes do componente, para "Código pai" não virar componente. */
const PRIORITY = ["parent_code", "level", "child_code", "qty", "unit", "description", "rev", "position", "alt_code", "manufacturer", "part_number", "notes", "category"];
/** Colunas que nunca são sugeridas para um campo (ex.: "Código alternativo" não é o componente). */
const EXCLUDE: Record<string, string[]> = {
  child_code: ["alternativ", "pai", "parent", "fabric"],
  parent_code: ["alternativ"],
};

/** Sugestão de mapeamento pelos nomes das colunas. Coluna nunca é usada por dois campos. */
export function suggestMapping(columns: string[]): Record<string, string> {
  const used = new Set<string>();
  const out: Record<string, string> = {};
  for (const field of PRIORITY) {
    const hint = HINTS[field] ?? [];
    const banned = EXCLUDE[field] ?? [];
    const found = columns.find(
      (c) => !used.has(c) && hint.some((h) => norm(c).includes(h)) && !banned.some((b) => norm(c).includes(b)),
    );
    if (found) {
      out[field] = found;
      used.add(found);
    }
  }
  return out;
}

export function ImportAssistant({ onCreated }: { onCreated: (structureId: string) => void }) {
  const queryClient = useQueryClient();
  const datasets = useQuery({ queryKey: ["datasets"], queryFn: listDatasets });
  const [datasetId, setDatasetId] = useState("");
  const [mode, setMode] = useState<BomMode>("explicit");
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [preview, setPreview] = useState<BomPreview | null>(null);
  const [busy, setBusy] = useState<"preview" | "create" | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const dataset: DatasetSummary | undefined = datasets.data?.find((d) => d.id === datasetId);
  const columns = dataset?.columns ?? [];
  const missing = BOM_FIELDS.filter((f) => f.required && !mapping[f.key]).map((f) => f.label);
  const needsParent = mode === "explicit" ? !mapping.parent_code : !mapping.level;
  const canPreview = Boolean(datasetId) && missing.length === 0 && !needsParent;

  function pickDataset(id: string) {
    setDatasetId(id);
    setPreview(null);
    const picked = datasets.data?.find((d) => d.id === id);
    setMapping(picked ? suggestMapping(picked.columns) : {});
    setName(picked ? picked.name.replace(/\.(csv|xlsx)$/i, "") : "");
  }

  async function runPreview() {
    setBusy("preview");
    setMessage(null);
    try {
      setPreview(await previewBom({ dataset_id: datasetId, mapping: cleanMapping(mapping), mode }));
    } catch (error) {
      setMessage(errorText(error));
      setPreview(null);
    } finally {
      setBusy(null);
    }
  }

  async function confirm() {
    setBusy("create");
    setMessage(null);
    try {
      const created = await createBomStructure({
        name,
        description,
        dataset_id: datasetId,
        mapping: cleanMapping(mapping),
        mode,
      });
      await queryClient.invalidateQueries({ queryKey: ["bom-structures"] });
      setPreview(null);
      setMessage(`Estrutura "${created.structure.name}" criada.`);
      onCreated(created.structure.id);
    } catch (error) {
      setMessage(errorText(error));
    } finally {
      setBusy(null);
    }
  }

  const errors = preview?.issue_counts.erro ?? 0;

  return (
    <section aria-labelledby="bom-import" className="space-y-3 card p-4">
      <h2 id="bom-import" className="font-medium">Importar estrutura</h2>
      <p className="text-xs text-[var(--color-muted)]">
        Use uma tabela do Data Studio (CSV ou XLSX, de ERP ou CAD). Nada é gravado antes da confirmação.
      </p>
      <label className="block text-sm">
        Tabela de origem
        <select
          aria-label="Tabela de origem"
          value={datasetId}
          onChange={(e) => pickDataset(e.target.value)}
          className={`${inputClass} mt-1 w-full`}
        >
          <option value="">Escolha uma tabela</option>
          {(datasets.data ?? []).map((d) => (
            <option key={d.id} value={d.id}>
              {d.name} ({d.row_count} linhas)
            </option>
          ))}
        </select>
      </label>

      <fieldset className="space-y-1 text-sm">
        <legend className="font-medium">Organização da hierarquia</legend>
        <label className="mr-4">
          <input type="radio" name="bom-mode" checked={mode === "explicit"} onChange={() => setMode("explicit")} /> Coluna de conjunto pai
        </label>
        <label>
          <input type="radio" name="bom-mode" checked={mode === "level"} onChange={() => setMode("level")} /> Níveis hierárquicos
        </label>
        {mode === "level" ? (
          <p className="text-xs text-[var(--color-muted)]">
            O pai é a última linha do nível anterior. Cada pai inferido aparece marcado na prévia.
          </p>
        ) : null}
      </fieldset>

      {dataset ? (
        <fieldset className="grid gap-2 text-sm">
          <legend className="font-medium">Mapeamento de colunas</legend>
          {BOM_FIELDS.map((f) => (
            <label key={f.key} className="grid grid-cols-[1fr_1.2fr] items-center gap-2">
              <span>
                {f.label}
                {f.required || (f.key === "parent_code" && mode === "explicit") || (f.key === "level" && mode === "level") ? (
                  <span className="text-[var(--color-danger)]"> *</span>
                ) : null}
              </span>
              <select
                aria-label={`Coluna para ${f.label}`}
                value={mapping[f.key] ?? ""}
                onChange={(e) => {
                  setPreview(null);
                  setMapping((prev) => ({ ...prev, [f.key]: e.target.value }));
                }}
                className={inputClass}
              >
                <option value="">— não usar —</option>
                {columns.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
          ))}
          <p className="text-xs text-[var(--color-muted)]">* obrigatório. Os demais campos são opcionais.</p>
        </fieldset>
      ) : null}

      <button type="button" onClick={() => void runPreview()} disabled={!canPreview || busy !== null} className={buttonClass}>
        {busy === "preview" ? "Gerando prévia…" : "Gerar prévia"}
      </button>

      {preview ? (
        <div className="space-y-2 rounded-md border border-[var(--color-border)] p-3 text-sm" role="region" aria-label="Prévia da importação">
          <p>
            <strong>{preview.line_count}</strong> linhas · raízes: {preview.roots.length ? preview.roots.join(", ") : "nenhuma"}
            {preview.inferred_parents ? ` · ${preview.inferred_parents} pais inferidos pelo nível` : ""}
          </p>
          <p role="status">
            Erros: {preview.issue_counts.erro ?? 0} · Alertas: {preview.issue_counts.alerta ?? 0} · Informações:{" "}
            {preview.issue_counts.informação ?? 0}
          </p>
          {errors > 0 ? (
            <p role="alert" className="text-[var(--color-danger)]">
              Há erros na prévia. A importação pode ser confirmada, mas os itens com erro aparecerão no painel de validação.
            </p>
          ) : null}
          <div className="max-h-48 overflow-auto">
            <table className="w-full text-xs">
              <caption className="sr-only">Amostra da estrutura</caption>
              <thead>
                <tr className="text-left text-[var(--color-muted)]">
                  <th className="px-1">Linha</th>
                  <th className="px-1">Pai</th>
                  <th className="px-1">Código</th>
                  <th className="px-1">Qtd</th>
                  <th className="px-1">Unid.</th>
                </tr>
              </thead>
              <tbody>
                {preview.sample.slice(0, 40).map((l) => (
                  <tr key={l.line_no}>
                    <td className="px-1">{l.line_no}</td>
                    <td className="px-1 font-mono">{l.parent ?? "(topo)"}{l.inferred_parent ? " *" : ""}</td>
                    <td className="px-1 font-mono">{l.child ?? "(sem código)"}</td>
                    <td className="px-1 font-mono">{l.qty ?? "(ausente)"}</td>
                    <td className="px-1">{l.unit ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <label className="block">
            Nome da estrutura
            <input value={name} onChange={(e) => setName(e.target.value)} className={`${inputClass} mt-1 w-full`} />
          </label>
          <label className="block">
            Descrição
            <input value={description} onChange={(e) => setDescription(e.target.value)} className={`${inputClass} mt-1 w-full`} />
          </label>
          <button type="button" onClick={() => void confirm()} disabled={!name.trim() || busy !== null} className={buttonClass}>
            {busy === "create" ? "Criando…" : "Confirmar importação"}
          </button>
        </div>
      ) : null}
      {message ? <p role="status" className="text-sm">{message}</p> : null}
    </section>
  );
}

/** Remove campos sem coluna escolhida, para não enviar chaves vazias. */
export function cleanMapping(mapping: Record<string, string>): Record<string, string> {
  return Object.fromEntries(Object.entries(mapping).filter(([, value]) => Boolean(value)));
}
