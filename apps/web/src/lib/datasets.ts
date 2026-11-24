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

export function listDatasets(): Promise<DatasetSummary[]> {
  return apiFetch<DatasetSummary[]>("/api/v1/datasets");
}

export function getDataset(id: string): Promise<DatasetDetail> {
  return apiFetch<DatasetDetail>(`/api/v1/datasets/${id}`);
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
