# Fase 2B — Data Studio Advanced: planejamento técnico (revisão 2)

Status: **planejamento aprovado conceitualmente, com ajustes incorporados nesta revisão. Implementação NÃO iniciada**: aguarda autorização do responsável e merge da Fase 2A (PR #1).

Uso individual. Sem RBAC, multi-tenancy, papéis, equipes, cobrança ou administração. Dados sintéticos apenas.

## 1. Princípios

1. **Original imutável.** `originals/<sha256>.<ext>` nunca é alterado. Toda transformação cria uma nova versão.
2. **Nada silencioso.** Toda operação passa por prévia, confirmação explícita e registro no histórico.
3. **Regra de negócio no backend.** O frontend envia parâmetros e apresenta resultados. Cada transformação é uma capacidade registrada (§3), reutilizável pelo futuro Workflow Studio e AI Copilot.
4. **Tipos explícitos.** Código é texto. Quantidade é `Decimal`. Cada célula tem três estados distintos: **vazio** (`""`), **desconhecido** (`null`) e **zero** (`"0"`). Nenhum vira outro.
5. **Sem fusão automática.** Códigos semelhantes e correspondências aproximadas são sugestões. Nunca são aplicadas sem decisão explícita.
6. **Determinismo.** Mesma entrada e mesma versão de capacidade produzem o mesmo resultado e o mesmo hash.

## 2. Entregas independentes

Cada entrega é mergeável sozinha, tem seus próprios testes, critérios de aceitação e atualização de documentação. A entrega seguinte só começa após a anterior ser aprovada.

### 2B.1 — Fundação das transformações

- Registro central de capacidades reutilizáveis (§3).
- Versionamento de tabelas: versões materializadas, versão 1 = original (§4).
- Histórico de operações com hash antes/depois.
- Prévia e confirmação: nenhuma mudança é persistida sem `preview_id` válido.
- Desfazer e refazer por ponteiro de versão.
- Controle de concorrência e idempotência (§6).
- Integridade e rastreabilidade: hashes canônicos (§5), linhagem registrada.

Operações mínimas nesta entrega: `rename_column`, `replace_text` (uma coluna), `select_rows_transform` (definir valor/limpar em seleção).

### 2B.2 — Manipulação de dados

- Templates reutilizáveis de mapeamento (versionados, §7).
- Filtros avançados por coluna: texto (igual, contém, prefixo), vazio, desconhecido, numérico (`gt`, `gte`, `lt`, `lte`, `between`) com `Decimal`.
- Pesquisa global e ordenação (texto ou `Decimal`).
- Localizar e substituir em lote com prévia de contagem e amostra.
- Seleção de linhas e transformação em lote.
- Renomeação e exclusão de tabelas (exclusão lógica enquanto houver dependente).
- **Seleção manual da linha de cabeçalho** (`header_row` informado pelo usuário, persistido como metadado versionado, §7).

### 2B.3 — Cruzamento de informações

- Super-PROCV (lookup) com colunas de retorno escolhidas.
- Junções `inner`, `left`, `right`, `full`.
- Comparação de valores entre tabelas (igual, diferente, só de um lado) com `Decimal` para números.
- Correspondências múltiplas: política `report` por padrão; `all` só com escolha explícita e prévia do aumento de linhas.
- Registros não encontrados listados em relatório.
- Agrupamentos e agregações (`count`, `count_distinct`, `sum` em `Decimal`), com vazio, desconhecido e zero contados separadamente.
- Linhagem de tabelas derivadas (ids, versões, chaves, tipo, política).
- Prevenção de multiplicação indevida (§6.4).

### 2B.4 — Interface e cálculos avançados

- Colunas calculadas com gramática segura (§8). Cálculos em `Decimal`.
- Virtualização de tabelas com `@tanstack/react-virtual` (**aprovação solicitada no PR desta revisão**; ver §11).
- Redimensionamento de colunas, cabeçalhos fixos, seleção de linhas.
- Indicadores de progresso para operações longas.
- Exportação de versões em CSV e XLSX (hash do arquivo, §5.2).
- **Testes de desempenho e capacidade** com medição registrada (§9).

## 3. Arquitetura: capacidades reutilizáveis

```
application/operations/
  base.py        Operation (Protocol)
  registry.py    OPERATIONS: dict[code, Operation]   # única lista de capacidades
  ...            uma classe por capacidade
```

Contrato de cada capacidade:

- `code` (estável), `version` (inteiro, incrementado a cada mudança de comportamento).
- `params_model` (Pydantic): valida a entrada.
- `reversible: bool`, `side_effects: "none" | "derived_dataset" | "new_version"`.
- `preview(table, params) -> PreviewResult`: contagens, amostra limitada, `after_sha256` calculado sem persistir.
- `apply(table, params) -> Table`: função pura. Não acessa banco nem sistema de arquivos.

API, interface, Workflow Studio e AI Copilot chamam **somente** `OPERATIONS`. Nenhuma regra é duplicada. Cálculos são determinísticos. Nenhuma IA participa de cálculo.

## 4. Persistência e versionamento

### 4.1 Tabelas (migração `0003`, entregue em 2B.1)

| Tabela | Campos principais | Finalidade |
|---|---|---|
| `dataset_versions` | `id`, `dataset_id`, `number`, `parent_version_id`, `row_count`, `content_sha256`, `schema_version`, `created_at`, `pinned` | versões materializadas; `pinned` = referenciada por tabela derivada |
| `dataset_version_rows` | `version_id`, `row_number`, `values` (JSON) — PK `(version_id, row_number)` | linhas por versão; imutáveis |
| `dataset_operations` | `id`, `dataset_id`, `seq`, `code`, `code_version`, `params` (JSON), `params_sha256`, `status` (`applied`/`undone`), `before_version_id`, `after_version_id`, `idempotency_key` (único por dataset), `actor`, `created_at` | histórico auditável; nunca apagado |
| `dataset_metadata_versions` | `id`, `dataset_id`, `version_id`, `columns` (JSON), `column_types` (JSON), `header_row`, `mapping` (JSON), `created_at` | colunas, tipos, cabeçalho e mapeamento versionados |
| `datasets` (alterada) | `current_version_id`, `kind` (`source`/`derived`), `lineage` (JSON), `deleted_at`, `name` | ponteiro atual e linhagem |
| `dataset_templates` | `id`, `name` (único), `kind`, `definition` (JSON), `definition_version`, `updated_at` | templates versionados |

Observação: a tabela `dataset_rows` da 2A passa a ser `dataset_version_rows` por migração que preserva as linhas da versão 1. A migração é testada em SQLite e PostgreSQL (upgrade, downgrade, upgrade).

### 4.2 Regras de integridade

- Linhas de uma versão são imutáveis após criadas.
- **Desfazer**: `datasets.current_version_id` aponta para `parent_version_id`; a operação vai para `undone`. Nada é apagado.
- **Refazer**: aponta para a versão desfeita mais recente, se nenhuma operação nova tiver sido aplicada.
- **Operação nova após desfazer**: o ramo de refazer é encerrado (operações ficam `undone`) e uma nova versão é criada a partir da atual.

### 4.3 Retenção, medida e segura

- Limite de versões não referenciadas por dataset: `MAX_UNPINNED_VERSIONS` (**valor a ser definido por medição**, §9; nenhum número é aceito antes disso).
- **Versões referenciadas por tabela derivada (`pinned=true`) nunca são removidas**, independentemente do limite. A versão 1 (original) também nunca é removida.
- Remoção de versão ocorre em transação, com verificação de que nenhuma tabela derivada a referencia.
- Exclusão de tabela é lógica (`deleted_at`) enquanto houver derivada que a referencie. Exclusão física só sem dependentes, com confirmação pelo nome exato.

## 5. Hashes: canônico, determinístico, separado por finalidade

### 5.1 Hash do conteúdo lógico (`content_sha256`)

- Serialização canônica: JSON com chaves de metadado ordenadas, linhas na ordem de `row_number`, valores como string UTF-8 em Unicode NFC, `null` para desconhecido, string vazia para vazio, separadores fixos, sem espaços.
- Inclui colunas, linhas, valores e `schema_version`. **Não inclui** datas de criação, ids, nomes de arquivo ou ordem de inserção.
- Dois conteúdos lógicos iguais geram o mesmo hash, independentemente de como foram gerados.

### 5.2 Hash do arquivo exportado (`file_sha256`)

- Hash dos bytes do CSV ou XLSX entregue. **Depende do formato**: XLSX contém metadados de data de criação do ZIP, então o mesmo conteúdo pode gerar bytes diferentes.
- Não é usado para comparar conteúdo. Serve para verificar integridade do arquivo entregue.
- O teste de exportação compara `content_sha256` relido do arquivo, e não o hash bruto do XLSX.

### 5.3 Original

- `source_sha256` (SHA-256 dos bytes do arquivo original) continua sendo o identificador do arquivo importado (2A).

## 6. Idempotência, concorrência e complexidade

### 6.1 Idempotência

- Toda operação que muda dados recebe `Idempotency-Key`. A mesma chave com os mesmos parâmetros retorna o resultado anterior. Mesma chave com parâmetros diferentes retorna `409`.
- `preview_id` é único e expira. Aplicar um `preview_id` duas vezes não cria duas versões.

### 6.2 Concorrência

- Concorrência otimista: a aplicação exige `base_version_id` igual à versão atual. Divergência retorna `409` e a prévia deve ser refeita.
- No banco: atualização condicional de `current_version_id` (`UPDATE ... WHERE current_version_id = :base`), na mesma transação da criação da versão. Em PostgreSQL, a linha de `datasets` é bloqueada (`SELECT ... FOR UPDATE`) durante a aplicação.
- Testes: duas aplicações simultâneas sobre a mesma base, uma aplicada e outra `409`. **Validação em PostgreSQL: pendente do CI** (marcado [PG]).

### 6.3 Limites de complexidade

| Recurso | Limite inicial | Justificativa |
|---|---|---|
| Expressão de coluna calculada | 200 nós na AST, profundidade 20 | evitar avaliação excessiva |
| Junção: pares produzidos | `MAX_JOIN_OUTPUT_ROWS` (a definir por medição) | prevenir explosão |
| Lookup/junção com chave de alta cardinalidade | política `report` por padrão | evitar multiplicação |
| Agrupamento: grupos | `MAX_GROUPS` (a definir) | memória |
| Candidatos de comparação | `MAX_CANDIDATE_PAIRS` = 300.000 (medido na Etapa 2) | já implementado |

Os valores marcados "a definir" **não são aceitos** antes de medição registrada em `FASE_2B_STATUS.md`.

### 6.4 Prevenção de multiplicação indevida

- Política `report` (padrão): chave com mais de uma correspondência não gera linhas extras. É listada em `multiple_matches` e a junção não é aplicada até decisão.
- Política `first`: primeira correspondência por ordem de `row_number`, registrada na prévia.
- Política `all`: produz o produto; a prévia mostra o número de linhas de saída e a operação exige confirmação com esse número.

## 7. Versionamento de metadados, colunas e mapeamentos

- Cada versão de tabela tem `dataset_metadata_versions` associado. Mudança de colunas (renomear, mapear, definir cabeçalho) cria nova versão de dados **e** de metadados.
- Templates de mapeamento têm `definition_version`. Aplicar um template grava a versão usada no histórico, para que a reaplicação futura seja reproduzível.
- `schema_version` entra no hash (§5.1). Mudança de versão de capacidade (`code_version`) fica registrada em cada operação.

## 8. Expressões de colunas calculadas (sem `eval`)

- Parser próprio com AST pequena e lista branca:
  - operadores `+ - * /`, parênteses, referências a colunas por nome entre aspas, literais decimais;
  - funções: `concat`, `coalesce`, `round(x, n)`.
- Sem atributos, sem subscrito, sem chamadas arbitrárias, sem acesso a variáveis do sistema.
- `Decimal` com contexto de precisão explícito. Divisão por zero é erro de linha, nunca zero.
- Vazio e desconhecido propagam `null` (desconhecido), nunca `0`.
- Testes obrigatórios: injeção (`__import__`, atributos, nomes não permitidos), limite de complexidade, precisão e propagação de nulos.

## 9. Medições e capacidade

- Nenhum limite de armazenamento, de linhas ou de junção é definido sem medição registrada.
- Cenários medidos e registrados em `docs/operations/FASE_2B_STATUS.md` (tempo, pico Python, tamanho em disco, linhas): 100 mil e 500 mil linhas, em SQLite e PostgreSQL 17 (CI quando disponível), para: filtro, ordenação, substituição em lote, junção, agrupamento e exportação.
- Os resultados definem `MAX_UNPINNED_VERSIONS`, `MAX_JOIN_OUTPUT_ROWS` e `MAX_GROUPS`.
- Sem medição, o planejamento não afirma capacidade.

## 10. Interface

- Tabela virtualizada (`@tanstack/react-virtual`) para o volume medido.
- Cabeçalho fixo, redimensionamento de colunas, seleção de linhas (clique, Shift, Ctrl).
- Barra de ferramentas e painel de transformações com prévia obrigatória antes de aplicar.
- Histórico com estado (aplicada/desfeita) e indicador de progresso para operações longas.
- Nenhuma regra de negócio no navegador; validações e cálculos vêm da API.

## 11. Dependência nova que requer aprovação

| Pacote | Versão a fixar | Motivo | Alternativa |
|---|---|---|---|
| `@tanstack/react-virtual` | versão estável no momento da entrega (ex.: 3.x), fixada no lockfile | virtualizar tabelas acima de alguns milhares de linhas | paginação server-side sem virtualização (mais lenta na navegação) |

**Solicitação:** aprovação para adicionar esta dependência na entrega 2B.4. Nenhuma instalação foi feita.

## 12. Contratos de API (`/api/v1`)

Convenções: Problem Details para erros; `Idempotency-Key` em operações que mudam dados; `base_version_id` em operações; paginação `offset`/`limit`; números como string decimal.

### 12.1 Entrega 2B.1 — fundação
- `GET /datasets/{id}/versions` · `GET /datasets/{id}/versions/{version_id}`
- `POST /datasets/{id}/operations/preview` — `{code, code_version, params, base_version_id}` → `{preview_id, expires_at, rows_affected, sample[], before_content_sha256, after_content_sha256, warnings[]}`
- `POST /datasets/{id}/operations` — headers `Idempotency-Key`; body `{preview_id}` → `{version_id, operation_id}`; `409` se `base_version_id` divergir.
- `GET /datasets/{id}/operations` — histórico
- `POST /datasets/{id}/undo` · `POST /datasets/{id}/redo` — `{base_version_id}` → `{current_version_id}`
- `GET /operations` — catálogo de capacidades (código, versão, schema de parâmetros)

### 12.2 Entrega 2B.2 — manipulação
- `GET /templates` · `POST /templates` · `GET /templates/{id}` · `PUT /templates/{id}` · `DELETE /templates/{id}`
- `POST /datasets/{id}/mapping/apply-template` — `{template_id, base_version_id}`
- `PUT /datasets/{id}/header` — `{header_row, base_version_id}` (cria versão de metadados)
- `GET /datasets/{id}/rows?version=&q=&filters=&sort=&offset=&limit=` — `filters` e `sort` em JSON, lista branca de operadores
- `PATCH /datasets/{id}` — `{name}`
- `DELETE /datasets/{id}` — `{confirm: "<nome exato>"}`; `409` com dependentes

### 12.3 Entrega 2B.3 — cruzamento
- `POST /datasets/join/preview` — `{left_id, right_id, left_key, right_key, how, match_policy, left_version?, right_version?}` → `{rows_out, matched, unmatched_left[], unmatched_right[], multiple_matches[], warnings[], preview_id}`
- `POST /datasets/join` — `{preview_id}` → tabela derivada com linhagem
- `POST /datasets/lookup/preview` — `{left_id, key, right_id, right_key, return_columns[], not_found: "empty"|"unknown", match_policy}`
- `POST /datasets/compare-values` — `{left_id, right_id, key_left, key_right, compare[]}` → `equal`/`different`/`only_left`/`only_right`
- `POST /datasets/group/preview` e `POST /datasets/group` — `{by[], aggregates[]}`

### 12.4 Entrega 2B.4 — cálculo e exportação
- `POST /datasets/{id}/operations/preview` com `code = add_calculated_column` (mesmo contrato da 2B.1)
- `GET /datasets/{id}/export?version=&format=csv|xlsx` — conteúdo da versão indicada; cabeçalho `X-Content-Sha256` com `content_sha256`

## 13. Critérios de aceitação

Itens marcados **[PG]** só são aceitos com validação em PostgreSQL 17 no CI. Itens marcados **[M]** exigem medição registrada.

| ID | Entrega | Critério |
|---|---|---|
| A-01 | 2B.1 | Hash do arquivo original idêntico ao da importação após qualquer sequência de operações |
| A-02 | 2B.1 | Prévia e aplicação produzem o mesmo `after_content_sha256` |
| A-03 | 2B.1 | Desfazer e refazer restauram exatamente o `content_sha256` anterior e posterior |
| A-04 | 2B.1 | Operação nova após desfazer não apaga histórico; a desfeita fica `undone` |
| A-05 | 2B.1 | Duas aplicações simultâneas sobre a mesma base: uma aplicada, outra `409` **[PG]** |
| A-06 | 2B.1 | Mesma `Idempotency-Key` com mesmos parâmetros retorna a mesma versão, sem nova versão |
| A-07 | 2B.1 | Migração 0003 sobe e desce em PostgreSQL sem perda nas tabelas da 2A **[PG]** |
| A-08 | 2B.1 | Hash canônico estável: mesmo conteúdo, geração diferente, mesmo hash |
| A-09 | 2B.1 | `content_sha256` difere de `file_sha256` do XLSX e o teste de exportação compara o conteúdo |
| A-10 | 2B.2 | Filtros distinguem vazio, desconhecido e zero (testes por operador) |
| A-11 | 2B.2 | Substituição em lote: prévia de contagem igual ao número de células alteradas |
| A-12 | 2B.2 | Template aplicado produz o mesmo mapeamento salvo, com `definition_version` registrada |
| A-13 | 2B.2 | Exclusão bloqueada com dependentes; confirmação exige o nome exato |
| A-14 | 2B.2 | Seleção de cabeçalho manual cria versão de metadados e preserva as linhas |
| A-15 | 2B.3 | Junções `inner`, `left`, `right`, `full` conferidas contra fixture |
| A-16 | 2B.3 | Chave duplicada não multiplica linhas na política `report` |
| A-17 | 2B.3 | Política `all` mostra o número de linhas de saída antes da confirmação |
| A-18 | 2B.3 | `00123` e `0123` nunca são fundidos em junção ou lookup |
| A-19 | 2B.3 | Agregações em `Decimal` conferem com referência; vazio, desconhecido e zero contados separadamente |
| A-20 | 2B.3 | Linhagem de derivada referencia versões de origem; versões referenciadas não são removidas pela retenção |
| A-21 | 2B.4 | Expressão fora da gramática é rejeitada (injeção, atributos, chamadas) |
| A-22 | 2B.4 | Divisão por zero gera erro de linha; nulos propagam como desconhecido |
| A-23 | 2B.4 | Exportação de versão tem o mesmo `content_sha256` que a versão |
| A-24 | 2B.4 | Medições de 100 mil e 500 mil linhas registradas para todas as operações **[M]** |
| A-25 | 2B.4 | Limites `MAX_UNPINNED_VERSIONS`, `MAX_JOIN_OUTPUT_ROWS`, `MAX_GROUPS` definidos apenas com base nas medições **[M]** |
| A-26 | todas | Nenhuma regra de negócio no frontend (testes de API cobrem cada regra) |
| A-27 | todas | Toda operação é capacidade registrada em `OPERATIONS` e chamável sem a UI |

## 14. Fora do escopo da 2B

Fusão automática de códigos; correspondência semântica ou por IA; reconhecimento de especificações por dicionário; multiusuário; conectores ERP/CAD; Workflow Studio (apenas o registro de capacidades é preparado); RBAC.

## 15. Riscos e decisões pendentes

- **Armazenamento por versões.** Cada versão copia linhas. Mitigação: limite medido (§9) e retenção com preservação das referenciadas. Alternativa futura: armazenar o delta da operação.
- **Expressões.** Gramática pequena reduz risco, mas exige testes próprios. Sem `eval`.
- **Junções em volume grande** podem exceder a memória de uma requisição. Mitigação: limites (§6.3) e execução assíncrona acima de limite medido.
- **Dependência de virtualização** (§11) depende de aprovação.
- **Hash do XLSX** varia com metadados do arquivo; por isso a verificação é pelo conteúdo (§5.2).
