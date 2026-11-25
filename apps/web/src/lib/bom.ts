/** Cliente do BOM Manager: tipos e chamadas à API (/api/v1/bom). Valores são texto, como no servidor. */

import { apiFetch } from "@/lib/api";

export const BOM_FIELDS = [
  { key: "child_code", label: "Código do componente", required: true },
  { key: "parent_code", label: "Código do conjunto pai", required: false },
  { key: "level", label: "Nível hierárquico", required: false },
  { key: "qty", label: "Quantidade", required: true },
  { key: "unit", label: "Unidade de medida", required: false },
  { key: "description", label: "Descrição", required: false },
  { key: "rev", label: "Revisão", required: false },
  { key: "position", label: "Posição", required: false },
  { key: "alt_code", label: "Código alternativo", required: false },
  { key: "manufacturer", label: "Fabricante", required: false },
  { key: "part_number", label: "Part number", required: false },
  { key: "notes", label: "Observações", required: false },
  { key: "category", label: "Categoria", required: false },
] as const;

export type BomMode = "explicit" | "level";

export interface BomRevision {
  id: string;
  number: number;
  label: string;
  parent_revision_id: string | null;
  source_dataset_id: string | null;
  mode: BomMode;
  line_count: number;
  content_sha256: string;
  actor: string;
  created_at: string | null;
}

export interface BomStructure {
  id: string;
  name: string;
  description: string;
  current_revision_id: string | null;
  revisions: BomRevision[];
}

export interface BomLine {
  line_no: number;
  source_row: number | null;
  parent: string | null;
  child: string | null;
  description: string | null;
  qty: string | null;
  unit: string | null;
  rev: string | null;
  position: string | null;
  level: number | null;
  alt_code: string | null;
  manufacturer: string | null;
  part_number: string | null;
  notes: string | null;
  category: string | null;
  inferred_parent: boolean;
}

export interface BomIssue {
  severity: "erro" | "alerta" | "informação";
  rule: string;
  message: string;
  line_no: number | null;
  code: string | null;
}

export interface BomPreview {
  line_count: number;
  roots: string[];
  issue_counts: Record<string, number>;
  issues: BomIssue[];
  inferred_parents: number;
  sample: BomLine[];
}

export interface BomExplosion {
  root: string;
  vehicles: string;
  consolidated: { code: string; unit: string; qty: string }[];
  occurrences: Record<string, number>;
  invalid_lines: number[];
  warnings: string[];
}

export interface BomComparison {
  counts: Record<string, number>;
  changes: { kind: string; child: string; parent: string | null; detail: string; line_no: number | null }[];
  unmatched_removed: string[];
  unmatched_added: string[];
  pending_code_changes: { from: string; to: string; status: string }[];
}

export interface BomCross {
  counts: Record<string, number>;
  items: {
    code: string;
    description: string | null;
    unit: string | null;
    matches: number;
    status: string;
    flags: string[];
    equivalent_candidates: string[];
  }[];
  key_mode: string;
}

export interface BomKit {
  id: string;
  name: string;
  parts: { code: string; qty: string }[];
}

export type BomEdit = Record<string, string | number | undefined> & { op: string };

export function previewBom(body: { dataset_id: string; mapping: Record<string, string>; mode: BomMode }) {
  return apiFetch<BomPreview>("/api/v1/bom/preview", { method: "POST", body: JSON.stringify(body) });
}

export function createBomStructure(body: {
  name: string;
  description: string;
  dataset_id: string;
  mapping: Record<string, string>;
  mode: BomMode;
}) {
  return apiFetch<{ structure: BomStructure; revision_id: string }>("/api/v1/bom/structures", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function listBomStructures() {
  return apiFetch<BomStructure[]>("/api/v1/bom/structures");
}

export function setBomCurrent(structureId: string, revisionId: string) {
  return apiFetch<BomStructure>(`/api/v1/bom/structures/${structureId}/current`, {
    method: "POST",
    body: JSON.stringify({ revision_id: revisionId }),
  });
}

export function getBomLines(revisionId: string) {
  return apiFetch<{ revision_id: string; lines: BomLine[] }>(`/api/v1/bom/revisions/${revisionId}/lines`);
}

export function editBom(revisionId: string, edits: BomEdit[]) {
  return apiFetch<{ revision: BomRevision; structure: BomStructure }>(`/api/v1/bom/revisions/${revisionId}/edits`, {
    method: "POST",
    body: JSON.stringify({ edits }),
  });
}

export function explodeBom(revisionId: string, root: string, vehicles: string) {
  return apiFetch<BomExplosion>(`/api/v1/bom/revisions/${revisionId}/explode`, {
    method: "POST",
    body: JSON.stringify({ root, vehicles }),
  });
}

export function compareBom(revisionA: string, revisionB: string) {
  return apiFetch<BomComparison>("/api/v1/bom/compare", {
    method: "POST",
    body: JSON.stringify({ revision_a: revisionA, revision_b: revisionB }),
  });
}

export function validateBom(revisionId: string, mode: BomMode) {
  return apiFetch<{ counts: Record<string, number>; issues: BomIssue[] }>(
    `/api/v1/bom/revisions/${revisionId}/validate?mode=${mode}`,
  );
}

export function crossBom(
  revisionId: string,
  body: {
    cadastro_dataset_id: string;
    key_column: string;
    description_column: string | null;
    unit_column: string | null;
    key_mode: "exato" | "normalizado";
  },
) {
  return apiFetch<BomCross>(`/api/v1/bom/revisions/${revisionId}/cross`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function listBomKits(structureId: string) {
  return apiFetch<BomKit[]>(`/api/v1/bom/structures/${structureId}/kits`);
}

export function createBomKit(structureId: string, name: string, parts: { code: string; qty: string }[]) {
  return apiFetch<BomKit>(`/api/v1/bom/structures/${structureId}/kits`, {
    method: "POST",
    body: JSON.stringify({ name, parts }),
  });
}

export function kitCalc(
  revisionId: string,
  parts: { code: string; qty: string }[],
  vehicles: string,
  lot: string,
) {
  return apiFetch<{ materials: { code: string; unit: string; qty: string }[] }>(
    `/api/v1/bom/revisions/${revisionId}/kit-calc`,
    { method: "POST", body: JSON.stringify({ parts, vehicles, lot }) },
  );
}

/** URL de exportação. O navegador baixa o arquivo com a sessão do usuário (mesma origem). */
export function bomExportUrl(revisionId: string, params: Record<string, string>) {
  const query = new URLSearchParams(params).toString();
  return `/api/v1/bom/revisions/${revisionId}/export?${query}`;
}
