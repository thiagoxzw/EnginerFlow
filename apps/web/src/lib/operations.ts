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

export function rawHead(datasetId: string, count = 30): Promise<RawRow[]> {
  return apiFetch<RawRow[]>(`/api/v1/datasets/${datasetId}/raw-head?count=${count}`);
}

export function metadataVersions(datasetId: string): Promise<MetadataVersion[]> {
  return apiFetch<MetadataVersion[]>(`/api/v1/datasets/${datasetId}/metadata-versions`);
}
