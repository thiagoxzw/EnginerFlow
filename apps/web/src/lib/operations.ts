/** Cliente genérico de operações (prévia e aplicação). Regras ficam na API. */

import { apiFetch } from "@/lib/api";
import type { DatasetState } from "@/lib/templates";

export interface OperationPreview {
  preview_id: string;
  expires_at: string;
  rows_affected: number;
  cells_changed: number;
  before_content_sha256: string;
  after_content_sha256: string;
}

export interface RawRow {
  row_number: number;
  values: (string | null)[];
}

export interface MetadataVersion {
  id: string;
  number: number;
  header_row: number | null;
  is_current: boolean;
}

export function previewOperation(
  datasetId: string,
  code: string,
  params: Record<string, unknown>,
  state: DatasetState,
): Promise<OperationPreview> {
  return apiFetch<OperationPreview>(`/api/v1/datasets/${datasetId}/operations/preview`, {
    method: "POST",
    body: JSON.stringify({
      code,
      params,
      base_version_id: state.dataVersionId,
      base_metadata_version_id: state.metadataVersionId,
    }),
  });
}

export function applyOperation(
  datasetId: string,
  previewId: string,
  state: DatasetState,
): Promise<unknown> {
  return apiFetch(`/api/v1/datasets/${datasetId}/operations`, {
    method: "POST",
    body: JSON.stringify({
      preview_id: previewId,
      base_version_id: state.dataVersionId,
      base_metadata_version_id: state.metadataVersionId,
    }),
  });
}

export interface OperationRecord {
  id: string;
  seq: number;
  code: string;
  code_version: number;
  status: "applied" | "undone";
  rows_affected: number;
  cells_changed: number;
  created_at: string;
}

export interface VersionRecord {
  id: string;
  number: number;
  row_count: number;
  content_sha256: string;
  created_at: string;
  is_current: boolean;
}

/** Desfaz/refaz: a API move os DOIS ponteiros e recusa se o estado mudou (409). */
export function moveHistory(
  datasetId: string,
  direction: "undo" | "redo",
  state: DatasetState,
): Promise<{ current_version_id: string; current_metadata_version_id: string }> {
  return apiFetch(`/api/v1/datasets/${datasetId}/${direction}`, {
    method: "POST",
    body: JSON.stringify({
      base_version_id: state.dataVersionId,
      base_metadata_version_id: state.metadataVersionId,
    }),
  });
}

export function listOperations(datasetId: string): Promise<OperationRecord[]> {
  return apiFetch<OperationRecord[]>(`/api/v1/datasets/${datasetId}/operations`);
}

export function listVersions(datasetId: string): Promise<VersionRecord[]> {
  return apiFetch<VersionRecord[]>(`/api/v1/datasets/${datasetId}/versions`);
}

export function rawHead(datasetId: string, count = 30): Promise<RawRow[]> {
  return apiFetch<RawRow[]>(`/api/v1/datasets/${datasetId}/raw-head?count=${count}`);
}

export function metadataVersions(datasetId: string): Promise<MetadataVersion[]> {
  return apiFetch<MetadataVersion[]>(`/api/v1/datasets/${datasetId}/metadata-versions`);
}
