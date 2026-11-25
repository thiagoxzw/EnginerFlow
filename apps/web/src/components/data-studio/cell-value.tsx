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
