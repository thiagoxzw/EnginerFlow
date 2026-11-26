"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { createBomKit, createKitFromTable, previewKitFromTable, type KitImportPreview } from "@/lib/bom";
import { listDatasets } from "@/lib/datasets";
import { errorText } from "@/components/data-studio/templates-section";

const inputClass = "rounded-md border border-[var(--color-border)] bg-transparent px-2 py-1 text-sm";
const buttonClass = "rounded-md border border-[var(--color-border)] px-3 py-1 text-sm disabled:opacity-50";

export interface DraftPart {
  code: string;
  qty: string;
  unit: string | null;
  description: string | null;
}

/** Rascunho de kit com componentes escolhidos diretamente na árvore do BOM. */
export function KitDraft({
  structureId,
  draft,
  onChange,
  onSaved,
}: {
  structureId: string;
  draft: DraftPart[];
  onChange: (next: DraftPart[]) => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  async function save() {
    setMessage(null);
    try {
      await createBomKit(structureId, name.trim(), draft.map((p) => ({ code: p.code, qty: p.qty, unit: p.unit })));
      setMessage("Kit salvo com a seleção.");
      onChange([]);
      setName("");
      onSaved();
    } catch (error) {
      setMessage(errorText(error));
    }
  }

  return (
    <section className="space-y-2 rounded-md border border-[var(--color-border)] p-3 text-sm">
      <h3 className="font-medium">Rascunho com seleção da árvore</h3>
      <p className="text-xs text-[var(--color-muted)]">
        Na aba Estrutura, use “+ kit” em cada linha. Subconjuntos entram com os componentes deles, como na explosão; componentes folha entram por si.
      </p>
      {draft.length === 0 ? <p className="text-xs text-[var(--color-muted)]">Nenhuma peça selecionada.</p> : null}
      <ul className="space-y-1">
        {draft.map((p, i) => (
          <li key={`${p.code}-${i}`} className="flex flex-wrap items-center gap-2">
            <span className="font-mono">{p.code}</span>
            <span className="text-xs text-[var(--color-muted)]">{p.unit ?? "sem unidade"}</span>
            <input
              aria-label={`Quantidade por kit de ${p.code}`}
              value={p.qty}
              onChange={(e) => onChange(draft.map((x, j) => (j === i ? { ...x, qty: e.target.value } : x)))}
              className={`${inputClass} w-20`}
            />
            <button type="button" className={buttonClass} onClick={() => onChange(draft.filter((_, j) => j !== i))}>
              Remover
            </button>
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-2">
        <input aria-label="Nome do kit com seleção" value={name} onChange={(e) => setName(e.target.value)} placeholder="Nome do kit" className={`${inputClass} flex-1`} />
        <button type="button" className={buttonClass} disabled={!name.trim() || draft.length === 0} onClick={() => void save()}>
          Salvar kit com a seleção
        </button>
      </div>
      {message ? <p role="status" className="text-xs">{message}</p> : null}
    </section>
  );
}

/** Kit a partir de uma tabela do Data Studio (CSV ou XLSX já importados), com prévia antes de criar. */
export function KitFromTable({ structureId, onSaved }: { structureId: string; onSaved: () => void }) {
  const datasets = useQuery({ queryKey: ["datasets"], queryFn: listDatasets });
  const [datasetId, setDatasetId] = useState("");
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [name, setName] = useState("");
  const [preview, setPreview] = useState<KitImportPreview | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const dataset = datasets.data?.find((d) => d.id === datasetId);
  const columns = dataset?.columns ?? [];
  const ready = Boolean(datasetId && mapping.code && mapping.qty);
  const clean = Object.fromEntries(Object.entries(mapping).filter(([, v]) => Boolean(v)));

  async function runPreview() {
    setMessage(null);
    try {
      setPreview(await previewKitFromTable(structureId, { dataset_id: datasetId, mapping: clean }));
    } catch (error) {
      setPreview(null);
      setMessage(errorText(error));
    }
  }

  async function create() {
    setMessage(null);
    try {
      await createKitFromTable(structureId, { name: name.trim(), dataset_id: datasetId, mapping: clean });
      setMessage("Kit criado a partir da tabela.");
      setPreview(null);
      setName("");
      onSaved();
    } catch (error) {
      setMessage(errorText(error));
    }
  }

  const errors = preview?.issues.filter((i) => i.severity === "erro").length ?? 0;

  return (
    <section className="space-y-2 rounded-md border border-[var(--color-border)] p-3 text-sm">
      <h3 className="font-medium">Importar kit de tabela</h3>
      <p className="text-xs text-[var(--color-muted)]">
        Use uma tabela do Data Studio (CSV ou XLSX). Código e quantidade são obrigatórios; unidade e descrição são opcionais. Nada é criado antes da prévia.
      </p>
      <label className="block">
        Tabela
        <select aria-label="Tabela do kit" value={datasetId} onChange={(e) => { setDatasetId(e.target.value); setMapping({}); setPreview(null); }} className={`${inputClass} mt-1 block w-full`}>
          <option value="">Escolha uma tabela</option>
          {(datasets.data ?? []).map((d) => (
            <option key={d.id} value={d.id}>{d.name}</option>
          ))}
        </select>
      </label>
      {dataset ? (
        <div className="grid gap-2 sm:grid-cols-2">
          {(["code", "qty", "unit", "description"] as const).map((field) => (
            <label key={field} className="flex items-center justify-between gap-2">
              <span>{{ code: "Código", qty: "Quantidade", unit: "Unidade (opcional)", description: "Descrição (opcional)" }[field]}</span>
              <select aria-label={`Coluna do kit para ${field}`} value={mapping[field] ?? ""} onChange={(e) => { setMapping({ ...mapping, [field]: e.target.value }); setPreview(null); }} className={inputClass}>
                <option value="">— não usar —</option>
                {columns.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </label>
          ))}
        </div>
      ) : null}
      <button type="button" className={buttonClass} disabled={!ready} onClick={() => void runPreview()}>
        Gerar prévia do kit
      </button>
      {preview ? (
        <div className="space-y-2" role="region" aria-label="Prévia do kit">
          <p role="status">{preview.parts.length} peça(s) · {errors} erro(s) · {preview.issues.length - errors} aviso(s)/informação(ões)</p>
          <ul className="max-h-40 space-y-1 overflow-auto text-xs">
            {preview.issues.map((i, idx) => (
              <li key={idx} className={i.severity === "erro" ? "text-[var(--color-danger)]" : "text-[var(--color-muted)]"}>
                {i.row !== null ? `linha ${i.row} · ` : ""}{i.severity}: {i.message}
              </li>
            ))}
          </ul>
          <table className="w-full text-xs">
            <caption className="sr-only">Peças da prévia</caption>
            <thead className="text-left text-[var(--color-muted)]"><tr><th className="px-1">Código</th><th className="px-1">Qtd. por kit</th><th className="px-1">Unidade</th></tr></thead>
            <tbody>
              {preview.parts.map((p) => (
                <tr key={`${p.code}-${p.unit ?? ""}`}><td className="px-1 font-mono">{p.code}</td><td className="px-1 font-mono">{p.qty}</td><td className="px-1">{p.unit ?? ""}</td></tr>
              ))}
            </tbody>
          </table>
          <div className="flex flex-wrap gap-2">
            <input aria-label="Nome do kit importado" value={name} onChange={(e) => setName(e.target.value)} placeholder="Nome do kit" className={`${inputClass} flex-1`} />
            <button type="button" className={buttonClass} disabled={!name.trim() || errors > 0} onClick={() => void create()}>
              Criar kit desta prévia
            </button>
          </div>
          {errors > 0 ? <p className="text-xs text-[var(--color-danger)]">Corrija os erros da tabela para criar o kit.</p> : null}
        </div>
      ) : null}
      {message ? <p role="status" className="text-xs">{message}</p> : null}
    </section>
  );
}
