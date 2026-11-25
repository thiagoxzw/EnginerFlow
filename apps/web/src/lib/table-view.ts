/**
 * Preferências de visualização de uma tabela: ordem das colunas, largura e fixação.
 * Não altera dados nem gera versão: ficam neste navegador, por tabela.
 */
export interface TableView {
  /** Ordem das colunas (nomes). Colunas novas entram no fim; nomes que sumiram são descartados. */
  order: string[];
  /** Largura em pixels por nome de coluna. Ausente = largura padrão. */
  widths: Record<string, number>;
  /** Colunas fixadas à esquerda, na ordem em que aparecem na tabela. */
  pinned: string[];
}

export const DEFAULT_WIDTH = 140;
export const MIN_WIDTH = 60;
export const MAX_WIDTH = 480;

export function viewKey(datasetId: string): string {
  return `engiflow:visao:${datasetId}`;
}

export function emptyView(columns: string[]): TableView {
  return { order: [...columns], widths: {}, pinned: [] };
}

/** Lê a visão guardada. Qualquer conteúdo inválido ou armazenamento indisponível vira visão padrão. */
export function readTableView(key: string, columns: string[]): TableView {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return emptyView(columns);
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return emptyView(columns);
    const candidate = parsed as Partial<TableView>;
    return reconcileView(
      {
        order: Array.isArray(candidate.order) ? candidate.order.filter(isString) : [],
        widths: isWidthMap(candidate.widths) ? candidate.widths : {},
        pinned: Array.isArray(candidate.pinned) ? candidate.pinned.filter(isString) : [],
      },
      columns,
    );
  } catch {
    return emptyView(columns);
  }
}

export function writeTableView(key: string, view: TableView): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(view));
  } catch {
    // armazenamento indisponível: a preferência vale só nesta sessão
  }
}

/** Ajusta a visão às colunas atuais: remove o que sumiu e acrescenta o que é novo, sem perder a ordem. */
export function reconcileView(view: TableView, columns: string[]): TableView {
  const present = new Set(columns);
  const kept = view.order.filter((c, i, all) => present.has(c) && all.indexOf(c) === i);
  const missing = columns.filter((c) => !kept.includes(c));
  const order = [...kept, ...missing];
  const pinned = order.filter((c) => view.pinned.includes(c));
  const widths: Record<string, number> = {};
  for (const [name, width] of Object.entries(view.widths)) {
    if (present.has(name)) widths[name] = clampWidth(width);
  }
  return { order, widths, pinned };
}

/** Ordem de exibição: fixadas primeiro (na ordem delas), depois as demais na ordem da visão. */
export function displayOrder(view: TableView): string[] {
  const pinned = view.pinned;
  return [...pinned, ...view.order.filter((c) => !pinned.includes(c))];
}

/** Move uma coluna uma posição para a esquerda (-1) ou direita (+1), dentro da ordem não fixada. */
export function moveColumn(view: TableView, name: string, delta: -1 | 1): TableView {
  const index = view.order.indexOf(name);
  const target = index + delta;
  if (index < 0 || target < 0 || target >= view.order.length) return view;
  const order = [...view.order];
  [order[index], order[target]] = [order[target] as string, order[index] as string];
  return { ...view, order };
}

export function togglePin(view: TableView, name: string): TableView {
  const pinned = view.pinned.includes(name)
    ? view.pinned.filter((c) => c !== name)
    : [...view.pinned, name];
  return { ...view, pinned: view.order.filter((c) => pinned.includes(c)) };
}

export function setWidth(view: TableView, name: string, width: number): TableView {
  return { ...view, widths: { ...view.widths, [name]: clampWidth(width) } };
}

/** Largura que cabe no conteúdo mostrado (estimativa por caracteres), dentro dos limites. */
export function fitWidth(header: string, values: (string | null)[]): number {
  let longest = header.length;
  for (const value of values) {
    if (value !== null && value.length > longest) longest = value.length;
  }
  return clampWidth(Math.round(longest * 7.5 + 24));
}

export function widthOf(view: TableView, name: string): number {
  return view.widths[name] ?? DEFAULT_WIDTH;
}

export function clampWidth(width: number): number {
  return Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, Math.round(width)));
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isWidthMap(value: unknown): value is Record<string, number> {
  return (
    typeof value === "object" &&
    value !== null &&
    Object.values(value).every((v) => typeof v === "number" && Number.isFinite(v))
  );
}
