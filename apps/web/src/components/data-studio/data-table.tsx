"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { errorText } from "@/components/data-studio/templates-section";
import {
  NUMERIC_OPS,
  OP_LABELS,
  VALUE_OPS,
  queryRows,
  type FilterClause,
  type FilterOp,
  type RowsQuery,
} from "@/lib/rows";

const inputClass = "rounded-md border border-[var(--color-border)] bg-transparent px-2 py-1 text-sm";
const buttonClass =
  "rounded-md border border-[var(--color-border)] px-2 py-1 text-sm hover:bg-[var(--color-border)] disabled:opacity-50";
const PAGE_SIZES = [25, 50, 100];
const OPS = Object.keys(OP_LABELS) as FilterOp[];

/** Mostra os três estados de célula de forma distinta, sem alterar o valor. */
export function CellValue({ value }: { value: string | null }) {
  if (value === null) {
    return (
      <span className="italic text-[var(--color-muted)]" title="Desconhecido">
        ∅ desconhecido
      </span>
    );
  }
  if (value === "") {
    return (
      <span className="text-[var(--color-muted)]" title="Vazio">
        (vazio)
      </span>
    );
  }
  return <span className="font-mono">{value}</span>;
}

export function DataTable({ datasetId, columns }: { datasetId: string; columns: string[] }) {
  const [q, setQ] = useState("");
  const [filters, setFilters] = useState<FilterClause[]>([]);
  const [sort, setSort] = useState<{ column: string; dir: "asc" | "desc" } | null>(null);
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);

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
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-[var(--color-surface)] text-left text-[var(--color-muted)]">
            <tr>
              <th className="px-2 py-1 font-medium">Linha</th>
              {columns.map((c) => {
                const active = sort?.column === c ? sort.dir : null;
                return (
                  <th
                    key={c}
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
            {(rows.data?.rows ?? []).map((row) => (
              <tr key={row.row_number} className="border-t border-[var(--color-border)]">
                <td className="px-2 py-1 text-[var(--color-muted)]">{row.row_number}</td>
                {row.values.map((value, i) => (
                  <td key={i} className="px-2 py-1 text-xs">
                    <CellValue value={value} />
                  </td>
                ))}
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
    </section>
  );
}
