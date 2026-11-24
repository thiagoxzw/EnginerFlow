# EngiFlow — Modelo de ameaças (STRIDE resumido)

Status: **Proposta** (Fase 0). Revisar a cada fase que adicione superfície de ataque.

## Ativos

Dados industriais sensíveis; credenciais de integração; identidade de agentes; integridade de BOM aprovada; trilha de auditoria; disponibilidade do sistema.

## Superfícies

1. Interface web e API REST.
2. Upload de planilhas e arquivos.
3. Agente local (canal de saída, tarefas recebidas, arquivos locais).
4. Conectores de ERP e CAD.
5. Provedor de IA (envio de contexto).
6. Documentos ingeridos (conteúdo tratado como dado; risco de injeção de instrução).
7. Pipeline de CI/CD e dependências.

## Ameaças principais

| # | Ameaça | Categoria STRIDE | Superfície | Severidade inicial | Controle previsto | Status |
|---|---|---|---|---|---|---|
| T-01 | Usuário de outra organização acessa projeto alheio por ID | Information disclosure / EoP | API | Alta | Checagem por objeto + testes de IDOR + RLS | Planejado |
| T-02 | Planilha maliciosa com fórmula/macro ou zip bomb | DoS / Tampering | Upload | Alta | Limites, leitura segura, sem execução de macro | Planejado |
| T-03 | Caminho `../` ou symlink para ler arquivo fora da pasta autorizada | Information disclosure | Agente | Crítica | Normalização, allowlist, bloqueio de symlink | Planejado |
| T-04 | Backend envia comando arbitrário ao agente | EoP / Tampering | Agente | Crítica | Catálogo fechado, schema de parâmetros, sem shell | Planejado |
| T-05 | Tarefa executada duas vezes (lease expirado) | Tampering | Agente / jobs | Média | `attempt_no` + `lease_token` + idempotência | Planejado |
| T-06 | Resultado tardio de tarefa anterior sobrescreve o atual | Tampering | Agente | Média | Validação de token no resultado | Planejado |
| T-07 | Credencial de agente roubada de estação | Spoofing | Agente | Alta | DPAPI, revogação, token de curta duração, hash no servidor | Planejado |
| T-08 | Dado industrial vazado ao provedor de IA externo | Information disclosure | IA | Crítica | Política de dados, gateway, provedor local preferido | Planejado |
| T-09 | Documento técnico contém instrução que manipula o agente de IA (prompt injection) | Tampering / EoP | IA + documentos | Alta | Conteúdo é dado; ferramentas com permissão própria; aprovação para escrita | Planejado |
| T-10 | Modelo de IA inventa código, quantidade ou resultado de integração | Repudiation / integridade | IA | Alta | Cálculo determinístico, citação de evidência, IA sem permissão de escrita | Planejado |
| T-11 | Alteração de BOM aprovada sem rastreio | Repudiation | Revisões | Alta | Revisão imutável + auditoria + aprovação | Planejado |
| T-12 | Segredo de ERP em log ou repositório | Information disclosure | Logs / Git | Alta | Cofre, mascaramento, gitleaks no CI | Planejado |
| T-13 | SSRF via URL de integração | Information disclosure | API | Média | Allowlist de destinos, bloqueio de faixas privadas | Planejado |
| T-14 | Dependência comprometida | Tampering | Supply chain | Alta | Lock files, auditoria de vulnerabilidades | Planejado |
| T-15 | Escrita direta em CAD alterando binário de montagem e corrompendo arquivo | Tampering / Integridade | CAD | Crítica | Proibido por ADR-0005; leitura apenas | Planejado (proibição documentada) |
| T-16 | Escrita em banco de ERP | Tampering | ERP | Crítica | Proibido por ADR-0006 | Planejado (proibição documentada) |
| T-17 | Negação de serviço por importação gigante | DoS | Upload / worker | Média | Limites de tamanho/linhas, fila, limite de concorrência | Planejado |
| T-18 | Abuso de rota de login | Spoofing | Auth | Média | Rate limit, bloqueio progressivo | Planejado |

## Abuso de dados de referência

Dados de teste ou demonstração com aparência de dado real podem vazar. Mitigação: fixtures marcadas com prefixo `SYN-` e identificador de ambiente visível na UI.

## Revisão

- Revisar este modelo antes da Fase 4 (agente) e da Fase 7 (IA com ferramentas).
- Pentest externo antes de qualquer exposição fora da rede corporativa (pendente de decisão).
