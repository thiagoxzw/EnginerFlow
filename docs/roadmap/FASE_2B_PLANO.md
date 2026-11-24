# Fase 2B — Data Studio Advanced: plano técnico

Status: **planejamento para aprovação**. Nada desta fase foi implementado. Início só após merge da Fase 2A (PR #1) e autorização.
Uso individual. Sem RBAC, multi-tenancy, papéis ou administração. Dados sintéticos apenas.

## 1. Princípios

1. **Original imutável.** O arquivo em `originals/` nunca muda. Toda transformação gera uma nova versão da tabela.
2. **Nada silencioso.** Toda operação passa por prévia, confirmação explícita e registro no histórico.
3. **Regra de negócio no backend.** O frontend apenas apresenta e envia parâmetros. Cada transformação é uma *capacidade* registrada (ver §3), reutilizável por Workflow Studio e AI Copilot.
4. **Tipos explícitos.** Código é texto (zeros preservados). Quantidade é `Decimal`. Três estados distintos por célula: **vazio** (`""`), **desconhecido** (`null`) e **zero** (`"0"`). Nenhum deles é convertido em outro.
5. **Sem fusão automática.** Códigos semelhantes e correspondências aproximadas são sugestões que exigem confirmação.

## 2. Funcionalidades (prioridade)

| # | Funcionalidade | Entrega |
|---|---|---|
| 1 | Templates de mapeamento reutilizáveis | salvar/aplicar mapeamento por nome |
| 2 | Filtros por coluna: texto (contém, igual, prefixo), vazio/desconhecido, numérico (>, <, intervalo) | filtro server-side, combinável |
| 3 | Ordenação e pesquisa global | ordenação por coluna (texto ou Decimal); busca em todas as colunas |
| 4 | Localizar e substituir em lote | prévia com contagem e amostra; aplicação por coluna ou tabela |
| 5 | Cruzamento tipo PROCV | lookup de uma chave em outra tabela, retornando colunas escolhidas |
| 6 | Junções inner, left, right, full | resultado em nova tabela derivada, com linhagem |
| 7 | Correspondências múltiplas e não encontrados | relatório: chaves sem par, chaves com N pares |
| 8 | Comparação de valores entre tabelas | igual / diferente / só de um lado, por coluna comparada |
| 9 | Colunas calculadas | expressão restrita (ver §5), resultado em `Decimal` |
| 10 | Renomear e excluir tabelas | exclusão só sem dependentes, com confirmação |
| 11 | Seleção e transformação de múltiplas linhas | aplicar operação às linhas selecionadas |
| 12 | Agrupamento por código, família ou categoria | soma/contagem por grupo, em `Decimal` |
| 13 | Histórico de transformações | lista de operações com parâmetros e hash antes/depois |
| 14 | Desfazer e refazer | ponteiro de versão; sem apagar histórico |
| 15 | Exportação CSV e XLSX dos dados transformados | reutiliza exportadores da 2A, com versão escolhida |

## 3. Arquitetura: capacidades reutilizáveis

Cada transformação é uma classe registrada em `application/operations/`:

```
Operation
  code: str            # ex.: "replace_text", "join", "filter_rows"
  version: int
  params_model: type   # Pydantic, valida entrada
  reversible: bool
  dry_run: bool        # sempre True: calcula prévia sem persistir
  def preview(table, params) -> PreviewResult   # contagens, amostra, hash resultado
  def apply(table, params) -> Table             # função pura; mesma entrada => mesma saída
```

- O registro (`OPERATIONS`) é a única lista de capacidades. API, UI, futuros workflows e o Copilot chamam o mesmo registro.
- `apply` é função pura sobre o conteúdo. Persistência e auditoria ficam fora (camada de aplicação).
- Cálculos (somas, contagens, expressões) são determinísticos. Nenhuma IA participa.

## 4. Persistência

Migração `0003_data_studio_advanced`:

| Tabela | Campos principais | Motivo |
|---|---|---|
| `dataset_versions` | `id`, `dataset_id`, `number` (1 = original), `parent_version_id`, `row_count`, `content_sha256`, `created_at` | desfazer/refazer e histórico sem apagar nada |
| `dataset_rows` (alterada) | acrescentar `version_id` (FK); índice `(version_id, row_number)` | linhas por versão; versão 1 é o original |
| `dataset_operations` | `id`, `dataset_id`, `version_id`, `seq`, `code`, `params` (JSON), `status` (`applied` / `undone`), `actor`, `created_at`, `before_sha256`, `after_sha256` | histórico auditável |
| `datasets` (alterada) | `current_version_id`, `deleted_at` (exclusão lógica para dependências), `kind` (`source` / `derived`), `lineage` (JSON) | ponteiro de versão e linhagem de tabelas derivadas |
| `dataset_templates` | `id`, `name` (único), `kind` (`mapping` / `operation`), `definition` (JSON), `updated_at` | templates reutilizáveis |

Regras de integridade:
- `dataset_rows` de uma versão é imutável após criada.
- Desfazer altera apenas `datasets.current_version_id` e marca a operação como `undone`. Refazer reverte esse ponteiro.
- Operação nova após desfazer descarta o ramo de refazer: a operação desfeita fica com `status=undone` no histórico, nunca é apagada.
- Retenção: no máximo `MAX_VERSIONS_PER_DATASET` versões materializadas (valor a definir com medição). Acima disso, a versão mais antiga é removida, **nunca** a versão 1.
- Exclusão de tabela é lógica (`deleted_at`) enquanto houver tabela derivada que a referencie; física apenas quando não houver dependentes, com confirmação.

## 5. Contratos de API (`/api/v1`)

Convenções: Problem Details para erros; `Idempotency-Key` em operações que mudam dados; paginação com `offset`/`limit`; números como string decimal.

### 5.1 Templates
- `POST /templates` — `{name, kind, definition}`
- `GET /templates?kind=` · `GET /templates/{id}` · `PUT /templates/{id}` · `DELETE /templates/{id}`
- `POST /datasets/{id}/mapping/apply-template` — `{template_id}` (reutiliza `PUT mapping`)

### 5.2 Leitura filtrada, ordenada e pesquisada
- `GET /datasets/{id}/rows?version=&q=&filters=&sort=&offset=&limit=`
  - `filters` (JSON) — ex.: `[{"column":"Código","op":"prefix","value":"00"}, {"column":"Qtd","op":"gt","value":"10"}]`
  - ops: `equals`, `contains`, `prefix`, `is_empty`, `is_unknown`, `gt`, `gte`, `lt`, `lte`, `between`
  - `sort` — `[{"column":"Qtd","type":"decimal","dir":"asc"}]`; tipos: `text`, `decimal`
  - Resposta: `total` (filtrado), `rows[]` com `row_number` e `values`.

### 5.3 Prévia e aplicação de operações (duas etapas)
- `POST /datasets/{id}/operations/preview` — `{code, params}` → `{preview_id, rows_affected, sample[], before_sha256, after_sha256, warnings[]}`. Não persiste.
- `POST /datasets/{id}/operations` — `{preview_id}` → cria nova versão. Recusa se a versão atual mudou desde a prévia (`409`).
- `GET /datasets/{id}/operations` — histórico (aplicadas e desfeitas).
- `POST /datasets/{id}/undo` · `POST /datasets/{id}/redo` → `{current_version_id}`

Operações previstas e seus `params` (resumo):
- `replace_text` — `{column|"*", find, replace, match_case, whole_cell, scope: "rows", row_numbers?}`
- `add_calculated_column` — `{name, expression}` (ver §6)
- `select_rows_transform` — `{row_numbers[], action: "set_column"|"clear"|"delete", column?, value?}`
- `rename_column` — `{from, to}`

### 5.4 Cruzamento e junções
- `POST /datasets/join/preview` — `{left_id, right_id, left_key, right_key, how: "inner"|"left"|"right"|"full", match_policy: "report"|"first"|"all"}` → `{rows_out, matched, unmatched_left, unmatched_right, multiple_matches[], warnings[]}`
- `POST /datasets/join` — `{preview_id}` → cria tabela **derivada** com `lineage` (ids, versões, chaves, tipo, política).
- Política padrão `report`: chave com mais de um par **não multiplica** linhas; é listada em `multiple_matches` e o resultado fica pendente de decisão. `all` exige escolha explícita e mostra o aumento de linhas na prévia.
- `POST /datasets/lookup/preview` — `{left_id, key, right_id, right_key, return_columns[], not_found: "empty"|"unknown"}` (PROCV). Mesma política de múltiplas correspondências.

### 5.5 Comparação de valores
- `POST /datasets/compare-values` — `{left_id, right_id, key_left, key_right, compare: [{left, right}]}` → por chave: `equal` / `different` / `only_left` / `only_right`, com valores lado a lado. Comparação de números usa `Decimal`; texto exato, sem normalização automática de especificação (regra da 2A).

### 5.6 Agrupamento
- `POST /datasets/{id}/group/preview` — `{by: [...], aggregates: [{column, fn: "count"|"sum"|"count_distinct"}]}` → prévia; `POST /datasets/{id}/group` cria derivada. Somas em `Decimal` com escala explícita; células vazias ou desconhecidas são contadas separadamente, nunca somadas como zero.

### 5.7 Tabelas
- `PATCH /datasets/{id}` — `{name}`
- `DELETE /datasets/{id}` — `{confirm: "<nome exato>"}`; `409` se houver dependentes.

### 5.8 Exportação
- Existentes da 2A ganham `?version=` (padrão: versão atual). Conteúdo idêntico ao `after_sha256` da versão.

## 6. Expressões de colunas calculadas

Gramática fechada, sem `eval`, sem SQL livre, sem acesso a atributos:
- operadores `+ - * /`, parênteses, referências a colunas por nome, literais decimais;
- funções: `concat`, `coalesce`, `round(x, n)`;
- avaliação com `decimal.Decimal` e contexto de precisão definido; divisão por zero gera erro de linha, não zero;
- célula vazia ou desconhecida propaga `null` (desconhecido), nunca `0`.

Implementação: parser próprio (AST pequeno) com lista branca. Testes de injeção e de precisão obrigatórios.

## 7. Interface

- Tabela virtualizada (`@tanstack/react-virtual`, nova dependência; justificativa: tabelas acima de alguns milhares de linhas).
- Cabeçalho fixo; redimensionamento de colunas; seleção de linhas (clique, Shift, Ctrl).
- Barra de ferramentas: filtrar, ordenar, pesquisar, substituir, calcular, juntar, agrupar, desfazer, refazer, exportar.
- Painel de transformações: parâmetros da operação, **prévia obrigatória**, botão de aplicar só habilitado após prévia.
- Histórico de operações com estado (aplicada/desfeita) e indicador de carregamento/progresso para operações longas (polling de status; execução síncrona enquanto o volume for pequeno).
- Nenhuma regra de negócio no navegador: cálculos e validações vêm da API.

## 8. Critérios de aceitação

Cada critério exige teste automatizado com dados sintéticos. Itens marcados **[PG]** só são aceitos com validação em PostgreSQL 17 (CI).

| ID | Critério |
|---|---|
| A-01 | Arquivo original: hash idêntico ao da importação após qualquer sequência de operações. |
| A-02 | Prévia e aplicação produzem o mesmo `after_sha256`. |
| A-03 | Desfazer e refazer restauram exatamente o `content_sha256` anterior/posterior. |
| A-04 | Operação nova após desfazer não apaga o histórico; a desfeita fica `undone`. |
| A-05 | Zeros à esquerda preservados em todas as operações, junções e exportações. |
| A-06 | Vazio, desconhecido e zero são distintos em filtros, ordenação, agrupamento e cálculos. |
| A-07 | Soma e cálculo com `Decimal` conferem com cálculo de referência (fixture com casas decimais). |
| A-08 | Junção `left/right/full/inner` conferida contra fixture; chave duplicada não multiplica linhas em política `report`. |
| A-09 | `all` na política mostra a contagem de linhas esperada antes de aplicar. |
| A-10 | Código semelhante (ex.: `00123` e `0123`) nunca é fundido automaticamente em junção ou lookup. |
| A-11 | Expressão de coluna calculada rejeita qualquer construção fora da gramática (testes de injeção). |
| A-12 | Exclusão bloqueada com dependentes; confirmação exige o nome exato. |
| A-13 | Templates de mapeamento aplicados produzem o mesmo mapeamento salvo. |
| A-14 | Operações sobre seleção de linhas afetam somente as linhas selecionadas (conferido por contagem e amostra). |
| A-15 | Concorrência: duas operações simultâneas na mesma versão — uma aplicada, a outra recebe `409`. **[PG]** |
| A-16 | Migração 0003 sobe e desce em PostgreSQL sem perda nas tabelas da 2A. **[PG]** |
| A-17 | Desempenho: metas não são aceitas sem medição. Medir filtros, ordenação e junção em 100 mil e 500 mil linhas e registrar resultados em `FASE_2B_STATUS.md`. |
| A-18 | Nenhuma regra de negócio no frontend (revisão de código e testes de API cobrindo cada regra). |
| A-19 | Exportação do resultado transformado é idêntica ao conteúdo da versão (comparação de hash). |

## 9. Fora do escopo da 2B

Fusão automática de códigos; correspondência semântica por IA; reconhecimento de especificações por dicionário; multiusuário; conectores ERP/CAD; Workflow Studio (apenas preparar o registro de capacidades).

## 10. Riscos e decisões pendentes

- **Crescimento de armazenamento por versões.** Cada versão materializada copia as linhas. Mitigação: limite de versões e medição; alternativa futura: armazenar apenas o delta por operação.
- **Expressões.** Gramática pequena reduz risco, mas exige testes próprios. Não usar `eval`.
- **Junções em volume grande** podem exceder a memória de uma única requisição. Mitigação: execução assíncrona acima de um limite a definir por medição.
- **Confirmação de dependência de nova lib** (`@tanstack/react-virtual`) antes da implementação.
