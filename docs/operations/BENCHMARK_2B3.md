# Benchmarks da Fase 2B.3

Dados 100% sintéticos. Ambiente: Windows 11, 12 CPUs lógicas, Python 3.14.10, PostgreSQL 17.12
em contêiner dedicado (`scripts/bench/docker-compose.bench.yml`, projeto `engiflow-bench`, volume próprio,
porta 5552). O banco é `engiflow_bench`, em 127.0.0.1. O script recusa qualquer outro banco ou a porta 5432.

## Como medir e o que cada coluna significa

- **Tempo**: uma execução com o relógio; cada operação é executada de novo para medir o pico Python.
- **Pico Python**: pico de alocação Python de UMA operação (tracemalloc).
- **Pico do processo**: pico de working set do processo inteiro (acumulado desde o início). Não é o
  consumo específico da operação. Mede também a importação e o que ficou alocado antes.
- **Saída**: linhas que a operação produz (prévia e tabela derivada, quando aplicável).
- **Recusa**: a operação foi interrompida pelo guarda de limite com a mensagem do produto.

## Versões do script (IMPORTANTE para comparação)

| Execução | Script | Diferença |
|---|---|---|
| 500 mil, dentro do limite | v1 | sem arquivo de resultados; pico do processo via GetProcessMemoryInfo; registro só no log |
| 500 mil, duplicatas | v2 | registra cada resultado num arquivo ao concluir |
| 100 mil (ambos) | v2 | igual à v2 |

Resultados da v1 e da v2 devem ser lidos como da mesma metodologia de medição (mesma lógica de operação).
A única diferença é o registro. Mesmo assim, o pico do processo é acumulado: valores de execuções
diferentes não são comparáveis entre si.

## 100 mil linhas por tabela (script v2, ambos os cenários)

Dentro do limite (chaves únicas): importação 54,7 s; Super-PROCV prévia 3,9 s (100 000 linhas);
junção esquerda prévia 8,8 s (100 000); comparação 3,2 s (80 000 diferenças: 20 000 removidas e
20 000 adicionadas; as idênticas não materializadas); agregação 1,7 s; materialização do Super-PROCV
28,2 s. Pico do processo: 349 MB.

Acima do limite (chaves repetidas): importação 51,1 s; Super-PROCV prévia 3,9 s; junção prévia 7,2 s
(saída 100 623 linhas, dentro do limite); comparação 3,8 s (saída 100 242 diferenças, dentro do limite);
agregação 2,1 s; materialização 27,3 s. Pico do processo: 357 MB.

Nesta escala nenhum guarda foi acionado: o limite de 500 mil só é atingido com 500 mil de entrada.

## Crescimento do banco

Não medido nestas execuções: o volume do benchmark é removido ao final de cada rodada. A medição de
armazenamento (`pg_total_relation_size`) foi implementada apenas na versão 2B.2 do benchmark. Fica como
limitação e como item para a 2B.4.

## 500 mil linhas por tabela

### Cenário A: dentro do limite (chaves únicas, 60% de sobreposição) — script v1

| Operação | Tempo (s) | Pico Python (MB) | Pico processo (MB, acumulado) | Saída |
|---|---|---|---|---|
| Importação das duas tabelas | 215,7 | n/a | n/a | — |
| Super-PROCV: prévia | 28,9 | 363,7 | 1177,3 | 500 000 linhas |
| Junção esquerda: prévia (cardinalidade e estimativa) | 47,6 | 429,4 | 1303,4 | 500 000 linhas (estimativa) |
| Comparação por chave | 24,2 | 274,7 | 1303,4 | 400 000 diferenças |
| Agregação (soma por unidade, decimal) | 15,0 | 1,6 | 1303,4 | 1 linha |
| Super-PROCV: materialização (tabela derivada) | 141,9 | n/a | 1303,4 | gravada |

Comparação com 300 mil casadas idênticas, 200 mil removidas e 200 mil adicionadas: a operação materializa
**somente as 400 mil diferenças**. As 300 mil linhas idênticas são contadas, não materializadas.

### Cenário B: acima do limite (chaves repetidas) — script v2

| Operação | Tempo (s) | Pico Python (MB) | Pico processo (MB) | Resultado |
|---|---|---|---|---|
| Importação das duas tabelas | 205,0 | n/a | 102,5 | — |
| Super-PROCV: prévia | 16,7 | 362,1 | 1170,6 | 500 000 linhas (dentro do limite) |
| Junção esquerda: prévia | 22,2 | 190,9 | 1170,6 | **recusada**: estimativa de 503 119 linhas > 500 000 |
| Comparação por chave | 27,0 | 279,4 | 1170,6 | **recusada** ao atingir 500 000 diferenças |
| Agregação | 8,0 | 1,6 | 1170,6 | 1 linha |
| Super-PROCV: materialização | 161,3 | n/a | 1170,6 | gravada |

### Os guardas interrompem antes de alocar o resultado excessivo?

- **Junção**: sim. A cardinalidade é calculada por contagem de chaves e a estimativa é verificada
  antes de qualquer linha ser materializada. A recusa ocorre no planejamento.
- **Comparação**: parcialmente. O guarda é incremental: a operação recusa ao emitir a linha que
  ultrapassaria o limite. Ou seja, o pico de memória cresce até o limite antes da recusa. Não há
  pré-contagem das diferenças. Isto é uma limitação conhecida (ver FASE_2B3_STATUS).

## Limitações

- Um único host Windows; resultados não são garantias de capacidade.
- Pico do processo é acumulado; o consumo específico de cada operação é o pico Python.
- Dados sintéticos com chaves de 8 dígitos; chaves reais podem ter outra distribuição.
