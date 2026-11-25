"""BOM (Bill of Materials): estrutura de materiais. Funções puras, sem banco e sem arquivo.

Regras de cálculo:
- Quantidades são Decimal; o texto original é preservado. Quantidade inválida nunca vira zero.
- Relacionamento pai-filho vem do dado (coluna de pai) ou, somente no modo "por nível" explícito,
  do nível hierárquico anterior. Nenhum relacionamento é inventado quando faltam dados.
- Explosão agrega por (código, unidade): unidades diferentes não são somadas.
- Ciclos são detectados antes de qualquer explosão.
- Ocorrências contam aparições do componente na estrutura expandida (não códigos únicos).
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Literal

from engiflow_api.domain.numeric import format_decimal, parse_decimal
from engiflow_api.domain.tabular import normalize_description

Severity = Literal["erro", "alerta", "informação"]
MODE_EXPLICIT = "explicit"
MODE_LEVEL = "level"
NO_UNIT = "(sem unidade)"


@dataclass(frozen=True)
class BomLine:
    line_no: int
    parent: str | None
    child: str | None
    description: str | None = None
    qty_raw: str | None = None
    unit: str | None = None
    rev: str | None = None
    position: str | None = None
    level: int | None = None
    alt_code: str | None = None
    manufacturer: str | None = None
    part_number: str | None = None
    notes: str | None = None
    category: str | None = None
    source_row: int | None = None
    inferred_parent: bool = False


@dataclass(frozen=True)
class Issue:
    severity: Severity
    rule: str
    message: str
    line_no: int | None = None
    code: str | None = None


@dataclass
class Explosion:
    root: str
    vehicles: Decimal
    # (código, unidade) -> quantidade total para o número de veículos informado.
    consolidated: dict[tuple[str, str], Decimal] = field(default_factory=dict)
    # código -> ocorrências na estrutura expandida (por veículo).
    occurrences: dict[str, int] = field(default_factory=dict)
    # Linhas com quantidade inválida, que não entraram no cálculo (com aviso).
    invalid_lines: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class BomError(ValueError):
    """Erro de regra de negócio (ciclo, raiz inexistente, quantidade de veículos inválida)."""


def qty_value(line: BomLine) -> Decimal | None:
    """Quantidade numérica da linha, ou None quando o texto é inválido ou ausente."""
    return parse_decimal(line.qty_raw)


def unit_key(unit: str | None) -> str:
    text = (unit or "").strip()
    return text.upper() if text else NO_UNIT


def _children_index(lines: list[BomLine]) -> dict[str, list[BomLine]]:
    index: dict[str, list[BomLine]] = defaultdict(list)
    for line in lines:
        if line.parent and line.child:
            index[line.parent].append(line)
    return index


def defined_codes(lines: list[BomLine]) -> set[str]:
    """Códigos que existem na estrutura: como componente de alguma linha ou como raiz declarada."""
    return {line.child for line in lines if line.child}


def find_cycles(lines: list[BomLine]) -> list[list[str]]:
    """Ciclos no grafo pai -> filho. Cada ciclo é a sequência de códigos que se repete."""
    index = _children_index(lines)
    state: dict[str, int] = {}  # 1 = em exploração, 2 = concluído
    stack: list[str] = []
    cycles: list[list[str]] = []

    def visit(code: str) -> None:
        state[code] = 1
        stack.append(code)
        for line in index.get(code, []):
            child = line.child or ""
            if state.get(child) == 1:
                start = stack.index(child)
                cycle = [*stack[start:], child]
                if cycle not in cycles:
                    cycles.append(cycle)
            elif child not in state:
                visit(child)
        stack.pop()
        state[code] = 2

    for code in list(index):
        if code not in state:
            visit(code)
    return cycles


def requirements(
    lines: list[BomLine],
    code: str,
    memo: dict[str, tuple[dict[tuple[str, str], Decimal], dict[str, int]]] | None = None,
) -> tuple[dict[tuple[str, str], Decimal], dict[str, int]]:
    """Necessidade por UMA unidade de `code`: quantidades por (componente, unidade) e ocorrências.

    Calculado com memória por código: subconjuntos compartilhados são processados uma vez.
    Pressupõe que não há ciclos (verificar antes com `find_cycles`).
    """
    if memo is None:
        memo = {}
    index = _children_index(lines)
    return _requirements(index, code, memo)


def _requirements(
    index: dict[str, list[BomLine]],
    code: str,
    memo: dict[str, tuple[dict[tuple[str, str], Decimal], dict[str, int]]],
) -> tuple[dict[tuple[str, str], Decimal], dict[str, int]]:
    if code in memo:
        return memo[code]
    qty: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal(0))
    occ: dict[str, int] = defaultdict(int)
    for line in index.get(code, []):
        child = line.child or ""
        local = qty_value(line)
        if local is None:
            continue  # quantidade inválida: não entra no cálculo (acusado na validação)
        unit = unit_key(line.unit)
        qty[(child, unit)] += local
        occ[child] += 1
        sub_qty, sub_occ = _requirements(index, child, memo)
        for (c, u), q in sub_qty.items():
            qty[(c, u)] += local * q
        for c, n in sub_occ.items():
            occ[c] += n
    result = (dict(qty), dict(occ))
    memo[code] = result
    return result


def explode(lines: list[BomLine], root: str, vehicles: Decimal) -> Explosion:
    """Explosão completa do `root` para `vehicles` veículos. Recusa ciclos e raiz inexistente."""
    if vehicles <= 0:
        raise BomError("A quantidade de veículos deve ser maior que zero.")
    if root not in defined_codes(lines):
        raise BomError(f"Conjunto '{root}' não existe nesta estrutura.")
    cycles = find_cycles(lines)
    reachable = _reachable(lines, root)
    relevant = [c for c in cycles if set(c) & reachable]
    if relevant:
        path = " → ".join(relevant[0])
        raise BomError(f"Ciclo detectado: {path}. A explosão foi recusada.")
    qty, occ = requirements(lines, root)
    result = Explosion(root=root, vehicles=vehicles)
    result.consolidated = {key: value * vehicles for key, value in qty.items()}
    result.occurrences = dict(occ)
    for line in lines:
        if line.parent and line.parent in reachable and qty_value(line) is None:
            result.invalid_lines.append(line.line_no)
    if result.invalid_lines:
        result.warnings.append(
            f"{len(result.invalid_lines)} linha(s) com quantidade inválida ficaram fora do cálculo."
        )
    units_by_code: dict[str, set[str]] = defaultdict(set)
    for code, unit in result.consolidated:
        units_by_code[code].add(unit)
    for code, units in sorted(units_by_code.items()):
        if len(units) > 1:
            result.warnings.append(
                f"'{code}' aparece com unidades diferentes ({', '.join(sorted(units))}): "
                "totais separados por unidade, não somados."
            )
    return result


def _reachable(lines: list[BomLine], root: str) -> set[str]:
    index = _children_index(lines)
    seen: set[str] = set()
    todo = [root]
    while todo:
        code = todo.pop()
        if code in seen:
            continue
        seen.add(code)
        todo.extend(line.child or "" for line in index.get(code, []))
    return seen


def kit_requirements(
    lines: list[BomLine],
    parts: list[tuple[str, Decimal]],
    vehicles: Decimal,
    lot: Decimal,
) -> dict[tuple[str, str], Decimal]:
    """Materiais de um kit: soma das necessidades de cada subconjunto (quantidade por kit).

    `parts` = [(código do subconjunto, quantidade por kit)]. Resultado = quantidade para
    vehicles × lot kits. Unidades continuam separadas.
    """
    if vehicles <= 0 or lot <= 0:
        raise BomError("Veículos e lote devem ser maiores que zero.")
    memo: dict[str, tuple[dict[tuple[str, str], Decimal], dict[str, int]]] = {}
    total: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal(0))
    cycles = find_cycles(lines)
    for code, per_kit in parts:
        if code not in defined_codes(lines):
            raise BomError(f"Conjunto '{code}' do kit não existe nesta estrutura.")
        if any(code in c for c in cycles):
            raise BomError(f"Ciclo envolvendo '{code}': kit recusado.")
        if per_kit <= 0:
            raise BomError(f"Quantidade por kit de '{code}' deve ser maior que zero.")
        qty, _ = requirements(lines, code, memo)
        for key, value in qty.items():
            total[key] += value * per_kit
    factor = vehicles * lot
    return {key: value * factor for key, value in total.items()}


def validate(lines: list[BomLine], mode: str = MODE_EXPLICIT) -> list[Issue]:
    """Painel de inconsistências. Não altera dados: apenas aponta, com o número da linha."""
    issues: list[Issue] = []
    defined = defined_codes(lines)
    roots = {line.child for line in lines if not line.parent and line.child}

    for line in lines:
        if not line.child:
            issues.append(Issue("erro", "sem_codigo", "Componente sem código.", line.line_no))
            continue
        if not (line.description or "").strip():
            issues.append(
                Issue(
                    "alerta", "sem_descricao", "Componente sem descrição.", line.line_no, line.child
                )
            )
        raw = line.qty_raw
        if raw is None or not raw.strip():
            issues.append(
                Issue(
                    "erro", "quantidade_invalida", "Quantidade ausente.", line.line_no, line.child
                )
            )
        else:
            value = qty_value(line)
            if value is None:
                issues.append(
                    Issue(
                        "erro",
                        "quantidade_invalida",
                        f"Quantidade inválida: '{raw}'.",
                        line.line_no,
                        line.child,
                    )
                )
            elif value < 0:
                issues.append(
                    Issue(
                        "erro",
                        "quantidade_negativa",
                        "Quantidade negativa.",
                        line.line_no,
                        line.child,
                    )
                )
            elif value == 0:
                issues.append(
                    Issue(
                        "alerta",
                        "quantidade_zerada",
                        "Quantidade zerada.",
                        line.line_no,
                        line.child,
                    )
                )
        if line.parent and line.parent not in defined:
            issues.append(
                Issue(
                    "erro",
                    "pai_inexistente",
                    f"Conjunto pai '{line.parent}' não existe nesta estrutura.",
                    line.line_no,
                    line.child,
                )
            )
        if line.inferred_parent:
            issues.append(
                Issue(
                    "informação",
                    "pai_por_nivel",
                    f"Pai '{line.parent}' inferido pelo nível hierárquico (modo por nível).",
                    line.line_no,
                    line.child,
                )
            )

    for cycle in find_cycles(lines):
        issues.append(
            Issue("erro", "ciclo", f"Referência circular: {' → '.join(cycle)}.", None, cycle[0])
        )

    if mode == MODE_LEVEL:
        issues.extend(_level_issues(lines))

    reachable: set[str] = set()
    for root in roots:
        reachable |= _reachable(lines, root)
    for line in lines:
        if line.child and line.child not in reachable and line.child not in roots:
            issues.append(
                Issue(
                    "alerta",
                    "orfao",
                    "Componente não ligado a nenhum conjunto de topo.",
                    line.line_no,
                    line.child,
                )
            )

    by_code: dict[str, list[BomLine]] = defaultdict(list)
    for line in lines:
        if line.child:
            by_code[line.child].append(line)
    for code, items in sorted(by_code.items()):
        units = {unit_key(i.unit) for i in items}
        if len(units) > 1:
            issues.append(
                Issue(
                    "alerta",
                    "unidade_incompativel",
                    f"Unidades diferentes: {', '.join(sorted(units))}.",
                    items[0].line_no,
                    code,
                )
            )
        revs = {(i.rev or "").strip() for i in items if (i.rev or "").strip()}
        if len(revs) > 1:
            issues.append(
                Issue(
                    "alerta",
                    "revisao_conflitante",
                    f"Revisões diferentes: {', '.join(sorted(revs))}.",
                    items[0].line_no,
                    code,
                )
            )
        descs = {normalize_description(i.description or "") for i in items if i.description}
        if len(descs) > 1:
            issues.append(
                Issue(
                    "alerta",
                    "descricao_divergente",
                    "Mesmo código com descrições divergentes.",
                    items[0].line_no,
                    code,
                )
            )

    seen_pairs: dict[tuple[str, str], int] = defaultdict(int)
    for line in lines:
        if line.parent and line.child:
            seen_pairs[(line.parent, line.child)] += 1
    for line in lines:
        if line.parent and line.child and seen_pairs[(line.parent, line.child)] > 1:
            issues.append(
                Issue(
                    "informação",
                    "duplicidade_no_conjunto",
                    f"'{line.child}' aparece mais de uma vez em '{line.parent}'. "
                    "Confirme se são posições distintas.",
                    line.line_no,
                    line.child,
                )
            )
    for line in lines:
        if is_provisional(line.child):
            issues.append(
                Issue(
                    "informação",
                    "codigo_provisorio",
                    f"Código provisório '{line.child}' gerado por duplicação. "
                    "Não é código oficial: confirme antes de usar.",
                    line.line_no,
                    line.child,
                )
            )
    return issues


def _level_issues(lines: list[BomLine]) -> list[Issue]:
    issues: list[Issue] = []
    for line in lines:
        if line.level is None:
            issues.append(
                Issue(
                    "erro", "nivel_ausente", "Nível hierárquico ausente.", line.line_no, line.child
                )
            )
        elif line.level > 1 and line.parent is None:
            issues.append(
                Issue(
                    "erro",
                    "nivel_sem_pai",
                    "Nível maior que 1 sem conjunto pai correspondente.",
                    line.line_no,
                    line.child,
                )
            )
    return issues


@dataclass(frozen=True)
class EdgeChange:
    kind: str  # adicionado, removido, quantidade, unidade, transferido, descricao, revisao
    child: str
    parent: str | None
    detail: str
    line_no: int | None = None


@dataclass
class Comparison:
    changes: list[EdgeChange] = field(default_factory=list)
    unmatched_removed: list[str] = field(default_factory=list)
    unmatched_added: list[str] = field(default_factory=list)
    identical: int = 0
    pending_code_changes: list[tuple[str, str]] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = defaultdict(int)
        for change in self.changes:
            out[change.kind] += 1
        out["sem_correspondencia"] = len(self.unmatched_removed) + len(self.unmatched_added)
        out["identicos"] = self.identical
        return dict(out)


def _edge_map(lines: list[BomLine]) -> dict[tuple[str | None, str, str], tuple[Decimal, list[int]]]:
    edges: dict[tuple[str | None, str, str], tuple[Decimal, list[int]]] = {}
    for line in lines:
        if not line.child:
            continue
        key = (line.parent, line.child, unit_key(line.unit))
        value = qty_value(line) or Decimal(0)
        total, nos = edges.get(key, (Decimal(0), []))
        edges[key] = (total + value, [*nos, line.line_no])
    return edges


def compare(a: list[BomLine], b: list[BomLine]) -> Comparison:
    """Compara duas estruturas (ou duas revisões). Chave = (pai, componente, unidade)."""
    ea, eb = _edge_map(a), _edge_map(b)
    result = Comparison()
    ka, kb = set(ea), set(eb)
    removed = ka - kb
    added = kb - ka
    for key in sorted(ka & kb, key=str):
        if ea[key][0] != eb[key][0]:
            parent, child, unit = key
            result.changes.append(
                EdgeChange(
                    "quantidade",
                    child,
                    parent,
                    f"{format_decimal(ea[key][0])} → {format_decimal(eb[key][0])} {unit}".strip(),
                    eb[key][1][0] if eb[key][1] else None,
                )
            )
        else:
            result.identical += 1

    # Componentes que saíram de um pai e entraram em outro: transferência (não é duplicata).
    added_by_child: dict[str, list[tuple[str | None, str, str]]] = defaultdict(list)
    for key in added:
        added_by_child[key[1]].append(key)
    removed_by_child: dict[str, list[tuple[str | None, str, str]]] = defaultdict(list)
    for key in removed:
        removed_by_child[key[1]].append(key)

    transferred_removed: set[tuple[str | None, str, str]] = set()
    transferred_added: set[tuple[str | None, str, str]] = set()
    for child in sorted(set(added_by_child) & set(removed_by_child)):
        for rkey in removed_by_child[child]:
            for akey in added_by_child[child]:
                if akey in transferred_added or rkey in transferred_removed:
                    continue
                if ea[rkey][0] == eb[akey][0] and rkey[0] != akey[0]:
                    transferred_removed.add(rkey)
                    transferred_added.add(akey)
                    result.changes.append(
                        EdgeChange(
                            "transferido",
                            child,
                            akey[0],
                            f"de '{rkey[0] or '(topo)'}' para '{akey[0] or '(topo)'}'",
                            eb[akey][1][0] if eb[akey][1] else None,
                        )
                    )
                    break

    for key in sorted(removed - transferred_removed, key=str):
        result.changes.append(
            EdgeChange(
                "removido",
                key[1],
                key[0],
                f"{format_decimal(ea[key][0])} {key[2]}".strip(),
                ea[key][1][0] if ea[key][1] else None,
            )
        )
    for key in sorted(added - transferred_added, key=str):
        result.changes.append(
            EdgeChange(
                "adicionado",
                key[1],
                key[0],
                f"{format_decimal(eb[key][0])} {key[2]}".strip(),
                eb[key][1][0] if eb[key][1] else None,
            )
        )

    # Unidades alteradas: mesmo par pai/componente, unidade diferente.
    pairs_a = {(k[0], k[1]): k for k in ka}
    for key in sorted(kb, key=str):
        pair = (key[0], key[1])
        if pair in pairs_a and pairs_a[pair][2] != key[2] and key not in ka:
            prev_key = pairs_a[pair]
            result.changes.append(
                EdgeChange(
                    "unidade",
                    key[1],
                    key[0],
                    f"{prev_key[2]} → {key[2]}",
                    eb[key][1][0] if eb[key][1] else None,
                )
            )
            # Remove dos adicionados/removidos genéricos para não contar duas vezes.
            added.discard(key)
            removed.discard(prev_key)

    # Descrição e revisão por código (valor da primeira ocorrência).
    desc_a = _first_by_code(a, "description")
    desc_b = _first_by_code(b, "description")
    rev_a = _first_by_code(a, "rev")
    rev_b = _first_by_code(b, "rev")
    for code in sorted(set(desc_a) & set(desc_b)):
        if normalize_description(desc_a[code][0] or "") != normalize_description(
            desc_b[code][0] or ""
        ):
            result.changes.append(
                EdgeChange(
                    "descricao",
                    code,
                    None,
                    f"'{desc_a[code][0]}' → '{desc_b[code][0]}'",
                    desc_b[code][1],
                )
            )
        if (rev_a.get(code, (None, None))[0] or "") != (
            rev_b.get(code, (None, None))[0] or ""
        ) and code in rev_b:
            result.changes.append(
                EdgeChange(
                    "revisao",
                    code,
                    None,
                    f"{rev_a.get(code, (None, None))[0] or '-'} → {rev_b[code][0] or '-'}",
                    rev_b[code][1],
                )
            )

    # Sem correspondência: removido sem par adicionado por código. Pares com mesma descrição e
    # código diferente viram "possível alteração de código", sempre pendente de confirmação.
    still_removed = sorted({k[1] for k in removed - transferred_removed})
    still_added = sorted({k[1] for k in added - transferred_added})
    for code in still_removed:
        if code in still_added:
            continue
        result.unmatched_removed.append(code)
    for code in still_added:
        if code in still_removed:
            continue
        result.unmatched_added.append(code)
    for old in list(result.unmatched_removed):
        old_desc = normalize_description(desc_a.get(old, (None, None))[0] or "")
        if not old_desc:
            continue
        for new in list(result.unmatched_added):
            if normalize_description(desc_b.get(new, (None, None))[0] or "") == old_desc:
                result.pending_code_changes.append((old, new))
    return result


def _first_by_code(lines: list[BomLine], attr: str) -> dict[str, tuple[str | None, int | None]]:
    out: dict[str, tuple[str | None, int | None]] = {}
    for line in lines:
        if line.child and line.child not in out:
            out[line.child] = (getattr(line, attr), line.line_no)
    return out


def consolidated_list(lines: list[BomLine]) -> list[dict[str, object]]:
    """Lista de componentes por código e unidade, sem explodir subconjuntos (uso direto)."""
    totals: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal(0))
    occ: dict[tuple[str, str], int] = defaultdict(int)
    desc: dict[str, str | None] = {}
    for line in lines:
        if not line.child:
            continue
        key = (line.child, unit_key(line.unit))
        value = qty_value(line)
        if value is not None:
            totals[key] += value
        occ[key] += 1
        desc.setdefault(line.child, line.description)
    return [
        {
            "code": code,
            "unit": unit,
            "qty": format_decimal(totals[(code, unit)]),
            "occurrences": occ[(code, unit)],
            "description": desc.get(code),
        }
        for code, unit in sorted(occ)
    ]


PROVISIONAL_SUFFIX = "-CP"


def is_provisional(code: str | None) -> bool:
    """Código provisório gerado pela duplicação: não é código oficial do ERP/cadastro.

    Identificado pelo sufixo `-CP` (ou `-CP2`, `-CP3`… quando há colisão). Nunca é atribuído a um
    código industrial real: o usuário deve confirmar a criação antes de usá-lo em outros sistemas.
    """
    if not code:
        return False
    return bool(re.search(r"-CP\d*$", code))


def _unique_provisional(base: str, taken: set[str]) -> str:
    candidate = f"{base}{PROVISIONAL_SUFFIX}"
    counter = 2
    while candidate in taken:
        candidate = f"{base}{PROVISIONAL_SUFFIX}{counter}"
        counter += 1
    return candidate


def duplicate_subtree(
    lines: list[BomLine],
    code: str,
    new_code: str,
    next_no: int,
) -> tuple[list[BomLine], dict[str, str]]:
    """Duplicação COMPLETA de um subconjunto, com todos os descendentes.

    - O conjunto recebe `new_code` (código informado pelo usuário) e fica nos mesmos pais.
    - Cada subconjunto interno recebe um código PROVISÓRIO único: código + `-CP`.
      Se já houver colisão (duplicação sucessiva), usa `-CP2`, `-CP3`. Nenhum código existente
      é reaproveitado.
    - Componentes folha mantêm o código: são o mesmo material.
    - Quantidades, unidades e propriedades são copiadas sem alteração.
    Retorna as linhas novas e o mapa código original -> código da cópia.
    """
    defined = defined_codes(lines)
    if code not in defined:
        raise BomError(f"Conjunto '{code}' não existe nesta estrutura.")
    if new_code in defined:
        raise BomError(f"O código '{new_code}' já existe nesta estrutura.")
    index = _children_index(lines)
    closure: set[str] = set()
    todo = [code]
    while todo:
        current = todo.pop()
        for line in index.get(current, []):
            child = line.child or ""
            if child not in closure:
                closure.add(child)
                todo.append(child)
    subassemblies = {c for c in closure | {code} if index.get(c)}
    mapping: dict[str, str] = {code: new_code}
    taken = set(defined) | {new_code}
    for sub in sorted(subassemblies - {code}):
        provisional = _unique_provisional(sub, taken)
        mapping[sub] = provisional
        taken.add(provisional)

    added: list[BomLine] = []
    n = next_no
    # 1) O conjunto aparece onde o original aparece (mesmos pais).
    for line in lines:
        if line.child == code:
            added.append(replace(line, line_no=n, child=new_code))
            n += 1
    # 2) Todas as linhas internas à subárvore, com pai e filho mapeados.
    for line in lines:
        if line.parent in mapping and line.parent is not None and line.parent in subassemblies:
            added.append(
                replace(
                    line,
                    line_no=n,
                    parent=mapping[line.parent],
                    child=mapping.get(line.child or "", line.child),
                )
            )
            n += 1
    return added, mapping


@dataclass(frozen=True)
class KitPart:
    """Peça de um kit: subconjunto (conta pelos componentes) ou componente folha (conta por ele)."""

    code: str
    qty: Decimal
    unit: str | None = None


def kit_requirements_for_parts(
    lines: list[BomLine],
    parts: list[KitPart],
    vehicles: Decimal,
    lot: Decimal,
) -> dict[tuple[str, str], Decimal]:
    """Materiais do kit para vehicles x lot kits.

    - Peça com filhos: entram os componentes dela (o próprio conjunto não é material).
    - Componente folha: entra pela quantidade e unidade informadas (ou a unidade da linha).
    """
    if vehicles <= 0 or lot <= 0:
        raise BomError("Veículos e lote devem ser maiores que zero.")
    index = _children_index(lines)
    defined = defined_codes(lines)
    cycles = find_cycles(lines)
    memo: dict[str, tuple[dict[tuple[str, str], Decimal], dict[str, int]]] = {}
    total: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal(0))
    for part in parts:
        if part.code not in defined:
            raise BomError(f"Componente '{part.code}' do kit não existe nesta estrutura.")
        if any(part.code in c for c in cycles):
            raise BomError(f"Ciclo envolvendo '{part.code}': kit recusado.")
        if part.qty <= 0:
            raise BomError(f"Quantidade por kit de '{part.code}' deve ser maior que zero.")
        if index.get(part.code):
            qty, _ = _requirements(index, part.code, memo)
            for key, value in qty.items():
                total[key] += value * part.qty
        else:
            unit = unit_key(part.unit) if part.unit else _line_unit(lines, part.code)
            total[(part.code, unit)] += part.qty
    factor = vehicles * lot
    return {key: value * factor for key, value in total.items()}


def _line_unit(lines: list[BomLine], code: str) -> str:
    for line in lines:
        if line.child == code:
            return unit_key(line.unit)
    return NO_UNIT
