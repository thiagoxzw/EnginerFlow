# Fase 2B.2 — Status de homologação

Branch: `feat/fase-2b-2-data-manipulation` · PR #3 (Draft até a conclusão desta revisão).
Dados: exclusivamente sintéticos. Uso individual, sem RBAC nem multi-tenancy.
Não há merge: a decisão de mesclar é do responsável pelo projeto.

## Blocos implementados

| Bloco | Conteúdo | Commits principais | Testes automatizados |
|---|---|---|---|
| 1 | Versionamento de mapeamentos e metadados; migração 0004 | `8994fdc` | `test_metadata_versioning_2b2.py` |
| 2 | Modelos de mapeamento reutilizáveis | `96469a7`, `5198260` | `test_templates_2b2.py`; `templates-section.test.tsx` |
| 3 | Seleção manual de cabeçalho (reconstrução do original) | `7874f55` | `test_header_2b2.py`; `header-section.test.tsx` |
| 4 | Filtros, pesquisa, ordenação e paginação no servidor | `1c140d8` | `test_query_2b2.py`; `data-table.test.tsx`; `rows.test.ts` |
| 5 | Localizar e substituir em lote | `04ccbf3` | `test_replace_2b2.py`; `replace-section.test.tsx` |
| 6 | Seleção e transformação de linhas; exclusão lógica | `b2008d8` | `test_rows_ops_2b2.py`; `row-actions.test.tsx` |
| 7 | Renomear, excluir logicamente e restaurar tabelas | `f219874` | `test_tables_2b2.py`; `table-admin.test.tsx` |
| 8 | Histórico, desfazer/refazer com atalhos, conflitos | `c0ae6e4` | `history-panel.test.tsx` |
| Integração | Invalidação centralizada após operações | `7c82399` | E2E (`data-studio.spec.ts`) |
| E2E | Playwright: fluxo completo e seis fluxos críticos | `56bab6d`, `b63fa0a` | `apps/web/e2e/*.spec.ts` |
| Medição | Script PostgreSQL 100k/500k e workflow manual | `a600397`, `de620aa` | `apps/api/scripts/bench_2b2_postgres.py` |

## Resultados verificados

- **CI no commit `1832fb7`** (execução `45535641946`): API (Python, PostgreSQL 17) sucesso; Web sucesso; E2E (Playwright) sucesso.
- **Execução manual `45535650972`** (mesmo commit): API, Web, E2E e benchmark sucesso.
- **Fluxos críticos** (`fluxos-criticos.spec.ts`): seis cenários passam localmente em banco novo, contra a API e a web de produção. No CI do commit `69bdf18` (execução `45537209605`) o job E2E passou, incluindo os seis fluxos.
- **Web:** 39 testes de componente e unidade; typecheck e lint limpos.
- **API:** 180 testes (SQLite e PostgreSQL 17 no CI).

## Medições de desempenho (PostgreSQL 17.12, dados sintéticos)

Ambiente: Linux (Azure, runner GitHub Actions), 4 CPUs lógicas, Python 3.14.4. Uma única execução por tamanho; não são garantias de capacidade.

| Operação | 100 mil linhas | 500 mil linhas | Memória Python de pico (100k / 500k) |
|---|---|---|---|
| Importação CSV (5,4 MB / 27,3 MB) | 3,0 s | 16,7 s | não medida (ver nota) |
| Filtragem (Qtd > 4,5, 100 linhas) | 0,31 s | 1,62 s | 2,0 MB / 2,0 MB |
| Pesquisa global (sem acento) | 0,50 s | 2,59 s | 2,0 MB / 2,0 MB |
| Ordenação numérica (todas as linhas) | 0,41 s | 2,39 s | 67,3 MB / 337,5 MB |
| Seleção de linhas por filtro | 0,29 s | 1,49 s | 3,5 MB / 9,9 MB |
| Geração de prévia (substituição) | 0,53 s | 2,90 s | 57,1 MB / 285,7 MB |
| Aplicação de substituição (prévia + aplicação) | 4,03 s | 20,67 s | 56,8 MB / 284,3 MB |
| Desfazer (move ponteiros) | 0,006 s | 0,006 s | 0,0 MB |
| Crescimento de armazenamento, versão 1 (importação) | 24,0 MB | 120,0 MB | — |
| Crescimento de armazenamento, nova versão por substituição | 51,8 MB | 265,3 MB | — |

Nota: a importação roda uma vez, sem a medição de memória por tracemalloc, para não duplicar o custo. O crescimento de armazenamento é o tamanho total da tabela `dataset_version_rows` (inclui índices) antes e depois de cada operação.

### Quais operações carregam a tabela inteira em memória

- **Carregam tudo:** geração e aplicação de substituição (`load_snapshot` lê todas as linhas da versão para reconstruir o snapshot); ordenação (materializa as linhas que casam); reconstrução por cabeçalho (lê o arquivo original inteiro).
- **Processamento incremental:** importação (streaming com lotes); filtragem, pesquisa e seleção (varredura em streaming com lotes de 2 mil linhas, guardando só a página ou a lista de números).
- **Desfazer/refazer:** não carregam linhas; movem os ponteiros.

### Crescimento por versão

Toda operação de dados cria uma nova versão completa das linhas (ver "Limitações"). Por isso uma substituição em 500 mil linhas acrescenta cerca de 265 MB. Operações só de metadados (renomear, mapear, aplicar modelo) não copiam linhas.

## Regras verificadas

- Estado da tabela = (versão de dados, versão de metadados). Operações só de metadados não copiam linhas.
- Requisições legadas sem `base_metadata_version_id` não aplicam sobre metadados obsoletos (409).
- Prévia é invalidada por mudança de dados ou de metadados; a aplicação recusa resultado divergente.
- Vazio (`""`), desconhecido (`null`) e zero (`"0"`) são estados distintos; desconhecido nunca é substituído.
- Números com vírgula decimal são interpretados só para filtro e ordenação; o valor armazenado não muda.
- Códigos com zeros à esquerda são preservados em importação, reconstrução e consulta.
- Exclusão de linhas é lógica e preserva os números das demais; desfazer restaura.
- Tabela excluída não aceita operações; restauração é recusada se o nome já estiver em uso por tabela ativa.
- Histórico nunca é apagado: desfazer e refazer movem ponteiros.

## Revisão de integridade e segurança

- **Imutabilidade:** versões de dados e de metadados são linhas inseridas, nunca alteradas; a aplicação só move ponteiros (testes de imutabilidade em `test_integridade_2b1.py`).
- **Arquivo original:** o upload é gravado pelo hash do conteúdo e não é sobrescrito; a reconstrução por cabeçalho relê esse arquivo.
- **Atualização atômica:** os dois ponteiros (dados e metadados) são trocados numa única atualização condicional; conflito devolve 409.
- **Concorrência:** prévia consumida por atualização condicional; teste de concorrência com aplicações simultâneas e verificação de conflito entre abas (E2E `conflito de versão`).
- **Idempotência:** `Idempotency-Key` com hash de parâmetros; reenvio devolve o resultado já aplicado.
- **Códigos e especificações:** nenhuma operação converte texto para número no armazenamento; zeros e vazios são preservados (testes em `test_query_2b2.py` e `test_replace_2b2.py`).
- **Repositório:** `git ls-files` lista apenas fixtures `SYN-*` em CSV; `.env.example` contém só valores de desenvolvimento; senhas de teste aparecem apenas em testes e no CI (variáveis de ambiente).
- **Exceções do `.gitignore`:** restritas a `.env.example` e a `SYN-*.csv/.xlsx` nas pastas de fixtures de teste (`apps/api/tests/fixtures/`, `apps/web/e2e/fixtures/`).
- **Artefatos:** `apps/web/test-results/` e `playwright-report/` ignorados e fora do repositório.
- **Regressões:** a suíte completa da API (180 testes, incluindo fases 2A e 2B.1) e a web (39 testes) passam.

## Revisão visual e funcional

Capturas em `C:\Dev\EngiFlow-dados\evidencias\` (fora do repositório):
- `02-data-studio-desktop.png`, `03-filtro-e-tabela.png`: tabela com filtro aplicado, contagem "Linhas 1–2 de 2", ações e seleção legíveis.
- `04-celular-375px.png`: layout em 375 px sem overflow horizontal (medido: 0 px).

Achados não corrigidos nesta fase (melhorias para a 2B.4, sem defeito funcional):
- A seção de modelos e a de cabeçalho ficam acima da tabela; em telas pequenas o usuário precisa rolar bastante até os dados.
- A prévia de cabeçalho mostra cada linha como texto com `|`, difícil de ler com muitas colunas.

## Limitações conhecidas

- **Cada operação de dados copia a tabela inteira** para uma nova versão. Em 500 mil linhas, uma substituição acrescenta cerca de 265 MB. Não há retenção nem compactação de versões.
- **Operações de dados carregam a versão inteira em memória** (substituição, ordenação, reconstrução). O pico medido foi cerca de 285 MB de objetos Python em 500 mil linhas; o processo inteiro consome mais.
- **Aplicação de substituição em 500 mil linhas leva ~21 s** (prévia + aplicação). Não há índice por coluna; filtros e pesquisa são varredura sequencial.
- Ordenação materializa as linhas que casam; teto de 500 mil linhas (acima disso é recusada).
- Seleção por filtro limitada a 10 mil linhas.
- Pesquisa global é substring sem acento sobre todas as colunas, sem índice.
- Modelos de mapeamento não podem ser excluídos (apenas editados), para preservar o histórico.
- Medição de memória usa `tracemalloc` (objetos Python); não mede o processo inteiro.
- Medição em um único ambiente (runner GitHub Actions) e uma execução por tamanho.
- Não foram medidos volumes acima de 500 mil linhas nem concorrência de carga; não há declaração de capacidade além do medido.

## Matriz de critérios de aceitação

| Critério | Situação | Evidência |
|---|---|---|
| Testes existentes (fases 2A e 2B.1) passam em PostgreSQL 17 | Aprovado | CI `45535641946` (API) |
| Migração 0004: upgrade, downgrade, upgrade | Aprovado | CI (job API) e `test_versioning_2b1.py` |
| Preservação do histórico das fases anteriores | Aprovado | testes de migração e de histórico |
| Concorrência de dados e metadados | Aprovado | testes de concorrência (API) e conflito entre abas (E2E) |
| Requisições legadas não alteram metadados obsoletos | Aprovado | `test_metadata_versioning_2b2.py` (409) |
| Aplicação de modelo com confirmação parcial | Aprovado | `fluxos-criticos.spec.ts`; CI `45537209605` |
| Seleção manual de cabeçalho | Aprovado | `test_header_2b2.py`; `fluxos-criticos.spec.ts` |
| Transformação e exclusão de linhas | Aprovado | `test_rows_ops_2b2.py`; `fluxos-criticos.spec.ts` |
| Desfazer e refazer | Aprovado | `history-panel.test.tsx`; E2E |
| Exclusão e restauração de tabelas | Aprovado | `test_tables_2b2.py`; `fluxos-criticos.spec.ts` |
| Tratamento de conflitos de versão | Aprovado | `fluxos-criticos.spec.ts` (conflito entre abas) |
| Benchmark 100 mil e 500 mil linhas em PostgreSQL 17 | Aprovado (medido) | execução `45535650972` |
| Capacidade acima de 500 mil linhas | Não verificado | não medido |
| Integridade e segurança do repositório | Aprovado | seção de revisão acima |
| Interface utilizável (desktop e 375 px) | Aprovado com melhorias registradas | capturas e medição de overflow |
| Playwright em CI | Aprovado | CI `45535641946` (job E2E) |

## Situação final

PR #3 marcado como pronto para revisão (não mesclado). A decisão de merge fica com o responsável pelo projeto.

