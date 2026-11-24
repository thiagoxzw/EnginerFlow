# EngiFlow — Design de sistema (sequências)

Status: **Proposta** (Fase 0).

## 1. Importação de planilha (síncrona para arquivos pequenos, assíncrona para grandes)

```mermaid
sequenceDiagram
  autonumber
  participant U as Usuário (web)
  participant API as API
  participant OBJ as Armazenamento
  participant W as Worker
  participant DB as PostgreSQL
  U->>API: POST /api/v1/materials/import (multipart, Idempotency-Key)
  API->>API: valida tamanho, extensão, tipo real (magic bytes), permissão
  API->>OBJ: grava original com nome gerado (sem nome do usuário)
  API->>DB: cria import_job (status=queued, sha256)
  API-->>U: 202 + job_id
  W->>DB: lease do job (SELECT ... FOR UPDATE SKIP LOCKED)
  W->>W: lê com OpenPyXL/Pandas em modo somente-leitura, colunas como texto
  W->>DB: transação: grava linhas normalizadas + registros de duplicidade
  W->>DB: audit_log + job_attempt(status=succeeded)
  U->>API: GET /api/v1/jobs/{id} (polling)
  API-->>U: resultado + contagens + erros por linha
```

## 2. Expansão de BOM e cálculo por chassi

```mermaid
sequenceDiagram
  participant U as Usuário
  participant API as API
  participant D as Motor de BOM (domínio puro)
  participant DB as PostgreSQL
  U->>API: POST /api/v1/boms/explode {bom_revision_id, chassis_qty: [1,10,50]}
  API->>DB: carrega itens da revisão (filtrado por organization_id)
  API->>D: explode(itens, regras do projeto)
  D->>D: detecta ciclo (DFS) → erro se houver
  D->>D: quantidades acumuladas em Decimal
  D-->>API: árvore + totais por componente + por kit
  API->>DB: cruza com inventory_snapshot (regra de reserva do projeto)
  API-->>U: necessidade, disponível, falta, excedente por N chassis
```

Cálculo é função determinística de domínio, testada com fixtures; IA não participa.

## 3. Comunicação com agente local (polling com lease)

```mermaid
sequenceDiagram
  participant AG as Agente local
  participant API as API
  participant DB as PostgreSQL
  AG->>API: POST /api/v1/agents/heartbeat (token do dispositivo)
  API-->>AG: 200 + política (versão mínima, pastas autorizadas)
  AG->>API: GET /api/v1/agents/tasks/next (long polling)
  API->>DB: atribui tarefa com lease_until e lease_token
  API-->>AG: task (id, operação do catálogo, parâmetros validados)
  AG->>AG: valida operação e parâmetros localmente
  AG->>API: POST /api/v1/agents/tasks/{id}/ack
  AG->>AG: executa operação permitida
  AG->>API: POST /api/v1/agents/tasks/{id}/result (lease_token)
  API->>DB: grava resultado somente se lease_token confere
```

Se o lease expirar sem resultado, a tarefa volta a `queued` com novo `attempt`; resultados tardios com token antigo são rejeitados (ver `LOCAL_AGENT_DESIGN.md`).

## 4. Workflow (execução linear)

```mermaid
sequenceDiagram
  participant API as API
  participant W as Worker
  participant DB as PostgreSQL
  API->>DB: workflow_run(status=queued) + step_runs (pendentes)
  W->>DB: lease do run
  loop cada passo em ordem
    W->>DB: step_run=running
    W->>W: executa ferramenta do catálogo (timeout, retentativa)
    W->>DB: step_run=succeeded|failed + saída (referência, não payload gigante)
  end
  W->>DB: run=succeeded|failed|waiting_approval
```

## 5. Limites de execução

| Operação | Síncrona | Assíncrona |
|---|---|---|
| Consulta de projeto/BOM pequena | sim | — |
| Importação de arquivo | até limite definido em `DEPLOYMENT.md` | acima do limite |
| Exportação | arquivos pequenos | sempre |
| Varredura de pasta autorizada | — | sempre (agente) |

Limites numéricos de tamanho e tempo: **a definir** após teste de carga com volume real.
