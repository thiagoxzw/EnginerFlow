# Fase 2 — Data Studio: status de verificação

Atualizado: 2026-11-24 (revisão técnica 1). Branch: `feat/fase-2-data-studio`.
Dados: **somente sintéticos** (prefixo `SYN-`, gerados em código). Nenhum dado real foi usado.

Legenda: **Testado** = executado nesta máquina · **Medido** = número real desta máquina, em amostra sintética · **Não validado** = sem medição ou sem teste.

## Entregue e revisado

| Item | Status | Evidência |
|---|---|---|
| Leitura CSV (delimitador, UTF-8 e Windows-1252) e XLSX (aba, cabeçalho após títulos) | Testado | `test_read_*`, `test_header_detection_*` |
| Códigos como texto, zeros à esquerda preservados | Testado | `test_read_xlsx_default_sheet_*`, `test_code_key_*` |
| Mapeamento de colunas validado e auditado | Testado | `test_validate_mapping_*`, `test_mapping_*` |
| Duplicatas exatas de código | Testado | `test_exact_duplicates_*` |
| Sugestões de zeros à esquerda (nunca fusão) | Testado | `test_leading_zero_suspicions_*` |
| Comparação de códigos entre tabelas | Testado | `test_compare_codes_*`, `test_mapping_then_duplicates_and_compare` |
| Idempotência por hash e aba | Testado | `test_import_is_idempotent_*` |
| Proteções: tamanho, linhas, colunas, assinatura, `.xls`, binário, zip bomb | Testado | `test_detect_kind_*`, `test_zip_bomb_*`, `test_row_limit_*`, `test_upload_over_limit_*` |
| Autenticação obrigatória | Testado | `test_upload_requires_authentication`, `test_regression_export_requires_authentication` |

### Correções da revisão técnica

**1. Comparação por zeros à esquerda não perde candidatos.** Três causas corrigidas:
- Só era guardada uma variante por grupo de zeros. Com `123` e `0123` na outra tabela, um candidato sumia.
- A comparação só considerava chaves exclusivas de um lado. `00123` × `123` (que existe nos dois lados) não era candidato.
- Códigos só de zeros (`000` e `0`) ficavam com chave vazia e nunca eram comparados.
- A API também **cortava as listas em 1.000 itens**. Agora as listas saem completas.

Testes: `test_regression_candidates_*`, `test_regression_all_zero_codes_*`, `test_regression_api_compare_returns_every_candidate_without_truncation` (1.100 candidatos).

**2. Memória na importação.** A versão anterior lia o arquivo inteiro para bytes, depois para texto, depois para uma lista de todas as linhas. Agora:
- O upload é gravado em disco em pedaços de 1 MB, com hash calculado durante a gravação.
- O CSV é lido linha a linha, do disco. O XLSX é lido em modo somente-leitura do openpyxl.
- As linhas são gravadas no banco em lotes (`INSERT_BATCH_SIZE`, padrão 2.000).

Testes: `test_regression_csv_rows_are_a_lazy_generator_*`, `test_regression_file_handle_is_closed_*`, `test_regression_large_import_is_written_in_batches`.

**Medições** (`apps/api/scripts/bench_data_studio.py`, máquina de desenvolvimento, Windows, SQLite, amostra sintética de linhas simples):

| Caso | 20 mil linhas (1,0 MB) | 100 mil linhas (5,3 MB) |
|---|---|---|
| Leitura CSV **antiga** (bytes em memória): tempo / pico Python | 0,06 s / 10,6 MB | 0,49 s / 53,2 MB |
| Leitura CSV **nova** (streaming): tempo / pico Python | 0,06 s / 0,2 MB | 0,29 s / 0,2 MB |
| Importação completa CSV (grava no SQLite): tempo / pico | 0,28 s / 2,8 MB | 1,43 s / 5,4 MB |
| Importação completa XLSX (grava no SQLite): tempo / pico | 0,93 s / 6,2 MB | 13,4 s / 13,0 MB |

Leitura de "pico Python" = memória alocada pelo código Python, medida com `tracemalloc`. **Não é o consumo do processo inteiro** (interpretador, SQLite e bibliotecas nativas ficam de fora). O pico da leitura CSV fica constante conforme o arquivo cresce; o pico da importação cresce com as linhas por causa do banco e do lote.

**3. Similaridade independente da ordem dos termos.** Antes, a comparação só era feita entre descrições com o mesmo prefixo de 3 caracteres. `M8 PARAFUSO` e `PARAFUSO M8` nunca eram comparadas. Agora:
- Candidatos vêm de um índice invertido por token (ordem não importa).
- Pontuação não afeta o score (`M8-SEXTAVADO` = `M8 SEXTAVADO`).
- Score = maior entre a similaridade do texto na ordem original e com os termos ordenados.
- Cada par informa o motivo: `descrição idêntica`, `mesmos termos em outra ordem` ou `texto semelhante`.

Testes: `test_regression_word_order_*`, `test_regression_pair_found_*`, `test_regression_punctuation_*`, `test_regression_common_token_*`.

**4. Consistência entre arquivo e transação.** Antes, o arquivo final era gravado antes da transação. Se o commit falhasse, ficava um arquivo órfão. Agora:
1. O upload vai para um temporário `.tmp-*` dentro da pasta de armazenamento.
2. As linhas são gravadas em lotes, dentro da transação ainda não confirmada.
3. O temporário é movido para o nome final (hash) só depois de todas as linhas.
4. Se qualquer passo falhar, a transação é desfeita e o arquivo final **criado por este pedido** é removido. Um arquivo que já existia nunca é removido.
5. Se outro pedido importar o mesmo arquivo entre a verificação e o commit (`IntegrityError`), o resultado é o registro existente.
6. Temporários de processos interrompidos (mais de 1 hora) são limpos na próxima importação.

Testes: `test_regression_failed_parse_leaves_no_dataset_no_file_no_temp`, `test_regression_commit_failure_removes_new_file_and_rows`, `test_regression_commit_failure_keeps_file_that_already_existed`.

**5. Exportação CSV e XLSX.** Disponível na API e na interface:
- Tabela: `GET /api/v1/datasets/{id}/export?format=csv|xlsx`
- Duplicatas: `GET /api/v1/datasets/{id}/duplicates/export?format=…` (no XLSX, uma aba por tipo de resultado)
- Comparação: `POST /api/v1/datasets/compare/export?format=…`

Regras:
- CSV com separador `;` e BOM UTF-8, padrão do Excel em português.
- Valores que o Excel tomaria como fórmula (`=`, `+`, `@`, e `-` seguido de letra) recebem apóstrofo. Códigos numéricos com sinal (ex.: `-0123`) não são alterados.
- XLSX: cada célula textual é gravada com tipo string explícito e formato `@`. Um código `=SUM(A1)` continua texto.

Testes: `test_regression_csv_export_*`, `test_regression_xlsx_export_*`, `test_regression_exported_csv_reimports_with_zeros_intact`, `test_regression_export_*`. Smoke ponta a ponta: `00123` abre como texto no XLSX exportado.

## Resultados das verificações

| Verificação | Resultado |
|---|---|
| `pytest` (API, SQLite) | **62 passaram** |
| `ruff check` e `ruff format --check` (API) | sem erros |
| `mypy` strict (API) | sem erros (30 arquivos) |
| `pnpm typecheck`, `pnpm lint` (web) | sem erros |
| `pnpm test` (web) | **11 passaram** |
| `pnpm build` (web) | compilou, rota `/data-studio` |
| Migrações 0001 → 0002 (SQLite) | sem erros |
| Smoke ponta a ponta: upload, mapeamento, 3 exportações, comparação | ok; XLSX com código como texto; armazenamento sem temporário |

## Não validado (limitações explícitas)

1. **Limites de capacidade não comprovados.** Os valores `max_upload_mb=100`, `max_rows=500.000` e o limite de 5.000 descrições para comparação aproximada são **configurações iniciais, não capacidades testadas**. Não há teste com 100 MB nem com 500 mil linhas. Não afirmamos que o sistema suporta esses volumes.
2. **Desempenho medido apenas em SQLite e em uma máquina.** Não há medição em PostgreSQL, nem em volume maior que 100 mil linhas, nem em disco lento.
3. **Memória da análise de duplicatas e das exportações não foi medida.** Ambas carregam todas as linhas do campo em memória. A comparação aproximada tem custo quadrático dentro de cada grupo de token, limitado pelo limite de 5.000 descrições.
4. **Exportação gera o arquivo inteiro em memória** (XLSX sempre; CSV também). Não há exportação em streaming.
5. **Blocagem por token pode perder pares:** tokens presentes em mais de 500 descrições não geram candidatos. Se duas descrições só compartilham tokens assim, o par não aparece. Limite documentado em `MAX_TOKEN_DOCUMENT_FREQUENCY`.
6. **XLSX é mais lento que CSV.** openpyxl é Python puro: cerca de 13 s para 100 mil linhas nesta máquina, contra 1,4 s do CSV.
7. **Códigos perdidos na origem não são recuperáveis.** Se o Excel já converteu o código em número, os zeros se foram. O sistema avisa, mas não corrige.
8. **Sem templates reutilizáveis de mapeamento, filtros, exclusão de tabela ou operações em lote.** Ficam para as próximas entregas.
9. **PostgreSQL local não verificado nesta máquina** (Docker sem virtualização). O CI roda a suíte contra PostgreSQL 17 quando o PR for aberto.

## Próximas etapas

1. Abrir o PR para `main` e acompanhar o CI.
2. Medir com volume maior (ex.: 500 mil linhas) em PostgreSQL, e só então definir limites com base nos números obtidos.
3. Medir a memória das duplicatas e das exportações, e avaliar exportação em streaming se o volume exigir.
4. Templates de mapeamento, filtros e exclusão de tabelas.
