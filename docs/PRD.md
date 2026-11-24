# EngiFlow — PRD (Product Requirements Document)

Status: **Planejado / proposta para revisão** (Fase 0). Nenhum requisito abaixo está implementado.

## 1. Escopo do MVP

Resolver o processo completo de engenharia descrito na Fase 1 do roadmap, usando **importação de arquivos** e **conectores mock**. Integração direta com Solid Edge e Protheus não bloqueia o MVP.

Fluxo obrigatório (conforme o prompt-mestre, seção 19):

1. Criar projeto.
2. Importar planilha de materiais.
3. Importar BOM.
4. Normalizar códigos e descrições.
5. Cruzar informações.
6. Identificar materiais sem correspondência.
7. Identificar duplicatas.
8. Classificar componentes.
9. Organizar materiais por kit.
10. Expandir estrutura multinível.
11. Calcular necessidades por chassi.
12. Simular necessidades para múltiplos chassis.
13. Importar saldo de estoque.
14. Identificar materiais faltantes.
15. Gerar relatórios.
16. Exportar Excel e CSV.
17. Registrar a execução no histórico.

## 2. Requisitos funcionais (MVP)

| ID | Requisito | Prioridade |
|---|---|---|
| RF-01 | Cadastrar organização, usuário, papel e projeto | Must |
| RF-02 | Importar planilhas Excel/CSV com seleção de aba, cabeçalho e mapeamento de colunas | Must |
| RF-03 | Preservar arquivo original (armazenado com hash SHA-256) | Must |
| RF-04 | Tratar códigos como texto (preservar zeros à esquerda) | Must |
| RF-05 | Normalizar descrições (caixa, espaços, acentos opcionais, unidades) com regra registrada | Must |
| RF-06 | Detectar duplicidade exata de código e similaridade de descrição com score e evidências | Must |
| RF-07 | Nunca marcar equivalência automática por descrição semelhante; sempre revisão humana | Must |
| RF-08 | Importar BOM hierárquica (pai/filho, quantidade, unidade) e validar ciclos | Must |
| RF-09 | Expandir estrutura multinível com quantidades acumuladas (Decimal) | Must |
| RF-10 | Agrupar por kit e calcular necessidade por chassi e para N chassis | Must |
| RF-11 | Importar saldo de estoque por filial/armazém e comparar com necessidade | Must |
| RF-12 | Listar faltas, excedentes e kits incompletos | Must |
| RF-13 | Exportar Excel e CSV com layout configurável | Must |
| RF-14 | Histórico de execuções com entradas, saídas, versão da regra e usuário | Must |
| RF-15 | Dashboard com indicadores calculados a partir de dados reais | Should |
| RF-16 | Comparar duas revisões de BOM | Should (Fase 3) |
| RF-17 | Conectar Solid Edge em modo somente leitura | Could (Fase 4) |
| RF-18 | Workflow linear com execução manual | Should (Fase 6) |

## 3. Requisitos não funcionais (MVP)

- **Isolamento:** toda consulta filtrada por `organization_id`; testes automatizados de isolamento.
- **Segurança:** autenticação, RBAC, validação de upload, limite de tamanho, auditoria de alterações.
- **Precisão:** quantidades em `NUMERIC`/`Decimal`; nenhuma quantidade calculada por LLM.
- **Rastreabilidade:** toda saída de relatório indica arquivo, revisão, aba e execução de origem.
- **Desempenho:** metas **não definidas**. Serão estabelecidas após medição com volume real (ver `TEST_STRATEGY.md`). Nenhuma garantia de desempenho é assumida.
- **Idioma:** português do Brasil; i18n preparada.
- **Plataforma:** web desktop-first; consultas responsivas em mobile.

## 4. Critérios de aceitação do MVP

Cada critério precisa de teste automatizado com dados sintéticos antes do aceite.

- **CA-01** Importar planilha com código de 8 dígitos iniciando em zero; o valor armazenado e exportado mantém os zeros.
- **CA-02** BOM com 4 níveis expande e a quantidade acumulada confere com cálculo de referência independente (fixture).
- **CA-03** BOM com ciclo é rejeitada com mensagem indicando o caminho do ciclo.
- **CA-04** Dois itens com mesmo código no mesmo projeto geram alerta de duplicidade; nenhum é removido automaticamente.
- **CA-05** Descrições semelhantes geram sugestão com score e evidências, status "pendente de revisão".
- **CA-06** Necessidade para 1, 10 e 50 chassis calculada e conferida contra fixture.
- **CA-07** Faltas = necessidade − disponível, com reserva considerada conforme regra configurada do projeto.
- **CA-08** Usuário de outra organização recebe 404 (não 403) para qualquer recurso de projeto alheio — teste de IDOR.
- **CA-09** Exportação Excel/CSV reproduz as contagens do relatório na tela.
- **CA-10** Toda execução aparece no histórico com usuário, entradas (hash), saída e status.
- **CA-11** Falha no meio de uma importação não deixa dados parciais visíveis (transação).
- **CA-12** Reimportação do mesmo arquivo (mesmo hash) não duplica registros (idempotência).

## 5. Fora do MVP

Conectores reais Solid Edge e Protheus, agente local, Workflow Studio visual, Document Center com busca semântica, AI Copilot com tool calling, módulos da fase 9.

## 6. Premissas e restrições

- Dados de referência do cenário (1.280 nomes de peças, 11 kits, 152 relações, 105 itens distintos, 1.167 peças por chassi) são **referências de um cenário específico**. O sistema não pode depender desses números.
- Classificações provisórias e premissas operacionais (ex.: regra de reserva, política de kit) são **configuráveis por projeto**, não constantes.
- Sem Node.js, Docker ou PostgreSQL instalados na máquina de desenvolvimento atual (verificado em 2026-11-24). Ver `DEPLOYMENT.md`.
