"use client";

import { useState, type DragEvent } from "react";

import { errorText } from "@/components/data-studio/templates-section";
import { inspectUpload, uploadDataset, type InspectOut } from "@/lib/datasets";

const sectionClass = "rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4 space-y-3";
const buttonClass =
  "rounded-md bg-[var(--color-accent)] px-4 py-2 font-medium text-white disabled:opacity-60";
const secondaryButton = "rounded-md border border-[var(--color-border)] px-3 py-1 text-sm disabled:opacity-50";

export const MAX_FILES = 20;

/** Só CSV e XLSX entram na fila. Outros arquivos são recusados com aviso. */
export function isAcceptedFile(name: string): boolean {
  return /\.(csv|xlsx)$/i.test(name);
}

export interface ImportItem {
  key: string;
  file: File;
  info: InspectOut | null;
  inspectError: string | null;
  /** Abas escolhidas (XLSX). Para CSV fica vazio e a importação usa o arquivo inteiro. */
  sheets: string[];
  status: "pendente" | "importando" | "importada" | "já estava importada" | "erro";
  message: string | null;
}

/** Monta as importações a partir da fila: uma por aba selecionada em XLSX, uma por arquivo em CSV. */
export function planImports(items: ImportItem[]): { key: string; file: File; sheet: string }[] {
  const plan: { key: string; file: File; sheet: string }[] = [];
  for (const item of items) {
    if (item.inspectError || !item.info) continue;
    if (item.info.kind === "xlsx") {
      for (const sheet of item.sheets) plan.push({ key: item.key, file: item.file, sheet });
    } else {
      plan.push({ key: item.key, file: item.file, sheet: "" });
    }
  }
  return plan;
}

function itemKey(file: File): string {
  return `${file.name}-${file.size}-${file.lastModified}`;
}

export function UploadSection({ onImported }: { onImported: (id: string) => void }) {
  const [items, setItems] = useState<ImportItem[]>([]);
  const [dragging, setDragging] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [progress, setProgress] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function addFiles(list: FileList | File[]) {
    const accepted: File[] = [];
    const rejected: string[] = [];
    for (const file of Array.from(list)) {
      if (isAcceptedFile(file.name)) accepted.push(file);
      else rejected.push(file.name);
    }
    setNotice(
      [
        rejected.length ? `Ignorado (formato não suportado): ${rejected.join(", ")}.` : null,
        items.length + accepted.length > MAX_FILES ? `Limite de ${MAX_FILES} arquivos por vez.` : null,
      ]
        .filter(Boolean)
        .join(" ") || null,
    );
    const room = Math.max(0, MAX_FILES - items.length);
    const fresh = accepted.slice(0, room).map<ImportItem>((file) => ({
      key: itemKey(file),
      file,
      info: null,
      inspectError: null,
      sheets: [],
      status: "pendente",
      message: null,
    }));
    if (fresh.length === 0) return;
    setItems((prev) => [...prev, ...fresh]);
    // Leitura prévia de cada arquivo: nada é gravado até o usuário importar.
    for (const item of fresh) {
      try {
        const info = await inspectUpload(item.file);
        setItems((prev) =>
          prev.map((p) =>
            p.key === item.key
              ? { ...p, info, sheets: info.kind === "xlsx" && info.sheet ? [info.sheet] : [] }
              : p,
          ),
        );
      } catch (error) {
        setItems((prev) =>
          prev.map((p) => (p.key === item.key ? { ...p, inspectError: errorText(error) } : p)),
        );
      }
    }
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    if (event.dataTransfer.files.length > 0) void addFiles(event.dataTransfer.files);
  }

  function toggleSheet(key: string, sheet: string, checked: boolean) {
    setItems((prev) =>
      prev.map((p) =>
        p.key === key
          ? {
              ...p,
              sheets: checked
                ? [...p.sheets, sheet]
                : p.sheets.filter((s) => s !== sheet),
            }
          : p,
      ),
    );
  }

  function remove(key: string) {
    setItems((prev) => prev.filter((p) => p.key !== key));
  }

  const plan = planImports(items);

  async function importAll() {
    setBusy(true);
    setNotice(null);
    let lastId: string | null = null;
    let failures = 0;
    for (let i = 0; i < plan.length; i++) {
      const step = plan[i];
      if (!step) continue;
      const label = step.sheet ? `${step.file.name} (aba ${step.sheet})` : step.file.name;
      setProgress(`Importando ${i + 1} de ${plan.length}: ${label}`);
      setItems((prev) =>
        prev.map((p) => (p.key === step.key ? { ...p, status: "importando", message: null } : p)),
      );
      try {
        const result = await uploadDataset(step.file, step.sheet);
        lastId = result.dataset.id;
        setItems((prev) =>
          prev.map((p) =>
            p.key === step.key
              ? {
                  ...p,
                  status: result.created ? "importada" : "já estava importada",
                  message: result.dataset.name,
                }
              : p,
          ),
        );
      } catch (error) {
        failures += 1;
        setItems((prev) =>
          prev.map((p) => (p.key === step.key ? { ...p, status: "erro", message: errorText(error) } : p)),
        );
      }
    }
    setProgress(null);
    setBusy(false);
    if (lastId) onImported(lastId);
    setNotice(
      plan.length === 0
        ? "Nada para importar."
        : `${plan.length - failures} de ${plan.length} importação(ões) concluída(s).${failures ? ` ${failures} com erro.` : ""}`,
    );
  }

  return (
    <section className={sectionClass} aria-labelledby="importar">
      <h2 id="importar" className="font-medium">
        Importar arquivos
      </h2>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`rounded-md border-2 border-dashed p-4 text-center text-sm ${
          dragging ? "border-[var(--color-accent)] bg-[var(--color-border)]" : "border-[var(--color-border)]"
        }`}
      >
        <p className="mb-2">Arraste arquivos CSV ou XLSX aqui</p>
        <label htmlFor="arquivo" className={`${secondaryButton} inline-block cursor-pointer`}>
          Escolher arquivos
        </label>
        <input
          id="arquivo"
          aria-label="Arquivo (.csv ou .xlsx)"
          type="file"
          multiple
          accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          onChange={(e) => {
            if (e.target.files) void addFiles(e.target.files);
            e.target.value = "";
          }}
          className="sr-only"
        />
      </div>

      {items.length > 0 ? (
        <ul className="space-y-3">
          {items.map((item) => (
            <li key={item.key} className="space-y-2 rounded-md border border-[var(--color-border)] p-3 text-sm">
              <div className="flex items-start justify-between gap-2">
                <span className="min-w-0 break-all font-medium">{item.file.name}</span>
                <button
                  type="button"
                  onClick={() => remove(item.key)}
                  disabled={busy || item.status === "importando"}
                  className={secondaryButton}
                  aria-label={`Remover ${item.file.name} da fila`}
                >
                  Remover
                </button>
              </div>

              {item.inspectError ? (
                <p role="alert" className="text-[var(--color-danger)]">
                  Não foi possível ler o arquivo: {item.inspectError}
                </p>
              ) : null}

              {!item.info && !item.inspectError ? (
                <p className="text-[var(--color-muted)]">Lendo o arquivo…</p>
              ) : null}

              {item.info && item.info.kind === "xlsx" && item.info.sheets.length > 0 ? (
                <fieldset className="space-y-1">
                  <legend className="text-xs text-[var(--color-muted)]">Abas a importar</legend>
                  <div className="flex flex-wrap gap-3">
                    {item.info.sheets.map((sheet) => (
                      <label key={sheet} className="flex items-center gap-1">
                        <input
                          type="checkbox"
                          checked={item.sheets.includes(sheet)}
                          disabled={busy}
                          onChange={(e) => toggleSheet(item.key, sheet, e.target.checked)}
                        />
                        {sheet}
                      </label>
                    ))}
                  </div>
                  <p className="text-xs text-[var(--color-muted)]">
                    A prévia abaixo mostra a primeira aba; cada aba marcada vira uma tabela.
                  </p>
                </fieldset>
              ) : null}

              {item.info ? <RawPreview info={item.info} /> : null}

              {item.info?.warnings.map((w) => (
                <p key={w} className="text-xs text-[var(--color-muted)]">
                  {w}
                </p>
              ))}

              {item.status !== "pendente" ? (
                <p role="status" className="text-xs">
                  {item.status === "erro" ? (
                    <span role="alert" className="text-[var(--color-danger)]">
                      Erro: {item.message}
                    </span>
                  ) : item.status === "importando" ? (
                    "Importando…"
                  ) : (
                    `${item.status}${item.message ? `: ${item.message}` : ""}`
                  )}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}

      <button type="button" onClick={() => void importAll()} disabled={busy || plan.length === 0} className={buttonClass}>
        {busy ? "Importando…" : `Importar ${plan.length} tabela(s)`}
      </button>

      {progress ? (
        <p role="status" className="text-sm text-[var(--color-muted)]">
          {progress}
        </p>
      ) : null}
      {notice ? (
        <p role="status" className="text-sm text-[var(--color-muted)]">
          {notice}
        </p>
      ) : null}
    </section>
  );
}

/** Prévia tabular do arquivo: uma célula por valor, cabeçalho detectado destacado. */
export function RawPreview({ info }: { info: InspectOut }) {
  const width = Math.max(1, ...info.preview.map((r) => r.values.length));
  return (
    <div className="max-h-56 overflow-auto rounded-md border border-[var(--color-border)]">
      <table className="w-full text-xs">
        <caption className="sr-only">Prévia das primeiras linhas do arquivo</caption>
        <tbody>
          {info.preview.map((row) => (
            <tr
              key={row.row_number}
              className={`border-t border-[var(--color-border)] ${
                row.row_number === info.header_row ? "bg-[var(--color-border)] font-semibold" : ""
              }`}
            >
              <td className="px-2 py-1 text-[var(--color-muted)]">{row.row_number}</td>
              {Array.from({ length: width }, (_, j) => (
                <td key={j} className="whitespace-nowrap px-2 py-1 font-mono">
                  {row.values[j] ?? ""}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {info.header_row !== null ? (
        <p className="px-2 py-1 text-xs text-[var(--color-muted)]">
          Cabeçalho detectado na linha {info.header_row}. Você pode ajustar depois de importar, em &ldquo;Mapeamento, cabeçalho e modelos&rdquo;.
        </p>
      ) : null}
    </div>
  );
}
