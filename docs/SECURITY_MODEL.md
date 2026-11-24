# EngiFlow — Modelo de segurança

Status: **Proposta** (Fase 0). Controles listados são **requisitos**, não controles implementados.

## 1. Classificação de dados

| Classe | Exemplos | Regra |
|---|---|---|
| Industrial sensível | BOM real, preços, estoque, código de fornecedor, desenhos | Não sai do ambiente corporativo sem autorização; não usar em repositórios públicos |
| Credencial | senhas, tokens, chaves de API, credenciais ERP | Nunca em logs, banco em texto ou repositório; cofre de segredos |
| Pessoal | nome, e-mail, login de usuário | Mínimo necessário; log sem dado pessoal desnecessário |
| Sintético | fixtures de teste | Único tipo permitido em repositório e em serviços externos |

**Dados reais da empresa não entram no repositório.** Fixtures são construídas a partir do formato, não do conteúdo.

## 2. Autenticação

- Senhas com Argon2id; política mínima de tamanho; bloqueio progressivo.
- SSO corporativo (Entra ID / Azure AD, Google Workspace ou outro) **pendente de decisão**. Quando disponível, é a forma preferida.
- Sessão com cookie `HttpOnly`, `Secure`, `SameSite=Lax`; expiração e rotação de ID de sessão no login.
- MFA recomendado para administradores; obrigatório quando houver SSO corporativo com MFA.

## 3. Autorização (RBAC + verificação por objeto)

- Permissões são códigos (`projects.read`, `boms.import`, `agents.approve`, `ai.use`, `integrations.write_external`).
- Papéis são coleções de permissões por organização.
- **Toda operação** verifica permissão **e** pertencimento do recurso à organização do usuário. Verificação em camada de aplicação, não apenas na rota.
- Operações de escrita em sistemas externos exigem permissão específica **e** aprovação registrada.
- Menor privilégio: contas de serviço e agentes recebem apenas o catálogo aprovado.

## 4. Proteções web

| Ameaça | Controle |
|---|---|
| SQL injection | Somente ORM/parâmetros; proibido SQL livre; lint de SQL concatenado |
| XSS | Escape padrão do React; sem `dangerouslySetInnerHTML` sem sanitização; CSP restritiva |
| CSRF | Cookie `SameSite` + token CSRF em métodos não seguros |
| IDOR | Checagem de organização e permissão em cada acesso por ID; teste automatizado por rota |
| Clickjacking | `frame-ancestors 'none'` |
| Headers | HSTS, `X-Content-Type-Options`, `Referrer-Policy` |

## 5. Uploads e arquivos

- Limite de tamanho por tipo (valores a definir; começar em dezenas de MB para planilhas).
- Validação de tipo por conteúdo (magic bytes), não só extensão.
- **Armazenamento com nome gerado**; nome original apenas como metadado, sanitizado.
- **Proteção contra zip bomb e arquivos compactados maliciosos:** limite de razão de descompressão, número de entradas e profundidade; leitura de `.xlsx` com limites de linhas e células.
- Caminhos: proibido `..`, caminhos absolutos e symlinks fora da área; normalização antes de qualquer uso.
- Varredura antimalware do arquivo antes do processamento (ferramenta a definir).

## 6. SSRF

- Nenhuma URL fornecida pelo usuário é buscada pelo servidor, exceto lista explícita de destinos de integração configurados por administrador.
- Bloqueio de faixas privadas e metadados de nuvem quando houver busca de URL.

## 7. Segredos e criptografia

- Segredos de integração armazenados cifrados (AES-GCM) com chave fora do banco (cofre ou variável protegida); rotação documentada.
- HTTPS obrigatório fora de desenvolvimento local.
- Credencial de agente: armazenada no Windows com DPAPI; servidor guarda somente hash.

## 8. Auditoria

- Registro de: usuário, organização, operação, recurso, valores anteriores e posteriores (campos sensíveis mascarados), origem, correlação, resultado, aprovações, erros.
- Log append-only para a aplicação; sem permissão de UPDATE/DELETE na tabela.
- **Nunca** registrar senha, token, chave, cabeçalho `Authorization` ou conteúdo integral de planilha.

## 9. Backups e recuperação

- Backup diário do PostgreSQL com retenção definida (pendente) e backup do armazenamento de arquivos.
- Teste de restauração **obrigatório** antes do primeiro uso produtivo; resultado registrado.
- RPO e RTO: **a definir** com a diretoria de TI.

## 10. Dependências e cadeia de suprimento

- Lock files commitados; atualização controlada.
- Análise de vulnerabilidades no CI (pip-audit, npm audit ou equivalente, SAST).
- Verificação de segredos no CI (ex.: gitleaks) em cada PR.
- Versões estáveis; dependências adicionais justificadas em ADR ou PR.

## 11. Gestão de IA e dados

Ver `AI_ARCHITECTURE.md` e ADR-0009. Resumo: provedor externo só recebe dados sintéticos ou dados explicitamente autorizados por política; prompts e respostas são auditados.

## 12. Controles adicionais para operações destrutivas ou em sistemas externos

Exigidos: confirmação explícita com resumo do impacto, dry run quando suportado, backup antes da alteração, aprovação registrada com versão do alvo, verificação posterior e registro em auditoria.

## Estado dos controles

| Controle | Status |
|---|---|
| Todos acima | Planejado |
| Auditoria, RBAC, IDOR, upload, SSRF, criptografia de segredos | Planejado, a implementar na Fase 1 e obrigatórios antes de qualquer piloto |
