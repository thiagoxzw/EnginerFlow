"""Regressões da Etapa 2 (verificação adicional da Fase 2A). Dados SINTÉTICOS (prefixo SYN-).

Cada teste documenta um defeito que foi reproduzido antes da correção.
Itens que exigem PostgreSQL NÃO são cobertos aqui: ver docs/operations/FASE_2_STATUS.md.
"""

from __future__ import annotations

import hashlib
import threading
import uuid
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import sessionmaker

from engiflow_api.application import data_studio as ds
from engiflow_api.domain import tabular
from engiflow_api.domain.errors import DomainError
from engiflow_api.domain.tabular import (
    detect_header_index,
    normalize_description,
    similar_descriptions,
    spec_signature,
    unique_headers,
)
from engiflow_api.infrastructure.models import Dataset, DatasetRow
from engiflow_api.infrastructure.readers import ImportLimits

SYN_CSV = "SYN-Código;SYN-Descrição\n00123;SYN parafuso m8\n0123;SYN parafuso m8\n".encode()


def _limits() -> ImportLimits:
    return ImportLimits()


# ---------- 1. colisão de nomes de cabeçalho ----------


def test_generated_header_never_collides_with_existing_name() -> None:
    """Defeito: ['A','A','A (2)'] gerava ['A','A (2)','A (2)'] (duplicado)."""
    names = unique_headers(["A", "A", "A (2)"])
    assert names == ["A", "A (2)", "A (2) (2)"]
    assert len({n.casefold() for n in names}) == 3


def test_header_names_are_unique_ignoring_case() -> None:
    names = unique_headers(["Código", "CÓDIGO", "código"])
    assert len({n.casefold() for n in names}) == 3


def test_blank_and_repeated_headers_stay_unique() -> None:
    names = unique_headers(["", "Coluna 2", "", "Coluna 2"])
    assert len({n.casefold() for n in names}) == 4


# ---------- 2. detecção de cabeçalho em planilha textual ----------


def test_header_detected_when_data_rows_are_wider_and_textual() -> None:
    """Defeito: a linha de dados mais larga e textual era escolhida como cabeçalho."""
    rows = [
        ["Código", "Descrição", "Unidade"],
        ["AB1", "Parafuso sextavado", "UN", "obs livre"],
        ["AB2", "Porca sextavada", "UN", "obs livre"],
    ]
    assert detect_header_index(rows) == 0


def test_header_detected_after_title_row_in_textual_sheet() -> None:
    rows = [["Relatório sintético"], ["Código", "Descrição"], ["AB1", "Parafuso"]]
    assert detect_header_index(rows) == 1


def test_numeric_row_is_not_a_header() -> None:
    rows = [["1", "2", "3"], ["Código", "Descrição", "Unidade"], ["AB1", "Parafuso", "UN"]]
    assert detect_header_index(rows) == 1


def test_fallback_without_candidate_uses_first_row() -> None:
    assert detect_header_index([["x"], ["y"]]) == 0


# ---------- 3. descrições idênticas com tokens frequentes ----------


def _frequent_background(n: int = 600) -> list[tuple[int, str]]:
    # 'parafuso' e 'peça' aparecem em centenas de descrições: ambos excedem o limite de token.
    return [(i + 2, f"parafuso peça item{i}") for i in range(n)]


def test_identical_descriptions_found_when_all_tokens_are_frequent() -> None:
    """Defeito: o par idêntico era ignorado porque todos os seus tokens excediam o limite."""
    items = _frequent_background() + [(900, "parafuso peça"), (901, "parafuso peça")]
    pairs = similar_descriptions(items, threshold=0.85, max_items=5000)
    match = [p for p in pairs if p.row_a == 900 and p.row_b == 901]
    assert match and match[0].score == 1.0
    assert match[0].reason == "descrição idêntica"


def test_same_terms_in_other_order_found_when_tokens_are_frequent() -> None:
    items = _frequent_background() + [(900, "parafuso peça m8"), (901, "m8 peça parafuso")]
    pairs = similar_descriptions(items, threshold=0.85, max_items=5000)
    assert any(p.row_a == 900 and p.row_b == 901 and p.score == 1.0 for p in pairs)


def test_frequent_common_token_alone_does_not_create_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Continua válido: pares que só compartilham token frequente não são gerados."""
    monkeypatch.setattr(tabular, "MAX_TOKEN_DOCUMENT_FREQUENCY", 2)
    items = [(i, f"comum item{i}") for i in range(1, 6)]
    assert similar_descriptions(items, threshold=0.5) == []


# ---------- 4. consumo de memória na geração de candidatos ----------


def test_candidate_generation_stops_at_cap_instead_of_growing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defeito: o limite era checado só ao final; no pior caso havia 3,3 milhões de pares
    (371 MB). Agora a geração para ao atingir o limite."""
    monkeypatch.setattr(tabular, "MAX_CANDIDATE_PAIRS", 100)
    pairs: set[tuple[int, int]] = set()
    with pytest.raises(DomainError, match="Muitos candidatos"):
        tabular._add_group_pairs(list(range(1000)), pairs)
    assert len(pairs) == 101  # parou logo após o limite


def test_worst_case_is_refused_with_bounded_pairs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tabular, "MAX_TOKEN_DOCUMENT_FREQUENCY", 10_000)
    items = [(i, " ".join(f"t{(i * k) % 40}" for k in range(1, 4))) for i in range(1500)]
    seen: list[int] = []
    original = tabular._add_group_pairs

    def spy(members: list[int], pairs: set[tuple[int, int]]) -> None:
        original(members, pairs)
        seen.append(len(pairs))

    monkeypatch.setattr(tabular, "_add_group_pairs", spy)
    monkeypatch.setattr(tabular, "MAX_CANDIDATE_PAIRS", 5_000)
    with pytest.raises(DomainError):
        similar_descriptions(items, threshold=0.0, max_items=5000)
    assert max(seen) <= 5_001


# ---------- 5. importações simultâneas do mesmo arquivo ----------


def test_concurrent_imports_of_same_file_create_exactly_one_dataset(
    engine: Engine,
    session_factory: sessionmaker,  # type: ignore[type-arg]
    tmp_path: Path,
) -> None:
    """Quatro pedidos simultâneos com o mesmo conteúdo: um registro, um arquivo, nenhum temporário.

    Roda contra o banco configurado em ENGIFLOW_TEST_DATABASE_URL (PostgreSQL 17 no CI) ou,
    na ausência dela, SQLite. Os dois resultados são evidências distintas: ver FASE_2_STATUS.md.
    """
    storage = tmp_path / "originals"
    storage.mkdir()
    digest = hashlib.sha256(SYN_CSV).hexdigest()
    results: list[bool] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(4)

    def worker() -> None:
        temp = storage / f".tmp-{uuid.uuid4().hex}"
        temp.write_bytes(SYN_CSV)
        barrier.wait()
        try:
            with session_factory() as db:
                result = ds.import_upload(
                    db,
                    actor="t@example.com",
                    filename="SYN-concorrente.csv",
                    temp_path=temp,
                    digest=digest,
                    sheet=None,
                    limits=_limits(),
                    storage_dir=storage,
                    correlation_id=None,
                )
                results.append(result.created)
        except BaseException as exc:  # registrado e verificado abaixo
            errors.append(exc)
            temp.unlink(missing_ok=True)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)

    with session_factory() as db:
        datasets = db.scalar(select(func.count()).select_from(Dataset))
        rows = db.scalar(select(func.count()).select_from(DatasetRow))
    finals = [p for p in storage.iterdir() if not p.name.startswith(".tmp-")]
    temps = [p for p in storage.iterdir() if p.name.startswith(".tmp-")]
    assert errors == [], f"erros inesperados: {errors!r}"
    assert datasets == 1
    assert rows == 2  # linhas do arquivo: nenhuma duplicada pelos pedidos concorrentes
    assert results.count(True) == 1
    assert len(finals) == 1 and finals[0].name == f"{digest}.csv"
    assert finals[0].read_bytes() == SYN_CSV
    assert temps == []


# ---------- 6. preservação de especificações técnicas ----------


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Ø10 mm", "10 mm"),  # diâmetro x medida simples
        ("±0,1 mm", "0,1 mm"),  # tolerância x valor nominal
        ("10,5 mm", "105 mm"),  # vírgula decimal não pode sumir
        ("M8 x 20 mm", "M8 x 25 mm"),  # comprimento diferente
        ("Parafuso 10 mm", "Parafuso 10 kg"),  # unidade diferente
        ("Tubo 45°", "Tubo 45"),  # ângulo x número puro
        ("Vedação 5%", "Vedação 5"),  # percentual x número puro
    ],
)
def test_technical_specs_differ_and_are_never_equivalent(left: str, right: str) -> None:
    pairs = similar_descriptions([(1, left), (2, right)], threshold=0.0)
    assert pairs, "par deve aparecer como semelhante, com evidência"
    assert pairs[0].spec_match is False
    assert pairs[0].reason.startswith("especificações diferentes")
    assert pairs[0].score < 1.0 or normalize_description(left) != normalize_description(right)


def test_same_spec_with_different_notation_is_equal() -> None:
    pairs = similar_descriptions([(1, "M8x20"), (2, "M8 x 20")], threshold=0.0)
    assert pairs[0].spec_match is True and pairs[0].score == 1.0


def test_decimal_comma_and_point_are_the_same_value() -> None:
    pairs = similar_descriptions([(1, "10,5 mm"), (2, "10.5 mm")], threshold=0.0)
    assert pairs[0].spec_match is True and pairs[0].score == 1.0


def test_spec_signature_keeps_symbols_and_units() -> None:
    assert spec_signature(normalize_description("Ø10 ±0,1 mm 45°").split()) == (
        "0.1",
        "10",
        "45",
        "diam",
        "graus",
        "mm",
        "tol",
    )


# ---------- 7. persistência após reinício ----------


def test_original_file_and_rows_survive_restart(
    engine: Engine, database_url: str, tmp_path: Path
) -> None:
    """Arquivo original e linhas continuam disponíveis após fechar e reabrir a conexão.

    Usa o banco configurado (PostgreSQL no CI quando ENGIFLOW_TEST_DATABASE_URL está definida).
    """
    storage = tmp_path / "originals"
    storage.mkdir()
    digest = hashlib.sha256(SYN_CSV).hexdigest()
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    temp = storage / f".tmp-{uuid.uuid4().hex}"
    temp.write_bytes(SYN_CSV)
    with factory() as db:
        ds.import_upload(
            db,
            actor="t@example.com",
            filename="SYN-reinicio.csv",
            temp_path=temp,
            digest=digest,
            sheet=None,
            limits=_limits(),
            storage_dir=storage,
            correlation_id=None,
        )
    engine.dispose()  # simula reinício: nenhuma conexão ou objeto em memória sobrevive

    engine2 = create_engine(database_url)
    factory2 = sessionmaker(bind=engine2, expire_on_commit=False)
    with factory2() as db:
        dataset = db.scalar(select(Dataset).where(Dataset.source_sha256 == digest))
        assert dataset is not None and dataset.row_count == 2
        stored_rows = db.scalar(
            select(func.count()).select_from(DatasetRow).where(DatasetRow.dataset_id == dataset.id)
        )
        assert stored_rows == 2
    stored = storage / f"{digest}.csv"
    assert stored.exists()
    assert hashlib.sha256(stored.read_bytes()).hexdigest() == digest
    engine2.dispose()


# ---------- 8. limite de cabeçalhos na importação real ----------


def test_import_with_colliding_headers_yields_unique_columns(tmp_path: Path) -> None:
    data = b"A;A;A (2)\n1;2;3\n"
    from engiflow_api.infrastructure.readers import open_csv

    path = tmp_path / "colisao.csv"
    path.write_bytes(data)
    with open_csv(path, _limits()) as stream:
        assert len({c.casefold() for c in stream.columns}) == 3


# ---------- 9. teto de candidatos também na comparação de códigos ----------


def test_zero_group_comparison_is_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    """Defeito: 1000 variantes do mesmo código geravam ~1 milhão de pares sem limite."""
    from engiflow_api.domain.tabular import compare_codes, leading_zero_suspicions

    monkeypatch.setattr(tabular, "MAX_CANDIDATE_PAIRS", 10)
    left = ["0" * k + "123" for k in range(1, 6)]  # 5 variantes
    right = ["0" * k + "123" for k in range(0, 5)]  # 5 variantes -> 25 pares possíveis
    with pytest.raises(DomainError, match="Muitos candidatos"):
        compare_codes(left, right)
    with pytest.raises(DomainError, match="Muitos candidatos"):
        leading_zero_suspicions(left + right)


def test_zero_group_comparison_within_cap_is_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    from engiflow_api.domain.tabular import compare_codes

    monkeypatch.setattr(tabular, "MAX_CANDIDATE_PAIRS", 100)
    result = compare_codes(["00123"], ["123", "0123"])
    assert len(result.leading_zero_candidates) == 2
