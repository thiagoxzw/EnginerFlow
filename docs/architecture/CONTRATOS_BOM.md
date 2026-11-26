# Contratos internos do BOM Manager (versão 1)

Estes contratos são a forma estável com que módulos futuros consultam o BOM Manager (Material Manager,
Solid Edge Connect, Inventory Manager, ERP Connect). Eles não expõem as tabelas `bom_*`.

- **Código:** `apps/api/src/engiflow_api/application/bom_contracts.py` (TypedDicts).
- **Teste de conformidade:** `apps/api/tests/test_bom_contracts_4.py` compara as respostas reais da API com cada contrato.
- **Acesso:** rotas REST em `/api/v1/bom/*`, com sessão. Contratos de leitura; as escritas são as rotas de edição e de kits.
- **Mudança:** alteração incompatível exige nova versão (`CONTRACT_VERSION`) e registro aqui.

## Convenções valem para todos os contratos

- Quantidades e códigos são **texto**. Zeros à esquerda, caracteres e desconhecidos (`null`) são preservados. Um código não é convertido em número.
- Quantidades são decimais exatos. Unidades diferentes nunca são somadas.
- **Código provisório:** código gerado por duplicação de subconjunto, com sufixo `-CP` (ou `-CP2`, `-CP3` em caso de colisão). Ele **não é código oficial** do ERP ou do cadastro. A validação o informa, e a interface o marca. Consumidores devem tratá-lo como provisório até confirmação.
- **Ocorrência** é uma aparição do componente na estrutura expandida, não um código único.

## Contratos

| Contrato | Conteúdo | Rota de origem |
|---|---|---|
| `StructureContract` | Estrutura, revisão atual e lista de revisões | `GET /structures`, `GET /structures/{id}` |
| `RevisionContract` | Revisão imutável: número, origem, modo, contagem, hash do conteúdo | dentro de `StructureContract` |
| `ComponentLineContract` | Aparição de componente: pai, filho, quantidade, unidade, propriedades | `GET /revisions/{id}/lines` |
| `ConsolidatedQuantityContract` | Quantidade total por código e unidade | `explode`, `kit-calc` |
| `ExplosionContract` | Explosão por veículo: consolidado, ocorrências, linhas inválidas, avisos | `POST /revisions/{id}/explode` |
| `ValidationResultContract` / `IssueContract` | Contagens e inconsistências (erro, alerta, informação) | `GET /revisions/{id}/validate` |
| `ComparisonContract` | Diferenças entre revisões, sem correspondência e trocas de código pendentes | `POST /compare` |
| `KitContract` / `KitPartContract` | Kit com peças (subconjunto ou folha, unidade opcional) | `POST /structures/{id}/kits` |
| `KitMaterialsContract` | Materiais de um kit para veículos × lote | `POST /revisions/{id}/kit-calc` |

## Garantias para consumidores

- Uma revisão nunca muda depois de criada. Consumidores podem guardar `revision_id` com segurança.
- `content_sha256` identifica o conteúdo de uma revisão.
- Os cálculos (explosão, kits, comparação) são feitos sobre todas as linhas da revisão. O limite visual da interface não afeta esses resultados.
- Avisos de kit sem linha da tabela (ex.: mesmo código em unidades diferentes) trazem `row: null`. Consumidores não devem exibir número de linha nesses casos.
- Exportação recusada (ex.: hierarquia acima de 200 mil linhas) responde `422` no formato de problema, com `detail` em texto. A interface mostra esse `detail` ao usuário.
- Código de peça provisória (`-CP`, `-CP2`…) não é código oficial do ERP. Consumidores devem tratá-lo como provisório até confirmação.

## Fora deste contrato (ainda)

- Escrita direta por módulos externos.
- Eventos ou notificações de mudança.
- Consulta de componentes por código entre estruturas (será tratada pelo Material Manager, Fase 5).
