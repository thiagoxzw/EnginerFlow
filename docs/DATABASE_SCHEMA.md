# EngiFlow — Modelo inicial de banco (PostgreSQL)

Status: **Proposta** (Fase 0). Nenhuma migração foi criada. Migrações Alembic começam na Fase 1.

## Convenções

- Chaves primárias `uuid` (gerado no servidor). Identificadores humanos são colunas separadas.
- Toda tabela de negócio tem `organization_id uuid NOT NULL` com FK para `organizations`.
- Timestamps `timestamptz` em UTC: `created_at`, `updated_at`. Tabelas versionadas têm `version integer` para controle otimista.
- Códigos de material: `text`, nunca numérico.
- Quantidades: `numeric(18,6)`.
- Hashes de arquivo: `bytea` ou `char(64)` (SHA-256 hex).
- Soft delete apenas onde o domínio exige; exclusão física proibida em revisões aprovadas e em auditoria.
- Índices únicos incluem `organization_id`.

## Tabelas (entidades pedidas no prompt-mestre)

| Tabela | Chave principal de negócio | Observações |
|---|---|---|
| `organizations` | `slug` único | sem `organization_id` (raiz) |
| `users` | `email` único (citext) | senha: hash Argon2id ou SSO, nunca texto |
| `memberships` | (`organization_id`, `user_id`) único | papel por organização |
| `roles` | (`organization_id`, `name`) | papéis customizáveis |
| `permissions` | `code` único global | catálogo fixo de permissões |
| `role_permissions` | (`role_id`, `permission_id`) | |
| `projects` | (`organization_id`, `code`) | `settings jsonb` validado por schema (regras do projeto) |
| `materials` | (`organization_id`, `internal_code`) | `description`, `normalized_description`, `category_id`, `unit` |
| `material_codes` | (`organization_id`, `source_system`, `code`) único | código ERP/CAD/fabricante |
| `material_categories` | (`organization_id`, `path`) | árvore via `parent_id` |
| `boms` | (`project_id`, `name`) | |
| `bom_revisions` | (`bom_id`, `revision_label`) | `status` (draft, approved, superseded), `approved_by`, `approved_at`; imutável após aprovação (trigger) |
| `bom_items` | (`bom_revision_id`, `parent_item_id`, `position`) | `quantity numeric(18,6)`, `unit`, `kind` |
| `bom_item_edges` | — | adiado: avaliar se árvore com `parent_item_id` basta (ver ADR-0002) |
| `inventory_snapshots` | (`project_id`, `as_of`, `source`) | |
| `inventory_items` | (`snapshot_id`, `material_id`, `branch`, `warehouse`) | `available`, `reserved` numeric |
| `documents` | (`organization_id`, `title`, `doc_type`) | |
| `document_revisions` | (`document_id`, `revision_label`) | aponta para `files` |
| `files` | `sha256` por organização | `storage_key` gerado, `original_name` apenas como metadado |
| `connections` | (`organization_id`, `name`) | configurações de integração; segredos fora da tabela (referência a cofre) |
| `agents` | (`organization_id`, `device_id`) | `status`, `last_seen_at`, `token_hash` |
| `agent_capabilities` | (`agent_id`, `operation_code`) | catálogo declarado pelo agente e aprovado pelo admin |
| `jobs` | `id` | `kind`, `status`, `payload_hash`, `idempotency_key` único por org |
| `job_attempts` | (`job_id`, `attempt_no`) | `lease_token`, `lease_until`, `worker_id`, `result` |
| `workflows` | (`organization_id`, `name`) | |
| `workflow_versions` | (`workflow_id`, `version`) | imutável após publicação |
| `workflow_nodes` | (`workflow_version_id`, `node_key`) | |
| `workflow_runs` | `id` | referencia `workflow_version_id` |
| `workflow_step_runs` | (`run_id`, `node_key`, `attempt_no`) | |
| `approvals` | `id` | `target_type`, `target_id`, `target_version`, `decision`, `decided_by` |
| `notifications` | `id` | `user_id`, `read_at` |
| `audit_logs` | `id bigserial` | append-only; sem UPDATE/DELETE por role da aplicação |
| `classification_rules` | (`organization_id`, `name`, `version`) | regras versionadas |
| `matching_rules` | (`organization_id`, `name`, `version`) | |
| `import_templates` | (`organization_id`, `name`) | mapeamento reutilizável |
| `export_templates` | (`organization_id`, `name`) | layout ERP configurável |

## Restrições críticas

- **Ciclo em BOM:** validado na aplicação (DFS antes de gravar) e garantido por teste. Constraint de banco sozinha não resolve grafo genérico; trigger de detecção fica como opção avaliada (ADR-0002).
- **Revisão aprovada imutável:** trigger `BEFORE UPDATE/DELETE` em `bom_items` quando `bom_revisions.status = 'approved'`.
- **Unicidade de código por fonte:** `UNIQUE (organization_id, source_system, code)` em `material_codes`.
- **Isolamento:** `ROW LEVEL SECURITY` ativado em tabelas de negócio com política `organization_id = current_setting('app.organization_id')::uuid`. A aplicação define a variável por transação. RLS é camada adicional; a checagem de autorização continua na aplicação.

## Concorrência

- Controle otimista via `version` em projetos, BOMs e materiais.
- Leases de job via `SELECT ... FOR UPDATE SKIP LOCKED` ou atualização condicional de `lease_token`.
- Idempotência por `idempotency_key` com índice único (`organization_id`, `idempotency_key`).

## Retenção

- `audit_logs`: retenção mínima a definir pela política corporativa (pendente).
- `job_attempts`: 12 meses sugerido, pendente.
- Arquivos originais: mantidos enquanto a revisão existir.

## Migrações

Alembic, uma migração por entrega vertical, revisão revisada em PR. Verificação de migração no CI (`upgrade head` → `downgrade -1` → `upgrade head`) em banco efêmero.
