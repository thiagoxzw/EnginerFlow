# Fase 2B.3 — Cruzamento e comparação de tabelas (Super-PROCV, junções, comparação, agrupamento)

Branch: `feat/fase-2b-3-data-crossing` · Pré-requisito: Fase 2B.2 concluída e mesclada (`90cb12e`).
Dados: exclusivamente sintéticos. Uso individual. PostgreSQL 17. Repositório público.

## 1. Objetivo

Transformar o Data Studio em ferramenta de cruzamento e comparação de informações de engenharia:
buscar correspondências entre tabelas (um "PROCV" mais completo), juntar tabelas com cardinalidade
explícita, comparar duas versões de um cadastro e agrupar/consolidar valores. Nenhuma tabela
original é alterada: todo resultado é uma **tabela derivada** com rastreabilidade completa.

## 2. Princípios (inegociáveis)

1. **Nada silencioso.** Multiplicação de registros, correspondências ambíguas, valores inválidos e
   aproximações são sempre apresentados com contagem e motivo, antes da confirmação.
2. **Equivalência técnica nunca é automática.** Correspondências aproximadas (descrição parecida) são
   *sugestões para revisão*; só entram no resultado se o usuário as confirmar.
3. **Preservação.** Códigos, zeros à esquerda e especificações (`M8` ≠ `M 8`) são comparados como texto
   canônico (`domain/tabular.py`, `normalize_*`); nunca convertidos para número para casar chaves.
4. **Decimal para números.** Somas, médias e diferenças usam `decimal.Decimal`; vírgula decimal é
   interpretada só para cálculo, o valor armazenado não muda.
5. **Limites explícitos.** Cardinalidade máxima do resultado, linhas de origem por execução e tamanho
   de saída são limitados; acima do limite a operação é recusada com orientação, não truncada.
6. **Versões imutáveis.** Tabela derivada referencia as versões de dados e de metadados de origem e
   as preserva (nenhuma retenção é removida nesta fase).
7. **Reutilização.** Toda operação é uma entrada do registro de operações (`application/operations`),
   pura sobre snapshots/leitores, e pode ser chamada por Workflow Studio e AI Copilot (sem UI).

## 3. Arquitetura

Camadas (seguindo o padrão 2B.1/2B.2):

```
domain/
  keys.py         chaves compostas: normalização canônica de cada parte (texto, NFC, sem alterar zeros)
  join.py         junções: cardinalidade, plano (contagens estimadas), execução em streaming
  match.py        Super-PROCV: política de correspondência (única/primeira/todas/erro), sugestões aproximadas
  compare.py      comparação: adicionados/removidos/modificados/idênticos, diffs por coluna, Decimal
  aggregate.py    agrupamentos: contagem, contagem distinta, soma, média, mín, máx, com invalidez explícita
application/
  crossing.py     casos de uso: planejar (prévia), executar, exportar; limites; hash do resultado
  derived.py      criação de tabela derivada (datasets com origem = 'derived') e rastreabilidade
infrastructure/
  models.py       + DatasetSource (origens da derivada), CrossingRun (execução: parâmetros, hash, contagens)
presentation/routes/crossing.py   API /api/v1/crossing/*
web/src/components/crossing/*     interface (um componente por bloco)
```

### Modelo de dados (migração `0005_crossing`)

- `crossing_runs`: `id`, `kind` (`lookup`|`join`|`compare`|`aggregate`), `params` (JSON canônico),
  `params_sha256`, `policy` (JSON), `result_dataset_id` (nullable até confirmar), `result_sha256`,
  `row_count`, `cardinality` (JSON), `actor`, `created_at`.
- `crossing_run_sources`: `run_id`, `dataset_id`, `version_id`, `metadata_version_id`, `role`
  (`left`|`right`|`group`). Congela exatamente as versões usadas.
- `datasets`: `source_kind` (`import`|`derived`, default `import`), `derived_run_id` (nullable).
- Nenhuma tabela existente é alterada além dessas colunas novas.

Migração: `upgrade`, `downgrade` e `upgrade` no CI (PostgreSQL 17). Downgrade remove apenas o que a
própria migração criou.

## 4. Operações (contratos reutilizáveis)

Todas recebem **snapshots de origem** (versão + metadados congelados) e devolvem um **plano** (prévia)
e depois um **resultado** (linhas + relatórios). Nenhuma escreve nas origens.

### 4.1 Super-PROCV (`lookup`)

Entrada: `left` (tabela de consulta), `right` (tabela de busca), `keys` (1..N pares de colunas,
comparação exata por texto canônico), `return_columns` (de `right`), `policy`:
- `duplicates`: `first` | `all` (linha por correspondência) | `error` (recusa se houver múltiplas)
- `unmatched`: `keep_empty` (padrão, mantém a linha de `left` com vazio/desconhecido) | `drop`
- `conflict_suffix`: sufixo para colunas homônimas (padrão ` (direita)`)

Saída: linhas de `left` com colunas retornadas, mais colunas de status:
`_status` ∈ {`encontrado`, `não encontrado`, `múltiplas correspondências`} e `_matches` (contagem).
Relatório: totais por status, lista das chaves sem correspondência (limitada), chaves duplicadas.

**Sugestões aproximadas:** opcional (`suggest: true`). Gera pares `left`×`right` sem chave exata,
com score de similaridade (reaproveita `similar_descriptions` da 2A/2B.1). Saída **separada**, marcada
`status = sugestão para revisão`. Não entra no resultado exceto por ação explícita do usuário
(`accept_suggestions: [ids]`), que aparece na política registrada.

### 4.2 Junções (`join`)

Tipos: `inner`, `left`, `right`, `full`. Chaves compostas (mesmo esquema de `keys`).

Cardinalidade (calculada antes de executar, pela contagem de chaves distintas por lado):
- `1:1` — cada chave aparece no máximo uma vez em cada lado;
- `1:N` / `N:1` — uma lado único, outro com repetição;
- `N:M` — repetição nos dois lados.

Regra de segurança: `N:M` e `1:N` exigem confirmação explícita; a prévia mostra **linhas estimadas
= soma, por chave, de (count_left × count_right)** para as chaves em comum, mais as não casadas em
`left`/`right` conforme o tipo. Se a estimativa passar do limite (`MAX_JOIN_ROWS`), a execução é recusada.

Colunas com nome conflitante: prefixo por tabela de origem (`left.col`, `right.col`), configurável.
Relatórios: correspondências por chave, não encontrados em cada lado, contagem por cardinalidade.

### 4.3 Comparação (`compare`)

Entrada: `left` (antiga) e `right` (nova), chave (1..N colunas), colunas de comparação (padrão: todas
as comuns exceto chave), `numeric_tolerance` (Decimal, padrão 0).

Saída por chave: `adicionado` (só em `right`), `removido` (só em `left`), `modificado` (diferença em
pelo menos uma coluna), `idêntico`. Para `modificado`: colunas diferentes com valor anterior/atual.
- Comparação de texto: canônica (NFC, sem alterar zeros); descrições com diferença só de
  acentos/caixa são marcadas como **divergência de descrição** (não como modificação silenciosa).
- Comparação numérica: `Decimal` quando ambos os lados são numéricos; dentro da tolerância = idêntico.
- Chaves duplicadas em qualquer lado: reportadas e não comparadas automaticamente (pedem política).

### 4.4 Agrupamento (`aggregate`)

Entrada: tabela, colunas de agrupamento (1..N), agregações `[{column, op}]` com `op` ∈ `count`,
`count_distinct`, `sum`, `avg`, `min`, `max`.

Regras: `sum`/`avg`/`min`/`max` usam `Decimal`; valores não numéricos, vazios e desconhecidos são
**contados à parte** (`invalid_count`, `empty_count`, `unknown_count`) e nunca somados como zero.
`count` conta linhas; `count_distinct` usa texto canônico. Grupos com chave desconhecida formam grupo
próprio `(desconhecido)`.

### 4.5 Exportação e tabela derivada

Qualquer resultado pode ser: (a) exportado (CSV/XLSX, reaproveita `infrastructure/exporters.py`),
(b) confirmado como **tabela derivada** (`datasets` com `source_kind = derived`), criada a partir do
resultado materializado. A derivada é uma tabela normal (versão 1), com `crossing_runs` ligado.

## 5. Limites (todos configuráveis em `Settings`, com teto default)

| Limite | Default | Ação ao exceder |
|---|---|---|
| Linhas de origem por execução | 500 000 | recusa com orientação |
| Linhas estimadas do resultado (junção/lookup) | 500 000 | recusa; sugere filtrar |
| Linhas de saída materializadas | 500 000 | recusa |
| Chaves distintas em memória (comparação/agrupamento) | 500 000 | recusa |
| Sugestões aproximadas geradas | 2 000 | recusa; sugere restringir chave |
| Colunas de retorno / agregações | 50 / 50 | validação |

Processamento: leitura em streaming por lotes de 2 000 linhas onde possível (lookup com índice
construído da tabela `right` em memória, limitada pelo teto de chaves distintas). Estruturas em
memória são medidas no benchmark.

## 6. Rastreabilidade

Cada `crossing_run` registra: tabelas de origem e papéis, **versão de dados e de metadados** usadas,
operação e versão do código da operação, parâmetros canônicos (`params_sha256`), política, chaves,
contagens, `result_sha256` (hash canônico do conteúdo do resultado, `rows-v1`), data de execução e
ator. Editar uma origem depois **não** altera o resultado: a derivada aponta para versões congeladas,
que a 2B.2 já preserva. Testes verificam isso explicitamente.

## 7. Interface (um bloco por entrega)

1. **Seleção de tabelas e chaves** — escolher origem(ns), colunas de chave (1..N, pareadas), visualizar
   amostra de cada lado e alertas de chave duplicada/vazia.
2. **Super-PROCV** — colunas de retorno, política de duplicatas, opção de sugestões; prévia com contagem
   por status; lista de não encontrados e de múltiplas correspondências; exportar; criar derivada.
3. **Junções** — tipo, chaves compostas, nomes conflitantes; **cardinalidade e linhas estimadas antes da
   confirmação**; relatório de correspondências e não encontrados.
4. **Comparação** — adicionados, removidos, modificados, idênticos, diferenças por coluna, divergências
   de descrição, chaves duplicadas; exportar.
5. **Agrupamento** — colunas de grupo, agregações, invalidez explícita por grupo; exportar; derivada.
6. **Histórico de execuções** — lista de `crossing_runs` com parâmetros, hash e origem; reabrir resultado.

Todo bloco: indicador de processamento, mensagens de erro compreensíveis (limites, chaves, política),
prévia antes da confirmação, relatório de inconsistências.

## 8. Testes

- **Domínio (puro):** chaves compostas e normalização; cada política de duplicatas; cardinalidade e
  estimativa; comparação (diffs, Decimal, tolerância, divergência de descrição); agregações com inválidos.
- **Aplicação/API:** prévia não grava; confirmação grava derivada e `crossing_runs`; limites recusam;
  origem editada não altera resultado existente; versões congeladas; idempotência; 409 em estado obsoleto.
- **Migração:** `0005` upgrade, downgrade, upgrade em PostgreSQL 17 (CI).
- **Componentes (Vitest):** cada tela com estados de carregamento, erro e prévia.
- **E2E (Playwright):** fluxo Super-PROCV completo (duas tabelas → chave → prévia → exportar → derivada),
  junção com aviso de N:M antes da confirmação, comparação de duas versões, agrupamento.
- **Desempenho:** script `bench_2b3_postgres.py` (100 mil e 500 mil linhas, sintético): lookup, join
  inner/left, comparação, agrupamento, criação de derivada; registra tempo e pico de memória Python.

## 9. Riscos

| Risco | Mitigação |
|---|---|
| Explosão de linhas em junções N:M | cardinalidade e estimativa antes da execução; teto; confirmação explícita |
| Chaves em memória (lookup/comparação) | teto de chaves distintas; medição; documentado para 2B.4 |
| Falsa equivalência por aproximação | sugestões separadas, nunca automáticas; registro da escolha |
| Perda de zeros/códigos | chave canônica textual; testes com `00123` vs `0123` |
| Divergência de resultado após edição da origem | versões congeladas; teste dedicado |
| Crescimento de armazenamento (derivadas grandes) | teto de saída; registrado para 2B.4 (retenção/compactação) |
| Escopo excessivo | blocos entregues sequencialmente, cada um com testes; 2B.4 fora do escopo |

## 10. Critérios de aceitação

1. Super-PROCV: exato, colunas de retorno, status (encontrado / não encontrado / múltiplas), políticas de
   duplicatas, prévia, exportação, derivada; origens inalteradas. Aprovado por teste de API, componente e E2E.
2. Sugestões aproximadas nunca entram no resultado sem aceite explícito, e aparecem rotuladas.
3. Junções: os quatro tipos com chaves compostas; conflito de nomes tratado; cardinalidade e linhas
   estimadas mostradas antes da confirmação; N:M exige confirmação; nenhuma multiplicação silenciosa.
4. Comparação: adicionados, removidos, modificados, idênticos, diffs por coluna, Decimal, divergência de
   descrição, chaves duplicadas, sem correspondência.
5. Agrupamento: as seis operações; Decimal; inválidos, vazios e desconhecidos informados separadamente.
6. Rastreabilidade completa por execução; origem editada não altera resultado existente.
7. Limites de cardinalidade, processamento e tamanho ativos, com mensagens de orientação.
8. Interface funcional nos seis blocos, com prévias, erros e relatórios; evidências por captura.
9. Migração `0005` validada em PostgreSQL 17 (upgrade/downgrade/upgrade).
10. Benchmarks em 100 mil e 500 mil linhas registrados; limitações declaradas.
11. Dados exclusivamente sintéticos; nenhuma credencial; exceções do `.gitignore` apenas para `SYN-*`.

## 11. Registro para a Fase 2B.4 (não implementar na 2B.3)

- Versionamento incremental ou por diferenças (hoje: cópia completa por versão de dados).
- Retenção segura de versões (política de limpeza com preservação de versões referenciadas por derivadas).
- Redução do crescimento do armazenamento (compactação, deduplicação de linhas).
- Processamento incremental de transformações (substituição e ordenação hoje carregam a tabela inteira).
- Otimização de consultas e índices (chaves, filtros, pesquisa).
- Virtualização de tabelas na interface.
- Melhorias de interface identificadas na revisão da 2B.2 (ordem das seções, prévia de cabeçalho legível).
