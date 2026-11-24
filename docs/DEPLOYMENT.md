# EngiFlow — Implantação e infraestrutura

Status: **Proposta** (Fase 0). Nada foi configurado.

## Estado do ambiente atual (verificado em 2026-11-24)

| Ferramenta | Situação |
|---|---|
| Git | presente |
| Python 3.14 | presente (fora do PATH da sessão; usar caminho completo ou `py`) |
| .NET SDK | presente |
| Node.js / npm | **ausente** — necessário para `apps/web` |
| Docker / Docker Compose | **ausente** — necessário para ambiente local, PostgreSQL e Redis |
| PostgreSQL | **ausente** |
| Solid Edge | **ausente** nesta máquina |

Instalação de Node.js, Docker e PostgreSQL altera o sistema e exige autorização do responsável pela máquina.

## Ambientes

| Ambiente | Propósito | Dados | Hospedagem |
|---|---|---|---|
| Development | desenvolvimento local | sintéticos | Docker Compose local |
| Testing | CI | sintéticos, efêmero | GitHub Actions (a confirmar) |
| Staging | homologação, validação de integrações | sintéticos ou autorizados | a definir |
| Production | uso real | real | a definir (on-premises, nuvem privada ou híbrido) |

A arquitetura não depende de um provedor de nuvem. Containers OCI e variáveis de ambiente são o contrato de implantação.

## Componentes de implantação

`web` · `api` · `worker` · `postgres` · `redis` · `minio` (ou S3-compatível) · `otel-collector` (opcional) · agente local instalado em estação (MSI ou pacote assinado — a definir).

## Health e readiness

- `GET /health/live`: processo ativo.
- `GET /health/ready`: banco, Redis e armazenamento acessíveis; migrações na versão esperada.
- Worker: heartbeat gravado em banco ou Redis.

## Procedimentos (a documentar com execução real)

Instalação · Configuração · Atualização · Backup · Restauração · Troubleshooting · Implantação · Rollback. **Nenhum destes procedimentos foi executado ainda**; serão escritos em `docs/operations` com os comandos testados.

## Configuração e segredos

- `.env.example` versionado, sem valores reais.
- Segredos em cofre ou variáveis protegidas do ambiente; nunca no repositório.
- Diferença entre ambientes apenas por variáveis e dados, não por código.

## CI/CD (GitHub Actions — proposta)

1. Lint (Ruff, ESLint).
2. Type check (MyPy, `tsc --noEmit` em modo strict).
3. Testes unitários e de integração (com PostgreSQL e Redis em serviço).
4. Verificação de migrações.
5. Validação de contrato OpenAPI.
6. Build de imagens.
7. Análise de dependências e de segredos.
8. E2E Playwright antes de release.

Deploy para staging e production: manual com aprovação; sem merge automático.

## Rollback

Imagem anterior versionada; migrações com `downgrade` testado ou plano de correção forward documentado por migração. Sem rollback de migração destrutiva sem backup verificado.

## Ligação com o repositório

O repositório está em `Documentos` dentro de pasta sincronizada pelo OneDrive. **Recomendação:** mover o repositório para fora da pasta sincronizada antes do primeiro commit, para evitar que arquivos de trabalho e histórico do Git sejam sincronizados e para reduzir o risco de vazamento de dados (ADR-0011).
