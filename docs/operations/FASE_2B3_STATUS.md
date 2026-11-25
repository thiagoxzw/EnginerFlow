# Fase 2B — Status consolidado (Data Studio completo)

Atualizado em 2026-11-25. Branch `feat/fase-2b-3-data-crossing`, PR #4 (draft, sem merge).
Este documento é o estado de referência. O checkpoint para retomadas está em `CHECKPOINT_2B3.md`.
Os documentos de subdivisões anteriores (2B.1, 2B.2, 2B.3 bloco 1) foram preservados como histórico.

## 1. Entregue nesta fase

**Importação**
- CSV e XLSX; arrastar e soltar; múltiplos arquivos e abas (uma importação por aba marcada).
- Inspeção prévia sem gravar (`POST /datasets/inspect`): nenhuma tabela é criada antes da importação.
- Prévia tabular (uma célula por valor); seleção de cabeçalho antes e depois da importação.
- Arquivos inválidos ou binários são recusados com mensagem; falhas parciais não impedem os demais arquivos.
- Repetir a importação reenvia só o que não foi concluído (estado por arquivo e por aba).
- Zeros à esquerda preservados; acentuação e caracteres especiais preservados.

**Edição de tabela**
- Edição de célula por duplo clique ou F2/Enter; Enter confirma, Escape cancela, setas e Tab navegam.
- Gravação pelo mesmo mecanismo de prévia e aplicação: aparece no histórico e pode ser desfeita.
- Área de transferência: Ctrl+C copia célula ou linhas selecionadas em TSV (compatível com Excel); Ctrl+V cola.
  Colagem com várias células é UMA operação (`set_cells`), validada antes (colunas, linhas da página, limite de 5 000 células), com confirmação acima de 20 células.
- Seleção manual, por página e por filtro; ações em lote contextuais (aparecem só com seleção).
- Substituição de texto, preenchimento de valores (vazio, desconhecido), exclusão lógica, renomeação.
- Ocultação de colunas por tabela (preferência guardada no navegador); colagem que atravessa colunas ocultas é recusada.

**Fórmulas**
- Analisador seguro, sem `eval`: referências `[Coluna]`, decimais com vírgula ou ponto, + - * /, comparações,
  SOMA, MEDIA, MIN, MAX, CONTAR, SE, CONCAT, MAIUSC, MINUSC, ESQUERDA, DIREITA.
- Precisão decimal (Decimal). Erros explícitos na célula: #VAZIO!, #DESCONHECIDO!, #VALOR!, #DIV/0!, #REF!, #SINTAXE!.
- Resultado: nova tabela derivada rastreável (a tabela de origem não muda).

**Cruzamento de tabelas**
- Super-PROCV (chaves simples e compostas, colunas de retorno, duplicidades, prévia, exportação CSV/XLSX).
- Junções INNER, LEFT, RIGHT, FULL com cardinalidade 1:1, 1:N, N:1, N:M, estimativa e confirmação para N:M.
- Comparação por chave com modos explícitos por coluna: texto exato (padrão), normalizado, numérico, descrição técnica.
- Agrupamento com contagem, distintos, soma, média, mínimo e máximo em Decimal; valores inválidos contados à parte.

**Integridade e rastreabilidade**
- `Idempotency-Key` em todas as derivações (migração 0006): repetição devolve a mesma tabela; mesma chave com
  parâmetros diferentes responde 409; colisão concorrente repete o resultado do vencedor.
- Falha antes do commit reverte tudo (sem tabela órfã). Falha após o commit é recuperada pela repetição com a mesma chave.
- Linhagem por tabela derivada (`GET /datasets/{id}/lineage`): operação, execução, origens com versões de dados e
  metadados, parâmetros, políticas, modos, contagens, hashes e data. Painel "Rastreabilidade" na tela.
- Alterações ou exclusões lógicas das origens não alteram a derivada (testado).
- Derivada pode ser origem de outra operação (testado).

**Interface**
- Cabeçalho com nome, linhas, colunas, origem, troca de tabela, desfazer, refazer e exportação.
- Tabela no centro, cabeçalho fixo, rolagem interna, paginação, pesquisa, filtros, ordenação.
- Abas: Transformar, Fórmulas, Cruzar tabelas (Super-PROCV, Junção, Comparar, Agrupar), Mapeamento,
  Histórico, Gerenciar, Duplicatas e Rastreabilidade (só em derivadas).
- Atalhos: Ctrl+C, Ctrl+V, Ctrl+Z, Ctrl+Y, Enter, Escape, Tab, setas. Não interferem em campos de texto.

## 2. Critérios de aceitação e evidências

| Critério | Evidência |
|---|---|
| Tabela visível sem rolagem excessiva em desktop | medição: topo da tabela em 141 px (antes 137 px, com mais conteúdo acima); altura da página 900 px em 1440×900 (antes 1861) |
| Ausência de overflow horizontal da página | medição: 0 px em 1920×1080, 1440×900, 1366×768 e 390×844 |
| Interface funcional em dispositivos menores | 390×844: tabela começa em 249 px com primeira linha visível (antes 1031 px, não visível) |
| Edição e colagem com desfazer | E2E `edicao-formulas.spec.ts` (edição, Escape, colagem em uma operação com desfazer único) |
| Fórmulas sem eval e com erros explícitos | `test_formula_2b3.py` (17 testes) e `test_formula_derive_2b3.py` |
| Idempotência e integridade | `test_idempotency_2b3.py` (6), `test_set_cells_2b3.py` (3), `test_lineage_2b3.py` (4) |
| Rastreabilidade | `test_lineage_2b3.py` e painel "Rastreabilidade" (E2E de cruzamento) |
| Migrações | `alembic upgrade head → downgrade -1 → upgrade head` em PostgreSQL 17 limpo (ver seção 4) |

Capturas (dados sintéticos): `scratchpad/visual/antes-*` e `depois-*` (ver métricas em `metricas-antes.json` e
`metricas-depois.json`). Não são versionadas no repositório.

## 3. Defeitos corrigidos nesta fase (registro)

| Defeito | Classificação | Correção |
|---|---|---|
| Derivação de junção devolvia 500 (cardinalidade em texto em um campo inteiro) | Crítico (falha de operação) | `counts` aceita texto; teste de rota |
| Tabela derivada indistinguível na lista | Correção necessária | `source_kind` na API; indicação na lista |
| Mensagem de derivação perdida ao trocar de tabela | Correção necessária | aviso na página, com execução e hash |
| Ações de linha ocupavam espaço vazio; confirmação sumia | Correção necessária | ações contextuais; confirmação na barra |
| Vazamento de valores de `mockResolvedValueOnce` entre testes | Correção de teste | `resetAllMocks` no setup global, com regressão `mock-isolation.test.ts` |
| Build web falhava por nome duplicado em edição intermediária | Bloqueio de build (sem commit) | corrigido antes do commit |
| Benchmark gravava pico do processo errado (launcher) | Correção de medição | medição pelo próprio processo |
| Banco de benchmark criado dentro do ambiente pessoal | Isolamento | runner dedicado; banco antigo mantido (ver seção 6) |
| E2E: conflito de porta com stack de auditoria; teardown antes da checagem | Correção de infraestrutura | portas próprias; remoção do próprio projeto antes da checagem |

## 4. Migrações

| Revisão | Conteúdo | Reversível |
|---|---|---|
| 0001–0004 | fases 2A e 2B.1–2B.2 | sim |
| 0005_crossing | `crossing_runs`, `crossing_run_sources`, `datasets.source_kind` e `derived_run_id` | sim |
| 0006_crossing_idempotency | coluna `idempotency_key` com restrição única em `crossing_runs` | sim |

Validação em PostgreSQL 17 limpo: `upgrade head`, `downgrade -1`, `upgrade head` (sucesso, versão final `0006`).
A API aplica `alembic upgrade head` ao iniciar; o backup do ambiente pessoal é feito antes (ver seção 7).

## 5. Benchmarks (resumo; detalhes em `BENCHMARK_2B3.md`)

- 500 mil e 100 mil linhas por tabela, em PostgreSQL dedicado. Super-PROCV, junção, comparação e agrupamento medidos.
- Cenário dentro do limite: comparação materializou só as 400 mil diferenças (300 mil idênticas contadas, não materializadas).
- Cenário acima do limite: junção recusada antes de materializar (estimativa 503 119 > 500 000); comparação recusada
  ao atingir 500 000 diferenças durante o streaming (o guarda é incremental, limitação documentada).
- Pico do processo chegou a ~1,3 GB em 500 mil; os valores são acumulados e não comparáveis entre execuções.
- Crescimento do banco não medido nas execuções de benchmark (limitação).
- As operações de colagem, fórmula e edição não foram medidas em 500 mil; são registradas como limitação.

## 6. Ambientes (ver `LOCAL_SETUP.md`)

| Ambiente | Projeto | Portas | Estado |
|---|---|---|---|
| Demonstrativo pessoal | `engiflow` | 3000 / 8000 / 5432 | em uso; dados preservados |
| Auditoria | `engiflow-audit` | 3100 / 8100 / 5433 | auxiliar; volumes preservados |
| E2E descartável | `engiflow-e2e` | 3210 / 8210 / 5542 | removido ao final de cada execução |
| Benchmark | `engiflow-bench` | 5552 | removido ao final de cada execução |

Banco `engiflow_bench` criado no PostgreSQL pessoal em sessão anterior: **mantido**, sem exclusão (exige autorização).

## 7. Pendências transferidas para a Fase 3 (não bloqueantes)

- Reordenação e redimensionamento de colunas (arrastar), fixação de colunas.
- Seleção de intervalos com Shift+setas, Ctrl+A e tecla Delete para exclusão.
- Conjunto de fórmulas além do inicial (ex.: funções estatísticas avançadas, referências entre tabelas).
- Versionamento incremental (hoje: snapshots completos; custo medido por operação).
- Virtualização da renderização para tabelas muito grandes (hoje: paginação de 25–100 linhas).
- Medição de crescimento do banco e de operações de edição em escala.
- Desfazer da colagem depende da operação única; a colagem é limitada à página carregada.

## 8. Riscos remanescentes

- Testes de interface foram validados por E2E em dados sintéticos e capturas; não há validação com uso real prolongado.
- Pico de memória em operações com centenas de milhares de linhas é alto (ver benchmarks).
- Comparação com guarda incremental pode consumir memória até o limite antes de recusar.

## 9. Estado de validação e CI

Ver a seção "Validação final" em `CHECKPOINT_2B3.md` (atualizada com os resultados do commit final).
O CI do GitHub é verificado no commit final antes de qualquer recomendação de merge.

## Encerramento administrativo (2026-11-25)

- Exclusão lógica de 37 tabelas sintéticas pela API; lista e IDs em `backups/removidos-sinteticos-20261125-135151.txt`.
- Duplicata de `Codigos totus - separado`: removida a cópia sem histórico (`ab5091de…`), conteúdo idêntico. Mantida `6aebaf7e…`, com a operação `set_mapping`.
- Recursos antigos de auditoria e benchmark removidos. Rede `engiflow-audit_default` inexistente. Sem comandos globais de limpeza.
- Início da Fase 3 com a seleção de intervalo de células (commit `94e68f7`). Demais itens da Fase 3 seguem pendentes.
- Descrição do PR #4 (texto para colar, pois este ambiente não tem autenticação GitHub):

> Fase 2B.3 concluída: cruzamentos e comparações de tabelas (PROCV, junção, comparação por chave, agregação e fórmulas), com prévia e aplicação, histórico, rastreabilidade e idempotência. Inclui migração 0006 (chave de idempotência). Fase 3 em commits separados para revisão independente.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

## Fase 3 — Estabilização, correções e otimização do Data Studio (entrega)

Uma única etapa, em commits separados no mesmo branch, para revisão independente.

### Entregue

- **Seleção:** arraste do mouse; Shift+clique; Shift+setas; Ctrl+A (células da página); clique no número da linha (linha inteira); clique na área do cabeçalho (coluna inteira); Home, End, Ctrl+Home, Ctrl+End, PageUp e PageDown.
- **Estrutura (operações versionadas):** `insert_rows`, `duplicate_rows`, `insert_column`, `duplicate_column` e `delete_columns`, além da exclusão de linhas existente. Todas passam por prévia, aplicação, histórico e desfazer. Linhas e colunas novas começam vazias (`""`); desconhecidos copiados ficam desconhecidos.
- **Edição em massa:** limpar, preencher para baixo (Ctrl+D) e aplicar um valor à seleção gravam uma única operação `set_cells`. Acima de 20 células pedem confirmação. Vazio, zero e desconhecido são preservados.
- **Área de transferência:** Ctrl+C copia o intervalo inteiro em TSV (colunas ocultas ficam de fora). Zeros à esquerda não são convertidos.
- **Organização por tabela:** redimensionamento por arraste na borda do cabeçalho; duplo clique ajusta ao conteúdo; reordenação e fixação de colunas pelo menu contextual; ocultação (já existente). Preferências guardadas neste navegador, por tabela, sem gerar versão.
- **Persistência:** a tabela aberta permanece após atualizar a página, neste navegador.
- **Fórmulas:** `E`, `OU`, `SEERRO`, `ARRED`, `ABS`, `ARRUMAR`, `NUM.CARACT`, `VERDADEIRO` e `FALSO`; aliases `MÍNIMO`, `MÁXIMO`, `CONTAGEM`, `CONCATENAR`, `MAIÚSCULA` e `MINÚSCULA`. As funções já corretas não foram alteradas. Sem `eval`, com `Decimal`.
- **Correção de ordem:** inserir e duplicar linhas renumeram as linhas na ordem exibida, como em planilha. A leitura ordena por número, e a versão não guarda posição. A exclusão continua preservando os números.

### Decisões

- **Limpeza grava vazio (`""`)**, não desconhecido, conforme aprovado.
- **Reordenação e largura são preferências de visualização.** Não entram no histórico de dados, por não alterarem o conteúdo.
- **Versionamento:** mantido o modelo de snapshots completos. Cada operação de dados grava a tabela inteira. A avaliação de um modelo incremental concluiu que a mudança alteraria o formato de armazenamento de todas as versões existentes, com risco de integridade e rastreabilidade, e não era segura sem migração destrutiva. Por isso não foi implementada. Medição atual no demonstrativo (somente leitura): 3786 linhas de versão, cerca de 1,1 MB; a tabela `Codigos totus - separado` (1706 linhas) tem uma versão, sem cópias extras. Estimativa (não medida, a partir de cerca de 290 bytes por linha de versão medidos): cada operação de dados numa tabela de 500 mil linhas grava outra cópia completa, da ordem de 150 MB. Esse é o principal ponto de crescimento a tratar numa próxima fase.
- **Virtualização de linhas não foi implementada:** a grade já pagina em 50 linhas por página, o que mantém o número de nós renderizados limitado. Virtualização de colunas foi avaliada e não é necessária no volume atual (poucas colunas por tabela).

### Limitações conhecidas (não críticas)

- O menu contextual abre com clique direito; não há tecla de menu nem atalho para inserir ou excluir linhas e colunas.
- Ao fixar colunas, apenas as colunas fixadas ficam sticky; o checkbox e o número da linha rolam para fora.
- Não há testes E2E específicos para os novos controles (cobertos por testes unitários de interface e por testes HTTP da API).
- Células com quebra de linha ou tabulação são copiadas sem aspas (TSV simples); colar esse texto pode dividir linhas. O Excel usa aspas nesses casos, e isso não é tratado.

### Validação

- API: suíte completa, 329 testes aprovados. Ruff e mypy sem erros.
- Web: typecheck, ESLint sem alertas e 101 testes de unidade aprovados.
- Testes direcionados das operações estruturais (unitários e HTTP com desfazer) e das fórmulas novas.
- Migrações: nenhuma migração nova nesta fase.
- Benchmarks de cruzamento: não repetidos, por não terem sido afetados pelas alterações.
- E2E isolado e CI do commit final: ver a seção de entrega no relatório da sessão.
