"use client";

import { useMemo, useState } from "react";

import { editBom, type BomLine } from "@/lib/bom";
import { errorText } from "@/components/data-studio/templates-section";
import {
  ancestorKeys,
  childrenIndex,
  expandableKeys,
  matchingLines,
  nodeKey,
  passesFilters,
  topLines,
  usageOf,
  visibleRows,
  type TreeFilters,
} from "@/lib/bom-tree";

const inputClass = "rounded-md border border-[var(--color-border)] bg-transparent px-2 py-1 text-sm";
const buttonClass = "rounded-md border border-[var(--color-border)] px-2 py-1 text-xs disabled:opacity-50";
const MAX_ROWS = 1500;

function distinct(lines: BomLine[], pick: (l: BomLine) => string | null): string[] {
  return [...new Set(lines.map(pick).filter((v): v is string => Boolean(v)))].sort();
}

export function TreeView({
  revisionId,
  lines,
  onNewRevision,
  onPickPart,
  focusLine = null,
}: {
  revisionId: string;
  lines: BomLine[];
  onNewRevision: (revisionId: string) => void;
  /** Adiciona um componente ao rascunho de kit (seleção direta pela árvore). */
  onPickPart?: (part: { code: string; unit: string | null; description: string | null }) => void;
  /** Linha indicada pela validação: vem selecionada, com o caminho até ela expandido. */
  focusLine?: number | null;
}) {
  const focusKey = focusLine !== null && lines.some((l) => l.line_no === focusLine) ? String(focusLine) : null;
  const [expanded, setExpanded] = useState<Set<string>>(() =>
    focusKey ? ancestorKeys(lines, new Set([focusKey])) : new Set<string>(),
  );
  const [term, setTerm] = useState("");
  const [filters, setFilters] = useState<TreeFilters>({});
  const [table, setTable] = useState(false);
  const [selectedKey, setSelectedKey] = useState<string | null>(focusKey);

  const roots = useMemo(() => topLines(lines), [lines]);
  const matched = useMemo(() => matchingLines(lines, term), [lines, term]);
  const searching = term.trim().length > 0;
  const filtering = Object.values(filters).some(Boolean);

  const ancestors = useMemo(() => (searching ? ancestorKeys(lines, matched) : new Set<string>()), [lines, matched, searching]);
  const effectiveExpanded = useMemo(() => {
    if (!searching) return expanded;
    return new Set([...expanded, ...ancestors]);
  }, [expanded, ancestors, searching]);

  const rows = useMemo(() => visibleRows(lines, effectiveExpanded, roots), [lines, effectiveExpanded, roots]);
  const shownRows = useMemo(() => {
    if (!searching && !filtering) return rows;
    return rows.filter((r) => {
      if (ancestors.has(r.key)) return true;
      const passSearch = !searching || matched.has(r.key);
      return passSearch && passesFilters(r.line, filters);
    });
  }, [rows, searching, filtering, ancestors, matched, filters]);

  const tableLines = useMemo(() => {
    const base = searching ? lines.filter((l) => matched.has(nodeKey(l))) : lines;
    return base.filter((l) => passesFilters(l, filters));
  }, [lines, matched, searching, filters]);

  const selected = lines.find((l) => nodeKey(l) === selectedKey) ?? null;
  const children = childrenIndex(lines);
  const keysWithChildren = useMemo(() => expandableKeys(lines), [lines]);

  const levels = distinct(lines, (l) => (l.level === null ? null : String(l.level)));
  const units = distinct(lines, (l) => l.unit);
  const revs = distinct(lines, (l) => l.rev);
  const categories = distinct(lines, (l) => l.category);

  function toggle(key: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
      <div className="min-w-0 space-y-3">
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-xs">
            Buscar por código ou descrição
            <input
              type="search"
              value={term}
              onChange={(e) => setTerm(e.target.value)}
              aria-label="Buscar na estrutura"
              className={`${inputClass} mt-1 block w-64`}
            />
          </label>
          <FilterSelect label="Nível" value={filters.level} options={levels} onChange={(v) => setFilters({ ...filters, level: v })} />
          <FilterSelect label="Unidade" value={filters.unit} options={units} onChange={(v) => setFilters({ ...filters, unit: v })} />
          <FilterSelect label="Revisão" value={filters.rev} options={revs} onChange={(v) => setFilters({ ...filters, rev: v })} />
          <FilterSelect label="Categoria" value={filters.category} options={categories} onChange={(v) => setFilters({ ...filters, category: v })} />
          <button type="button" className={buttonClass} onClick={() => setExpanded(new Set(keysWithChildren))}>
            Expandir tudo
          </button>
          <button type="button" className={buttonClass} onClick={() => setExpanded(new Set())}>
            Recolher tudo
          </button>
          <button type="button" className={buttonClass} onClick={() => setTable((t) => !t)} aria-pressed={table}>
            {table ? "Ver como árvore" : "Ver como tabela"}
          </button>
        </div>
        <p className="text-xs text-[var(--color-muted)]" role="status">
          {table
            ? `${tableLines.length} linha(s)`
            : `${shownRows.length} linha(s) visíveis${shownRows.length > MAX_ROWS ? ` · mostrando ${MAX_ROWS}; refine a busca` : ""}`}
          {searching ? ` · ${matched.size} resultado(s) destacado(s)` : ""}
        </p>

        {table ? (
          <TableList lines={tableLines} selectedKey={selectedKey} onSelect={setSelectedKey} />
        ) : (
          <ul role="tree" aria-label="Árvore de materiais" className="max-h-[70vh] overflow-auto rounded-md border border-[var(--color-border)]">
            {shownRows.slice(0, MAX_ROWS).map((row) => {
              const hit = searching && matched.has(row.key);
              const isSelected = row.key === selectedKey;
              return (
                <li
                  key={row.key}
                  role="treeitem"
                  aria-level={row.depth + 1}
                  aria-expanded={row.hasChildren ? row.expanded : undefined}
                  aria-selected={isSelected}
                  className={`flex items-center gap-2 border-b border-[var(--color-border)] px-2 py-1 text-sm ${
                    hit ? "bg-[var(--color-accent-soft,rgba(245,158,11,0.18))]" : ""
                  } ${isSelected ? "outline outline-1 outline-[var(--color-accent)]" : ""}`}
                  style={{ paddingLeft: `${row.depth * 16 + 8}px` }}
                >
                  {row.hasChildren ? (
                    <button
                      type="button"
                      aria-label={`${row.expanded ? "Recolher" : "Expandir"} ${row.line.child ?? "linha"}`}
                      onClick={() => toggle(row.key)}
                      className="w-5 text-left"
                    >
                      {row.expanded ? "▾" : "▸"}
                    </button>
                  ) : (
                    <span className="inline-block w-5" />
                  )}
                  <button type="button" onClick={() => setSelectedKey(row.key)} className="flex min-w-0 flex-1 items-center gap-2 text-left">
                    <span className="font-mono">{row.line.child ?? "(sem código)"}</span>
                    <span className="truncate text-[var(--color-muted)]">{row.line.description ?? ""}</span>
                    {row.cycle ? <span className="text-[var(--color-danger)]">ciclo</span> : null}
                    {row.line.inferred_parent ? <span className="text-xs text-[var(--color-muted)]">pai inferido</span> : null}
                  </button>
                  {onPickPart && row.line.child ? (
                    <button type="button" className={buttonClass} onClick={() => onPickPart({ code: row.line.child as string, unit: row.line.unit, description: row.line.description })}>
                      + kit
                    </button>
                  ) : null}
                  <span className="whitespace-nowrap font-mono text-xs" title="Quantidade local">
                    {row.qtyLocal ?? "(ausente)"} {row.line.unit ?? ""}
                  </span>
                  <span className="whitespace-nowrap font-mono text-xs text-[var(--color-muted)]" title="Quantidade acumulada por 1 unidade do topo">
                    = {row.qtyAccumulated ?? "—"}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <aside aria-label="Detalhes do componente" className="min-w-0 space-y-3 text-sm">
        {selected ? (
          <Details
            key={selected.line_no}
            line={selected}
            lines={lines}
            usage={usageOf(lines, selected.child ?? "")}
            childCount={children.get(selected.child ?? "")?.length ?? 0}
            revisionId={revisionId}
            onSelect={setSelectedKey}
            onNewRevision={onNewRevision}
            definedCodes={[...new Set(lines.map((l) => l.child).filter((c): c is string => Boolean(c)))].sort()}
          />
        ) : (
          <p className="text-[var(--color-muted)]">Selecione um componente para ver detalhes, onde ele aparece e editar.</p>
        )}
      </aside>
    </div>
  );
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string | undefined;
  options: string[];
  onChange: (value: string | undefined) => void;
}) {
  return (
    <label className="text-xs">
      {label}
      <select aria-label={`Filtrar por ${label.toLowerCase()}`} value={value ?? ""} onChange={(e) => onChange(e.target.value || undefined)} className={`${inputClass} mt-1 block`}>
        <option value="">Todos</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </label>
  );
}

function TableList({ lines, selectedKey, onSelect }: { lines: BomLine[]; selectedKey: string | null; onSelect: (key: string) => void }) {
  return (
    <div className="max-h-[70vh] overflow-auto rounded-md border border-[var(--color-border)]">
      <table className="w-full text-xs">
        <caption className="sr-only">Lista de componentes da revisão</caption>
        <thead className="sticky top-0 bg-[var(--color-surface)] text-left text-[var(--color-muted)]">
          <tr>
            <th className="px-2 py-1">Linha</th>
            <th className="px-2 py-1">Conjunto pai</th>
            <th className="px-2 py-1">Código</th>
            <th className="px-2 py-1">Descrição</th>
            <th className="px-2 py-1">Qtd.</th>
            <th className="px-2 py-1">Unidade</th>
            <th className="px-2 py-1">Revisão</th>
          </tr>
        </thead>
        <tbody>
          {lines.slice(0, 1500).map((l) => (
            <tr
              key={l.line_no}
              onClick={() => onSelect(nodeKey(l))}
              className={`cursor-pointer border-t border-[var(--color-border)] ${selectedKey === nodeKey(l) ? "bg-[var(--color-border)]" : ""}`}
            >
              <td className="px-2 py-1">{l.line_no}</td>
              <td className="px-2 py-1 font-mono">{l.parent ?? "(topo)"}</td>
              <td className="px-2 py-1 font-mono">{l.child ?? "(sem código)"}</td>
              <td className="px-2 py-1">{l.description ?? ""}</td>
              <td className="px-2 py-1 font-mono">{l.qty ?? "(ausente)"}</td>
              <td className="px-2 py-1">{l.unit ?? ""}</td>
              <td className="px-2 py-1">{l.rev ?? ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Details({
  line,
  lines,
  usage,
  childCount,
  revisionId,
  onSelect,
  onNewRevision,
  definedCodes,
}: {
  line: BomLine;
  lines: BomLine[];
  usage: BomLine[];
  childCount: number;
  revisionId: string;
  onSelect: (key: string) => void;
  onNewRevision: (revisionId: string) => void;
  definedCodes: string[];
}) {
  const [qty, setQty] = useState(line.qty ?? "");
  const [description, setDescription] = useState(line.description ?? "");
  const [child, setChild] = useState("");
  const [childQty, setChildQty] = useState("1");
  const [childUnit, setChildUnit] = useState("UN");
  const [newCode, setNewCode] = useState("");
  const [moveTo, setMoveTo] = useState("");
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function apply(edits: Parameters<typeof editBom>[1], doneText: string) {
    setBusy(true);
    setMessage(null);
    try {
      const result = await editBom(revisionId, edits);
      setMessage(doneText);
      onNewRevision(result.revision.id);
    } catch (error) {
      setMessage(errorText(error));
    } finally {
      setBusy(false);
    }
  }

  const parentLine = lines.find((l) => l.child === line.parent);

  return (
    <div className="space-y-3 rounded-md border border-[var(--color-border)] p-3">
      <h3 className="font-mono text-sm font-medium">{line.child ?? "(sem código)"}</h3>
      <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1 text-xs">
        <dt className="text-[var(--color-muted)]">Descrição</dt>
        <dd>{line.description ?? "(sem descrição)"}</dd>
        <dt className="text-[var(--color-muted)]">Quantidade</dt>
        <dd className="font-mono">{line.qty ?? "(ausente)"} {line.unit ?? ""}</dd>
        <dt className="text-[var(--color-muted)]">Conjunto pai</dt>
        <dd className="font-mono">
          {line.parent ?? "(topo)"}
          {parentLine ? (
            <button type="button" className={`${buttonClass} ml-2`} onClick={() => onSelect(nodeKey(parentLine))}>
              Ir ao pai
            </button>
          ) : null}
        </dd>
        <dt className="text-[var(--color-muted)]">Revisão · Posição</dt>
        <dd>{line.rev ?? "—"} · {line.position ?? "—"}</dd>
        <dt className="text-[var(--color-muted)]">Fabricante · Part number</dt>
        <dd>{line.manufacturer ?? "—"} · {line.part_number ?? "—"}</dd>
        <dt className="text-[var(--color-muted)]">Filhos diretos</dt>
        <dd>{childCount}</dd>
        <dt className="text-[var(--color-muted)]">Linha da planilha</dt>
        <dd>{line.source_row ?? "—"}</dd>
      </dl>

      <div>
        <h4 className="text-xs font-medium">Aparece em {usage.length} conjunto(s)</h4>
        <ul className="mt-1 space-y-1 text-xs">
          {usage.map((u) => (
            <li key={u.line_no} className="flex items-center gap-2">
              <span className="font-mono">{u.parent ?? "(topo)"}</span>
              <span>× {u.qty ?? "(ausente)"}</span>
              {u.parent ? (
                <button
                  type="button"
                  className={buttonClass}
                  onClick={() => {
                    const target = lines.find((l) => l.child === u.parent);
                    if (target) onSelect(nodeKey(target));
                  }}
                >
                  Ir ao conjunto
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      </div>

      <fieldset className="space-y-2 border-t border-[var(--color-border)] pt-3 text-xs" disabled={busy}>
        <legend className="font-medium">Editar (cria nova revisão; a anterior permanece)</legend>
        <div className="flex gap-2">
          <input aria-label="Nova quantidade" value={qty} onChange={(e) => setQty(e.target.value)} className={`${inputClass} w-24`} />
          <button type="button" className={buttonClass} onClick={() => void apply([{ op: "set_qty", line_no: line.line_no, qty }], "Quantidade alterada.")}>
            Gravar quantidade
          </button>
        </div>
        <div className="flex gap-2">
          <input aria-label="Nova descrição" value={description} onChange={(e) => setDescription(e.target.value)} className={`${inputClass} flex-1`} />
          <button
            type="button"
            className={buttonClass}
            onClick={() => void apply([{ op: "set_description", code: line.child ?? "", description }], "Descrição alterada em todas as ocorrências do código.")}
            disabled={!line.child}
          >
            Gravar descrição
          </button>
        </div>
        <div className="space-y-1 rounded border border-[var(--color-border)] p-2">
          <p className="font-medium">Adicionar componente a este conjunto</p>
          <div className="flex flex-wrap gap-1">
            <input aria-label="Código do componente a adicionar" placeholder="Código" value={child} onChange={(e) => setChild(e.target.value)} className={`${inputClass} w-32`} />
            <input aria-label="Quantidade do componente" value={childQty} onChange={(e) => setChildQty(e.target.value)} className={`${inputClass} w-16`} />
            <input aria-label="Unidade do componente" value={childUnit} onChange={(e) => setChildUnit(e.target.value)} className={`${inputClass} w-16`} />
            <button
              type="button"
              className={buttonClass}
              disabled={!child.trim() || !line.child}
              onClick={() =>
                void apply(
                  [{ op: "add_line", parent: line.child ?? "", child: child.trim(), qty: childQty, unit: childUnit }],
                  "Componente adicionado.",
                )
              }
            >
              Adicionar
            </button>
          </div>
        </div>
        <div className="flex gap-2">
          <select aria-label="Mover para o conjunto" value={moveTo} onChange={(e) => setMoveTo(e.target.value)} className={`${inputClass} flex-1`}>
            <option value="">Mover para outro conjunto…</option>
            {definedCodes.filter((c) => c !== line.parent).map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <button
            type="button"
            className={buttonClass}
            disabled={!moveTo}
            onClick={() => void apply([{ op: "move_line", line_no: line.line_no, parent: moveTo }], `Componente movido para ${moveTo}.`)}
          >
            Mover
          </button>
        </div>
        <div className="flex gap-2">
          <input aria-label="Novo código do conjunto duplicado" placeholder="Novo código" value={newCode} onChange={(e) => setNewCode(e.target.value)} className={`${inputClass} flex-1`} />
          <button
            type="button"
            className={buttonClass}
            disabled={!newCode.trim() || !line.child}
            onClick={() => void apply([{ op: "duplicate_subassembly", code: line.child ?? "", new_code: newCode.trim() }], "Filhos diretos duplicados sob o novo código. Subconjuntos internos continuam compartilhados.")}
          >
            Duplicar só filhos diretos
          </button>
          <button
            type="button"
            className={buttonClass}
            disabled={!newCode.trim() || !line.child}
            title="Copia o conjunto e todos os descendentes. Subconjuntos internos recebem código com sufixo -CP."
            onClick={() => void apply([{ op: "duplicate_subtree", code: line.child ?? "", new_code: newCode.trim(), suffix: "-CP" }], "Conjunto completo duplicado (descendentes incluídos; subconjuntos internos com sufixo -CP).")}
          >
            Duplicar conjunto completo
          </button>
        </div>
        <div className="flex gap-2">
          {confirmRemove ? (
            <>
              <button type="button" className={buttonClass} onClick={() => void apply([{ op: "remove_line", line_no: line.line_no }], "Linha removida desta revisão.")}>
                Confirmar remoção
              </button>
              <button type="button" className={buttonClass} onClick={() => setConfirmRemove(false)}>
                Cancelar
              </button>
            </>
          ) : (
            <button type="button" className={buttonClass} onClick={() => setConfirmRemove(true)}>
              Remover esta linha
            </button>
          )}
        </div>
      </fieldset>
      {message ? <p role="status" className="text-xs">{message}</p> : null}
    </div>
  );
}
