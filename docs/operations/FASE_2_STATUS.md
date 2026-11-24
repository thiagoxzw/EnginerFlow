# Fase 2 — Data Studio: status de verificação

Data: 2026-11-24. Branch: `feat/fase-2-data-studio`. Dados: **somente sintéticos** (prefixo `SYN-`, gerados em código).

Legenda: **Testado** = executado e observado nesta máquina · **Testado em CI** = configurado, aguardando execução · **Planejado** = não feito.

## Entregue

| Item | Status | Evidência |
|---|---|---|
| Importar CSV: detecção de delimitador (`,` `;` tab `|`), encoding UTF-8 e Windows-1252 | Testado | `test_read_csv_detects_semicolon_and_cp1252_and_keeps_zeros` |
| Importar XLSX: seleção de aba, primeira aba por padrão, cabeçalho detectado após linhas de título | Testado | `test_read_xlsx_*`, `test_header_detection_skips_title_row` |
| Códigos como texto: zeros à esquerda preservados em CSV e XLSX | Testado | `test_read_xlsx_default_sheet_keeps_text_codes_and_warns_on_numbers`, `test_code_key_preserves_leading_zeros...` |
| Aviso quando o Excel já converteu códigos em número (zeros possivelmente perdidos na origem) | Testado | `test_read_xlsx_default_sheet...` (aviso emitido) |
| Identificação de cabeçalho, colunas vazias e repetidas | Testado | `test_unique_headers_fills_blanks_and_suffixes_repeats` |
| Mapeamento de colunas para campos canônicos (código, descrição, unidade, quantidade, categoria), validado | Testado | `test_validate_mapping_rejects_*`, `test_mapping_rejects_unknown_column`, `test_mapping_then_duplicates_and_compare` |
| Template de mapeamento: o mapeamento fica salvo na tabela (`mapping`), com auditoria de antes/depois | Testado (salvo por tabela) | `data_studio.mapping` na auditoria. **Templates reutilizáveis entre arquivos ficam para a próxima etapa** |
| Duplicatas exatas de código (chave sem diferença de caixa nem espaços nas bordas) | Testado | `test_exact_duplicates_do_not_merge_leading_zero_variants`, API `duplicates` |
| Zeros à esquerda: `00123` × `0123` são **sugestão**, nunca fusão | Testado | `test_leading_zero_suspicions_are_only_suggestions` |
| Descrições semelhantes: score (0 a 1) e tokens em comum como evidência; sem equivalência automática | Testado | `test_similar_descriptions_report_score_and_evidence` |
| Comparação de códigos entre duas tabelas (somente em A, somente em B, em ambas, candidatos por zeros) | Testado | `test_compare_codes_keeps_zero_variants_as_candidates_only`, `test_mapping_then_duplicates_and_compare` |
| Idempotência: mesmo arquivo (mesmo SHA-256 e aba) não duplica registros | Testado | `test_import_is_idempotent_for_same_hash_and_sheet` |
| Preservação do arquivo original (guardado com nome gerado pelo hash) | Testado | `test_import_is_idempotent...` (verifica o arquivo gravado) |
| Proteções: limite de tamanho (MB), limite de linhas, limite de colunas, validação por assinatura, rejeição de `.xls` e binário | Testado | `test_detect_kind_rejects_*`, `test_row_limit_is_enforced`, `test_upload_over_limit_is_rejected` |
| Proteção contra zip bomb no XLSX (razão de compressão e número de partes) | Testado | `test_zip_bomb_like_xlsx_is_rejected` |
| Autenticação obrigatória nas rotas | Testado | `test_upload_requires_authentication` |
| Auditoria de importação, mapeamento e comparação | Testado (importação e mapeamento) | `test_upload_list_detail_and_rows_flow` (ação `data_studio.import`) |
| Erros de regra de negócio em Problem Details (422) | Testado | `test_mapping_then_duplicates_and_compare` (comparação sem mapeamento) |
| Interface: upload, lista, mapeamento, prévia, avisos, duplicatas e comparação | Testado (unitário + build + navegador) | 2 testes do cliente; captura de tela |

## Resultados das verificações

| Verificação | Resultado |
|---|---|
| `pytest` (API, SQLite) | 40 passaram (18 da Fase 1 e 22 novos) |
| `ruff check` e `ruff format --check` | sem erros |
| `mypy` strict | sem erros (29 arquivos) |
| `pnpm typecheck` | sem erros |
| `pnpm lint` (`max-warnings=0`) | sem erros |
| `pnpm test` (Vitest) | 9 passaram |
| `pnpm build` | compilou; rota `/data-studio` gerada |
| Migrações 0001 → 0002 → 0001 → 0002 (SQLite) | sem erros |
| Smoke ponta a ponta (API e web em produção local) | upload 201, mapeamento 200, duplicatas `00123`/`AB1`, sugestão `00123`×`0123`, semelhança `1.0` e `0.9583` |

## Limitações conhecidas

1. **PostgreSQL local não verificado** (mesmo bloqueio da Fase 1). A suíte roda contra PostgreSQL no CI, quando o PR for aberto.
2. **Desempenho não medido.** As metas de 100 MB, 500 mil linhas e 100 mil ocorrências ainda não foram testadas com arquivo real de tamanho. As linhas são gravadas como JSON, uma por linha, e a análise de duplicatas carrega todas as linhas do campo em memória.
3. **Comparação aproximada limitada a 5.000 descrições** por análise. Acima disso, a API recusa e pede filtro. A blocagem pelos três primeiros caracteres também perde pares cujos prefixos diferem (ex.: `M8 PARAFUSO` × `PARAFUSO M8`).
4. **Sem templates reutilizáveis de mapeamento** entre arquivos, sem transformações em lote, sem localizar e substituir, sem filtros e sem exportação Excel/CSV do resultado. Ficam para as próximas entregas da fase.
5. **Sem exclusão de tabela** pela interface ainda.
6. Arquivos de **dados reais não foram usados** em nenhum teste nem smoke.

## Próximas etapas

1. Abrir o PR `feat/fase-2-data-studio` → `main` e confirmar o CI (PostgreSQL 17 e web).
2. Medir desempenho com planilha sintética de 100 MB e 500 mil linhas, e ajustar limites com os números reais.
3. Templates reutilizáveis de mapeamento, filtros, exportação Excel/CSV e exclusão de tabelas.
