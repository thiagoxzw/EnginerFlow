"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import {
  compareBom,
  downloadBomExport,
  createBomKit,
  crossBom,
  explodeBom,
  kitCalc,
  listBomKits,
  setBomCurrent,
  validateBom,
  type BomCross,
  type BomExplosion,
  type BomIssue,
  type BomLine,
  type BomMode,
  type BomStructure,
  type BomComparison,
} from "@/lib/bom";
import { listDatasets } from "@/lib/datasets";
import { errorText } from "@/components/data-studio/templates-section";
import { topLines } from "@/lib/bom-tree";

const inputClass = "rounded-md border border-[var(--color-border)] bg-transparent px-2 py-1 text-sm";
const buttonClass = "rounded-md border border-[var(--color-border)] px-3 py-1 text-sm disabled:opacity-50";
/** Baixa uma exportação do BOM; a recusa da API (ex.: limite da hierarquia) aparece na tela. */
async function exportBom(revisionId: string, params: Record<string, string>, onError: (text: string | null) => void) {
  onError(null);
  try {
    await downloadBomExport(revisionId, params);
  } catch (error) {
    onError(errorText(error));
  }
}

function Table({ caption, headers, rows }: { caption: string; headers: string[]; rows: (string | number | null)[][] }) {
  return (
    <div className="max-h-96 overflow-auto rounded-md border border-[var(--color-border)]">
      <table className="w-full text-xs">
        <caption className="sr-only">{caption}</caption>
        <thead className="sticky top-0 bg-[var(--color-surface)] text-left text-[var(--color-muted)]">
          <tr>
            {headers.map((h) => (
              <th key={h} className="px-2 py-1 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-[var(--color-border)]">
              {r.map((cell, j) => (
                <td key={j} className="px-2 py-1 font-mono">
                  {cell ?? ""}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ExplodeTab({ revisionId, lines }: { revisionId: string; lines: BomLine[] }) {
  const tops = [...new Set(topLines(lines).map((l) => l.child).filter((c): c is string => Boolean(c)))];
  const [root, setRoot] = useState(tops[0] ?? "");
  const [vehicles, setVehicles] = useState("1");
  const [result, setResult] = useState<BomExplosion | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true);
    setMessage(null);
    try {
      setResult(await explodeBom(revisionId, root, vehicles));
    } catch (error) {
      setResult(null);
      setMessage(errorText(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-2 text-sm">
        <label>
          Conjunto de topo
          <select aria-label="Conjunto de topo" value={root} onChange={(e) => setRoot(e.target.value)} className={`${inputClass} mt-1 block`}>
            {tops.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        <label>
          Veículos
          <input aria-label="Quantidade de veículos" value={vehicles} onChange={(e) => setVehicles(e.target.value)} className={`${inputClass} mt-1 block w-28`} />
        </label>
        <button type="button" className={buttonClass} onClick={() => void run()} disabled={!root || busy}>
          {busy ? "Calculando…" : "Explodir"}
        </button>
        {root ? (
          <>
            <button type="button" className={buttonClass} onClick={() => void exportBom(revisionId, { kind: "consolidated", fmt: "xlsx", root, vehicles }, setMessage)}>
              Exportar consolidada (XLSX)
            </button>
            <button type="button" className={buttonClass} onClick={() => void exportBom(revisionId, { kind: "hierarchy", fmt: "xlsx", root }, setMessage)}>
              Exportar hierárquica (XLSX)
            </button>
          </>
        ) : null}
      </div>
      {message ? <p role="alert" className="text-sm text-[var(--color-danger)]">{message}</p> : null}
      {result ? (
        <>
          <p className="text-sm" role="status">
            {result.consolidated.length} material(is) para {result.vehicles} veículo(s).
          </p>
          {result.warnings.map((w) => (
            <p key={w} className="text-xs text-[var(--color-muted)]">{w}</p>
          ))}
          <Table
            caption="Quantidades consolidadas"
            headers={["Código", "Unidade", "Quantidade total", "Ocorrências na estrutura"]}
            rows={result.consolidated.map((c) => [c.code, c.unit, c.qty, result.occurrences[c.code] ?? null])}
          />
        </>
      ) : null}
    </div>
  );
}

export function CompareTab({ structure }: { structure: BomStructure }) {
  const revs = structure.revisions;
  const [a, setA] = useState(revs[0]?.id ?? "");
  const [b, setB] = useState(revs[revs.length - 1]?.id ?? "");
  const [result, setResult] = useState<BomComparison | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function run() {
    setMessage(null);
    try {
      setResult(await compareBom(a, b));
    } catch (error) {
      setResult(null);
      setMessage(errorText(error));
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-2 text-sm">
        <label>
          Revisão A
          <select aria-label="Revisão A" value={a} onChange={(e) => setA(e.target.value)} className={`${inputClass} mt-1 block`}>
            {revs.map((r) => (
              <option key={r.id} value={r.id}>r{r.number} · {r.label}</option>
            ))}
          </select>
        </label>
        <label>
          Revisão B
          <select aria-label="Revisão B" value={b} onChange={(e) => setB(e.target.value)} className={`${inputClass} mt-1 block`}>
            {revs.map((r) => (
              <option key={r.id} value={r.id}>r{r.number} · {r.label}</option>
            ))}
          </select>
        </label>
        <button type="button" className={buttonClass} onClick={() => void run()} disabled={!a || !b}>
          Comparar
        </button>
        {a && b ? (
          <button type="button" className={buttonClass} onClick={() => void exportBom(a, { kind: "compare", fmt: "xlsx", other_revision: b }, setMessage)}>
            Exportar comparação (XLSX)
          </button>
        ) : null}
      </div>
      {message ? <p role="alert" className="text-sm text-[var(--color-danger)]">{message}</p> : null}
      {result ? (
        <>
          <p className="text-sm" role="status">
            {Object.entries(result.counts).map(([k, v]) => `${k}: ${v}`).join(" · ")}
          </p>
          <Table
            caption="Diferenças entre as revisões"
            headers={["Tipo", "Código", "Conjunto", "Detalhe", "Linha"]}
            rows={result.changes.map((c) => [c.kind, c.child, c.parent, c.detail, c.line_no])}
          />
          {result.pending_code_changes.length ? (
            <p className="text-xs">
              Possíveis trocas de código (pendentes de confirmação, não aplicadas):{" "}
              {result.pending_code_changes.map((p) => `${p.from} → ${p.to}`).join("; ")}
            </p>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

export function ValidateTab({
  revisionId,
  mode,
  onGoto,
}: {
  revisionId: string;
  mode: BomMode;
  onGoto: (lineNo: number) => void;
}) {
  const [issues, setIssues] = useState<BomIssue[] | null>(null);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [message, setMessage] = useState<string | null>(null);

  async function run() {
    setMessage(null);
    try {
      const result = await validateBom(revisionId, mode);
      setIssues(result.issues);
      setCounts(result.counts);
    } catch (error) {
      setMessage(errorText(error));
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <button type="button" className={buttonClass} onClick={() => void run()}>
          Validar estrutura
        </button>
        {issues ? (
          <span role="status">
            Erros: {counts.erro ?? 0} · Alertas: {counts.alerta ?? 0} · Informações: {counts["informação"] ?? 0}
          </span>
        ) : null}
        <button type="button" className={buttonClass} onClick={() => void exportBom(revisionId, { kind: "issues", fmt: "xlsx", mode }, setMessage)}>
          Exportar inconsistências (XLSX)
        </button>
      </div>
      <p className="text-xs text-[var(--color-muted)]">
        O painel aponta os problemas e não altera dados. Use “Ir à linha” para localizar o componente.
      </p>
      {message ? <p role="alert" className="text-sm text-[var(--color-danger)]">{message}</p> : null}
      {issues ? (
        <ul className="max-h-96 space-y-1 overflow-auto text-sm" aria-label="Inconsistências">
          {issues.map((i, idx) => (
            <li key={idx} className="flex flex-wrap items-center gap-2 border-b border-[var(--color-border)] py-1">
              <span className={i.severity === "erro" ? "text-[var(--color-danger)]" : "text-[var(--color-muted)]"}>{i.severity}</span>
              <span className="font-mono text-xs">{i.code ?? ""}</span>
              <span className="flex-1">{i.message}</span>
              {i.line_no !== null ? (
                <button type="button" className={buttonClass} onClick={() => onGoto(i.line_no as number)}>
                  Ir à linha {i.line_no}
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export function CrossSection({ revisionId }: { revisionId: string }) {
  const datasets = useQuery({ queryKey: ["datasets"], queryFn: listDatasets });
  const [cadastroId, setCadastroId] = useState("");
  const [key, setKey] = useState("");
  const [desc, setDesc] = useState("");
  const [unit, setUnit] = useState("");
  const [keyMode, setKeyMode] = useState<"exato" | "normalizado">("exato");
  const [result, setResult] = useState<BomCross | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const cad = datasets.data?.find((d) => d.id === cadastroId);

  async function run() {
    setMessage(null);
    try {
      setResult(
        await crossBom(revisionId, {
          cadastro_dataset_id: cadastroId,
          key_column: key,
          description_column: desc || null,
          unit_column: unit || null,
          key_mode: keyMode,
        }),
      );
    } catch (error) {
      setResult(null);
      setMessage(errorText(error));
    }
  }

  return (
    <div className="space-y-3 rounded-md border border-[var(--color-border)] p-3">
      <h3 className="text-sm font-medium">Cruzamento com cadastro de materiais</h3>
      <p className="text-xs text-[var(--color-muted)]">
        Escolha a tabela de cadastro e as colunas. Correspondências ambíguas ficam pendentes; nenhum código é atribuído automaticamente.
      </p>
      <div className="flex flex-wrap items-end gap-2 text-sm">
        <label>
          Cadastro de referência
          <select aria-label="Cadastro de referência" value={cadastroId} onChange={(e) => { setCadastroId(e.target.value); setKey(""); setDesc(""); setUnit(""); }} className={`${inputClass} mt-1 block`}>
            <option value="">Escolha uma tabela</option>
            {(datasets.data ?? []).map((d) => (
              <option key={d.id} value={d.id}>{d.name}</option>
            ))}
          </select>
        </label>
        {cad ? (
          <>
            <ColumnSelect label="Coluna do código" value={key} columns={cad.columns} onChange={setKey} />
            <ColumnSelect label="Coluna da descrição (opcional)" value={desc} columns={cad.columns} onChange={setDesc} optional />
            <ColumnSelect label="Coluna da unidade (opcional)" value={unit} columns={cad.columns} onChange={setUnit} optional />
            <label>
              Comparação de códigos
              <select aria-label="Comparação de códigos" value={keyMode} onChange={(e) => setKeyMode(e.target.value as "exato" | "normalizado")} className={`${inputClass} mt-1 block`}>
                <option value="exato">Exata</option>
                <option value="normalizado">Normalizada (sem diferença de caixa ou espaços)</option>
              </select>
            </label>
          </>
        ) : null}
        <button type="button" className={buttonClass} disabled={!cadastroId || !key} onClick={() => void run()}>
          Cruzar
        </button>
      </div>
      {message ? <p role="alert" className="text-sm text-[var(--color-danger)]">{message}</p> : null}
      {result ? (
        <>
          <p role="status" className="text-sm">{Object.entries(result.counts).map(([k, v]) => `${k}: ${v}`).join(" · ")}</p>
          <Table
            caption="Resultado do cruzamento"
            headers={["Código", "Descrição", "Unidade", "Situação", "Correspondências", "Divergências", "Possíveis equivalentes (pendente)"]}
            rows={result.items.map((i) => [i.code, i.description, i.unit, i.status, i.matches, i.flags.join(", "), i.equivalent_candidates.join(", ")])}
          />
        </>
      ) : null}
    </div>
  );
}

function ColumnSelect({ label, value, columns, onChange, optional }: { label: string; value: string; columns: string[]; onChange: (v: string) => void; optional?: boolean }) {
  return (
    <label>
      {label}
      <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)} className={`${inputClass} mt-1 block`}>
        <option value="">{optional ? "— nenhuma —" : "Escolha"}</option>
        {columns.map((c) => (
          <option key={c} value={c}>{c}</option>
        ))}
      </select>
    </label>
  );
}

export function KitsTab({ structure, revisionId }: { structure: BomStructure; revisionId: string }) {
  const kits = useQuery({ queryKey: ["bom-kits", structure.id], queryFn: () => listBomKits(structure.id) });
  const [name, setName] = useState("");
  const [partsText, setPartsText] = useState("");
  const [vehicles, setVehicles] = useState("1");
  const [lot, setLot] = useState("1");
  const [kitId, setKitId] = useState("");
  const [materials, setMaterials] = useState<{ code: string; unit: string; qty: string }[] | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  function parseParts(text: string): { code: string; qty: string }[] {
    return text
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const [code = "", qty = ""] = line.split(";").map((p) => p.trim());
        return { code, qty };
      });
  }

  async function createKit() {
    setMessage(null);
    try {
      await createBomKit(structure.id, name, parseParts(partsText));
      await kits.refetch();
      setMessage("Kit criado.");
      setName("");
      setPartsText("");
    } catch (error) {
      setMessage(errorText(error));
    }
  }

  async function calc(parts: { code: string; qty: string }[]) {
    setMessage(null);
    try {
      setMaterials((await kitCalc(revisionId, parts, vehicles, lot)).materials);
    } catch (error) {
      setMaterials(null);
      setMessage(errorText(error));
    }
  }

  const selected = kits.data?.find((k) => k.id === kitId);

  return (
    <div className="space-y-4 text-sm">
      <section className="space-y-2 rounded-md border border-[var(--color-border)] p-3">
        <h3 className="font-medium">Criar kit</h3>
        <p className="text-xs text-[var(--color-muted)]">Um subconjunto por linha, no formato código;quantidade por kit. Ex.: CONJ-SYN-TRAC;1</p>
        <input aria-label="Nome do kit" value={name} onChange={(e) => setName(e.target.value)} placeholder="Nome do kit" className={`${inputClass} w-full`} />
        <textarea aria-label="Subconjuntos do kit" value={partsText} onChange={(e) => setPartsText(e.target.value)} rows={3} className={`${inputClass} w-full font-mono`} />
        <button type="button" className={buttonClass} disabled={!name.trim() || !partsText.trim()} onClick={() => void createKit()}>
          Salvar kit
        </button>
      </section>

      <section className="space-y-2 rounded-md border border-[var(--color-border)] p-3">
        <h3 className="font-medium">Calcular materiais do kit</h3>
        <div className="flex flex-wrap items-end gap-2">
          <label>
            Kit
            <select aria-label="Kit para cálculo" value={kitId} onChange={(e) => setKitId(e.target.value)} className={`${inputClass} mt-1 block`}>
              <option value="">Escolha um kit</option>
              {(kits.data ?? []).map((k) => (
                <option key={k.id} value={k.id}>{k.name}</option>
              ))}
            </select>
          </label>
          <label>
            Veículos
            <input aria-label="Veículos do cálculo" value={vehicles} onChange={(e) => setVehicles(e.target.value)} className={`${inputClass} mt-1 block w-24`} />
          </label>
          <label>
            Lote de kits
            <input aria-label="Lote do cálculo" value={lot} onChange={(e) => setLot(e.target.value)} className={`${inputClass} mt-1 block w-24`} />
          </label>
          <button type="button" className={buttonClass} disabled={!selected} onClick={() => selected && void calc(selected.parts)}>
            Calcular
          </button>
        </div>
        {materials ? (
          <>
            <Table caption="Materiais do kit" headers={["Código", "Unidade", "Quantidade para separar"]} rows={materials.map((m) => [m.code, m.unit, m.qty])} />
            <button type="button" className={buttonClass} onClick={() => downloadCsv("separacao-materiais.csv", [["Código", "Unidade", "Quantidade"], ...materials.map((m) => [m.code, m.unit, m.qty])])}>
              Exportar lista de separação (CSV)
            </button>
          </>
        ) : null}
      </section>

      <section className="space-y-2 rounded-md border border-[var(--color-border)] p-3">
        <h3 className="font-medium">Comparar composição de kits</h3>
        <KitCompare kits={kits.data ?? []} revisionId={revisionId} vehicles={vehicles} lot={lot} />
      </section>
      {message ? <p role="status">{message}</p> : null}
    </div>
  );
}

function KitCompare({ kits, revisionId }: { kits: { id: string; name: string; parts: { code: string; qty: string }[] }[]; revisionId: string; vehicles: string; lot: string }) {
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [rows, setRows] = useState<(string | null)[][] | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function run() {
    setMessage(null);
    try {
      const ka = kits.find((k) => k.id === a);
      const kb = kits.find((k) => k.id === b);
      if (!ka || !kb) return;
      const [ma, mb] = await Promise.all([kitCalc(revisionId, ka.parts, "1", "1"), kitCalc(revisionId, kb.parts, "1", "1")]);
      const map = (list: { code: string; unit: string; qty: string }[]) => new Map(list.map((m) => [`${m.code}|${m.unit}`, m.qty]));
      const mapA = map(ma.materials);
      const mapB = map(mb.materials);
      const keys = [...new Set([...mapA.keys(), ...mapB.keys()])].sort();
      setRows(
        keys.map((k) => {
          const [code = "", unit = ""] = k.split("|");
          const qa = mapA.get(k) ?? null;
          const qb = mapB.get(k) ?? null;
          const status = qa === null ? "só no kit B" : qb === null ? "só no kit A" : qa === qb ? "igual" : "quantidade diferente";
          return [code, unit, qa, qb, status];
        }),
      );
    } catch (error) {
      setMessage(errorText(error));
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-end gap-2">
        <select aria-label="Kit A" value={a} onChange={(e) => setA(e.target.value)} className={inputClass}>
          <option value="">Kit A</option>
          {kits.map((k) => <option key={k.id} value={k.id}>{k.name}</option>)}
        </select>
        <select aria-label="Kit B" value={b} onChange={(e) => setB(e.target.value)} className={inputClass}>
          <option value="">Kit B</option>
          {kits.map((k) => <option key={k.id} value={k.id}>{k.name}</option>)}
        </select>
        <button type="button" className={buttonClass} disabled={!a || !b} onClick={() => void run()}>Comparar kits</button>
      </div>
      {message ? <p role="alert" className="text-[var(--color-danger)]">{message}</p> : null}
      {rows ? <Table caption="Comparação de kits" headers={["Código", "Unidade", "Kit A", "Kit B", "Situação"]} rows={rows} /> : null}
    </div>
  );
}

export function HistoryTab({
  structure,
  onUse,
  onOpen,
}: {
  structure: BomStructure;
  onUse: (structure: BomStructure) => void;
  onOpen: (revisionId: string) => void;
}) {
  const [message, setMessage] = useState<string | null>(null);

  async function use(revisionId: string) {
    setMessage(null);
    try {
      onUse(await setBomCurrent(structure.id, revisionId));
    } catch (error) {
      setMessage(errorText(error));
    }
  }

  return (
    <div className="space-y-2 text-sm">
      <p className="text-xs text-[var(--color-muted)]">
        Revisões são imutáveis. Desfazer e refazer apenas trocam a revisão atual: nenhuma revisão é apagada.
      </p>
      {message ? <p role="alert" className="text-[var(--color-danger)]">{message}</p> : null}
      <table className="w-full text-xs">
        <caption className="sr-only">Histórico de revisões</caption>
        <thead className="text-left text-[var(--color-muted)]">
          <tr>
            <th className="px-2 py-1">Revisão</th>
            <th className="px-2 py-1">Origem</th>
            <th className="px-2 py-1">Linhas</th>
            <th className="px-2 py-1">Criada em</th>
            <th className="px-2 py-1">Por</th>
            <th className="px-2 py-1">Ações</th>
          </tr>
        </thead>
        <tbody>
          {structure.revisions.map((r) => (
            <tr key={r.id} className={`border-t border-[var(--color-border)] ${r.id === structure.current_revision_id ? "font-semibold" : ""}`}>
              <td className="px-2 py-1">r{r.number} · {r.label}{r.id === structure.current_revision_id ? " (atual)" : ""}</td>
              <td className="px-2 py-1">{r.parent_revision_id ? "alteração" : "importação"}</td>
              <td className="px-2 py-1 font-mono">{r.line_count}</td>
              <td className="px-2 py-1">{r.created_at ? new Date(r.created_at).toLocaleString("pt-BR") : "—"}</td>
              <td className="px-2 py-1">{r.actor}</td>
              <td className="flex gap-1 px-2 py-1">
                <button type="button" className={buttonClass} onClick={() => onOpen(r.id)}>Abrir</button>
                {r.id !== structure.current_revision_id ? (
                  <button type="button" className={buttonClass} onClick={() => void use(r.id)}>Usar como atual</button>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** CSV no navegador (lista de separação). Campos com ponto e vírgula, aspas ou quebra são entre aspas. */
export function downloadCsv(name: string, rows: (string | number | null)[][]): void {
  const text = rows
    .map((r) => r.map((v) => { const s = v === null ? "" : String(v); return /[";\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; }).join(";"))
    .join("\r\n");
  const blob = new Blob(["﻿", text], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}
