# Homologação do Super-PROCV (2B.3, bloco 1)

Data: 2026-11-25. Ambiente: stack Docker demonstrativo (`docker compose`), `http://127.0.0.1:3000/data-studio`.
Dados: exclusivamente sintéticos (`SYN-*`). Nenhum dado real foi usado em testes automatizados nem enviado a serviços externos.

## Onde acessar

1. Abra `http://127.0.0.1:3000/data-studio` e faça login.
2. Escolha uma tabela na lista à esquerda ("Abrir").
3. Na tabela aberta, expanda **"Cruzar com outra tabela (PROCV)"**.

## Commits (branch `feat/fase-2b-3-data-crossing`, PR #4 em draft, não mesclado)

| Commit | Conteúdo |
|---|---|
| `6039fb4` | Seção PROCV na tela: tabela de busca, chave única, colunas de retorno, prévia, tabela derivada |
| `34e7a61` | Chaves compostas (até 10), exportação CSV/XLSX da prévia, `source_kind` na API, resumo da derivação |
| `18cdc9a` | Testes E2E com duplicidades, chave vazia, zeros e XLSX |
| `df6090d` | Indicação de tabela derivada na linha de metadados |

## Testes executados

| Suíte | Resultado |
|---|---|
| API: ruff, format, mypy (src + tests) | aprovado |
| API: pytest completo | 220 passaram |
| Web: typecheck, lint | aprovado |
| Web: Vitest | 45 passaram (uma execução isolada falhou sem causa identificada; três execuções seguintes passaram) |
| Playwright contra o ambiente demo | 9 passaram: 6 fluxos críticos anteriores, 3 do PROCV |

### Cobertura do PROCV

| Item solicitado | Onde é verificado |
|---|---|
| Seleção das tabelas de origem | E2E `procv.spec.ts` (1 e 2) |
| Chaves simples e compostas | E2E (1: `B1_COD`+`B1_UM` contra `Código`+`Unidade`); unitário `buildLookupBody` |
| Colunas retornadas | E2E (1: coluna `Saldo`) |
| Correspondências exatas | E2E (1: contagem "Encontrados") e API `test_lookup_2b3` |
| Registros não encontrados | E2E (3: "Não encontrados: 1") |
| Correspondências múltiplas | E2E (3: "Com múltiplas correspondências: 2"); política "Recusar a operação" mostra erro |
| Chaves inválidas | E2E (3: chave vazia conta como "Chave inválida: 1") |
| Zeros à esquerda | E2E (1 e 3: `000123`, `00123` visíveis); API `test_crossing_derive_2b3` |
| Tratamento de duplicidades | E2E (3: "Usar a primeira", "Recusar a operação"); API |
| Prévia dos resultados | E2E (1 e 3: contagens e linhas) |
| Criação de tabela derivada | E2E (1: aparece na lista como "derivada") |
| Exportação CSV e XLSX | E2E (1: CSV; 3: XLSX, pelo nome do arquivo); API `test_export_csv_*` e `test_export_xlsx_*` verificam o conteúdo |
| Rastreabilidade das origens | API: `CrossingRun` e `CrossingRunSource` (versões congeladas). Na tela aparecem execução e hash |
| Preservação após alterar as origens | API `test_editing_a_source_later_does_not_change_the_derived_table` |

## Defeitos encontrados e corrigidos

1. **Tabela derivada indistinguível na lista.** Corrigido: API expõe `source_kind`; a lista e o cabeçalho mostram "derivada". Primeiro tentei um badge no nome, mas ele era cortado em nomes longos; passou para a linha de metadados.
2. **Chaves compostas ilegíveis** (`000210|CH`). Corrigido: exibidas como `000210 + CH`.
3. **Seletor de chaves único.** Corrigido: lista de pares, com adicionar/remover até 10 chaves.
4. **Exportação ausente na prévia.** Corrigido: botões CSV e XLSX.
5. **Teste E2E casava com a tabela derivada** (`hasText` ambíguo). Corrigido: nome exato.

## Avaliação visual

- Seletores e labels: nomes de coluna visíveis em cada seletor; a legenda explica que todas as chaves precisam bater.
- Contadores: linha única com status, quebrando em telas estreitas.
- Prévia: tabela com cabeçalho fixo e rolagem interna; em 390 px rola horizontalmente dentro do bloco, sem rolagem da página.
- Indicadores: "Calculando a prévia…", "Criando a tabela derivada…", "Preparando a exportação…" (região `role="status"`).
- Erros: mensagens em `role="alert"` (ex.: duplicidade com política "Recusar").

## Limitações conhecidas (não resolvidas nesta etapa)

- A tela não lista as tabelas de origem da derivação; a rastreabilidade completa está na API. Exibir as origens na tabela derivada fica para o próximo bloco.
- Cada execução de derivação cria uma tabela nova; não há deduplicação de resultados idênticos.
- Os testes E2E criam tabelas `SYN-*` e derivadas no ambiente demo a cada execução.
- Não foi feita revisão visual com interação manual de mouse; a avaliação foi feita por capturas de tela e pelos testes.
- Em tabelas grandes, a prévia tem limite de amostra (50 linhas) e o resultado completo vem na exportação.

## Preservação de dados

- Nenhuma tabela foi excluída. As duas tabelas sintéticas excluídas logicamente (`SYN-cadastro-materiais`, `SYN-bom-valvula-vx100-revA`) continuam restauráveis.
- `Codigos totus - separado` (1706 linhas) não foi alterada nem usada nos testes.
- Migrações: `0005_crossing` aplicada automaticamente pelo container da API.
