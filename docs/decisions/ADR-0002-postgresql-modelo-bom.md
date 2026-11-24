# ADR-0002 — PostgreSQL local (via Docker) e modelo de BOM por arestas

- **Status:** Revisada (2026-11-24) — aguarda aprovação
- **Substitui:** versão anterior "PostgreSQL com RLS e organization_id"

## Contexto
Dados relacionais com transações e consultas recursivas (explosão de BOM). Uso individual: não há multi-tenancy, RBAC nem RLS.

## Decisão
1. PostgreSQL como banco único, executado via Docker Compose (instalação de Docker autorizada; ver ADR-0010).
2. **Sem `organization_id`, sem RLS, sem tabelas de usuários/papéis/organizações nesta fase.** Se houver autenticação, ela fica restrita a um usuário (ADR-0012).
3. BOM modelada como arestas pai→filho por revisão (`bom_items`); explosão com `WITH RECURSIVE`; ciclos detectados no domínio antes de gravar.
4. Revisões aprovadas marcadas como imutáveis pela aplicação; trigger de banco só se o teste mostrar necessidade.
5. Migrações com Alembic desde a primeira tabela.

## Alternativas descartadas
- SQLite: simples, mas o PostgreSQL já foi autorizado e atende o uso previsto sem custo adicional relevante. Pode ser reavaliado se o Docker não for viável.
- Neo4j: sem necessidade demonstrada.

## Pendências
- Confirmar se árvore com `parent_item_id` basta (medição com BOM sintético grande).
