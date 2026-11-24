# EngiFlow Connect — Design do agente local Windows

Status: **Proposta** (Fase 0). Implementação na Fase 4.

## Objetivo

Executar operações autorizadas em estações Windows (Solid Edge, Excel, pastas compartilhadas) sem expor portas de entrada na rede corporativa.

## Modelo de comunicação

- **Conexão iniciada pelo agente**, saindo por HTTPS para a API. Nenhuma porta de entrada.
- Fase inicial: **long polling autenticado**. WebSocket só com necessidade demonstrada (ADR-0007).
- Cada agente tem identidade própria: `device_id` + credencial de longa duração armazenada com proteção do Windows (DPAPI). O servidor guarda apenas o hash da credencial.
- Tokens de acesso de curta duração emitidos após registro e aprovação por administrador.

## Ciclo de vida

1. **Registro:** agente gera par de chaves local, envia pedido de registro; administrador aprova na UI; servidor emite credencial.
2. **Heartbeat:** a cada intervalo configurado, com versão do agente e capacidades declaradas.
3. **Descoberta de capacidades:** agente informa quais operações do catálogo suporta (ex.: Solid Edge instalado, versão). Servidor cruza com política aprovada.
4. **Recebimento de tarefa:** lease com `lease_token` e `lease_until`.
5. **Confirmação (ack):** agente confirma recebimento antes de executar.
6. **Execução:** somente operações do catálogo local, com parâmetros validados por schema.
7. **Resultado:** enviado com `lease_token`; servidor aceita somente se o token ainda for o da tentativa vigente.
8. **Revogação:** administrador revoga o dispositivo; próximo heartbeat recebe `401` e o agente para de processar.

## Garantias de execução

- **Execução única efetiva:** cada tarefa tem `attempt_no`. Resultado com token de tentativa anterior é descartado e registrado em auditoria.
- **Lease expirado:** tarefa volta à fila; operações devem ser idempotentes ou ter verificação de estado antes de repetir.
- **Cancelamento:** suportado apenas para operações que declaram essa capacidade.
- **Recuperação de falha:** agente persiste a tarefa em execução em disco local; ao reiniciar, reporta estado ao servidor antes de receber nova tarefa.
- **Logs locais:** rotação e retenção definidas; sem credenciais nos logs.

## Catálogo de operações (fechado)

Cada operação declara: código, versão, schema de parâmetros, pastas permitidas, efeito colateral (`read` ou `write`), necessidade de aprovação, timeout.

Exemplos iniciais (somente leitura):

| Código | Descrição | Efeito |
|---|---|---|
| `fs.list_authorized` | Lista arquivos em pasta autorizada | read |
| `fs.read_hash` | Calcula hash de arquivo autorizado | read |
| `se.open_assembly_readonly` | Abre montagem em modo somente leitura e extrai árvore | read |
| `se.extract_properties` | Extrai propriedades | read |
| `excel.read_range` | Lê intervalo de planilha autorizada | read |

Operações de escrita (`se.set_property`, `fs.write`) **não existem** até a fase de aprovação e verificação estar pronta.

## Controles de segurança do agente

- Sem execução de shell, sem `eval`, sem download e execução de código remoto.
- Caminhos normalizados e verificados contra allowlist (`Path.resolve()` + checagem de prefixo; bloqueio de junções/symlinks fora da área).
- Pastas autorizadas configuradas por administrador na API e recebidas pelo agente; o agente também mantém cópia local de políticas mínimas.
- Atualizações do agente assinadas; versão mínima imposta pelo servidor.
- Processo rodando com a conta do usuário, sem privilégio de administrador.

## Limitações conhecidas

- Solid Edge via COM pode exigir sessão interativa e um usuário logado. Agente como serviço Windows sem sessão pode não funcionar para esse conector.
- Automação COM pode abrir janelas e exigir licença ativa; comportamento a validar em estação real.
- Sem Solid Edge instalado na máquina de desenvolvimento atual, o conector real não pode ser testado aqui (ver `TEST_STRATEGY.md`).

## Estado

Toda a comunicação do agente está **planejada**. Nenhum código foi escrito.
