# EngiFlow — Estratégia de testes

Status: **Proposta** (Fase 0). Nenhum teste foi escrito.

## Pirâmide e tipos

| Tipo | Ferramenta | Escopo | Quando roda |
|---|---|---|---|
| Unitário (domínio) | Pytest | regras de BOM, quantidades, normalização, ciclos | cada PR |
| Unitário (front) | Vitest | componentes e validações Zod | cada PR |
| Integração (API + banco) | Pytest + PostgreSQL efêmero | repositórios, transações, RLS, migrações | cada PR |
| Contrato | Schemathesis ou testes gerados do OpenAPI; testes de conector | API e conectores mock × reais | cada PR; conectores reais sob demanda |
| Autorização / isolamento | Pytest dedicado | IDOR, multi-organização, RBAC por rota | cada PR (bloqueante) |
| Segurança | pip-audit, npm audit, gitleaks, SAST | dependências, segredos | cada PR |
| Processamento de arquivo | Pytest com fixtures | planilhas inconsistentes, zeros à esquerda, zip bomb, limites | cada PR |
| Concorrência | Pytest com processos paralelos | leases, idempotência, dupla execução | nightly |
| Recuperação de jobs | Pytest + kill de worker | retomada após falha | nightly |
| End-to-end | Playwright | fluxo MVP de 17 passos | antes de release |
| Regressão | suíte completa | todo o acima | antes de release |

## Fixtures sintéticas obrigatórias

Criadas a partir de geradores versionados em `tests/fixtures`, com prefixo `SYN-`:

- BOM multinível (4+ níveis, profundidade variável).
- BOM com referência circular.
- Materiais duplicados (mesmo código, descrições diferentes e iguais).
- Códigos com zeros à esquerda (`00123`, `0045`).
- Componentes compartilhados entre kits.
- Planilhas inconsistentes (cabeçalho deslocado, células mescladas, texto em número, linhas vazias, encodings mistos).
- Kits (incluindo kit não encontrado no documento de referência).
- Estoque insuficiente e estoque reservado.
- Revisões divergentes.
- Documentos técnicos sintéticos (PDF com tabela ambígua).
- Falhas de comunicação com agente (timeout, lease expirado, resultado tardio, revogação).

Nenhum arquivo derivado de dados reais entra em `tests/fixtures`.

## Oráculos de cálculo

Quantidades acumuladas são verificadas contra um **cálculo de referência independente** escrito de forma simples (força bruta sobre caminhos) e comparado com a implementação otimizada. Divergência reprova.

## Conectores reais

Solid Edge e Protheus **não são testáveis** na máquina atual (sem Solid Edge e sem acesso ao ERP). Esses testes ficam marcados como `@pytest.mark.requires_solidedge` / `requires_protheus` e executam apenas em estação ou ambiente de homologação autorizados. Até lá, o status desses conectores é "Simulado" ou "Pendente de homologação", nunca "Testado".

## Ambientes

Development (local) · Testing (CI, banco efêmero) · Staging (homologação, dados sintéticos ou autorizados) · Production (sem testes destrutivos).

## Métricas de qualidade

- Cobertura: reportada, sem meta fixa nesta fase. Caminhos de domínio e autorização devem ter cobertura de ramos alta; a meta numérica será definida após a primeira linha de base.
- Zero teste bloqueante ignorado (`skip`/`xfail`) sem issue associada.

## Critério de "testado"

Uma funcionalidade só é classificada como **Testada** quando há teste automatizado que passa em CI e a execução foi observada. Teste manual isolado não conta.
