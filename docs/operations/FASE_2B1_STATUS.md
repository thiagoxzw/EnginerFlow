# Fase 2B.1 — Fundação das transformações: status

Atualizado: 2026-11-24. Branch: `feat/fase-2b-1-transformations` (a partir da `main` após o merge da 2A, commit `4f3c9d3`).
Dados: **somente sintéticos** (prefixo `SYN-`).

## Entregue

| Item | Como | Evidência |
|---|---|---|
| Registro central de capacidades | `application/operations/registry.py`: `OPERATIONS` com `rename_column`, `replace_text`, `set_rows_value`. Cada uma tem código, versão, esquema de parâmetros (Pydantic, campos extras proibidos) e função pura de aplicação | `test_registry_lists_the_three_minimal_operations`, `test_params_forbid_unknown_fields`, `GET /api/v1/operations/catalog` |
| Versionamento de tabelas | Tabela `dataset_versions`; versão 1 = importação original (id = id da tabela); versões seguintes são imutáveis | `test_import_creates_version_one_with_content_hash`, `test_preview_changes_nothing_and_apply_creates_new_version` |
| Linhas por versão | `dataset_version_rows` (substitui `dataset_rows`) | migração 0003 e testes da 2A adaptados (116 testes) |
| Metadados versionados | `dataset_metadata_versions`: colunas e mapeamento de cada versão | `test_rename_updates_columns_and_mapping_and_undo_restores` |
| Histórico de operações | `dataset_operations`: sequência, parâmetros, hash dos parâmetros, status (`applied`/`undone`), versão antes e depois, ator; nunca apagado | `test_history_lists_applied_operations_in_order` |
| Prévia e confirmação | `POST .../operations/preview` gera `preview_id` (validade de 15 min). Nada é gravado. Aplicar exige prévia válida e não usada | `test_preview_changes_nothing...`, `test_preview_is_single_use...`, `test_unknown_rows_and_expired_preview_are_refused` |
| Prévia == aplicação | a aplicação recalcula o resultado e compara o hash de conteúdo com o da prévia; divergência é `409` | `test_preview_changes_nothing...` (`content_sha256 == after_content_sha256`) |
| Desfazer e refazer | ponteiro de versão atual; a operação vai para `undone`; nada é apagado | `test_undo_and_redo_move_the_pointer_without_deleting_history`, `test_undo_with_stale_base_and_nothing_to_undo` |
| Proteção contra concorrência | `base_version_id` obrigatório; troca de versão é `UPDATE ... WHERE current_version_id = base`; consumo de prévia condicional; `IntegrityError` vira `409` | `test_concurrent_applications_on_same_base_create_one_version`, `test_stale_base_is_a_conflict_and_nothing_changes` |
| Idempotência | `Idempotency-Key`: mesma chave e mesma operação devolvem o resultado existente (`200`); chave usada por outra operação é `409` | `test_idempotency_key_replays_the_same_result` |
| Integridade e rastreabilidade | hash canônico do conteúdo (§ abaixo); auditoria de cada operação com hashes antes/depois | `test_canonical_*`, `test_streaming_hasher_matches_one_shot` |
| Valores vazio, desconhecido e zero | `""` = vazio; `null` = desconhecido; `"0"` = zero. Célula ausente em linha curta vira desconhecido (antes virava vazio) | `test_canonical_distinguishes_unknown_empty_and_zero`, `test_set_rows_value_distinguishes_empty_unknown_and_text` |
| Zeros à esquerda e especificações | valores são sempre texto; operações não convertem números | `test_undo...`, `test_preview_changes_nothing...` (`00123` preservado) |
| Arquivo original intacto | o arquivo em `originals/` não é alterado por nenhuma operação | `test_preview_changes_nothing...` (hash do arquivo antes e depois) |
| Migração 0003 com dados | versão 1 criada para cada tabela da 2A; linhas e hash preservados; downgrade restaura `dataset_rows` | `test_migration_0003_preserves_existing_rows_and_hash` |

### Hash canônico do conteúdo (§5.1 do planejamento)

- JSON com separadores fixos, chaves ordenadas, UTF-8 sem escape, strings em Unicode NFC.
- Cabeçalho: `{"columns":[...],"schema":1}`; uma linha JSON por linha de dados, terminada em `\n`.
- Inclui colunas, valores e a versão do esquema. Não inclui ids, datas, nome de arquivo nem ordem de inserção.
- Calculado em streaming. O teste `test_canonical_hash_is_stable_and_pinned` fixa a serialização: mudança nela quebra o teste de propósito.
- O hash do **arquivo exportado** é outra grandeza (depende do formato). Não é usado para comparar conteúdo.

### Decisões

- **Mapeamento é configuração atual, não versionado nesta entrega.** Alterar o mapeamento (`PUT /mapping`) continua sendo uma ação auditada, sem nova versão de dados. Versionar mapeamentos completos entra com os templates, na 2B.2. Desfazer e refazer de renomeação inverte e reaplica o nome dentro do mapeamento atual.
- **Operações não copiam para uma tabela nova** (ainda não há tabelas derivadas; isso é a 2B.3).
- **Cada versão materializa todas as linhas.** Simples e verificável; o custo de armazenamento será medido antes de definir retenção (2B.4).

## Resultados das verificações

| Verificação | Resultado |
|---|---|
| `pytest` (API, SQLite) | **116 passaram** (89 da 2A + 27 da 2B.1) |
| `ruff check`, formatação | sem erros |
| `mypy` strict | sem erros (37 arquivos) |
| `pnpm typecheck`, `lint`, `test`, `build` (web) | sem erros; 11 testes passaram |
| Migração 0001 → 0002 → 0003 e downgrade (SQLite) | coberto pelo teste de migração com dados |
| PostgreSQL 17 | **pendente do CI** (ver abaixo) |

## Pendente de PostgreSQL 17 (marcado, não substituído por SQLite)

- Migração 0003 upgrade, downgrade e upgrade em PostgreSQL.
- Teste de concorrência de aplicações simultâneas na mesma base (`test_concurrent_applications_on_same_base_create_one_version`), que usa o banco configurado.
- Migração de dados da 2A em PostgreSQL (tipos JSON reais, em vez de SQLite).

## Limitações conhecidas

1. **Sem interface.** A 2B.1 entrega a API e as capacidades. A UI de transformação (prévia, histórico, desfazer) é da 2B.4.
2. **Operações mínimas.** Só `rename_column`, `replace_text` e `set_rows_value`. As demais (filtros, substituição em lote com seleção, junções) estão nas entregas seguintes.
3. **Sem retenção.** Todas as versões são mantidas. `MAX_UNPINNED_VERSIONS` só será definido com medição.
4. **Operação carrega a tabela inteira na memória** para calcular a prévia e a aplicação. Não há medição de desempenho nesta entrega.
5. **Sem seleção manual de cabeçalho** (prevista para 2B.2).
6. **Mapeamento não versionado** (decisão acima).

## Homologação (revisão de integridade e CI)

### CI do commit `3e86aa0` (execução 45480885868) — concluído com sucesso

| Job | Resultado |
|---|---|
| API (Python) | **sucesso**: lint, formatação, mypy strict, migrações (upgrade, downgrade, upgrade), testes |
| Web (TypeScript) | **sucesso**: install com lockfile, typecheck, lint, teste (11), build |

- **116 testes aprovados** no PostgreSQL 17 (serviço `postgres:17-alpine` do CI, `ENGIFLOW_TEST_DATABASE_URL` definida). Inclui a migração 0003 nos três sentidos, a concorrência de aplicações simultâneas e a migração de dados da 2A.
- Nenhuma anotação nas execuções (sem avisos de depreciação de Actions).
- Execução anterior (`1d42470`, run 45480455872): falhou em PostgreSQL por um defeito real, corrigido em `3e86aa0` (ver CHANGELOG).

### Revisão de integridade (commit seguinte a `3e86aa0`)

| # | Cenário | Cobertura | Teste |
|---|---|---|---|
| 1 | Duas operações simultâneas na mesma versão | existente (PG no CI) | `test_concurrent_applications_on_same_base_create_one_version` |
| 2 | Mesma `Idempotency-Key` com parâmetros diferentes | **adicionado** | `test_same_idempotency_key_with_different_params_is_conflict` |
| 3 | Aplicação de prévia expirada | existente | `test_unknown_rows_and_expired_preview_are_refused` |
| 4 | Reutilização de prévia consumida | existente | `test_preview_is_single_use_and_apply_requires_same_base` |
| 5 | Prévia após undo e redo | **adicionado** (dois casos) | `test_preview_from_undone_state_is_refused_after_redo_changes_base`, `test_preview_generated_in_restored_state_is_refused_after_redo_and_hash_is_deterministic` |
| 6 | Nova operação após múltiplos undos | **adicionado** | `test_new_operation_after_multiple_undos_discards_the_redo_branch` |
| 7 | Mapeamentos em renomeações sucessivas | **adicionado** | `test_mapping_survives_successive_renames_and_undo_steps_back` |
| 8 | Rollback completo em falha durante a transformação | **adicionado** | `test_failure_mid_transformation_rolls_back_version_operation_and_preview` |
| 9 | Zeros à esquerda, vazio, desconhecido e zero | existente (unidade) + **adicionado** (fluxo com operações) | `test_empty_unknown_zero_and_leading_zeros_survive_operations` |
| 10 | Imutabilidade das versões anteriores | **adicionado** | `test_previous_versions_are_not_modified_by_later_operations` |
| 11 | Integridade do hash canônico | existente (vetor fixo) + **adicionado** (hash armazenado de cada versão recalculado a partir das linhas) | `test_stored_hash_of_every_version_matches_its_rows` |
| 12 | Colisão de nomes durante renomeação | existente | `test_rename_refuses_collision_ignoring_case_and_keeps_rows` |

- Nove testes novos em `tests/test_integridade_2b1.py`. Nenhum teste existente foi duplicado.
- **Defeitos de produto encontrados nesta revisão: nenhum.** Os erros que apareceram ao escrever os testes foram do próprio teste (base de prévia incorreta, fixture duplicada, patch de módulo inexistente) e foram corrigidos.
- Total local: **125 testes da API** (SQLite) e 11 do web. Lint, formatação, mypy strict, typecheck, lint e build sem erros.

### Limitações que permanecem
1. Sem interface de transformação (2B.2 entrega a interface).
2. Operações mínimas (três).
3. Sem retenção de versões.
4. Operações carregam a tabela inteira na memória. Sem medição de desempenho nesta entrega.
5. Mapeamento não versionado nesta entrega (a 2B.2 versiona mapeamentos e metadados).
