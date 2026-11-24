# ADR-0004 — Jobs com estado no PostgreSQL, sem Celery/Redis nesta fase

- **Status:** Revisada (2026-11-24) — aguarda aprovação
- **Substitui:** "Celery + Redis com estado em PostgreSQL"

## Contexto
O pedido diz para usar Redis e Celery somente quando houver necessidade. Com um único usuário, não há fila concorrente que justifique broker e worker separados.

## Decisão
- Tabela `jobs` e `job_attempts` no PostgreSQL registram cada operação longa (importação, explosão grande, exportação, varredura de pasta).
- Execução em um executor interno (thread/processo de background) do próprio backend, que lê jobs `queued` do banco.
- Retentativa e timeout definidos na própria operação; cancelamento cooperativo.
- Idempotência por chave única por operação (evita reimportar o mesmo arquivo como novo).
- Redis e Celery ficam **fora do escopo** até haver necessidade medida (ex.: jobs simultâneos que travem a interface).

## Consequência
Menos serviços para instalar e manter. Se o executor interno virar gargalo, a troca por Celery é localizada: o estado já está no banco.

## Pendência
Nenhuma; reavaliar após os testes de processamento de 100 MB.
