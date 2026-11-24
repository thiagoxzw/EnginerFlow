# Revisão da Fase 0 — direcionamento de uso individual

Data: 2026-11-24. Este documento registra as respostas do responsável e o que mudou.

## Respostas incorporadas

| Tema | Decisão |
|---|---|
| Uso | Individual, local, para uso diário e validação de viabilidade |
| Hospedagem | Local agora; arquitetura preparada para servidor interno futuro, sem implementar |
| Ferramentas | Autorizado instalar Node.js LTS, Python, Git, Docker Desktop, WSL 2 e dependências; PostgreSQL e Redis via Docker. **Instalação pendente: sem acesso de administrador** |
| Repositório | GitHub privado; migrar para `C:\Dev\EngiFlow`; preservar original até validar |
| Autenticação | Simples e segura, somente se necessária; sem SSO/MFA; sem exposição pública |
| Usuários | Um usuário; sem RBAC, convites, organizações, planos |
| CAD | Versão e licença pendentes; conectores simulados; agente em sessão interativa iniciado manualmente |
| ADR-0005 | Scripts atuais como operação manual; alterações com confirmação manual |
| Protheus | XLSX/CSV manual com mapeamento, delimitador, encoding e zeros à esquerda; API não bloqueia |
| Kits | Política configurável com quatro modos: adquirido integralmente, adquirido por componentes, agrupamento, indefinido |
| Estoque | Físico, reservado, bloqueado, disponível, por filial, por armazém, data; desconhecido ≠ zero |
| Classificação | Hierarquia configurável (categoria, família, subfamília, classe, subclasse, material); validação manual |
| Unidades | Suporte a unidades; conversão só com fator validado |
| Dados | Confidenciais; dados sintéticos no desenvolvimento |
| IA | Complementar; interface para OpenAI, Anthropic, Gemini e Ollama; não implementar todos |
| Retenção | Histórico, originais, backups locais; limpeza manual |
| Metas | Um usuário; sem SLA; limites de teste: 100 MB, 500 mil linhas, 100 mil ocorrências (metas, não capacidades) |
| Ordem | Fundação simplificada → interface → Data Studio → BOM → Materiais → Classificação → Protheus → Estoque → Agente → Solid Edge → CAD×ERP → relatórios → workflow → Document Center → Copilot |

## ADRs alteradas

| ADR | Situação |
|---|---|
| 0001 monólito modular | Revisada: um processo backend |
| 0002 PostgreSQL | Revisada: sem organization_id nem RLS |
| 0003 stack | Mantida |
| 0004 jobs | Revisada: sem Celery/Redis por enquanto |
| 0005 CAD | Revisada: confirmação manual, sem aprovação corporativa |
| 0006 ERP | Revisada: importação manual de XLSX/CSV |
| 0007 agente | Revisada: processo local manual, sem polling |
| 0008 decimal/texto | Mantida |
| 0009 IA | Revisada: complementar |
| 0010 ferramentas | Revisada: instalação pendente de administrador |
| 0011 dados/repositório | Revisada: C:\Dev\EngiFlow |
| 0012 escopo individual | Nova |

## Documentos que ainda descrevem o escopo corporativo

Os documentos abaixo ainda citam multi-tenancy, RBAC, SSO, MFA ou infraestrutura corporativa. Eles serão atualizados na primeira passagem da Fase 1, e até lá **as ADRs prevalecem**:

- `PRD.md` (CA-08, requisitos de isolamento e NFRs)
- `ARCHITECTURE.md`, `SYSTEM_DESIGN.md`
- `DATABASE_SCHEMA.md` (organization_id, RLS)
- `API_CONTRACTS.md` (organizações, membros, agentes com token)
- `SECURITY_MODEL.md`, `THREAT_MODEL.md` (partes de RBAC e multiorganização)
- `LOCAL_AGENT_DESIGN.md` (polling e leases)
- `DEPLOYMENT.md` (ambientes corporativos)
- `ROADMAP.md`, `BACKLOG.md` (itens F1-06, F1-07, F1-08 mudam de escopo)

## Bloqueios atuais

1. Instalação de Node.js, Docker Desktop, WSL 2: aguarda acesso administrativo.
2. Criação do repositório GitHub: aguarda autorização para criar recurso remoto.
3. Solid Edge: versão e licença pendentes.
