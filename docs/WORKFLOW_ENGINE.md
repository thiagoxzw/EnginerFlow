# EngiFlow — Motor de workflows

Status: **Proposta** (Fase 0). Implementação na Fase 6, após o núcleo de engenharia estar estável.

## Conceitos

- **Ferramenta (Tool):** unidade reutilizável registrada no catálogo central. É a única forma de executar capacidade de negócio; usada pela UI, workflows, API e IA sem duplicar regra.
- **Workflow:** grafo de nós conectados. Versões são imutáveis após publicação.
- **Run:** execução de uma versão, com passos (`step_runs`).

## Contrato de ferramenta

Cada ferramenta declara: identificador, nome, descrição, versão, schema de entrada, schema de saída, permissões exigidas, ambiente de execução (`server` ou `local-agent`), timeout, política de retentativa, efeitos colaterais (`none`, `read`, `write_internal`, `write_external`), necessidade de aprovação, compatibilidade com dry run.

Ferramentas com `write_external` só executam com aprovação registrada e dry run prévio quando suportado.

## Tipos de gatilho e de ação

Gatilhos e ações são os listados no prompt-mestre (seção 8.11). Ordem de entrega:

1. Fase 6a: execução manual, workflow linear, ferramentas de importação, cálculo e exportação.
2. Fase 6b: condições simples (ramificação com expressão validada), agendamento.
3. Fase 6c+: aprovação humana, eventos, webhooks autorizados, paralelismo — **somente após o executor estabilizar**.

## Garantias do executor

- **Idempotência:** cada passo tem chave `(run_id, node_key, attempt_no)`; ferramentas com efeito externo recebem `idempotency_key`.
- **Retentativas:** exponencial com teto, apenas para erros marcados como transitórios pela ferramenta.
- **Timeout:** por passo, definido na ferramenta e sobrescrível dentro do limite permitido.
- **Cancelamento:** cooperativo; marca `cancel_requested` e o executor verifica entre passos.
- **Recuperação:** run com lease expirado é retomado a partir do último passo concluído.
- **Execução parcial:** permitida apenas quando o passo declara que é segura para reexecução.
- **Validação antes da execução:** grafo acíclico, tipos de porta compatíveis, parâmetros obrigatórios presentes, permissões do usuário suficientes.
- **Logs por etapa:** entrada (hash ou referência), saída (referência), duração, erro, tentativa.

## Entradas e saídas tipadas

Portas têm tipo (`table`, `file_ref`, `bom_ref`, `number_decimal`, `text`, `boolean`, `json_schema:<nome>`). Conexão só é válida se os tipos forem compatíveis. Payloads grandes são armazenados como arquivo e passados por referência.

## Versionamento e templates

- Publicação gera `workflow_versions` imutável.
- Templates são workflows publicados copiáveis por organização; não são referenciados por runs antigos após edição.

## Aprovação humana

Passo `approval` cria registro em `approvals` vinculado ao alvo e à versão. O run fica em `waiting_approval` até decisão. Decisão sobre versão diferente da atual é rejeitada.

## Limites

- Número máximo de nós e de profundidade por versão (valores a definir).
- Limite de concorrência por organização.

## Fora de escopo inicial

Loops arbitrários, sub-workflows aninhados, código do usuário dentro de nós. Scripts livres não são permitidos.
