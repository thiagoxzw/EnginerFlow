# Fase 2B — Data Studio completo (consolidação)

Atualizado em 2026-11-25. Substitui a abordagem de subdivisões (2B.3.x, 2B.4.x).
Roadmap oficial: Fase 0, 1, 2A, **2B (Data Studio completo)**, 3 (Estabilização e otimização do
Data Studio), 4 (BOM Manager), 5 (Material Manager), 6 (Inventory Manager), 7 (Solid Edge Connect),
8 (ERP Connect), 9 (Workflow Studio), 10 (AI Copilot). Os documentos das subdivisões anteriores são preservados.

## Já entregue e preservado (não reimplementar)

Importação CSV/XLSX, múltiplos arquivos e abas, arrastar e soltar, prévia tabular, seleção de cabeçalho,
mapeamento de colunas, modelos, filtros, pesquisa, ordenação, paginação, seleção de linhas, substituição de
valores, preenchimento, exclusão lógica, renomeação, histórico, desfazer e refazer, Super-PROCV, junções,
comparação por chave com modos explícitos, agrupamento com Decimal, tabelas derivadas, idempotência
(`Idempotency-Key`, migração 0006), rastreabilidade (linhagem), exportação CSV e XLSX, e a reorganização da tela
(cabeçalho com ações, tabela central, abas Transformar / Cruzar tabelas / Mapeamento / Histórico / Gerenciar /
Duplicatas / Rastreabilidade).

## Pendente nesta fase (implementação)

1. Editor de células: edição por duplo clique, Enter confirma, Escape cancela, navegação por setas e Tab.
   Cada alteração usa o mecanismo existente de prévia e aplicação (histórico e desfazer preservados).
2. Área de transferência: Ctrl+C copia a seleção em TSV; Ctrl+V cola TSV (compatível com Excel), com
   prévia e confirmação antes de alterações extensas.
3. Seleção de intervalos e de linhas/colunas; atalhos Ctrl+A, Delete, Escape, setas (sem interferir em campos).
4. Organização visual: largura de colunas, ocultação, fixação de colunas, cabeçalho fixo e preferências persistidas.
5. Fórmulas: interpretador seguro (sem eval) com soma, subtração, multiplicação, divisão, média, mín, máx,
   contagem, condições, concatenação, texto e referências a colunas; precisão Decimal; erros explícitos.
   Colunas calculadas persistentes.
6. Desempenho: renderização virtualizada, redução de requisições redundantes.

## Transferido para a Fase 3 (não crítico ou risco estrutural)

- Versionamento incremental por diferenças (o atual usa snapshots completos; medido e documentado).
- Compressão e retenção de snapshots.
- Fórmulas além do conjunto inicial (funções financeiras, estatísticas avançadas, referências entre tabelas).
- Seleção de intervalos com operações em massa de colar sobre múltiplas colunas além de um lote de operações.
- Crescimento do banco não medido nas execuções de benchmark (ver BENCHMARK_2B3.md).

## Critérios de conclusão da Fase 2B

Ver `docs/operations/FASE_2B3_STATUS.md` (checklist atualizado a cada conjunto entregue).
