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

## Etapa 2 — verificações adicionais (2026-11-24)

Cada item foi reproduzido com um script antes da correção. Os testes de regressão estão em `apps/api/tests/test_data_studio_revisao2.py`.

| Verificação | Resultado antes | Ação | Status |
|---|---|---|---|
| Colisão de nomes de cabeçalho | `['A','A','A (2)']` gerava `A (2)` duplicado | Dedup contra todos os nomes já usados, sem diferença de caixa | **Corrigido**: `unique_headers(["A","A","A (2)"])` → `A`, `A (2)`, `A (2) (2)` |
| Detecção de cabeçalho em planilha textual | linha de dados mais larga era escolhida (índice 1 em vez de 0) | Primeira linha plausível: largura compatível, sem números puros, nomes únicos | **Corrigido**; títulos de uma célula são ignorados. Limitação: se o cabeçalho vier depois de um título com 2 ou mais células textuais, o título pode ser escolhido |
| Descrições idênticas com tokens frequentes | par `parafuso peça` / `parafuso peça` ignorado (todos os tokens acima de 500) | Candidatos também por descrição normalizada idêntica e por mesmos termos, independentemente da frequência | **Corrigido** |
| Memória na geração de candidatos | pior caso: 3,3 milhões de pares, **371 MB** e 5,5 s antes de recusar | Teto aplicado durante a geração, não ao final | **Corrigido**: 36,7 MB e 0,5 s (mesmo caso); também na comparação por zeros e na suspeita de zeros |
| Importações simultâneas do mesmo arquivo | não testado | 4 threads, mesmo conteúdo | **Testado em SQLite**: 1 registro, 1 arquivo final, nenhum temporário, sem erro. **PostgreSQL: pendente** |
| Especificações técnicas (Ø, ±, °, %, vírgula decimal, unidades) | `Ø10` = `10`; `±0,1` = `0,1`; `10,5` = `10 5` | Símbolos viram termos; decimal preservado; especificação comparada à parte | **Corrigido**. Pares com especificação diferente aparecem com `spec_match=false` e motivo "não considerar equivalente" |
| Persistência após reinício | não testado | fechar engine, reabrir, comparar hash do arquivo e contagem de linhas | **Testado em SQLite** |

### Decisões que afetam o uso

- `M8` vira o token `m8` (designação de peça). `M8x20` vira `m8`, `x`, `20`. `M 8` (com espaço) não é igual a `M8`: a comparação é conservadora e marca como diferente.
- Especificação é o conjunto de números, unidades e símbolos. Dois textos com mesmo texto mas especificação diferente nunca são equivalentes.
- O teto de candidatos é `MAX_CANDIDATE_PAIRS` (300.000). Acima disso a análise é recusada com mensagem para filtrar. O valor não foi calibrado com dados reais.

### Limitações ainda abertas

1. **PostgreSQL não verificado localmente.** Concorrência real, migração 0002 e a suíte completa contra PostgreSQL 17 dependem do CI do PR #1, que não rodou (ver abaixo).
2. **Concorrência testada só com SQLite**, em que a escrita é serializada. O comportamento com `IntegrityError` e bloqueio de linha em PostgreSQL não foi reproduzido.
3. **Descrição sem termos em comum e com ordem trocada de tokens frequentes** ainda pode não ser comparada se o score de texto ficar abaixo do limite. Não há semântica de sinônimos: `parafuso` e `fixador` não são semelhantes.
4. **Materiais tecnicamente equivalentes não são reconhecidos automaticamente.** A ferramenta sugere, a decisão é humana.
5. **Memória das exportações e da análise de duplicatas segue não medida** para volumes grandes.
6. **Um título com duas células textuais antes do cabeçalho** pode ser escolhido como cabeçalho.

### Homologação no GitHub Actions (PR #1)

O repositório foi tornado público pelo responsável, e a cobrança que bloqueava os jobs deixou de se aplicar.

| Execução | Commit | API (Python) | Web (TypeScript) |
|---|---|---|---|
| 45475952114 (reexecução) | 9188e91 | **sucesso** (todos os passos: dependências com lock, ruff, mypy strict, migrações upgrade/downgrade/upgrade, testes) | **sucesso** (install, typecheck, lint, teste, build) |

- A suíte da API rodou no job com **PostgreSQL 17** (serviço do CI, `ENGIFLOW_TEST_DATABASE_URL` definida). Esta é a evidência em PostgreSQL da migração 0002 e dos testes da API.
- Os 89 testes da API passaram localmente; no CI, a execução do commit 9188e91 concluiu com sucesso.
- **Concorrência e persistência em PostgreSQL:** os testes foram reescritos para usar o banco configurado. A execução deste commit (ver histórico do PR) é que valida essa parte em PostgreSQL. Até essa execução concluir, ela figura como pendente.
- Ausência de avisos de depreciação: verificada nas anotações da execução (ver seção de revisão de segurança e CI).

### Revisão de segurança do repositório público

Resumo em `docs/security/REVISAO_REPO_PUBLICO.md`:
- Nenhum arquivo de dados, CAD, banco local ou segredo versionado, no HEAD e no histórico.
- Nenhum padrão de credencial encontrado no histórico.
- Exposição: o e-mail pessoal do autor está visível nos commits. Não foi reescrito o histórico; a decisão está documentada.

### Limitações restantes

1. Medições de desempenho em 100 mil e 500 mil linhas ainda não foram feitas (dependem da Fase 2B.4).
2. Concorrência: a validação em PostgreSQL depende da execução do CI deste commit.
3. Os limites de capacidade (100 MB, 500 mil linhas, 300 mil candidatos) são configuração, não capacidade comprovada.
4. Sinônimos e equivalência técnica não são reconhecidos automaticamente.
5. Um título com duas células textuais antes do cabeçalho ainda pode ser escolhido como cabeçalho.
6. Exportações e análise de duplicatas não foram medidas em memória para grandes volumes.

## Planejamento da Fase 2B

Ver `docs/roadmap/FASE_2B_PLANO.md` (revisão 2): quatro entregas independentes (2B.1 a 2B.4), versionamento de metadados, hashes canônicos separados por finalidade, idempotência, concorrência otimista, limites de complexidade, retenção que preserva versões referenciadas, e 27 critérios de aceitação. **Não iniciada.** Aguarda autorização e merge.
