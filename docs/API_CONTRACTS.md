# EngiFlow — Contratos de API (v1)

Status: **Proposta** (Fase 0). Contrato OpenAPI será gerado na Fase 1 a partir do código FastAPI e versionado em `packages/contracts`.

Base: `/api/v1`. Autenticação por sessão (web) ou token por dispositivo (agente).

## Convenções

- **Erros padronizados** (RFC 9457 Problem Details): `type`, `title`, `status`, `detail`, `instance`, `correlation_id`, `errors[]` para validação.
- **Paginação:** `?limit=` (máx. 200) e `?cursor=` opaco. Resposta com `next_cursor`.
- **Filtros e ordenação:** `?filter[campo]=valor`, `?sort=-campo`. Campos permitidos por lista (allowlist).
- **Idempotência:** header `Idempotency-Key` obrigatório em criação de jobs, importações, exportações e aprovações.
- **Correlação:** header `X-Correlation-Id` aceito ou gerado; devolvido em todas as respostas e gravado em auditoria.
- **IDs:** UUID. Códigos de material como string.
- **Não existente ou de outra organização → 404** (evita enumeração).
- **Rate limit:** por usuário/dispositivo em endpoints de login, upload e IA.

## Endpoints planejados

| Área | Método e caminho | Resultado |
|---|---|---|
| Auth | `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` | sessão; MFA/SSO pendente de decisão |
| Organizações | `GET /organizations/current`, `GET /organizations/{id}/members` | |
| Projetos | `POST /projects`, `GET /projects`, `GET /projects/{id}`, `PATCH /projects/{id}` | `version` obrigatório no PATCH (If-Match) |
| Materiais | `POST /materials/import`, `GET /materials`, `GET /materials/{id}`, `POST /materials/duplicates/check` | import → 202 + job |
| Revisões de material | `GET /materials/{id}/history` | |
| Importações | `POST /imports`, `GET /imports/{id}`, `PUT /imports/{id}/mapping` | upload + mapeamento |
| BOM | `POST /boms/import`, `GET /boms/{id}/tree`, `GET /boms/{id}/revisions` | |
| Cálculo | `POST /boms/explode` | cálculo síncrono para escopo pequeno; grande vira job |
| Comparação | `POST /boms/compare` | entre revisões ou estruturas |
| Revisões | `POST /revisions`, `POST /revisions/{id}/approve`, `GET /revisions/{id}/diff` | |
| Estoque | `POST /inventory/import`, `GET /inventory/snapshots`, `POST /inventory/check` | check com parâmetros de chassi |
| Documentos | `POST /documents`, `GET /documents`, `GET /documents/{id}/extractions` | Fase 7 |
| Integrações | `GET /connections`, `POST /connections/{id}/test` | segredos nunca retornam |
| Agentes | `POST /agents/register`, `POST /agents/heartbeat`, `GET /agents/tasks/next`, `POST /agents/tasks/{id}/ack`, `POST /agents/tasks/{id}/result`, `POST /agents/{id}/revoke` | ver `LOCAL_AGENT_DESIGN.md` |
| Jobs | `GET /jobs/{id}`, `POST /jobs/{id}/cancel` | |
| Workflows | `POST /workflows`, `GET /workflows`, `POST /workflows/{id}/versions`, `POST /workflows/{id}/run` | |
| Aprovações | `GET /approvals`, `POST /approvals/{id}/approve`, `POST /approvals/{id}/reject` | exige `version` do alvo |
| Auditoria | `GET /audit-logs` | somente leitura, permissão específica |
| Analytics | `GET /analytics/summary`, `GET /analytics/automations` | calculado de dados reais |
| Ferramentas | `GET /tools`, `POST /tools/{code}/invoke` | catálogo único para UI, workflow, API e IA |

## Exemplos de corpo (ilustrativos)

`POST /api/v1/boms/explode`

```json
{
  "bom_revision_id": "0f6c1d2e-5b1a-4c1e-9a1e-2f3a4b5c6d7e",
  "chassis_quantities": ["1", "10", "50"],
  "policy": { "kit_purchase_mode": "components" }
}
```

Quantidades chegam como string decimal para não perder precisão no JSON.

## Versionamento

- Mudança incompatível → nova versão (`/api/v2`). Mudança aditiva → mesma versão.
- Campos removidos passam por ciclo de depreciação com cabeçalho `Deprecation` por no mínimo uma versão de release.
- Cliente TypeScript gerado a partir do OpenAPI em `packages/api-client`; diferença de contrato quebra o CI.

## Ainda não definido

- Formato exato de exportação ERP (depende do layout real do Protheus e de validação com o time de ERP).
- Política de limite de tamanho de upload (ver `SECURITY_MODEL.md`).
