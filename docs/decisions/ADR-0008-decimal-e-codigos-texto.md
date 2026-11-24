# ADR-0008 — Quantidades em Decimal e códigos sempre como texto

- **Status:** Mantida (2026-11-24) — aguarda aprovação

## Decisão
- Quantidades: `Decimal` em Python; `numeric(18,6)` no PostgreSQL; enviadas na API como string decimal. Nunca `float`.
- Códigos de material: `text` em importação, banco, API e exportação. Nenhuma conversão numérica.
- Testes obrigatórios para zeros à esquerda e arredondamento.

## Motivo
Perda de zeros à esquerda e erros de ponto flutuante geram divergências de materiais.
