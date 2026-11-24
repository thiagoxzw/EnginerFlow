# ADR-0011 — Dados industriais confidenciais; repositório em `C:\Dev\EngiFlow`

- **Status:** Revisada (2026-11-24) — aguarda aprovação

## Decisão
1. Repositório Git em `C:\Dev\EngiFlow`, fora do OneDrive. Migração feita por cópia; o diretório original em `Documentos\engiflow` **não é apagado** até a validação da cópia pelo responsável.
2. Repositório privado no GitHub (criação do repositório remoto depende de autorização explícita no momento).
3. Dados reais ficam em pasta local **fora do repositório** (`C:\Dev\EngiFlow-dados`, sugerida), incluída no `.gitignore` por segurança.
4. Dados sintéticos, com prefixo `SYN-`, são os únicos versionados.
5. Nenhum arquivo real é enviado a serviço externo sem autorização.
6. Retenção: sem política automática. Mantemos histórico de importações, execuções e alterações, arquivos originais e backups locais. Limpeza de temporários é manual.

## Backups
Backup local manual do banco (`pg_dump`) e da pasta de dados, com comando documentado na Fase 1. Teste de restauração antes de depender do sistema.
