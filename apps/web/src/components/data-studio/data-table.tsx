"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  useState,
  type ClipboardEvent,
  type KeyboardEvent,
  type MouseEvent as ReactMouseEvent,
} from "react";

import { EditableCell, commitCells, commitOperation } from "@/components/data-studio/cell-editor";
import { StructureMenu, type MenuItem } from "@/components/data-studio/structure-menu";
import { RowActions } from "@/components/data-studio/row-actions";
import { errorText } from "@/components/data-studio/templates-section";
import { copyText, parseTsv, planPaste, type CellTarget, type PasteCell, type PastePlan } from "@/lib/clipboard";
import { invalidateDataset } from "@/lib/invalidate";
import { clearRangeCells, extendRange, pageRange, rangeContains, type CellRange } from "@/lib/range";
import {
  NUMERIC_OPS,
  OP_LABELS,
  VALUE_OPS,
  queryRows,
  selectRows,
  type FilterClause,
  type FilterOp,
  type RowsQuery,
} from "@/lib/rows";

const inputClass = "rounded-md border border-[var(--color-border)] bg-transparent px-2 py-1 text-sm";
const buttonClass =
  "rounded-md border border-[var(--color-border)] px-2 py-1 text-sm hover:bg-[var(--color-border)] disabled:opacity-50";
const PAGE_SIZES = [25, 50, 100];
/** Lê as colunas ocultas guardadas neste navegador. Falha de armazenamento não quebra a tabela. */
export function readHiddenColumns(key: string): Set<string> {
  try {
    const raw = window.localStorage.getItem(key);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return new Set(Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === "string") : []);
  } catch {
    return new Set();
  }
}

export function writeHiddenColumns(key: string, hidden: Set<string>): void {
  try {
    window.localStorage.setItem(key, JSON.stringify([...hidden]));
  } catch {
    // armazenamento indisponível (navegação privada, por exemplo): a preferência vale só nesta sessão
  }
}

/** Colagens com mais células que isto pedem confirmação explícita antes de gravar. */
const CONFIRM_PASTE_ABOVE = 20;
const OPS = Object.keys(OP_LABELS) as FilterOp[];

export { CellValue } from "@/components/data-studio/cell-value";

export function DataTable({ datasetId, columns }: { datasetId: string; columns: string[] }) {
  const [q, setQ] = useState("");
  const [filters, setFilters] = useState<FilterClause[]>([]);
  const [sort, setSort] = useState<{ column: string; dir: "asc" | "desc" } | null>(null);
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  // Seleção: manual (linhas marcadas), da página atual ou de todas as que casam com os filtros.
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [scope, setScope] = useState<"manual" | "page" | "filter">("manual");
  const [selectMessage, setSelectMessage] = useState<string | null>(null);
  // Confirmação de ações em linhas: fica visível mesmo depois que a seleção é limpa.
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  // Colagem: mensagens de validação e confirmação para colagens grandes.
  const queryClient = useQueryClient();
  const [pasteMessage, setPasteMessage] = useState<string | null>(null);
  const [pendingPaste, setPendingPaste] = useState<(PastePlan & { ok: true }) | null>(null);
  const [pasting, setPasting] = useState(false);
  // Intervalo de células (mouse e teclado) e limpeza grande que aguarda confirmação.
  // A seleção guarda a chave da visão em que foi feita: trocar página, filtro, ordem ou busca a descarta.
  const [selection, setSelection] = useState<{ scope: string; range: CellRange } | null>(null);
  const [pendingClear, setPendingClear] = useState<{ scope: string; cells: PasteCell[] } | null>(null);
  const scopeKey = `${offset}|${limit}|${q}|${JSON.stringify(sort)}|${JSON.stringify(filters)}`;
  const range = selection && selection.scope === scopeKey ? selection.range : null;
  // Menu contextual (linha ou coluna) e ação estrutural que aguarda confirmação (exclusão de coluna).
  const [menu, setMenu] = useState<{ x: number; y: number; label: string; items: MenuItem[] } | null>(null);
  const [pendingAction, setPendingAction] = useState<{
    scope: string;
    message: string;
    confirmLabel: string;
    run: () => Promise<void>;
  } | null>(null);

  function commitRange(next: CellRange | null) {
    setSelection(next ? { scope: scopeKey, range: next } : null);
  }
  // Colunas ocultas: preferência de visualização desta tabela, guardada só neste navegador.
  const hiddenKey = `engiflow:colunas-ocultas:${datasetId}`;
  const [hidden, setHidden] = useState<Set<string>>(() => readHiddenColumns(hiddenKey));

  function toggleHidden(column: string) {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(column)) {
        next.delete(column);
      } else if (columns.length - next.size > 1) {
        next.add(column); // nunca oculta todas as colunas
      }
      writeHiddenColumns(hiddenKey, next);
      return next;
    });
  }

  /** Célula de origem do evento de copiar/colar, com o valor exibido. Null fora das células. */
  function focusedCell(target: EventTarget | null): (CellTarget & { value: string | null }) | null {
    if (!(target instanceof HTMLElement)) return null;
    const cell = target.closest<HTMLElement>('td[data-cell="1"]');
    if (!cell) return null;
    const rowIndex = Number(cell.dataset.rowIndex);
    const colIndex = Number(cell.dataset.colIndex);
    const row = rows.data?.rows[rowIndex];
    if (!row) return null;
    return { rowNumber: row.row_number, rowIndex, colIndex, value: row.values[colIndex] ?? null };
  }

  function onCopy(event: ClipboardEvent<HTMLTableElement>) {
    if (event.target instanceof HTMLInputElement) return; // edição de célula usa o copiar do campo
    const focus = focusedCell(event.target);
    if (!focus) return;
    const selectedValues = (rows.data?.rows ?? [])
      .filter((r) => selected.has(r.row_number))
      .map((r) => r.values);
    event.preventDefault();
    event.clipboardData.setData("text/plain", copyText(focus.value, selectedValues));
  }

  function onPaste(event: ClipboardEvent<HTMLTableElement>) {
    if (event.target instanceof HTMLInputElement) return;
    const focus = focusedCell(event.target);
    if (!focus) return;
    event.preventDefault();
    const matrix = parseTsv(event.clipboardData.getData("text/plain"));
    const width = Math.max(0, ...matrix.map((r) => r.length));
    const crossesHidden = Array.from({ length: width }, (_, k) => focus.colIndex + k).some((k) =>
      hidden.has(columns[k] ?? ""),
    );
    if (crossesHidden) {
      // Colar numa coluna oculta sem perceber seria uma alteração invisível: a colagem é recusada.
      setPasteMessage("A colagem atravessa colunas ocultas. Mostre-as no menu “Colunas” para colar.");
      return;
    }
    const plan = planPaste(
      matrix,
      focus,
      columns,
      (rows.data?.rows ?? []).map((r) => r.row_number),
    );
    setPasteMessage(null);
    if (!plan.ok) {
      setPasteMessage(plan.reason); // recusa antes de qualquer alteração
      return;
    }
    // Colagens grandes pedem confirmação explícita; as pequenas são aplicadas e desfeitas pelo histórico.
    if (plan.cells.length > CONFIRM_PASTE_ABOVE) {
      setPendingPaste(plan);
      return;
    }
    void applyPaste(plan.cells);
  }

  function pointer(rowIndex: number, colIndex: number, shift: boolean) {
    commitRange(
      shift && range
        ? { anchor: range.anchor, focus: { rowIndex, colIndex } }
        : { anchor: { rowIndex, colIndex }, focus: { rowIndex, colIndex } },
    );
  }

  function extend(rowIndex: number, colIndex: number, rowDelta: number, colDelta: number) {
    const maxRow = (rows.data?.rows.length ?? 1) - 1;
    const maxCol = columns.length - 1;
    commitRange(
      extendRange(
        range ?? { anchor: { rowIndex, colIndex }, focus: { rowIndex, colIndex } },
        rowDelta,
        colDelta,
        maxRow,
        maxCol,
      ),
    );
  }

  /** Delete/Backspace: limpa o intervalo visível. Grandes limpezas pedem confirmação, como as colagens. */
  function clearSelection() {
    if (!range || !rows.data) return;
    const cells = clearRangeCells(range, rows.data.rows, columns, hidden);
    if (cells.length === 0) return;
    if (cells.length > CONFIRM_PASTE_ABOVE) {
      setPendingClear({ scope: scopeKey, cells });
      return;
    }
    void applyClear(cells);
  }

  async function applyClear(cells: PasteCell[]) {
    setPasting(true);
    setPasteMessage(null);
    try {
      await commitCells(datasetId, cells);
      await invalidateDataset(queryClient, datasetId);
      setActionMessage(`${cells.length} célula(s) limpas. Uma única operação: desfazer reverte tudo.`);
    } catch (error) {
      setPasteMessage(errorText(error));
    } finally {
      setPasting(false);
      setPendingClear(null);
    }
  }

  /** Executa uma operação estrutural e registra a mensagem; erros aparecem sem alterar nada. */
  async function runStructure(code: string, params: Record<string, unknown>, message: string) {
    setPasting(true);
    setPasteMessage(null);
    try {
      await commitOperation(datasetId, code, params);
      await invalidateDataset(queryClient, datasetId);
      setActionMessage(message);
    } catch (error) {
      setPasteMessage(errorText(error));
    } finally {
      setPasting(false);
      setPendingAction(null);
    }
  }

  /** Nome livre para uma coluna nova: “base”, “base 2”, “base 3”… sem conflito de maiúsculas. */
  function freeColumnName(base: string): string {
    const taken = new Set(columns.map((c) => c.toLowerCase()));
    let name = base;
    let n = 2;
    while (taken.has(name.toLowerCase())) {
      name = `${base} ${n}`;
      n += 1;
    }
    return name;
  }

  function openRowMenu(event: ReactMouseEvent, rowNumber: number) {
    event.preventDefault();
    setMenu({
      x: event.clientX,
      y: event.clientY,
      label: `Linha ${rowNumber}`,
      items: [
        {
          label: "Inserir linha abaixo",
          run: () =>
            void runStructure(
              "insert_rows",
              { after_row_number: rowNumber, count: 1 },
              `Linha vazia inserida após a linha ${rowNumber}. Desfazer reverte.`,
            ),
        },
        {
          label: "Duplicar linha",
          run: () =>
            void runStructure(
              "duplicate_rows",
              { row_numbers: [rowNumber] },
              `Linha ${rowNumber} duplicada. Desfazer reverte.`,
            ),
        },
        {
          label: "Excluir linha",
          danger: true,
          run: () =>
            void runStructure(
              "delete_rows",
              { row_numbers: [rowNumber] },
              `Linha ${rowNumber} excluída logicamente. Desfazer reverte.`,
            ),
        },
      ],
    });
  }

  function openColumnMenu(event: ReactMouseEvent, column: string) {
    event.preventDefault();
    setMenu({
      x: event.clientX,
      y: event.clientY,
      label: `Coluna ${column}`,
      items: [
        {
          label: "Inserir coluna à direita",
          run: () =>
            void runStructure(
              "insert_column",
              { after_column: column, name: freeColumnName("Nova coluna") },
              "Coluna vazia inserida. Renomeie-a pelo cabeçalho se precisar. Desfazer reverte.",
            ),
        },
        {
          label: "Duplicar coluna",
          run: () =>
            void runStructure(
              "duplicate_column",
              { column, name: freeColumnName(`${column} (cópia)`) },
              `Coluna ${column} duplicada. Desfazer reverte.`,
            ),
        },
        {
          label: "Excluir coluna",
          danger: true,
          run: () =>
            setPendingAction({
              scope: scopeKey,
              message: `Excluir a coluna “${column}”? Exclusão lógica: o desfazer a restaura.`,
              confirmLabel: "Confirmar exclusão",
              run: () =>
                runStructure("delete_columns", { columns: [column] }, `Coluna ${column} excluída. Desfazer reverte.`),
            }),
        },
      ],
    });
  }

  /** Ctrl+A fora da edição seleciona as células da página exibida (nunca as de outras páginas). */
  function onKeyDown(event: KeyboardEvent<HTMLTableElement>) {
    if (event.target instanceof HTMLInputElement) return;
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "a") {
      const all = pageRange(rows.data?.rows.length ?? 0, columns.length);
      if (!all) return;
      event.preventDefault();
      commitRange(all);
      setActionMessage("Células da página selecionadas. Delete limpa a seleção; desfazer reverte.");
    }
  }

  async function applyPaste(cells: PasteCell[]) {
    setPasting(true);
    setPasteMessage(null);
    try {
      await commitCells(datasetId, cells);
      await invalidateDataset(queryClient, datasetId);
      setActionMessage(`${cells.length} célula(s) coladas. Uma única operação: desfazer reverte tudo.`);
    } catch (error) {
      setPasteMessage(errorText(error));
    } finally {
      setPasting(false);
      setPendingPaste(null);
    }
  }

  const query: RowsQuery = {
    offset,
    limit,
    q,
    filters,
    sort: sort?.column ?? null,
    dir: sort?.dir ?? "asc",
  };
  const rows = useQuery({
    queryKey: ["rows", datasetId, query],
    queryFn: () => queryRows(datasetId, query),
    placeholderData: (previous) => previous,
  });

  const total = rows.data?.total ?? 0;
  const first = total === 0 ? 0 : offset + 1;
  const last = Math.min(offset + limit, total);

  function resetPage() {
    setOffset(0);
  }

  function addFilter() {
    setFilters((prev) => [...prev, { column: columns[0] ?? "", op: "eq", value: "" }]);
    resetPage();
  }

  function updateFilter(index: number, patch: Partial<FilterClause>) {
    setFilters((prev) => prev.map((f, i) => (i === index ? { ...f, ...patch } : f)));
    resetPage();
  }

  function removeFilter(index: number) {
    setFilters((prev) => prev.filter((_, i) => i !== index));
    resetPage();
  }

  function toggleSort(column: string) {
    setSort((prev) => {
      if (prev?.column !== column) return { column, dir: "asc" };
      if (prev.dir === "asc") return { column, dir: "desc" };
      return null;
    });
    resetPage();
  }

  return (
    <section className="space-y-3" aria-labelledby="linhas">
      <h2 id="linhas" className="font-medium">
        Dados
      </h2>

      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor="busca" className="sr-only">
          Pesquisar em todas as colunas
        </label>
        <input
          id="busca"
          type="search"
          placeholder="Pesquisar em todas as colunas"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            resetPage();
          }}
          className={`${inputClass} min-w-64`}
        />
        <button type="button" onClick={addFilter} className={buttonClass}>
          Adicionar filtro
        </button>
        {filters.length > 0 ? (
          <button
            type="button"
            onClick={() => {
              setFilters([]);
              resetPage();
            }}
            className={buttonClass}
          >
            Limpar filtros
          </button>
        ) : null}
        <label htmlFor="tamanho" className="ml-auto text-sm text-[var(--color-muted)]">
          Linhas por página
        </label>
        <select
          id="tamanho"
          value={limit}
          onChange={(e) => {
            setLimit(Number(e.target.value));
            resetPage();
          }}
          className={inputClass}
        >
          {PAGE_SIZES.map((size) => (
            <option key={size} value={size}>
              {size}
            </option>
          ))}
        </select>
      </div>

      {filters.map((clause, index) => (
        <div key={index} className="flex flex-wrap items-center gap-2">
          <select
            aria-label={`Coluna do filtro ${index + 1}`}
            value={clause.column}
            onChange={(e) => updateFilter(index, { column: e.target.value })}
            className={inputClass}
          >
            {columns.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <select
            aria-label={`Operador do filtro ${index + 1}`}
            value={clause.op}
            onChange={(e) => updateFilter(index, { op: e.target.value as FilterOp })}
            className={inputClass}
          >
            {OPS.map((op) => (
              <option key={op} value={op}>
                {OP_LABELS[op]}
              </option>
            ))}
          </select>
          {VALUE_OPS.includes(clause.op) || clause.op === "between" ? (
            <input
              aria-label={`Valor do filtro ${index + 1}`}
              value={clause.value ?? ""}
              onChange={(e) => updateFilter(index, { value: e.target.value })}
              inputMode={NUMERIC_OPS.includes(clause.op) ? "decimal" : undefined}
              className={inputClass}
            />
          ) : null}
          {clause.op === "between" ? (
            <input
              aria-label={`Valor máximo do filtro ${index + 1}`}
              value={clause.value2 ?? ""}
              onChange={(e) => updateFilter(index, { value2: e.target.value })}
              inputMode="decimal"
              className={inputClass}
            />
          ) : null}
          <button
            type="button"
            onClick={() => removeFilter(index)}
            aria-label={`Remover filtro ${index + 1}`}
            className={buttonClass}
          >
            Remover
          </button>
        </div>
      ))}

      {rows.isError ? (
        <p role="alert" className="text-sm text-[var(--color-danger)]">
          {errorText(rows.error)}
        </p>
      ) : null}

      <div className="max-h-[32rem] overflow-auto rounded-md border border-[var(--color-border)]">
        <table className="w-full text-sm" onCopy={onCopy} onPaste={onPaste} onKeyDown={onKeyDown}>
          <thead className="sticky top-0 bg-[var(--color-surface)] text-left text-[var(--color-muted)]">
            <tr>
              <th className="px-2 py-1 font-medium">
                <input
                  type="checkbox"
                  aria-label="Selecionar todas as linhas desta página"
                  checked={(rows.data?.rows.length ?? 0) > 0 && rows.data?.rows.every((r) => selected.has(r.row_number)) === true}
                  onChange={(e) => {
                    const page = rows.data?.rows.map((r) => r.row_number) ?? [];
                    setSelected(e.target.checked ? new Set(page) : new Set());
                    setScope("page");
                  }}
                />
              </th>
              <th className="px-2 py-1 font-medium">Linha</th>
              {columns.map((c) => {
                if (hidden.has(c)) return null;
                const active = sort?.column === c ? sort.dir : null;
                return (
                  <th
                    key={c}
                    onContextMenu={(e) => openColumnMenu(e, c)}
                    className="px-2 py-1 font-medium"
                    aria-sort={active === "asc" ? "ascending" : active === "desc" ? "descending" : "none"}
                  >
                    <button type="button" onClick={() => toggleSort(c)} className="hover:underline">
                      {c}
                      {active === "asc" ? " ▲" : active === "desc" ? " ▼" : ""}
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {(rows.data?.rows ?? []).map((row, rowIndex) => (
              <tr key={row.row_number} className="border-t border-[var(--color-border)]">
                <td className="px-2 py-1">
                  <input
                    type="checkbox"
                    aria-label={`Selecionar linha ${row.row_number}`}
                    checked={selected.has(row.row_number)}
                    onChange={(e) => {
                      setSelected((prev) => {
                        const next = new Set(prev);
                        if (e.target.checked) next.add(row.row_number);
                        else next.delete(row.row_number);
                        return next;
                      });
                      setScope("manual");
                    }}
                  />
                </td>
                <td
                  className="px-2 py-1 text-[var(--color-muted)]"
                  onContextMenu={(e) => openRowMenu(e, row.row_number)}
                >
                  {row.row_number}
                </td>
                {row.values.map((value, i) =>
                  hidden.has(columns[i] ?? "") ? null : (
                    <EditableCell
                      key={i}
                      datasetId={datasetId}
                      rowNumber={row.row_number}
                      rowIndex={rowIndex}
                      colIndex={i}
                      column={columns[i] ?? ""}
                      value={value}
                      range={{
                        inRange: rangeContains(range, rowIndex, i),
                        onPointer: pointer,
                        onExtend: (rowDelta, colDelta) => extend(rowIndex, i, rowDelta, colDelta),
                        onClear: clearSelection,
                      }}
                    />
                  ),
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span role="status">
          {rows.isPending ? "Carregando…" : `Linhas ${first}–${last} de ${total}`}
        </span>
        <button
          type="button"
          onClick={() => setOffset((o) => Math.max(0, o - limit))}
          disabled={offset === 0}
          className={buttonClass}
        >
          Anterior
        </button>
        <button
          type="button"
          onClick={() => setOffset((o) => o + limit)}
          disabled={offset + limit >= total}
          className={buttonClass}
        >
          Próxima
        </button>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <button
          type="button"
          onClick={async () => {
            try {
              const result = await selectRows(datasetId, q, filters);
              setSelected(new Set(result.row_numbers));
              setScope("filter");
              setSelectMessage(null);
            } catch (error) {
              setSelectMessage(errorText(error));
            }
          }}
          className={buttonClass}
        >
          Selecionar todas que casam com os filtros
        </button>
        <button
          type="button"
          onClick={() => {
            setSelected(new Set());
            setScope("manual");
          }}
          disabled={selected.size === 0}
          className={buttonClass}
        >
          Limpar seleção
        </button>
        {selectMessage ? (
          <span role="alert" className="text-[var(--color-danger)]">
            {selectMessage}
          </span>
        ) : null}
      </div>

      <details className="text-sm">
        <summary className="cursor-pointer">
          Colunas: {columns.length - hidden.size} de {columns.length} visíveis
        </summary>
        <div className="mt-2 flex flex-wrap gap-3">
          {columns.map((c) => (
            <label key={c} className="flex items-center gap-1">
              <input type="checkbox" checked={!hidden.has(c)} onChange={() => toggleHidden(c)} />
              {c}
            </label>
          ))}
        </div>
      </details>

      {pasteMessage ? (
        <p role="alert" className="text-sm text-[var(--color-danger)]">
          {pasteMessage}
        </p>
      ) : null}

      {pendingPaste ? (
        <div role="alert" className="flex flex-wrap items-center gap-2 text-sm">
          <span>
            Colar {pendingPaste.cells.length} célula(s) em {pendingPaste.rows} linha(s)? Uma única operação; o
            desfazer reverte tudo.
          </span>
          <button
            type="button"
            onClick={() => void applyPaste(pendingPaste.cells)}
            disabled={pasting}
            className={buttonClass}
          >
            Confirmar colagem
          </button>
          <button type="button" onClick={() => setPendingPaste(null)} disabled={pasting} className={buttonClass}>
            Cancelar
          </button>
        </div>
      ) : null}

      {pendingAction && pendingAction.scope === scopeKey ? (
        <div role="alert" className="flex flex-wrap items-center gap-2 text-sm">
          <span>{pendingAction.message}</span>
          <button
            type="button"
            onClick={() => void pendingAction.run()}
            disabled={pasting}
            className={buttonClass}
          >
            {pendingAction.confirmLabel}
          </button>
          <button type="button" onClick={() => setPendingAction(null)} disabled={pasting} className={buttonClass}>
            Cancelar
          </button>
        </div>
      ) : null}

      {menu ? (
        <StructureMenu
          x={menu.x}
          y={menu.y}
          label={menu.label}
          items={menu.items}
          onClose={() => setMenu(null)}
        />
      ) : null}

      {pendingClear && pendingClear.scope === scopeKey ? (
        <div role="alert" className="flex flex-wrap items-center gap-2 text-sm">
          <span>
            Limpar {pendingClear.cells.length} célula(s)? Uma única operação; o desfazer reverte tudo.
          </span>
          <button
            type="button"
            onClick={() => void applyClear(pendingClear.cells)}
            disabled={pasting}
            className={buttonClass}
          >
            Confirmar limpeza
          </button>
          <button type="button" onClick={() => setPendingClear(null)} disabled={pasting} className={buttonClass}>
            Cancelar
          </button>
        </div>
      ) : null}

      {actionMessage ? (
        <p role="status" className="text-sm text-[var(--color-muted)]">
          {actionMessage}
        </p>
      ) : null}

      <RowActions
        datasetId={datasetId}
        columns={columns}
        selected={[...selected].sort((a, b) => a - b)}
        onApplied={(confirmation) => {
          setSelected(new Set());
          setScope("manual");
          setActionMessage(confirmation);
        }}
        scopeLabel={
          scope === "filter"
            ? "todas as linhas que casam com os filtros"
            : scope === "page"
              ? "linhas da página atual"
              : "seleção manual"
        }
      />
    </section>
  );
}
