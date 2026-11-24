# ADR-0007 — Agente local: processo iniciado manualmente na sessão do usuário, sem polling remoto

- **Status:** Revisada (2026-11-24) — aguarda aprovação
- **Substitui:** "agente com polling HTTPS e leases de tarefa"

## Contexto
Aplicação de uso individual, executada no mesmo computador do agente. Não há servidor remoto que precise receber conexões de estações. O agente só precisa rodar com a sessão do usuário logado.

## Decisão
- O agente (`apps/local-agent`) é um processo Python iniciado manualmente, na sessão Windows do usuário.
- Comunica-se com a API **somente em `127.0.0.1`**, com token local gerado na instalação e guardado no perfil do usuário.
- Catálogo fechado de operações (leitura de pasta autorizada, leitura de propriedades Solid Edge, leitura de planilha). Sem shell, sem execução de comando recebido.
- Pastas autorizadas definidas em arquivo de configuração local do usuário.
- Sem leases e sem fila distribuída: a API chama a operação e aguarda resultado; se o agente não estiver rodando, a API informa "agente indisponível".
- Escrita em CAD só com a regra da ADR-0005.

## Não fazer agora
Serviço Windows permanente, registro de múltiplas estações, WebSocket, polling remoto, atualização automática assinada.

## Gatilho para revisão
Uso em outra máquina ou em mais de uma estação (então reavaliar autenticação e transporte).
