# Fase 2B.2 — Manipulação de dados: planejamento detalhado

Status: **planejamento para aprovação. Implementação NÃO iniciada.** Depende do merge do PR #2 (2B.1) e de autorização.
Uso individual. Sem RBAC, multi-tenancy, papéis ou administração. Dados sintéticos apenas.

## 1. Objetivo

Tornar a 2B.1 utilizável no dia a dia: versionar mapeamentos e metadados, reaproveitar mapeamentos por templates, escolher o cabeçalho manualmente, filtrar, pesquisar, ordenar, substituir e transformar linhas em lote, renomear e excluir tabelas, **com interface funcional para tudo isso**. Refinamentos avançados (virtualização, cálculos, redimensionamento) ficam na 2B.4.

## 2. Escopo e ordem de entrega dentro da 2B.2

| Ordem | Bloco | Tipo |
|---|---|---|
| 1 | Versionamento de mapeamento e metadados (§3) | escrita (versão) |
| 2 | Templates de mapeamento (§4) | escrita (versão de metadados) |
| 3 | Seleção manual do cabeçalho (§5) | escrita (versão de dados e metadados) |
| 4 | Filtros, pesquisa e ordenação (§6) | leitura, sem versão |
| 5 | Localizar e substituir em lote (§7) | escrita (versão) |
| 6 | Seleção e transformação de linhas, inclusive exclusão lógica de linhas (§8) | escrita (versão) |
| 7 | Renomear e excluir tabelas (§9) | metadado da tabela, sem versão de dados |
| 8 | Interface completa para os blocos 1 a 7 e para a 2B.1 (§10) | UI |

Cada bloco é um conjunto de commits com testes próprios. A interface é entregue **por bloco**, à medida que o bloco fica pronto (não no fim da fase).

## 3. Versionamento completo de mapeamentos e metadados

### 3.1 Problema
Hoje o mapeamento é configuração mutável (decisão da 2B.1). Para o histórico ser completo, mudanças de mapeamento precisam ser versionadas sem copiar linhas.

### 3.2 Modelo
Duas cadeias independentes, ligadas por referência:

- `dataset_versions` (dados): imutáveis, como na 2B.1.
- `dataset_metadata_versions` (metadados): cada linha tem `id`, `dataset_id`, `number`, `parent_metadata_version_id`, `data_version_id` (FK para a versão de dados que ela descreve), `columns` (JSON), `mapping` (JSON), `header_row` (inteiro), `created_at`, `actor`.
- `datasets`: `current_version_id` (dados) e `current_metadata_version_id` (metadados). `columns`, `mapping`, `row_count` continuam como espelho da versão atual, para leitura rápida.

Consequências:
- Mudar só o mapeamento cria nova **versão de metadados** apontando para a mesma versão de dados. Nenhuma linha é copiada.
- Mudar dados (operação) cria nova versão de dados e, se as colunas mudarem, nova versão de metadados.
- Desfazer e refazer movem os dois ponteiros juntos, conforme o registro de cada operação.

### 3.3 Operações de mapeamento
- `set_mapping` (capacidade nova): `{mapping}` → nova versão de metadados. Valida colunas existentes.
- `rename_column` passa a registrar a nova versão de metadados (já faz isso de forma implícita na 2B.1; aqui vira explícito).

### 3.4 Migração 0004
- Cria `dataset_metadata_versions` nova com as colunas acima e migra as linhas existentes (uma por tabela, `data_version_id` = versão atual, `number`=1).
- Adiciona `datasets.current_metadata_version_id`.
- Mantém compatibilidade de leitura: `GET /datasets/{id}` continua devolvendo `columns` e `mapping` atuais.
- Downgrade restaura a tabela de metadados anterior a partir da versão atual.

## 4. Templates reutilizáveis de mapeamento

- Template: `{name (único), definition: {mapping por NOME DE COLUNA}, definition_version, updated_at}`. Mapeia **nomes de colunas**, não posições, para funcionar em tabelas diferentes com o mesmo layout.
- Aplicar template a uma tabela: valida que todas as colunas citadas existem; caso contrário, relatório de colunas ausentes e aplicação parcial **somente** se o usuário confirmar (lista do que será mapeado e do que ficará sem mapeamento).
- A aplicação cria nova versão de metadados e registra `template_id` e `definition_version` na versão.
- Editar um template não altera mapeamentos já aplicados (histórico preservado).
- Templates são capacidade reutilizável: `apply_mapping_template` registrada em `OPERATIONS`.

## 5. Seleção manual da linha de cabeçalho

- Operação `set_header_row` com `{header_row}` (número da linha na **origem**, 1-based).
- Implementação: relê o **arquivo original** preservado em `originals/` com o cabeçalho escolhido. Não usa o conteúdo já transformado. Prova direta da preservação do original.
- Gera nova versão de dados (novas colunas, linhas a partir da linha seguinte ao cabeçalho) e nova versão de metadados com `header_row`.
- Validação: a linha deve existir; a linha escolhida deve ter ao menos duas células preenchidas; nomes de colunas passam pelo mesmo tratamento da importação (dedupe, sem colisão).
- Limitação: para XLSX, a linha é a da planilha escolhida na importação (aba preservada em `sheet_name`).

## 6. Filtros, pesquisa e ordenação (leitura, sem versão)

### 6.1 Filtros
Lista de condições combinadas por E. Operadores:

| Tipo | Operadores | Semântica |
|---|---|---|
| Texto | `equals`, `contains`, `prefix`, `not_equals` | sensível a caixa só se `match_case=true` (padrão: não) |
| Vazio/desconhecido | `is_empty` (`""`), `is_unknown` (`null`) | distintos: vazio ≠ desconhecido ≠ zero |
| Numérico | `gt`, `gte`, `lt`, `lte`, `between` | `Decimal`; célula não numérica não casa e é contada no resumo |

Retorno inclui `matched_count` e `not_numeric_count` para que o usuário veja o que foi excluído.

### 6.2 Pesquisa global
Texto livre (`q`) procurado em todas as colunas da versão atual: sem diferença de caixa e de acento, por substring. Resultado com coluna onde casou (destaque na UI).

### 6.3 Ordenação
`sort=[{column, type: text|decimal, dir: asc|desc}]`. Texto: ordem Unicode sobre a forma NFC normalizada. Decimal: valores não numéricos vão para o fim, nunca como zero. Desconhecido sempre no fim, independentemente da direção. Empate mantém a ordem da origem (`row_number`).

### 6.4 Limites
- `limit` máximo 500 por página; filtros e ordenação são feitos no banco quando possível e, para texto acento-insensível, em aplicação sobre o conjunto filtrado (limite de linhas medido, §11).

## 7. Localizar e substituir em lote

- Estende `replace_text` (code_version 2): `columns: [..] | "*"`, `where: [filtro]` (mesmo formato do §6.1), `match_case`, `whole_cell`.
- Prévia obrigatória: contagem por coluna e amostra de até 20 alterações (antes/depois).
- Desconhecido nunca é substituído. Substituição não cria valor a partir de vazio, salvo se `find` for vazio e a operação for explicitamente `fill_empty` (fora do escopo desta entrega).
- Validação: `find` não vazio; número de colunas limitado ao existente.

## 8. Seleção e transformação de linhas

- Seleção: lista de `row_number` (até 10.000), ou resultado de um filtro (`select_by_filter`), sempre mostrada com contagem antes de aplicar.
- Ações (operação `transform_rows`, code_version 1):
  - `set_value` (já existe como `set_rows_value`: manter e expor na UI);
  - `delete_rows` — **exclusão lógica**: as linhas saem da versão nova, o `row_number` original é preservado nas demais, e as excluídas ficam listadas na versão anterior (nada se perde, a operação pode ser desfeita).
- Limite: `delete_rows` com mais de 10.000 linhas exige seleção por filtro, não lista.

## 9. Renomear e excluir tabelas

- **Renomear**: `PATCH /datasets/{id}` com `{name}`. Atualiza apenas o nome (não é versão de dados). Auditado com nome anterior e novo. Nomes únicos entre tabelas ativas.
- **Excluir**: `DELETE /datasets/{id}` com `{confirm: "<nome exato>"}`. Exclusão **lógica** (`deleted_at`): a tabela some das listagens e não pode ser editada; as versões e o arquivo original são mantidos. Restauração disponível enquanto não houver purga.
- **Purga física**: fora desta entrega. Só será feita por rotina explícita, após a política de retenção medida (2B.4).
- Não há exclusão em cascata de tabelas derivadas nesta entrega (derivadas são da 2B.3).

## 10. Interface funcional

Telas e componentes (sem virtualização; paginação server-side de 100 linhas):

1. **Barra de ferramentas da tabela**: buscar, filtrar, ordenar, substituir, editar mapeamento, cabeçalho, desfazer, refazer, histórico, exportar, renomear, excluir.
2. **Painel de filtros** (lista de condições com operador e valor) e **resumo** (linhas exibidas, excluídas por tipo).
3. **Painel de transformação**: escolher a operação, preencher parâmetros (formulário gerado do esquema da capacidade), **prévia obrigatória** (contagem e amostra antes/depois) e botão "Aplicar" só após prévia. Sinaliza `409` com mensagem para atualizar.
4. **Seleção de linhas**: checkbox por linha, "selecionar resultado do filtro", contagem visível.
5. **Histórico de operações**: lista com código, parâmetros, status (aplicada/desfeita), data, ator; botões desfazer/refazer no topo.
6. **Versões**: lista de versões de dados e de metadados; indicador da atual; nenhum conteúdo é apagado.
7. **Templates de mapeamento**: criar a partir do mapeamento atual, aplicar com lista de colunas ausentes, editar (cria nova definição).
8. **Cabeçalho**: visualização das primeiras linhas da origem com seleção da linha de cabeçalho; aplicação pela operação `set_header_row` (com prévia).
9. **Renomear e excluir** (com confirmação digitando o nome).
10. **Estados**: carregando, vazio, erro com Problem Details, conflito (409) com ação de atualizar, prévia expirada com ação de gerar nova.

Regra: nenhuma regra de negócio no navegador. Validações de forma (campos obrigatórios) são feitas também na API.

## 11. Critérios de aceitação

Itens marcados **[PG]** exigem validação em PostgreSQL 17 no CI. Itens **[M]** exigem medição registrada em `FASE_2B2_STATUS.md`.

| ID | Critério |
|---|---|
| B2-01 | Mudança só de mapeamento cria versão de metadados sem copiar linhas (conferido pelo número de linhas gravadas). |
| B2-02 | Versões de metadados são imutáveis; cada uma aponta para uma versão de dados existente. |
| B2-03 | Desfazer e refazer movem dados e metadados juntos, conforme o registro da operação. |
| B2-04 | Migração 0004 preserva os metadados da 2B.1 e volta no downgrade **[PG]**. |
| B2-05 | Template aplicado produz mapeamento igual ao da definição; colunas ausentes são listadas e exigem confirmação. |
| B2-06 | Editar template não altera mapeamentos já aplicados. |
| B2-07 | `set_header_row` relê o arquivo original: hash do original inalterado e linhas conferidas contra a origem. |
| B2-08 | Filtros: vazio, desconhecido e zero são distintos; numérico usa `Decimal`; `not_numeric_count` correto. |
| B2-09 | Pesquisa global ignora caixa e acento; resultado informa a coluna onde casou. |
| B2-10 | Ordenação numérica usa `Decimal`; não numéricos e desconhecidos vão para o fim; empate preserva a ordem da origem. |
| B2-11 | Substituição em lote: prévia com contagem igual ao número de células alteradas; desconhecido nunca é substituído. |
| B2-12 | `delete_rows` preserva os demais `row_number`; a operação é desfeita com exatidão (hash igual ao anterior). |
| B2-13 | Renomear não cria versão de dados; nome duplicado é recusado. |
| B2-14 | Excluir exige o nome exato; tabela excluída não aparece em listagens nem aceita operações; versões e original permanecem. |
| B2-15 | Interface: cada bloco tem teste de componente e verificação no navegador com dados sintéticos. |
| B2-16 | Limite de páginas e de seleção (10.000) aplicados e testados. |
| B2-17 | [M] Filtro, pesquisa, ordenação e substituição medidos em 100 mil e 500 mil linhas. Limites de página e de linhas definidos só com esses números. |
| B2-18 | Nenhuma regra de negócio no frontend (cada regra tem teste na API). |

## 12. Riscos e decisões

- **Crescimento de armazenamento**: cada operação de dados copia linhas. Operações de metadados não copiam. A medição de B2-17 decide a retenção (2B.4).
- **Pesquisa e ordenação acento-insensíveis** em aplicação podem ser lentas em volume grande. Mitigação: medição e, se preciso, coluna de chave normalizada em tabela auxiliar (decisão na medição).
- **Cabeçalho escolhido após transformações**: `set_header_row` sempre parte do original; transformações anteriores são recalculadas a partir dele não automaticamente. Decisão: ao mudar o cabeçalho, as operações posteriores são marcadas como `undone` (com aviso prévio na UI). Alternativa rejeitada: reaplicar automaticamente (risco de alteração silenciosa).
- **Exclusão lógica** mantém dados sensíveis em disco até a purga. Documentado; purga é decisão explícita futura.
