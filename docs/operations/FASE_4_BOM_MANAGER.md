# Fase 4 — BOM Manager (status de entrega)

Atualizado em 2026-11-26. Dados de exemplo sintéticos (prefixo `SYN-`, `BOM-SYN`). Nenhum dado real.

## Entregue

- **Importação com mapeamento:** tabela do Data Studio (CSV, XLSX, ERP ou CAD) com assistente de
  mapeamento. A sugestão é pelos nomes das colunas e pode ser alterada. Campos obrigatórios:
  código do componente, quantidade e pai (ou nível). Os demais são opcionais. Prévia antes de confirmar.
- **Dois modos de hierarquia:** coluna de conjunto pai (explícito) e níveis hierárquicos. No modo
  por nível, o pai é a última linha do nível anterior e aparece marcado como inferido. Sem nível
  anterior, o pai fica vazio e a validação aponta.
- **Árvore de materiais:** expandir e recolher por conjunto, expandir ou recolher tudo, busca por
  código, código alternativo, descrição ou part number, com destaque e expansão do caminho até o
  resultado. Filtros por nível, unidade, revisão e categoria. Alternância entre árvore e tabela.
  Quantidades local e acumulada por unidade do topo (decimal exato no navegador). Painel de detalhes
  com "aparece em" e navegação até o conjunto pai.
- **Edições:** quantidade, descrição (em todas as ocorrências do código), adicionar componente,
  mover para outro conjunto, duplicar conjunto (filhos diretos) e remover linha. Cada edição cria
  uma nova revisão; a anterior permanece.
- **Histórico:** desfazer e refazer apenas trocam a revisão atual. Nenhuma revisão é apagada.
- **Explosão:** por veículo, com consolidação por código e unidade (unidades diferentes não são
  somadas), ocorrências por aparição na estrutura, e avisos para linhas com quantidade inválida.
  Ciclos são recusados antes do cálculo.
- **Comparação entre revisões:** quantidade, transferência entre conjuntos, unidade, descrição,
  revisão, sem correspondência, e possível troca de código (sempre pendente, nunca aplicada).
- **Validação:** erro, alerta e informação. Regras: sem código, sem descrição, quantidade ausente,
  inválida, negativa ou zerada, pai inexistente, ciclo, órfão, unidade incompatível, revisão
  conflitante, descrição divergente, duplicidade no mesmo conjunto, e nível inconsistente (modo por nível).
  Navegação direta para a linha. Nada é alterado automaticamente.
- **Cruzamento com cadastro:** tabela de cadastro escolhida pelo usuário, com coluna de código,
  descrição e unidade configuráveis. Situações: encontrado, sem cadastro, múltiplas correspondências,
  descrição e unidade divergentes, e possível equivalente (pendente). Comparação de códigos exata
  ou normalizada. Nenhum código é atribuído automaticamente.
- **Kits:** criação com subconjuntos e quantidade por kit, cálculo por veículo e lote, comparação de
  composição entre dois kits (só em um, quantidade diferente), e lista de separação em CSV.
- **Exportações (XLSX e CSV):** lista de componentes, consolidada, hierárquica (com nível e
  quantidades local e acumulada), inconsistências e comparação entre revisões. A lista de separação
  de kits é gerada no navegador.
- **Auditoria:** criação de estrutura, edição, mudança de revisão atual e criação de kit são registradas.

## Arquitetura

- Domínio puro em `domain/bom.py`: explosão com memória por conjunto, detecção de ciclos,
  comparação, validação e kits. Sem banco e sem arquivo.
- Aplicação em `application/bom.py` e `application/bom_export.py`. Reutiliza o leitor de versões do
  Data Studio, o formato de exportação e a auditoria.
- Persistência em tabelas próprias `bom_structures`, `bom_revisions`, `bom_lines` e `bom_kits`
  (modelos em `infrastructure/bom_models.py`). Quantidades e códigos são texto: zeros à esquerda,
  caracteres especiais e valores desconhecidos são preservados.
- Rotas em `presentation/routes/bom.py`, sob `/api/v1/bom`.
- Interface em `components/bom/` e `app/bom`. Funções puras da árvore em `lib/bom-tree.ts`.

## Migrações

- `0007_bom_manager`: cria as quatro tabelas acima e seus índices. Não altera tabela existente.
  Downgrade remove apenas essas tabelas.
- Validada em PostgreSQL 17 (upgrade, downgrade e novo upgrade) em banco descartável, e no stack
  E2E isolado. No SQLite, a mesma sequência também passa.

## Testes

- Domínio: `tests/test_bom_domain_4.py` (19), incluindo o exemplo do pedido: 2 conjuntos A, 4
  componentes B por A, 8 por veículo e 80 para 10 veículos, e ciclo em cadeia de 3000 níveis.
- API: `tests/test_bom_api_4.py` (19): importação, prévia, zero à esquerda, explosão, edição com
  nova revisão e desfazer, ciclo recusado, comparação, validação, cruzamento, kits (com subconjunto
  e com unidades diferentes), duplicação, exportações e recusa da hierarquia acima do limite.
- Contratos: `tests/test_bom_contracts_4.py` (3), conformidade com as respostas reais da API.
- Interface (unitários): `lib/bom-tree.test.ts` (decimal exato, árvore, busca, filtros),
  `components/bom/bom-import.test.ts` (sugestão de mapeamento) e `lib/bom-export.test.ts`
  (mensagem de recusa da exportação).
- E2E: `e2e/bom.spec.ts` (5 testes): importação com cálculo de explosão, edição com desfazer,
  validação de erro, kit com seleção exata e duplicação completa.
- Sem teste automatizado: a trava de numeração de revisão sob edições concorrentes (exige
  PostgreSQL com duas conexões) e a troca de estrutura com linhas antigas na árvore.

## Limitações conhecidas

- Desfazer e refazer são por revisão, e não por operação dentro da revisão.
- Duplicar conjunto copia só os filhos diretos. Subconjuntos mais profundos continuam compartilhados.
- A lista de materiais de um kit é informada em texto (`código;quantidade`). Não há importação de
  lista de kits na interface, embora a API aceite criação de kits.
- Edições em massa pela árvore são uma a uma. A API aceita lista de alterações.
- Cruzamento por código exato ou normalizado. Equivalentes são sugeridos só por descrição normalizada.
- A árvore renderiza até 1500 linhas visíveis. Não há virtualização; a busca e a expansão controlam o volume.
- Exportação hierárquica limitada a 200 mil linhas.
- Sem conexão direta com Protheus ou Solid Edge, conforme o escopo. Sem movimentação de estoque.
- Desempenho medido para 1 mil, 5 mil e 10 mil componentes em `docs/operations/BOM_DESEMPENHO_4.md`.
  O cálculo é memorizado por conjunto.
- Capturas de tela: uma captura da página no demonstrativo, com "Carregando…" na lista. Não há
  conjunto de capturas por seção nesta entrega.

## Próximas melhorias (não críticas)

- Desfazer por operação dentro da revisão.
- Virtualização da árvore. A medição de desempenho já foi feita (ver `BOM_DESEMPENHO_4.md`).
- Importação de listas de kits na interface e seleção manual de componentes.
- Contratos de integração para Material Manager, Solid Edge Connect, Inventory Manager e ERP Connect: não preparados nesta entrega (o pedido previa apenas contratos, sem implementação).

## Ajustes essenciais (segunda rodada)

- **Duplicação completa de subconjunto:** copia o conjunto com todos os descendentes. Subconjuntos internos recebem código provisório `-CP`. Em duplicação sucessiva, a colisão vira `-CP2`, `-CP3`… Componentes folha mantêm o código. Código informado pelo usuário que já existe é recusado. A diferença para "só filhos diretos" está na interface.
- **Códigos provisórios:** `-CP` identifica código gerado por duplicação, que **não é código oficial do ERP**. A validação informa cada um, a árvore os marca como "provisório", e o contrato documenta que consumidores devem tratá-los assim até confirmação.
- **Kits:** peça folha entra por si, com unidade informada ou a da linha. Subconjunto entra como material junto com os componentes dele, como na explosão. Importação de tabela (CSV ou XLSX) com prévia. Mesmo código em unidades diferentes gera peças separadas, com aviso, e nunca é somado. Código fora da estrutura bloqueia a criação.
- **Limite visual de 1.500 linhas:** é só de exibição. "Mostrar mais" libera o restante, e busca, filtros, cálculos e exportações usam sempre todas as linhas.
- **Contratos internos:** `docs/architecture/CONTRATOS_BOM.md` e `bom_contracts.py`, com teste de conformidade contra as respostas reais da API.
- **Desempenho:** `docs/operations/BOM_DESEMPENHO_4.md`, para 1 mil, 5 mil e 10 mil componentes.

**Limitações restantes:**
- Desfazer é por revisão, não por operação.
- Duplicação só cria `-CP` para subconjuntos; não há confirmação de código provisório no ERP (fora do escopo, sem integração).
- A busca leva cerca de 300 ms com 10 mil componentes e roda a cada tecla (sem adiamento).
- Não há virtualização da árvore; a exibição é paginada.
- Não há contratos de Material Manager, Solid Edge, Inventory ou ERP Connect implementados — só arquitetura da Fase 5, em branch separado.

**Limite da exportação hierárquica:** 200 mil linhas. Como a hierarquia expande cada caminho, estruturas com subconjuntos muito compartilhados podem atingir o limite. Escolha um conjunto de nível mais baixo como topo da exportação. A recusa aparece na tela do BOM, na seção de explosão, com a mensagem do servidor.
