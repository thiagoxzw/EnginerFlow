/**
 * Decide se as linhas anteriores podem continuar na tela enquanto a revisão nova carrega.
 * Só vale para a MESMA estrutura: trocar de estrutura não pode mostrar (nem editar) linhas da outra.
 */
export function keepPreviousLines<T>(
  previous: T | undefined,
  previousQueryKey: readonly unknown[] | undefined,
  structureId: string | null,
): T | undefined {
  return previousQueryKey?.[1] === structureId ? previous : undefined;
}
