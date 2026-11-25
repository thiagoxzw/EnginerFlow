"use client";

const inputClass = "rounded-md border border-[var(--color-border)] bg-transparent px-2 py-1 text-sm";
const buttonClass =
  "rounded-md border border-[var(--color-border)] px-3 py-2 text-sm hover:bg-[var(--color-border)] disabled:opacity-50";

export const MAX_KEYS = 10;

export interface KeyPair {
  left: string;
  right: string;
}

/** Pares de chave só valem quando todos os lados estão preenchidos. */
export function keysComplete(keys: KeyPair[]): boolean {
  return keys.length > 0 && keys.every((k) => k.left !== "" && k.right !== "");
}

/** Editor de chaves compostas: uma linha por par, até MAX_KEYS pares. */
export function KeyPairsEditor({
  idPrefix,
  legend,
  keys,
  onChange,
  leftColumns,
  rightColumns,
  rightEnabled,
}: {
  idPrefix: string;
  legend: string;
  keys: KeyPair[];
  onChange: (next: KeyPair[]) => void;
  leftColumns: string[];
  rightColumns: string[];
  rightEnabled: boolean;
}) {
  const defaultLeft = leftColumns[0] ?? "";

  return (
    <fieldset className="space-y-2">
      <legend className="text-sm font-medium">
        {legend} (todas precisam bater; máximo {MAX_KEYS})
      </legend>
      {keys.map((k, i) => (
        <div key={i} className="flex flex-wrap items-end gap-2">
          <div className="space-y-1">
            <label htmlFor={`${idPrefix}-lk-${i}`} className="block text-xs text-[var(--color-muted)]">
              Coluna nesta tabela
            </label>
            <select
              id={`${idPrefix}-lk-${i}`}
              value={k.left}
              onChange={(e) => onChange(keys.map((p, j) => (j === i ? { ...p, left: e.target.value } : p)))}
              className={`${inputClass} min-w-40`}
            >
              {leftColumns.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>
          <span aria-hidden="true" className="pb-2 text-[var(--color-muted)]">
            =
          </span>
          <div className="space-y-1">
            <label htmlFor={`${idPrefix}-rk-${i}`} className="block text-xs text-[var(--color-muted)]">
              Coluna na outra tabela
            </label>
            <select
              id={`${idPrefix}-rk-${i}`}
              value={k.right}
              disabled={!rightEnabled}
              onChange={(e) => onChange(keys.map((p, j) => (j === i ? { ...p, right: e.target.value } : p)))}
              className={`${inputClass} min-w-40`}
            >
              <option value="">— escolher —</option>
              {rightColumns.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>
          {keys.length > 1 ? (
            <button
              type="button"
              onClick={() => onChange(keys.filter((_, j) => j !== i))}
              className={buttonClass}
            >
              Remover chave {i + 1}
            </button>
          ) : null}
        </div>
      ))}
      {keys.length < MAX_KEYS ? (
        <button
          type="button"
          onClick={() => onChange([...keys, { left: defaultLeft, right: "" }])}
          className={buttonClass}
        >
          Adicionar chave
        </button>
      ) : null}
    </fieldset>
  );
}
