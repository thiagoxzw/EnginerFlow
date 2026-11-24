# ADR-0012 — Escopo: aplicação de uso individual, local, extensível

- **Status:** Proposta para aprovação (2026-11-24)

## Decisão
- Um usuário, um computador, execução local. Sem exposição pública.
- **Fora do escopo agora:** multi-tenancy, organizações, workspaces, RBAC e papéis, convites, gestão de equipes, SSO, MFA corporativo, Entra ID, planos e cobrança, alta disponibilidade, balanceamento, infraestrutura distribuída, aprovações corporativas, políticas corporativas de retenção.
- **Autenticação:** a aplicação escuta somente em `127.0.0.1`. Se houver tela de acesso, é um login local simples com senha armazenada com Argon2id. Decisão final pendente da sua resposta.
- Arquitetura extensível sem módulos vazios: cada funcionalidade entra quando for usada.

## Consequências
Menos tabelas, menos código de segurança de organização, menos testes de isolamento. Os critérios CA-08 (isolamento) e a parte de RBAC do documento de segurança deixam de ser exigidos nesta fase.
