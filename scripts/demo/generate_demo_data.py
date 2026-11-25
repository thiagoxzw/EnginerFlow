"""Gera dados DEMONSTRATIVOS exclusivamente sintéticos para o EngiFlow.

Simula atividades de engenharia industrial (cadastro, exportação do ERP, BOM em duas revisões,
estoque, kits). Nenhum dado real ou corporativo é usado: nomes, códigos e valores são inventados.
A saída é determinística (semente fixa): gerar de novo produz os mesmos arquivos.

Uso (a partir da raiz do repositório):
    apps/api/.venv/Scripts/python.exe scripts/demo/generate_demo_data.py --out demo-data

Requer openpyxl (já é dependência da API). Não lê nenhum arquivo do usuário.
"""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

from openpyxl import Workbook

SEED = 20260125
EMPRESA = "SYN Industrial Ltda (dados fictícios)"

MATERIAIS = [
    ("000123", "Parafuso sextavado M8x25 DIN933 zincado", "PC", "COMPRADO", "0,012"),
    ("000124", "Porca sextavada M8 DIN934 zincada", "PC", "COMPRADO", "0,006"),
    ("000125", "Arruela lisa 8,4 mm DIN125 zincada", "PC", "COMPRADO", "0,002"),
    ("000210", "Chapa aço SAE1020 2,00 mm 1000x2000", "CH", "FABRICADO", "31,400"),
    ("000211", "Suporte dobrado 40x40 aço SAE1020", "PC", "FABRICADO", "0,350"),
    ("000305", "Mancal flangeado 25 mm rolamento 6205", "PC", "COMPRADO", "0,780"),
    ("000306", "Rolamento rígido de esferas 6205 2RS", "PC", "COMPRADO", "0,120"),
    ("000410", "Tubo aço carbono Ø 25,4 x 1,65 mm", "M", "COMPRADO", "0,980"),
    ("000411", "Cola epóxi bicomponente 50 ml", "UN", "COMPRADO", "0,090"),
    ("000123", "Parafuso sextavado M8x25 DIN933 zincado (cadastro antigo)", "PC", "COMPRADO", "0,012"),
    ("000500", "Válvula esfera latão 1/2 pol", "PC", "COMPRADO", "0,210"),
    ("000501", "Junta de vedação NBR Ø 30 mm", "PC", "COMPRADO", "0,004"),
    ("000600", "Eixo de transmissão aço 1045 Ø 20 mm", "PC", "FABRICADO", "1,150"),
    ("000601", "Pino elástico 4 x 20 mm", "PC", "COMPRADO", "0,003"),
    ("000700", "Correia dentada HTD 8M 1200", "PC", "COMPRADO", "0,240"),
]

# Exportação simulada do ERP: códigos com preenchimento, nomes de campo do ERP e um item a mais.
PROTHEUS_EXTRA = [
    ("000999", "Filtro de óleo hidráulico 10 µm", "PC", "COMPRADO", "0,450"),
]

ESTOQUE_LOCAIS = ["A-01", "A-02", "B-10", "C-03"]

COMPONENTES_CONJUNTO = [
    # codigo, descricao, qtd_rev_a, qtd_rev_b, unidade
    ("000123", "Parafuso sextavado M8x25 DIN933 zincado", "8", "10", "PC"),
    ("000124", "Porca sextavada M8 DIN934 zincada", "8", "8", "PC"),
    ("000125", "Arruela lisa 8,4 mm DIN125 zincada", "16", "16", "PC"),
    ("000305", "Mancal flangeado 25 mm rolamento 6205", "2", "2", "PC"),
    ("000306", "Rolamento rígido de esferas 6205 2RS", "2", "2", "PC"),
    ("000600", "Eixo de transmissão aço 1045 Ø 20 mm", "1", "1", "PC"),
    ("000601", "Pino elástico 4 x 20 mm", "2", "4", "PC"),
    ("000700", "Correia dentada HTD 8M 1200", "1", "1", "PC"),
    ("000411", "Cola epóxi bicomponente 50 ml", "0,5", "0,25", "UN"),
    ("000900", "Retentor 25 x 40 x 7 mm NBR", "2", "0", "PC"),
    ("000901", "Anel O-ring 20 x 2,5 mm FKM", "0", "2", "PC"),
]


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow(header)
        writer.writerows(rows)


def _write_xlsx(path: Path, sheet: str, rows: list[list[str]], title_rows: list[str] | None = None) -> None:
    """Planilha com códigos como TEXTO (formato '@'), preservando zeros à esquerda."""
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = sheet
    for line in title_rows or []:
        ws.append([line])
    for row in rows:
        ws.append(row)
    for row in ws.iter_rows():
        for cell in row:
            cell.number_format = "@"
    wb.save(path)


def generate(out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    files: list[Path] = []

    # 1) Cadastro de materiais (contém código duplicado de propósito).
    cad = out / "SYN-cadastro-materiais.csv"
    _write_csv(
        cad,
        ["Código", "Descrição", "Unidade", "Classificação", "Peso (kg)"],
        [list(m) for m in MATERIAIS],
    )
    files.append(cad)

    # 2) Exportação simulada do Protheus (campos B1_*, códigos de 6 posições, um item a mais).
    prot = out / "SYN-protheus-produtos.csv"
    _write_csv(
        prot,
        ["B1_COD", "B1_DESC", "B1_UM", "B1_TIPO", "B1_PESO"],
        [[c, d, u, t, p] for c, d, u, t, p in MATERIAIS[:-3] + PROTHEUS_EXTRA],
    )
    files.append(prot)

    # 3) BOM em duas revisões (XLSX), com cabeçalho depois de linhas de título.
    titulo = [
        f"Estrutura do conjunto válvula VX-100 — {EMPRESA}",
        "Documento fictício para demonstração",
        "",
    ]
    for revisao, col in (("A", 2), ("B", 3)):
        rows = [["Nível", "Código Componente", "Descrição", "Quantidade", "Unidade", "Revisão"]]
        for nivel, comp in enumerate(COMPONENTES_CONJUNTO, start=1):
            codigo, descricao, qa, qb, unidade = comp
            qtd = qa if col == 2 else qb
            if qtd == "0":
                continue  # componente removido na revisão B
            rows.append([str(1), codigo, descricao, qtd, unidade, revisao])
        # Divergência de descrição na revisão B para o mesmo código.
        if revisao == "B":
            rows = [r if r[1] != "000601" else [r[0], r[1], "Pino elástico 4 x 20 mm (ajustado)", r[3], r[4], r[5]] for r in rows]
        path = out / f"SYN-bom-valvula-vx100-rev{revisao}.xlsx"
        _write_xlsx(path, f"Rev {revisao}", rows, title_rows=titulo)
        files.append(path)

    # 4) Estoque de componentes (CSV com decimal de vírgula e um componente sem cadastro).
    est = out / "SYN-estoque-componentes.csv"
    estoque_rows: list[list[str]] = []
    for codigo, descricao, _qa, _qb, unidade in COMPONENTES_CONJUNTO:
        saldo = f"{rng.randint(0, 400)},{rng.randint(0, 99):02d}"
        estoque_rows.append([codigo, rng.choice(ESTOQUE_LOCAIS), saldo, unidade, "2026-01-15"])
    estoque_rows.append(["000777", "C-03", "12,00", "PC", "2026-01-15"])  # sem cadastro
    _write_csv(est, ["Código", "Local", "Saldo", "Unidade", "Última contagem"], estoque_rows)
    files.append(est)

    # 5) Kits (um código aparece em dois kits; um componente ausente do cadastro).
    kits = out / "SYN-kits.csv"
    _write_csv(
        kits,
        ["Kit", "Código Componente", "Quantidade"],
        [
            ["KIT-MONT-01", "000123", "8"],
            ["KIT-MONT-01", "000124", "8"],
            ["KIT-MONT-01", "000125", "16"],
            ["KIT-VED-02", "000501", "2"],
            ["KIT-VED-02", "000123", "2"],
            ["KIT-VED-02", "000998", "1"],  # sem correspondência no cadastro
        ],
    )
    files.append(kits)

    # 6) Relatório de estoque em XLSX com título (teste de seleção manual de cabeçalho).
    rel = out / "SYN-relatorio-estoque.xlsx"
    rel_rows = [["Código", "Descrição", "Saldo"]]
    for codigo, descricao, *_ in COMPONENTES_CONJUNTO[:5]:
        rel_rows.append([codigo, descricao, str(rng.randint(0, 200))])
    _write_xlsx(rel, "Estoque", rel_rows, title_rows=[f"Relatório fictício — {EMPRESA}", ""])
    files.append(rel)

    leia = out / "LEIA-ME.txt"
    leia.write_text(
        "Dados DEMONSTRATIVOS sintéticos gerados por scripts/demo/generate_demo_data.py.\n"
        "Não contêm informações reais. Códigos, nomes e valores são inventados.\n"
        "Codificação CSV: UTF-8 com ponto e vírgula. Planilhas: XLSX.\n",
        encoding="utf-8",
    )
    files.append(leia)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="demo-data", help="pasta de saída (ignorada pelo git)")
    args = parser.parse_args()
    files = generate(Path(args.out))
    for path in files:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
