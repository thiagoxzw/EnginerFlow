# Fase 2B.2 — Status de implementação

Branch: `feat/fase-2b-2-data-manipulation` · Draft PR #3 (não mesclado).
Dados: exclusivamente sintéticos. Uso individual, sem RBAC nem multi-tenancy.

## Blocos

| Bloco | Conteúdo | Commit(s) | Testes automatizados |
|---|---|---|---|
| 1 | Versionamento de mapeamentos e metadados; migração 0004 | `8994fdc` | API: `test_metadata_versioning_2b2.py` |
| 2 | Modelos de mapeamento reutilizáveis (backend + interface) | `96469a7`, `5198260` | API: `test_templates_2b2.py`; Web: `templates-section.test.tsx` |
| 3 | Seleção manual de cabeçalho (reconstrução do original) | `7874f55` | API: `test_header_2b2.py`; Web: `header-section.test.tsx` |
| 4 | Filtros, pesquisa, ordenação e paginação no servidor | `1c140d8` | API: `test_query_2b2.py`; Web: `data-table.test.tsx`, `rows.test.ts` |
| 5 | Localizar e substituir em lote | `04ccbf3` | API: `test_replace_2b2.py`; Web: `replace-section.test.tsx` |
| 6 | Seleção e transformação de linhas, exclusão lógica | `b2008d8` | API: `test_rows_ops_2b2.py`; Web: `row-actions.test.tsx` |
| 7 | Renomear, excluir logicamente e restaurar tabelas | `f219874` | API: `test_tables_2b2.py`; Web: `table-admin.test.tsx` |
| 8 | Histórico, desfazer/refazer com atalhos, conflitos | `c0ae6e4` | Web: `history-panel.test.tsx` |
| E2E | Playwright: login, importação, filtro, substituição, desfazer | `56bab6d`, `09d97f2`, `a600397` | `apps/web/e2e/data-studio.spec.ts` (job `e2e` no CI) |
| Medição | Script PostgreSQL 100k/500k e job manual no CI | `a600397` | `apps/api/scripts/bench_2b2_postgres.py` |

## Regras verificadas por teste

- Estado da tabela = (versão de dados, versão de metadados). Operações só de metadados não copiam linhas.
- Requisições legadas sem `base_metadata_version_id` não aplicam sobre metadados obsoletos (409).
- Prévia é invalidada por mudança de dados ou de metadados; aplicação recusa resultado divergente.
- Vazio (`""`), desconhecido (`null`) e zero (`"0"`) são estados distintos em filtros, ordenação e substituição; desconhecido nunca é substituído.
- Números com vírgula decimal são interpretados só para filtro e ordenação; o valor armazenado não muda.
- Códigos com zeros à esquerda são preservados (testados em importação, reconstrução e consulta).
- Exclusão de linhas é lógica e preserva os números das demais linhas; desfazer restaura.
- Tabela excluída não aceita operações; restauração é recusada se o nome já estiver em uso por tabela ativa.
- Histórico nunca é apagado: desfazer e refazer movem ponteiros.

## Verificações

- Suíte de API: 180 testes no último ciclo local (SQLite) e no CI (PostgreSQL 17) para os blocos 1 e 2.
  Os blocos 3 a 8 foram verificados localmente em SQLite; o CI com PostgreSQL 17 deve ser conferido no commit final.
- Web: 39 testes de componente e unidade, typecheck e lint limpos.
- E2E: um fluxo completo (login → importação → filtro → substituição com prévia → desfazer), executado no job `e2e` com PostgreSQL 17.

## Pendente antes de marcar o PR como pronto

1. **Medições de desempenho (100 mil e 500 mil linhas, PostgreSQL 17).** O job `benchmark` é manual (`workflow_dispatch`) e ainda não foi executado. Nenhuma capacidade deve ser declarada até que os números estejam registrados aqui.
2. **CI verde no commit final**, incluindo o job `e2e`.
3. **Revisão de integridade e segurança** do conjunto final (dados sintéticos, senhas apenas em variáveis de CI, nenhuma credencial no repositório).

## Limitações conhecidas

- Ordenação materializa as linhas que casam. O teto é 500 mil linhas; acima disso a consulta é recusada. O custo real em memória deve ser lido na medição.
- Seleção por filtro é limitada a 10 mil linhas; acima disso o usuário precisa refinar os filtros.
- A reconstrução por cabeçalho lê o arquivo original inteiro e gera uma nova versão completa.
- Pesquisa global é substring sem acento sobre todas as colunas; não há índice (varredura).
- Filtros usam varredura sequencial da versão atual; não há índices por coluna.
- Modelos de mapeamento não podem ser excluídos (apenas editados), para preservar referências no histórico.
- Não há retenção de versões: o histórico cresce com cada operação.
- Medição de memória usa `tracemalloc` (objetos Python), não o processo inteiro.
