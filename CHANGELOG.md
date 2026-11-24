# Changelog

Formato: Keep a Changelog. Versionamento: Semantic Versioning (ainda sem versão publicada).

## [Unreleased]

### Adicionado
- Fase 0: documentação de visão, PRD, arquitetura e decisões (ADR-0001 a ADR-0012), revisadas para uso individual.
- Fase 1 (em verificação): backend FastAPI com health e readiness; login de usuário único com sessão em cookie HttpOnly; logout; auditoria de login e logout; dashboard com dados reais; erros em Problem Details; correlação de requisições; migração inicial; frontend Next.js com login e dashboard; `docker-compose.yml` com PostgreSQL; CI no GitHub Actions.

### Corrigido (verificação adicional da Fase 2A)
- Cabeçalhos gerados nunca colidem com nomes existentes; comparação sem diferença de caixa.
- Detecção de cabeçalho: primeira linha plausível, não a mais preenchida.
- Descrições idênticas com tokens frequentes são comparadas.
- Teto de candidatos aplicado durante a geração (pior caso: 371 MB para 37 MB), também na comparação por zeros.
- Especificações técnicas preservadas (símbolos, vírgula decimal, unidades); pares com especificação diferente nunca são equivalentes.
- Testes de concorrência e reinício usam o banco configurado (PostgreSQL no CI).
- `.gitignore` cobre CAD, bancos locais, armazenamento e segredos.

### Corrigido (revisão técnica da Fase 2)
- Comparação por zeros à esquerda: nenhum candidato perdido (várias variantes, chaves em ambos os lados, códigos só de zeros). A API não corta mais as listas.
- Importação em streaming: arquivo lido do disco linha a linha e gravado em lotes.
- Similaridade de descrições independente da ordem dos termos e da pontuação.
- Consistência arquivo x transação: escrita temporária, rollback e remoção do arquivo órfão.
- Leitura XLSX por handle (não depende da extensão do arquivo).

### Adicionado (Fase 2 — Data Studio)
- Exportação de tabela, duplicatas e comparação em CSV e XLSX, com códigos como texto.
- Script de medição `apps/api/scripts/bench_data_studio.py` (manual, fora do CI).
- Importação de CSV e XLSX com detecção de delimitador, encoding (UTF-8 e Windows-1252), aba e cabeçalho.
- Códigos como texto, com zeros à esquerda preservados; aviso quando o Excel já converteu códigos em número.
- Mapeamento de colunas para campos canônicos, validado e auditado.
- Duplicatas exatas de código, sugestões de zeros à esquerda e descrições semelhantes com score e evidência. Nenhuma fusão automática.
- Comparação de códigos entre duas tabelas.
- Proteções: limites de tamanho, linhas e colunas; validação por assinatura; proteção contra zip bomb.
- Interface em `/data-studio`.

### Alterado
- CI: `actions/checkout` v4 → v6, `astral-sh/setup-uv` v6 → v7, `actions/setup-node` v4 → v6 e `pnpm/action-setup` v4 → v6. As novas versões rodam em Node 24, eliminando o aviso de depreciação do Node 20. Parâmetros mantidos (cache do uv, `cache-dependency-glob`, `version` do pnpm, cache do pnpm). Node 22 do build web e comandos de teste inalterados.

### Pendente de verificação
- Execução contra PostgreSQL real (bloqueada: Docker sem virtualização habilitada nesta máquina).
