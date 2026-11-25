/** Invalidação das consultas de UMA tabela após qualquer operação aplicada (2B.2). */

import type { QueryClient } from "@tanstack/react-query";

/** Consultas que dependem do estado atual da tabela (chaves com o id da tabela). */
export const DATASET_SCOPED_KEYS = [
  "dataset",
  "rows",
  "operations",
  "versions",
  "metadata-versions",
  "raw-head",
] as const;

/** Atualiza linhas, histórico, versões e metadados depois de qualquer aplicação. */
export async function invalidateDataset(client: QueryClient, datasetId: string): Promise<void> {
  await Promise.all(
    DATASET_SCOPED_KEYS.map((key) => client.invalidateQueries({ queryKey: [key, datasetId] })),
  );
  // Lista de tabelas guarda contagens e colunas: também precisa ser atualizada.
  await client.invalidateQueries({ queryKey: ["datasets"] });
}
