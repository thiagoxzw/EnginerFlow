/** Cliente do Data Studio. Os textos das regras vêm da API; nada é calculado no navegador. */

import { apiFetch } from "@/lib/api";

export const CANONICAL_FIELDS = ["code", "description", "unit", "quantity", "category"] as const;
export type CanonicalField = (typeof CANONICAL_FIELDS)[number];

export const FIELD_LABELS: Record<CanonicalField, string> = {
  code: "Código",
  description: "Descrição",
  unit: "Unidade",
  quantity: "Quantidade",
  category: "Categoria",
};

export interface DatasetSummary {
  id: string;
  name: string;
  source_filename: string;
  file_kind: string;
  sheet_name: string | null;
  columns: string[];
  row_count: number;
  mapping: Partial<Record<CanonicalField, string>>;
  warnings: string[];
  created_at: string;
  /** "import" para arquivos enviados; "derived" para resultados de cruzamento. */
  source_kind?: string;
}

export function isDerived(dataset: Pick<DatasetSummary, "source_kind">): boolean {
  return dataset.source_kind === "derived";
}

export interface DatasetDetail extends DatasetSummary {
  preview: Record<string, string>[];
}

export interface ImportOut {
  created: boolean;
  dataset: DatasetSummary;
}

export interface DuplicatesOut {
  exact_codes: { key: string; row_numbers: number[]; values: string[] }[];
  leading_zero_suspicions: { key_a: string; key_b: string }[];
  similar_descriptions: {
    row_a: number;
    row_b: number;
    value_a: string;
    value_b: string;
    score: number;
    shared_tokens: string[];
  }[];
  note: string;
}

export interface CompareOut {
  only_left_count: number;
  only_right_count: number;
  in_both_count: number;
  only_left: string[];
  only_right: string[];
  leading_zero_candidates: { esquerda: string; direita: string }[];
  note: string;
}

/** Remove campos sem coluna escolhida. Mapeamento vazio não é enviado como valor. */
export function buildMappingPayload(
  form: Partial<Record<CanonicalField, string>>,
): Partial<Record<CanonicalField, string>> {
  const out: Partial<Record<CanonicalField, string>> = {};
  for (const field of CANONICAL_FIELDS) {
    const value = form[field];
    if (value) {
      out[field] = value;
    }
  }
  return out;
}

/** Aviso exibido ao criar uma tabela derivada: nome, linhas, execução, hash e origens preservadas. */
export function derivedNotice(result: {
  name: string;
  row_count: number;
  run_id: string;
  result_sha256: string;
}): string {
  return (
    `Tabela derivada "${result.name}" criada com ${result.row_count} linhas. ` +
    `Execução ${result.run_id.slice(0, 8)} · hash ${result.result_sha256.slice(0, 12)}. ` +
    "As tabelas de origem não foram alteradas."
  );
}

export function listDatasets(): Promise<DatasetSummary[]> {
  return apiFetch<DatasetSummary[]>("/api/v1/datasets");
}

export function getDataset(id: string): Promise<DatasetDetail> {
  return apiFetch<DatasetDetail>(`/api/v1/datasets/${id}`);
}

export interface InspectRow {
  row_number: number;
  values: (string | null)[];
}

/** Resultado da leitura prévia (sem gravar). Ver POST /api/v1/datasets/inspect. */
export interface InspectOut {
  kind: string;
  sheets: string[];
  sheet: string | null;
  header_row: number | null;
  columns: string[];
  preview: InspectRow[];
  warnings: string[];
}

export function inspectUpload(file: File): Promise<InspectOut> {
  const body = new FormData();
  body.append("file", file);
  return apiFetch<InspectOut>("/api/v1/datasets/inspect", { method: "POST", body });
}

export function uploadDataset(file: File, sheet: string): Promise<ImportOut> {
  const body = new FormData();
  body.append("file", file);
  if (sheet.trim()) {
    body.append("sheet", sheet.trim());
  }
  return apiFetch<ImportOut>("/api/v1/datasets", { method: "POST", body });
}

export function saveMapping(
  id: string,
  mapping: Partial<Record<CanonicalField, string>>,
): Promise<DatasetSummary> {
  return apiFetch<DatasetSummary>(`/api/v1/datasets/${id}/mapping`, {
    method: "PUT",
    body: JSON.stringify({ mapping }),
  });
}

export function getDuplicates(id: string, threshold: number): Promise<DuplicatesOut> {
  return apiFetch<DuplicatesOut>(
    `/api/v1/datasets/${id}/duplicates?threshold=${threshold}&descriptions=true`,
  );
}

export function compareDatasets(leftId: string, rightId: string): Promise<CompareOut> {
  return apiFetch<CompareOut>("/api/v1/datasets/compare", {
    method: "POST",
    body: JSON.stringify({ left_id: leftId, right_id: rightId }),
  });
}

export type ExportFormat = "csv" | "xlsx";

/** Extrai o nome do arquivo de um cabeçalho Content-Disposition. Retorna null se ausente. */
export function filenameFromDisposition(header: string | null): string | null {
  if (!header) {
    return null;
  }
  const match = /filename="([^"]+)"/i.exec(header);
  return match?.[1] ?? null;
}

/** Baixa um arquivo exportado pela API (mesma origem, com cookie de sessão). */
export async function downloadExport(
  path: string,
  format: ExportFormat,
  init: RequestInit = {},
): Promise<void> {
  const response = await fetch(`${path}${path.includes("?") ? "&" : "?"}format=${format}`, {
    ...init,
    credentials: "same-origin",
  });
  if (!response.ok) {
    throw new Error(`Exportação falhou (HTTP ${response.status}).`);
  }
  const blob = await response.blob();
  const name =
    filenameFromDisposition(response.headers.get("Content-Disposition")) ?? `resultado.${format}`;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function exportDatasetPath(id: string): string {
  return `/api/v1/datasets/${id}/export`;
}

export function exportDuplicatesPath(id: string, threshold: number): string {
  return `/api/v1/datasets/${id}/duplicates/export?threshold=${threshold}&descriptions=true`;
}

export const EXPORT_COMPARE_PATH = "/api/v1/datasets/compare/export";
