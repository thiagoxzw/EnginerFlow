# Revisão de segurança do repositório público

Data: 2026-11-24. Escopo: todos os arquivos versionados no HEAD e todas as referências do histórico (`git log --all`). Método: busca por extensões, padrões de credencial e termos de risco. **Nenhum conteúdo sensível foi copiado para este documento**: apenas caminhos, contagens e categorias.

## Resultado

| Verificação | Resultado |
|---|---|
| Arquivos de dados tabulares (XLSX, XLS, CSV) versionados | **nenhum** no HEAD e no histórico |
| Arquivos CAD (ASM, PAR, PSM, DFT, prt, etc.) | nenhum |
| Bancos locais (DB, SQLite) e backups | nenhum |
| Arquivos de configuração com segredos (`.env`, chaves, PEM, PFX) | apenas `.env.example`, com nomes de variáveis e valores de desenvolvimento |
| Padrões de credencial (tokens GitHub, chaves AWS, chaves privadas, tokens Slack, chaves Google e OpenAI) no histórico | **0 ocorrências** em todos os padrões verificados |
| Termos de arquivos reais da empresa (nomes de projetos internos, nomes de pastas de trabalho, sigla de organização) | **0 ocorrências** |
| Termos genéricos de sistemas (ERP, CAD, nomes de produtos) | presentes em documentação de arquitetura, sem dados |
| E-mails em arquivos | apenas domínios de exemplo (`example.com`) em testes |
| Identidade de autor dos commits | **exposição (ver abaixo)** |
| Artefatos e logs do CI | nenhum artefato é enviado; logs de teste contêm apenas dados sintéticos |

## Achados

### 1. Identidade de autor no histórico (exposição, requer decisão)

Os commits da branch foram feitos com o e-mail pessoal do responsável. Como o repositório é público, esse endereço fica visível em todos os commits. **Não foi alterado**: reescrever o histórico exige autorização explícita.

Opções para decidir:
- (a) manter como está;
- (b) ativar, nas configurações pessoais do GitHub, a opção de manter o e-mail privado, e usar o endereço `noreply` do GitHub nos próximos commits (sem reescrever o histórico);
- (c) reescrever o histórico com `git filter-repo` para substituir o autor (exige autorização, força o push e invalida referências a commits antigos).

Recomendação: (b) agora, e (c) apenas se o responsável considerar a exposição do endereço inaceitável.

### 2. Credenciais de desenvolvimento no repositório (aceitável, documentado)

- `docker-compose.yml` usa a senha `engiflow-dev-only` como padrão para o PostgreSQL local, bindado em `127.0.0.1`.
- `.github/workflows/ci.yml` usa `ci-only-password` no serviço PostgreSQL efêmero do CI.

Ambas são senhas de serviço descartável, sem acesso a sistemas reais. Não são segredos de produção. Mantidas, com a observação de que nenhuma credencial real pode ser usada nesses arquivos.

### 3. Documentação com contexto de negócio (revisar)

Os documentos de produto e roadmap mencionam o cenário de referência com contagens agregadas (quantidade de kits e de peças), derivadas do prompt de planejamento. São números agregados, sem nomes de peças, fornecedores ou valores. Mantidos, mas o responsável pode decidir removê-los antes de tornar o repositório público definitivo.

### 4. Proteções adicionadas

O `.gitignore` agora bloqueia extensões de CAD (ASM, PAR, PSM, DFT, PRT, SLDPRT, SLDASM, IPT, IAM, DWG, STEP, STP), bancos locais (DB, SQLITE, SQLITE3), backups, pastas de armazenamento (`originals/`, `data/`), arquivos compactados e arquivos de segredos (`.env.local`, PFX, P12, `secrets.*`).

## Recomendações contínuas

- Manter dados reais fora do repositório (ADR-0011).
- Antes de cada PR, rodar uma varredura de padrões de credencial (lista acima) e revisar novos arquivos de dados.
- Considerar a ativação do *secret scanning* do GitHub, disponível em repositórios públicos.
