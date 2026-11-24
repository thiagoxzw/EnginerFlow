# ADR-0001 — Aplicação modular em um único processo backend

- **Status:** Revisada (2026-11-24) — aguarda aprovação
- **Substitui:** versão anterior "monólito modular com workers e agente"

## Contexto
Uso individual, local, em um único computador. Não há necessidade de escalar horizontalmente nem de separar processos por domínio.

## Decisão
- Um único processo backend (FastAPI) que serve a API e executa o domínio.
- Frontend Next.js rodando localmente, conversando com a API em `127.0.0.1`.
- Módulos internos organizados por pacote (`domain`, `application`, `infrastructure`, `presentation`), sem dependência de framework no domínio.
- Processamento longo executado em thread/processo interno com estado no banco (ver ADR-0004).
- Agente Windows continua como processo separado, pois precisa rodar na sessão interativa (ADR-0007).

## Não fazer agora
Microsserviços, workers distribuídos, balanceamento, alta disponibilidade.

## Gatilho para revisão
Necessidade real de execução concorrente pesada que o processo único não atenda, medida nos testes.
