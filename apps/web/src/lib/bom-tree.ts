/**
 * Funções puras da árvore de materiais: aritmética decimal exata (sem ponto flutuante), montagem
 * da árvore visível, busca e uso de componentes. A tela só renderiza o que está expandido.
 */

import type { BomLine } from "@/lib/bom";

/** Decimal exato: valor = n / 10^s. Quantidades da estrutura podem ter vírgula ou ponto. */
export interface Dec {
  n: bigint;
  s: number;
}

const DEC_RE = /^-?\d+(?:[.,]\d+)?$/;

export function parseDec(text: string | null | undefined): Dec | null {
  if (text === null || text === undefined) return null;
  const trimmed = text.trim();
  if (!DEC_RE.test(trimmed)) return null;
  const negative = trimmed.startsWith("-");
  const body = negative ? trimmed.slice(1) : trimmed;
  const [intPart, fracPart = ""] = body.split(/[.,]/);
  const n = BigInt(`${intPart}${fracPart}`);
  return { n: negative ? -n : n, s: fracPart.length };
}

export function mulDec(a: Dec, b: Dec): Dec {
  return { n: a.n * b.n, s: a.s + b.s };
}

export function addDec(a: Dec, b: Dec): Dec {
  const s = Math.max(a.s, b.s);
  return { n: a.n * 10n ** BigInt(s - a.s) + b.n * 10n ** BigInt(s - b.s), s };
}

export const ZERO: Dec = { n: 0n, s: 0 };
export const ONE: Dec = { n: 1n, s: 0 };

/** Texto em pt-BR, sem zeros à direita desnecessários: 0,5 × 2 = 1; 0,25 × 4 = 1. */
export function formatDec(d: Dec): string {
  const negative = d.n < 0n;
  const abs = negative ? -d.n : d.n;
  let digits = abs.toString().padStart(d.s + 1, "0");
  let int = d.s > 0 ? digits.slice(0, digits.length - d.s) : digits;
  let frac = d.s > 0 ? digits.slice(digits.length - d.s) : "";
  frac = frac.replace(/0+$/, "");
  int = int.replace(/^0+(?=\d)/, "");
  digits = frac ? `${int},${frac}` : int;
  return negative && digits !== "0" ? `-${digits}` : digits;
}

export interface TreeRow {
  key: string;
  line: BomLine;
  depth: number;
  hasChildren: boolean;
  expanded: boolean;
  /** Quantidade local (texto original) e acumulada por 1 unidade do topo (calculada aqui). */
  qtyLocal: string | null;
  qtyAccumulated: string | null;
  cycle: boolean;
}

/** Filhos por código de conjunto pai. */
export function childrenIndex(lines: BomLine[]): Map<string, BomLine[]> {
  const index = new Map<string, BomLine[]>();
  for (const line of lines) {
    if (line.parent && line.child) {
      const list = index.get(line.parent) ?? [];
      list.push(line);
      index.set(line.parent, list);
    }
  }
  return index;
}

/** Linhas de topo: sem pai, com componente. */
export function topLines(lines: BomLine[]): BomLine[] {
  return lines.filter((line) => !line.parent && line.child);
}

export function nodeKey(line: BomLine): string {
  return String(line.line_no);
}

/**
 * Linhas visíveis da árvore, na ordem da estrutura. Só desce em nós expandidos, então uma
 * estrutura com milhares de componentes não gera milhares de linhas na tela.
 */
export function visibleRows(
  lines: BomLine[],
  expanded: Set<string>,
  roots: BomLine[] = topLines(lines),
): TreeRow[] {
  const index = childrenIndex(lines);
  const rows: TreeRow[] = [];
  const walk = (line: BomLine, depth: number, acc: Dec, path: string[]) => {
    const local = parseDec(line.qty);
    const accumulated = local ? mulDec(acc, local) : null;
    const code = line.child ?? "";
    const cycle = path.includes(code);
    const children = cycle ? [] : (index.get(code) ?? []);
    const key = nodeKey(line);
    const isOpen = expanded.has(key) && children.length > 0;
    rows.push({
      key,
      line,
      depth,
      hasChildren: children.length > 0,
      expanded: isOpen,
      qtyLocal: line.qty,
      qtyAccumulated: accumulated ? formatDec(accumulated) : null,
      cycle,
    });
    if (isOpen) {
      for (const child of children) {
        walk(child, depth + 1, accumulated ?? ZERO, [...path, code]);
      }
    }
  };
  for (const root of roots) {
    walk(root, 0, ONE, []);
  }
  return rows;
}

/** Chaves de todos os nós que têm filhos (para "expandir todos"). */
export function expandableKeys(lines: BomLine[]): Set<string> {
  const index = childrenIndex(lines);
  const keys = new Set<string>();
  for (const line of lines) {
    if (line.child && index.has(line.child)) keys.add(nodeKey(line));
  }
  return keys;
}

/** Normaliza para busca: sem acento e sem diferença de caixa. */
export function searchable(text: string): string {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLocaleLowerCase("pt-BR");
}

/** Linhas que casam com o termo (código, código alternativo, descrição ou part number). */
export function matchingLines(lines: BomLine[], term: string): Set<string> {
  const q = searchable(term.trim());
  const found = new Set<string>();
  if (!q) return found;
  for (const line of lines) {
    const haystack = [line.child, line.alt_code, line.description, line.part_number]
      .filter((v): v is string => Boolean(v))
      .map(searchable)
      .join(" | ");
    if (haystack.includes(q)) found.add(nodeKey(line));
  }
  return found;
}

/** Chaves dos ancestrais de cada linha casada: para expandir o caminho até o resultado. */
export function ancestorKeys(lines: BomLine[], matched: Set<string>): Set<string> {
  const byChild = new Map<string, BomLine[]>();
  for (const line of lines) {
    if (line.child) {
      const list = byChild.get(line.child) ?? [];
      list.push(line);
      byChild.set(line.child, list);
    }
  }
  const out = new Set<string>();
  const stack = lines.filter((l) => matched.has(nodeKey(l))).map((l) => l.parent ?? "");
  const seen = new Set<string>();
  while (stack.length > 0) {
    const code = stack.pop() ?? "";
    if (!code || seen.has(code)) continue;
    seen.add(code);
    for (const owner of byChild.get(code) ?? []) {
      out.add(nodeKey(owner));
      stack.push(owner.parent ?? "");
    }
  }
  return out;
}

/** Em quais conjuntos um componente aparece (com a quantidade em cada um). */
export function usageOf(lines: BomLine[], code: string): BomLine[] {
  return lines.filter((line) => line.child === code);
}

export interface TreeFilters {
  level?: string;
  unit?: string;
  rev?: string;
  category?: string;
}

/** Filtro por nível, unidade, revisão e categoria. Vazio = sem filtro. */
export function passesFilters(line: BomLine, filters: TreeFilters): boolean {
  if (filters.level && String(line.level ?? "") !== filters.level) return false;
  if (filters.unit && (line.unit ?? "").toUpperCase() !== filters.unit.toUpperCase()) return false;
  if (filters.rev && (line.rev ?? "") !== filters.rev) return false;
  if (filters.category && (line.category ?? "") !== filters.category) return false;
  return true;
}

/** Código provisório gerado por duplicação (sufixo -CP, -CP2...). Não é código oficial do ERP. */
export function isProvisionalCode(code: string | null | undefined): boolean {
  return Boolean(code) && /-CP\d*$/.test(code as string);
}
