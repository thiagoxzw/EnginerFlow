/** Cliente de consulta de linhas (filtros, pesquisa, ordenação e página). */

import { apiFetch } from "@/lib/api";

export type FilterOp =
  | "eq"
  | "neq"
  | "contains"
  | "starts"
  | "gt"
  | "gte"
  | "lt"
  | "lte"
  | "between"
  | "is_empty"
  | "not_empty"
  | "is_unknown"
  | "not_unknown"
  | "is_zero"
  | "not_zero";

export interface FilterClause {
  column: string;
  op: FilterOp;
  value?: string;
  value2?: string;
}

export interface RowsQuery {
  offset: number;
  limit: number;
  q: string;
  filters: FilterClause[];
  sort: string | null;
  dir: "asc" | "desc";
}

export interface RowItem {
  row_number: number;
  values: (string | null)[];
}

export interface RowsPage {
  total: number;
  offset: number;
  limit: number;
  columns: string[];
  rows: RowItem[];
}

/** Operadores que exigem valor; os demais são de estado (vazio, desconhecido, zero). */
export const VALUE_OPS: FilterOp[] = ["eq", "neq", "contains", "starts", "gt", "gte", "lt", "lte"];
export const NUMERIC_OPS: FilterOp[] = ["gt", "gte", "lt", "lte", "between"];

export const OP_LABELS: Record<FilterOp, string> = {
  eq: "é igual a",
  neq: "é diferente de",
  contains: "contém",
  starts: "começa com",
  gt: "maior que",
  gte: "maior ou igual a",
  lt: "menor que",
  lte: "menor ou igual a",
  between: "entre",
  is_empty: "está vazio",
  not_empty: "não está vazio",
  is_unknown: "é desconhecido",
  not_unknown: "não é desconhecido",
  is_zero: "é zero",
  not_zero: "não é zero",
};

/** Filtro só é enviado quando completo. Validação de regra fica na API. */
export function isComplete(clause: FilterClause): boolean {
  if (clause.op === "between") {
    return Boolean(clause.value?.trim()) && Boolean(clause.value2?.trim());
  }
  if (VALUE_OPS.includes(clause.op)) {
    return Boolean(clause.value?.trim());
  }
  return true;
}

export function buildRowsParams(query: RowsQuery): URLSearchParams {
  const params = new URLSearchParams({
    offset: String(query.offset),
    limit: String(query.limit),
  });
  if (query.q.trim()) {
    params.set("q", query.q.trim());
  }
  const filters = query.filters.filter(isComplete).map((f) => ({
    column: f.column,
    op: f.op,
    ...(f.value !== undefined && f.op !== "is_empty" ? { value: f.value } : {}),
    ...(f.op === "between" ? { value2: f.value2 } : {}),
  }));
  if (filters.length > 0) {
    params.set("filters", JSON.stringify(filters));
  }
  if (query.sort) {
    params.set("sort", query.sort);
    params.set("dir", query.dir);
  }
  return params;
}

export function queryRows(datasetId: string, query: RowsQuery): Promise<RowsPage> {
  return apiFetch<RowsPage>(`/api/v1/datasets/${datasetId}/rows?${buildRowsParams(query)}`);
}

export interface SelectionPage {
  count: number;
  row_numbers: number[];
}

/** Números de TODAS as linhas que casam com os filtros atuais (não só a página). */
export function selectRows(
  datasetId: string,
  q: string,
  filters: FilterClause[],
): Promise<SelectionPage> {
  const complete = filters.filter(isComplete).map((f) => ({
    column: f.column,
    op: f.op,
    ...(f.value !== undefined && f.op !== "is_empty" ? { value: f.value } : {}),
    ...(f.op === "between" ? { value2: f.value2 } : {}),
  }));
  return apiFetch<SelectionPage>(`/api/v1/datasets/${datasetId}/rows/selection`, {
    method: "POST",
    body: JSON.stringify({ q: q.trim(), filters: complete }),
  });
}
