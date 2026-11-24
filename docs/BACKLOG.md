# EngiFlow — Backlog priorizado (Fase 0 → Fase 3)

Prioridade: P0 (bloqueia o MVP) · P1 (necessário ao MVP) · P2 (desejável) · P3 (futuro). Tamanho em pontos relativos (P=pequeno, M=médio, G=grande).

## Fase 1 — Foundation

| ID | Item | Prioridade | Tamanho | Critério de aceitação |
|---|---|---|---|---|
| F1-01 | Criar monorepo com estrutura da seção 7 do prompt | P0 | P | estrutura existe; README e CHANGELOG |
| F1-02 | Definir gerenciadores de pacote (uv para Python, pnpm para TS) e lock files | P0 | P | instalação reprodutível em máquina limpa |
| F1-03 | Docker Compose: PostgreSQL, Redis, MinIO | P0 | M | `compose up` sobe serviços com health check |
| F1-04 | Backend FastAPI com health/readiness e log estruturado | P0 | M | testes de health; logs sem segredos |
| F1-05 | Migrações Alembic e primeira migração (organizations, users, memberships, roles, permissions) | P0 | M | upgrade/downgrade testados no CI |
| F1-06 | Autenticação (sessão + Argon2id) | P0 | M | testes de login, bloqueio, expiração |
| F1-07 | RBAC e verificação por objeto | P0 | M | testes de autorização por rota |
| F1-08 | Testes de isolamento multiorganização (IDOR) | P0 | M | CA-08 passando |
| F1-09 | Auditoria básica (audit_logs append-only) | P0 | M | registros com correlação; sem segredos |
| F1-10 | Frontend Next.js strict com layout, navegação, tema claro/escuro | P0 | M | build, lint, typecheck e teste de componente |
| F1-11 | Cliente de API gerado do OpenAPI | P1 | P | contrato validado no CI |
| F1-12 | Dashboard inicial com dados reais (mesmo que zerados) | P1 | P | sem números fictícios fora de demo |
| F1-13 | CI: lint, tipos, testes, migrações, dependências, segredos | P0 | M | pipeline verde em PR de exemplo |
| F1-14 | Documentação operacional inicial (instalação, configuração) | P1 | P | comandos executados e registrados |
| F1-15 | Mover repositório para fora do OneDrive (ver ADR-0011) | P0 | P | decisão registrada e executada |

## Fase 2 — Data Studio

| ID | Item | Prioridade | Tamanho |
|---|---|---|---|
| F2-01 | Upload com validação, hash SHA-256 e armazenamento seguro | P0 | M |
| F2-02 | Leitura Excel/CSV com colunas como texto (CA-01) | P0 | M |
| F2-03 | Seleção de aba e detecção de cabeçalho | P0 | M |
| F2-04 | Mapeamento de colunas salvo como template | P0 | M |
| F2-05 | Normalização de texto com regra versionada | P0 | M |
| F2-06 | Detecção de duplicatas exatas e aproximadas com evidência | P0 | G |
| F2-07 | Filtros, ordenação, comparação de arquivos | P1 | M |
| F2-08 | Exportação Excel/CSV | P0 | M |
| F2-09 | Histórico de operações e desfazer (dados internos) | P1 | M |

## Fase 3 — Engineering Core

| ID | Item | Prioridade | Tamanho |
|---|---|---|---|
| F3-01 | Projetos com configurações (políticas de reserva e kit) | P0 | M |
| F3-02 | Materiais com códigos por fonte e unicidade | P0 | M |
| F3-03 | Importação de BOM e validação de ciclos (I-01) | P0 | G |
| F3-04 | Motor de explosão de BOM com Decimal (CA-02, CA-03) | P0 | G |
| F3-05 | Agrupamento por kit e cálculo por chassi (CA-06) | P0 | M |
| F3-06 | Classificação por regras + revisão humana (CA-05) | P0 | M |
| F3-07 | Importação de saldo e cálculo de faltas (CA-07) | P0 | M |
| F3-08 | Relatórios e exportações (CA-09) | P0 | M |
| F3-09 | Histórico de execução (CA-10) e idempotência (CA-12) | P0 | M |
| F3-10 | Revisões imutáveis e comparação (Fase 3 completa) | P1 | G |
| F3-11 | Exportação em layout configurável para ERP (sem validação real) | P1 | M |
| F3-12 | Job assíncrono para importação grande (leases, retentativa) | P0 | G |

## Itens bloqueados por dependência externa

| ID | Item | Bloqueio |
|---|---|---|
| X-01 | Conector Solid Edge real | licença/versão, estação com Solid Edge, sessão interativa |
| X-02 | Conector Protheus API | endpoint e credencial de homologação autorizados |
| X-03 | Provedor de IA externo | aprovação de política de dados e contrato |
| X-04 | Modelo local (Ollama) | hardware definido |
| X-05 | SSO corporativo | definição do provedor de identidade |
| X-06 | Hospedagem de produção | decisão de infraestrutura |

## Itens que dependem de decisão de negócio

Layouts de importação e exportação reais; regra de kit comprado × componentes; regra de reserva de estoque; classificação de componentes (categorias oficiais). **Nenhum deles deve virar constante no código.**
