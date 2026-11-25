"""Fórmulas por linha, sem eval e sem execução de código. Números com Decimal.

Sintaxe suportada (separador de argumentos: ponto e vírgula):
- Referências a colunas: [Nome da coluna]  (colchetes permitem espaços e acentos)
- Números: 12 ou 12,5 ou 12.5 (decimal com vírgula ou ponto)
- Textos: "entre aspas"
- Operadores: + - * /  (com parênteses), e comparações = <> < > <= >= (resultado VERDADEIRO/FALSO)
- Funções numéricas: SOMA(a;b;...), MEDIA(a;...), MIN(a;...), MAX(a;...), CONTAR(a;...)
- Lógica: SE(condição; valor_se_verdadeiro; valor_se_falso)
- Texto: CONCAT(a;b;...), MAIUSC(t), MINUSC(t), ESQUERDA(t;n), DIREITA(t;n)

Erros são explícitos e aparecem na célula, nunca viram zero silenciosamente:
#VAZIO! (vazio em conta), #DESCONHECIDO! (desconhecido em conta), #VALOR! (texto em conta numérica),
#DIV/0! (divisão por zero), #REF! (coluna inexistente), #SINTAXE! (fórmula inválida).
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from engiflow_api.domain.numeric import format_decimal, parse_decimal


class FormulaError(Exception):
    """Fórmula inválida (sintaxe ou referência). Mensagem em português, para o usuário."""


@dataclass(frozen=True)
class Err:
    code: str


ERR_EMPTY = "#VAZIO!"
ERR_UNKNOWN = "#DESCONHECIDO!"
ERR_VALUE = "#VALOR!"
ERR_DIV0 = "#DIV/0!"
ERR_REF = "#REF!"
ERR_SYNTAX = "#SINTAXE!"

_OPS = ("<>", "<=", ">=", "=", "<", ">", "+", "-", "*", "/", "(", ")", ";")


@dataclass(frozen=True)
class _Token:
    kind: str  # NUM, STR, REF, IDENT, OP, END
    text: str


def _tokenize(source: str) -> list[_Token]:
    tokens: list[_Token] = []
    i = 0
    while i < len(source):
        ch = source[i]
        if ch.isspace():
            i += 1
            continue
        if ch == "[":
            end = source.find("]", i + 1)
            if end < 0:
                raise FormulaError("Referência de coluna sem ']'.")
            tokens.append(_Token("REF", source[i + 1 : end].strip()))
            i = end + 1
            continue
        if ch == '"':
            end = source.find('"', i + 1)
            if end < 0:
                raise FormulaError("Texto sem aspas de fechamento.")
            tokens.append(_Token("STR", source[i + 1 : end]))
            i = end + 1
            continue
        if ch.isdigit():
            j = i
            while j < len(source) and (
                source[j].isdigit()
                or (source[j] in ".," and j + 1 < len(source) and source[j + 1].isdigit())
            ):
                j += 1
            tokens.append(_Token("NUM", source[i:j]))
            i = j
            continue
        if ch.isalpha():
            j = i
            while j < len(source) and (source[j].isalnum() or source[j] == "_"):
                j += 1
            tokens.append(_Token("IDENT", source[i:j]))
            i = j
            continue
        matched = next((op for op in _OPS if source.startswith(op, i)), None)
        if matched is None:
            raise FormulaError(f"Caractere não suportado: '{ch}'.")
        tokens.append(_Token("OP", matched))
        i += len(matched)
    tokens.append(_Token("END", ""))
    return tokens


def _name(text: str) -> str:
    """Nome de função sem acento e em maiúsculas: MÉDIA, Media e MEDIA são a mesma função."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).upper()


# AST como tuplas simples: ("num", Decimal) | ("str", s) | ("ref", nome) | ("neg", x)
# | ("bin", op, a, b) | ("cmp", op, a, b) | ("call", nome, [args])


class _Parser:
    def __init__(self, tokens: list[_Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> _Token:
        return self.tokens[self.pos]

    def take(self) -> _Token:
        token = self.tokens[self.pos]
        self.pos += 1
        return token

    def expect_op(self, op: str) -> None:
        token = self.take()
        if token.kind != "OP" or token.text != op:
            raise FormulaError(f"Esperado '{op}'.")

    def parse(self) -> Any:
        node = self.comparison()
        if self.peek().kind != "END":
            raise FormulaError("Conteúdo após o fim da fórmula.")
        return node

    def comparison(self) -> Any:
        left = self.additive()
        token = self.peek()
        if token.kind == "OP" and token.text in ("=", "<>", "<", ">", "<=", ">="):
            self.take()
            return ("cmp", token.text, left, self.additive())
        return left

    def additive(self) -> Any:
        node = self.term()
        while self.peek().kind == "OP" and self.peek().text in ("+", "-"):
            op = self.take().text
            node = ("bin", op, node, self.term())
        return node

    def term(self) -> Any:
        node = self.unary()
        while self.peek().kind == "OP" and self.peek().text in ("*", "/"):
            op = self.take().text
            node = ("bin", op, node, self.unary())
        return node

    def unary(self) -> Any:
        if self.peek().kind == "OP" and self.peek().text == "-":
            self.take()
            return ("neg", self.unary())
        return self.primary()

    def primary(self) -> Any:
        token = self.take()
        if token.kind == "NUM":
            number = parse_decimal(token.text)
            if number is None:
                raise FormulaError(f"Número inválido: {token.text}.")
            return ("num", number)
        if token.kind == "STR":
            return ("str", token.text)
        if token.kind == "REF":
            return ("ref", token.text)
        if token.kind == "IDENT":
            self.expect_op("(")
            args: list[Any] = []
            if not (self.peek().kind == "OP" and self.peek().text == ")"):
                args.append(self.comparison())
                while self.peek().kind == "OP" and self.peek().text == ";":
                    self.take()
                    args.append(self.comparison())
            self.expect_op(")")
            return ("call", _name(token.text), args)
        if token.kind == "OP" and token.text == "(":
            node = self.comparison()
            self.expect_op(")")
            return node
        raise FormulaError("Expressão incompleta.")


@dataclass(frozen=True)
class Formula:
    source: str
    tree: Any
    references: tuple[str, ...]


def compile_formula(source: str, columns: Sequence[str]) -> Formula:
    """Analisa a fórmula e confere as referências. Erros de sintaxe e de coluna são FormulaError."""
    if not source.strip():
        raise FormulaError("A fórmula está vazia.")
    tree = _Parser(_tokenize(source)).parse()
    known = {c.casefold(): c for c in columns}
    references: list[str] = []

    def visit(node: Any) -> None:
        kind = node[0]
        if kind == "ref":
            if node[1].casefold() not in known:
                raise FormulaError(f"Coluna '{node[1]}' não existe nesta tabela.")
            references.append(known[node[1].casefold()])
        elif kind in ("bin", "cmp"):
            visit(node[2])
            visit(node[3])
        elif kind == "neg":
            visit(node[1])
        elif kind == "call":
            for arg in node[2]:
                visit(arg)

    visit(tree)
    return Formula(source=source, tree=tree, references=tuple(dict.fromkeys(references)))


Value = str | Decimal | bool | None | Err


def _number(value: Value) -> Decimal | Err:
    if isinstance(value, Err):
        return value
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Err(ERR_UNKNOWN)
    if isinstance(value, bool):
        return Err(ERR_VALUE)
    if value == "":
        return Err(ERR_EMPTY)
    number = parse_decimal(value)
    return number if number is not None else Err(ERR_VALUE)


def _text(value: Value) -> str | Err:
    if isinstance(value, Err):
        return value
    if value is None:
        return Err(ERR_UNKNOWN)
    if isinstance(value, Decimal):
        return format_decimal(value)
    if isinstance(value, bool):
        return "VERDADEIRO" if value else "FALSO"
    return value


def _compare(op: str, a: Value, b: Value) -> bool | Err:
    for side in (a, b):
        if isinstance(side, Err):
            return side
        if side is None:
            return Err(ERR_UNKNOWN)
    na, nb = _number(a), _number(b)
    if isinstance(na, Decimal) and isinstance(nb, Decimal):
        return _ordered(op, na, nb)
    text_a, text_b = _text(a), _text(b)
    if isinstance(text_a, Err) or isinstance(text_b, Err):
        return Err(ERR_VALUE)
    return _ordered(op, text_a, text_b)


def _ordered[T: (Decimal, str)](op: str, left: T, right: T) -> bool:
    """Comparação de dois valores do mesmo tipo (dois números ou dois textos)."""
    if op == "=":
        return left == right
    if op == "<>":
        return left != right
    if op == "<":
        return left < right
    if op == ">":
        return left > right
    if op == "<=":
        return left <= right
    return left >= right


def _arith(op: str, a: Value, b: Value) -> Decimal | Err:
    na = _number(a)
    nb = _number(b)
    if isinstance(na, Err):
        return na
    if isinstance(nb, Err):
        return nb
    if op == "+":
        return na + nb
    if op == "-":
        return na - nb
    if op == "*":
        return na * nb
    if nb == 0:
        return Err(ERR_DIV0)
    return na / nb


def _numbers(args: list[Value]) -> list[Decimal] | Err:
    out: list[Decimal] = []
    for arg in args:
        number = _number(arg)
        if isinstance(number, Err):
            return number
        out.append(number)
    return out


def _call(name: str, args: list[Value]) -> Value:
    for arg in args:
        if isinstance(arg, Err):
            return arg
    if name == "SOMA":
        nums = _numbers(args)
        return nums if isinstance(nums, Err) else sum(nums, Decimal(0))
    if name == "MEDIA":
        nums = _numbers(args)
        if isinstance(nums, Err):
            return nums
        return Err(ERR_VALUE) if not nums else sum(nums, Decimal(0)) / Decimal(len(nums))
    if name == "MIN":
        nums = _numbers(args)
        return nums if isinstance(nums, Err) else (min(nums) if nums else Err(ERR_VALUE))
    if name == "MAX":
        nums = _numbers(args)
        return nums if isinstance(nums, Err) else (max(nums) if nums else Err(ERR_VALUE))
    if name == "CONTAR":
        return Decimal(sum(1 for a in args if a not in (None, "")))
    if name == "SE":
        if len(args) != 3 or not isinstance(args[0], bool):
            return Err(ERR_VALUE)
        return args[1] if args[0] else args[2]
    if name == "CONCAT":
        parts = [_text(a) for a in args]
        for part in parts:
            if isinstance(part, Err):
                return part
        return "".join(p for p in parts if isinstance(p, str))
    if name in ("MAIUSC", "MINUSC", "ESQUERDA", "DIREITA"):
        text = _text(args[0]) if args else Err(ERR_VALUE)
        if isinstance(text, Err):
            return text
        if name == "MAIUSC":
            return text.upper()
        if name == "MINUSC":
            return text.lower()
        count = _number(args[1]) if len(args) == 2 else Err(ERR_VALUE)
        if isinstance(count, Err) or count < 0:
            return Err(ERR_VALUE)
        n = int(count)
        return text[:n] if name == "ESQUERDA" else (text[len(text) - n :] if n else "")
    return Err(ERR_SYNTAX)


def _evaluate(node: Any, row: Mapping[str, str | None]) -> Value:
    kind: str = node[0]
    if kind == "num":
        number: Decimal = node[1]
        return number
    if kind == "str":
        text: str = node[1]
        return text
    if kind == "ref":
        column: str = node[1]
        cell: str | None = row.get(column)
        return cell
    if kind == "neg":
        value = _number(_evaluate(node[1], row))
        return value if isinstance(value, Err) else -value
    if kind == "bin":
        return _arith(node[1], _evaluate(node[2], row), _evaluate(node[3], row))
    if kind == "cmp":
        return _compare(node[1], _evaluate(node[2], row), _evaluate(node[3], row))
    if kind == "call":
        # SE avalia só o ramo escolhido: erros do ramo não escolhido não se propagam.
        if node[1] == "SE" and len(node[2]) == 3:
            condition = _evaluate(node[2][0], row)
            if isinstance(condition, Err) or not isinstance(condition, bool):
                return condition if isinstance(condition, Err) else Err(ERR_VALUE)
            return _evaluate(node[2][1] if condition else node[2][2], row)
        return _call(node[1], [_evaluate(arg, row) for arg in node[2]])
    return Err(ERR_SYNTAX)


def render(value: Value) -> str | None:
    """Texto da célula calculada. Erros viram o código do erro, para aparecerem explicitamente."""
    if isinstance(value, Err):
        return value.code
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format_decimal(value)
    if isinstance(value, bool):
        return "VERDADEIRO" if value else "FALSO"
    return value


def evaluate_row(formula: Formula, row: Mapping[str, str | None]) -> str | None:
    """Resultado de UMA linha. Não lança exceção por dado ruim: o erro fica na célula."""
    return render(_evaluate(formula.tree, row))


ERROR_CODES = (ERR_EMPTY, ERR_UNKNOWN, ERR_VALUE, ERR_DIV0, ERR_REF, ERR_SYNTAX)


def is_error_text(text: str | None) -> bool:
    """A célula calculada contém um erro explícito (não um resultado)."""
    return text in ERROR_CODES
