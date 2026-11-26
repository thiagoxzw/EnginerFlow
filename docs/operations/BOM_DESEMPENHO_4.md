# BOM Manager — medição sintética de desempenho

Gerada em 2026-11-25 pelos testes com `BOM_PERF=1`: `apps/api/tests/test_bom_perf_4.py` (importação, prévia, criação, leitura, explosão, validação, comparação e memória) e `apps/web/src/lib/bom-tree-perf.test.ts` (árvore no navegador). Dados totalmente sintéticos (`TOP-SYN`, `SUB-SYN`, `CMP-SYN`).

**Ambiente:** Windows 11, Python 3.14, banco de testes SQLite (não PostgreSQL), Node com vitest e jsdom. Os números servem para comparar tamanhos entre si, não como medição de produção.

## Backend (segundos; memória de pico em MB, tracemalloc)

| Componentes (linhas) | Importação | Prévia | Criação | Leitura das linhas | Explosão (API) | Explosão (domínio) | Validação | Comparação | Busca em texto |
|---|---|---|---|---|---|---|---|---|---|
| 1.000 (961) | 0,343 | 0,268 | 0,488 | 0,095 | 0,111 | 0,112 (0,47 MB) | 0,183 (0,16 MB) | 0,314 (0,91 MB) | 0,0008 |
| 5.000 (4.761) | 0,643 | 0,470 | 1,685 | 0,471 | 0,408 | 0,599 (2,34 MB) | 0,868 (0,54 MB) | 1,203 (4,95 MB) | 0,0036 |
| 10.000 (9.511) | 0,865 | 0,750 | 2,659 | 0,645 | 0,728 | 1,211 (4,73 MB) | 1,836 (1,16 MB) | 2,490 (10,29 MB) | 0,0088 |

## Navegador (milissegundos; pior caso = árvore inteira expandida)

| Componentes (linhas) | Expandir tudo | Busca por texto | Filtro (unidade e revisão) | Recolhida |
|---|---|---|---|---|
| 1.000 (961) | 19,4 | 59,3 | 2,9 | 1,1 |
| 5.000 (4.761) | 34,4 | 186,9 | 3,5 | 2,6 |
| 10.000 (9.511) | 118,4 | 297,1 | 1,9 | 1,4 |

## Leitura dos resultados

- A importação, a criação e a explosão crescem de forma aproximadamente linear com o número de linhas. Até 10 mil componentes, cada etapa fica abaixo de 3 segundos.
- A comparação é a etapa mais cara em memória (cerca de 10 MB no pico para 10 mil linhas), porque mantém os dois conjuntos de arestas. É aceitável para uso individual.
- A expansão da árvore inteira no navegador fica abaixo de 120 ms com 10 mil componentes. A interface renderiza no máximo 1.500 linhas por vez, então esse custo é menor do que o total de linhas.
- **Ponto de atenção:** a busca por texto leva cerca de 300 ms com 10 mil componentes e roda a cada tecla. Não foi implementado adiamento da busca; a melhoria prevista é `useDeferredValue` ou um atraso curto na entrada.

## Decisão sobre virtualização

Não foi implementada. Com a limitação de 1.500 linhas renderizadas e a expansão sob demanda, a tela responde em tempo aceitável para 10 mil componentes. Virtualização fica registrada como melhoria futura, caso estruturas acima de 10 mil linhas se tornem comuns.

## Limitações desta medição

- Hierarquia sintética de três níveis, com componentes reaproveitados entre subconjuntos. Estruturas reais podem ter mais níveis e mais repetição.
- Banco SQLite nos testes. PostgreSQL não foi medido nesta rodada.
- Memória medida só nas funções de cálculo, com tracemalloc. Não inclui o processo do servidor nem o navegador.
