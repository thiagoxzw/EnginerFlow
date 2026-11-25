# Fase 5 — Material Manager (arquitetura)

Status: **arquitetura apenas.** Nenhuma implementação nesta fase de planejamento. Este documento é a base para a
implementação, em uma fase posterior autorizada. Não usar dados industriais reais no repositório: fixtures e
exemplos são sintéticos.

## Problema

Identificar, localizar, comparar e relacionar materiais cadastrados em sistemas diferentes (Totus, Protheus,
estruturas do BOM Manager, desenhos do Solid Edge). Hoje isso é feito manualmente, com cruzamento em planilhas.

## Princípio central

**Nunca atribuir um código industrial oficial apenas por semelhança de descrição.** Toda correspondência tem uma
classe de evidência e, quando não é exata, fica pendente até uma decisão humana registrada.

## Classes de correspondência

| Classe | Critério | Atribuição |
|---|---|---|
| **Confirmada** | Decisão humana registrada (ou código idêntico em cadastro único, com regra explícita aprovada) | Pode ser exportada |
| **Provável** | Evidência forte e única (ex.: código alternativo cadastrado, part number idêntico) | Pendente de confirmação |
| **Ambígua** | Dois ou mais candidatos com evidência comparável | Fila de revisão manual |
| **Não encontrada** | Nenhum candidato acima do limiar | Cadastro sugerido, não criado automaticamente |

## Modelo de domínio (proposto)

- **Material:** registro do cadastro central, com código oficial, fonte, descrição original e normalizada,
  unidade, atributos técnicos, status (ativo, obsoleto, duplicado).
- **MaterialSource:** lote de importação (Totus, Protheus ou planilha), com hash do arquivo, mapeamento usado
  e versão do normalizador. Permite reproduzir a importação.
- **Specification:** atributos técnicos extraídos da descrição (diâmetro, comprimento, classe, norma, material,
  acabamento) com unidade e origem. Comparação por atributo, não por texto.
- **CodeAlias:** código alternativo ou legado de um material (ex.: código de outro sistema). Tem o mesmo peso
  de evidência de um código exato, quando validado.
- **MatchEvidence:** cada motivo de correspondência (código exato, alias, part number, atributos compatíveis,
  similaridade de descrição normalizada) com peso e explicação.
- **MatchDecision:** decisão confirmada ou rejeitada sobre a correspondência de um componente do BOM a um Material.
  Registra usuário, data, justificativa e evidências no momento da decisão.
- **ReviewQueue:** itens ambíguos ou prováveis aguardando decisão, priorizados por impacto (quantidade no BOM,
  número de estruturas que usam o componente).
- **DecisionHistory:** imutável. Nunca se apaga uma decisão; uma decisão posterior substitui a vigente e
  preserva a anterior.
- **ExportBatch:** exportação de códigos confirmados, com versão do cadastro e das decisões usadas.

## Normalização de descrições técnicas

- Versão explícita do normalizador (gravada em cada lote), para reprodutibilidade.
- Sem acentos, caixa baixa, símbolos técnicos convertidos (Ø, ±, °, ×), vírgula decimal como ponto.
- Extração de atributos por padrões (dimensão, classe, norma), com lista de padrões revisável.
- Descrição normalizada **nunca substitui** a original; ambas são guardadas.

## Identificação de duplicidades

- Código idêntico com descrições normalizadas divergentes: alerta, não correção automática.
- Descrições normalizadas iguais com códigos diferentes: candidato a duplicidade, decidido por humano.
- Mesmo material com unidades diferentes: alerta de conversão, sem conversão automática.

## Correspondência exata e aproximada

1. **Exata:** código oficial idêntico (comparação configurável: exata ou normalizada, como no cruzamento do BOM).
2. **Por alias:** código alternativo validado.
3. **Por part number:** igualdade de part number do fabricante.
4. **Aproximada:** atributos técnicos compatíveis e descrição normalizada próxima. Sempre classe **Provável** ou
   **Ambígua**, nunca Confirmada.

## Equivalentes

Materiais equivalentes são uma relação explícita e revisada (substituto aprovado, com faixa de atributos), não um
resultado automático de similaridade.

## Integração com o BOM Manager

- Cada componente de uma revisão do BOM recebe, no máximo, uma decisão vigente por material, referenciando a
  revisão e a linha.
- A validação do BOM passa a consultar o Material Manager por contrato (ver `CONTRATOS_BOM.md`), sem acessar
  tabelas do outro módulo.
- Revisões do BOM continuam imutáveis: uma nova decisão não altera revisões antigas.

## Integração futura com Solid Edge

- Contrato de leitura: propriedades de peça (código, descrição, revisão, material) como fonte de evidência
  adicional, com o mesmo peso de uma importação de cadastro.
- Sem escrita no Solid Edge nesta arquitetura. Exportação de códigos confirmados é a única saída.

## Exportação

- Códigos confirmados, com: código do componente no BOM, código oficial, fonte, classe de evidência, decisão
  vigente, data e versão do normalizador.
- Pendentes e ambíguos exportam em relatório separado, nunca como código confirmado.

## Persistência e migrações

- Tabelas novas com prefixo `mat_`. Nenhuma tabela `bom_*` é alterada.
- Migrações somente de criação, com downgrade que remove apenas as tabelas criadas.
- Importações de cadastro são reprodutíveis pelo hash e pela versão do normalizador.

## Priorização de utilidade prática

1. Importar o cadastro e classificar correspondências dos componentes de uma estrutura.
2. Fila de revisão com decisão rápida e histórico.
3. Exportação de códigos confirmados.
4. Equivalentes aprovados e integração com Solid Edge.

## Segurança e dados

- Repositório público: somente dados sintéticos em testes, fixtures, exemplos e documentação.
- Nenhum dado de cadastro real é enviado a serviços externos de IA.

## Fora de escopo desta arquitetura

- Implementação de qualquer módulo.
- Conexão direta com Protheus ou Solid Edge.
- Atribuição automática de código industrial.
