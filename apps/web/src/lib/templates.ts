/** Cliente de modelos de mapeamento (2B.2). Regras de negócio ficam na API. */

import { apiFetch } from "@/lib/api";
import type { CanonicalField } from "@/lib/datasets";

export type TemplateMapping = Partial<Record<CanonicalField, string>>;

export interface Template {
  id: string;
  name: string;
  mapping: TemplateMapping;
  definition_version: number;
  updated_at: string;
}

export interface TemplatePreview {
  /** Ausente quando há colunas faltando e a aplicação ainda não foi confirmada. */
  preview_id: string | null;
  expires_at: string | null;
  template_id: string;
  definition_version: number;
  missing_fields: Partial<Record<CanonicalField, string>>;
}

export interface DatasetState {
  dataVersionId: string;
  metadataVersionId: string;
}

interface VersionRow {
  id: string;
  is_current: boolean;
}

export function listTemplates(): Promise<Template[]> {
  return apiFetch<Template[]>("/api/v1/templates");
}

export function createTemplate(name: string, mapping: TemplateMapping): Promise<Template> {
  return apiFetch<Template>("/api/v1/templates", {
    method: "POST",
    body: JSON.stringify({ name, mapping }),
  });
}

export function updateTemplate(
  id: string,
  patch: { name?: string; mapping?: TemplateMapping },
): Promise<Template> {
  return apiFetch<Template>(`/api/v1/templates/${id}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

/** Estado atual da tabela: versão de dados e versão de metadados correntes. */
export async function getDatasetState(datasetId: string): Promise<DatasetState> {
  const [versions, metas] = await Promise.all([
    apiFetch<VersionRow[]>(`/api/v1/datasets/${datasetId}/versions`),
    apiFetch<VersionRow[]>(`/api/v1/datasets/${datasetId}/metadata-versions`),
  ]);
  const dataVersion = versions.find((v) => v.is_current);
  const metaVersion = metas.find((m) => m.is_current);
  if (!dataVersion || !metaVersion) {
    throw new Error("Tabela sem versão atual.");
  }
  return { dataVersionId: dataVersion.id, metadataVersionId: metaVersion.id };
}

export function previewTemplate(
  datasetId: string,
  templateId: string,
  state: DatasetState,
  allowMissing: boolean,
): Promise<TemplatePreview> {
  return apiFetch<TemplatePreview>(
    `/api/v1/datasets/${datasetId}/templates/${templateId}/preview`,
    {
      method: "POST",
      body: JSON.stringify({
        base_version_id: state.dataVersionId,
        base_metadata_version_id: state.metadataVersionId,
        allow_missing: allowMissing,
      }),
    },
  );
}

/** Aplica uma prévia já gerada. A API recusa se o estado mudou (409). */
export function applyPreview(
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
