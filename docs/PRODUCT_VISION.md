# EngiFlow — Visão do produto

Status: **Planejado / proposta para revisão** (Fase 0).

## Problema

Atividades recorrentes de engenharia industrial (BOM, codificação de componentes, conferência de estoque, quantificação por kit e chassi, geração de arquivos de importação) são feitas manualmente em planilhas, no Solid Edge e no ERP. Isso gera retrabalho, erros de digitação, perda de rastreabilidade e dependência de pessoas específicas.

## Visão

Uma plataforma central de automação e inteligência de engenharia industrial que funciona como **camada de integração e automação** entre sistemas existentes (Solid Edge, Excel, TOTVS Protheus, sistema de arquivos). Não substitui essas ferramentas.

## Objetivos de produto

1. Automatizar tarefas operacionais repetitivas com rastreabilidade.
2. Centralizar informações técnicas (BOM, materiais, revisões, documentos).
3. Padronizar processos e reduzir erros humanos com validações determinísticas.
4. Transformar cada nova necessidade em capacidade reutilizável (ferramenta no catálogo, endpoint, workflow).
5. Usar IA como camada de assistência — nunca como fonte de cálculos ou códigos.

## Não objetivos (fase inicial)

- Substituir Solid Edge, Protheus ou planilhas corporativas.
- Escrever diretamente em banco de dados de ERP.
- Alterar arquivos CAD sem backup, dry run, aprovação e verificação posterior.
- Implementar módulos futuros (Production Planning, Quality, Cost, Maintenance etc.) antes do núcleo estabilizar.
- Oferecer chatbot genérico.

## Usuários previstos

| Papel | Necessidade principal |
|---|---|
| Engenheiro de produto | Estruturas BOM, comparação de revisões, codificação |
| Analista de materiais | Cadastro, duplicatas, equivalências, importações |
| Planejamento / PCP | Necessidade por chassi e lote, faltas, kits incompletos |
| Administrador | Usuários, permissões, agentes locais, integrações |

Papéis finais e número de usuários **pendentes de confirmação** (ver `decisions/OPEN_QUESTIONS.md`).

## Evolução

Inicialmente ferramenta interna de uma organização. A arquitetura prevê isolamento por organização desde o início para permitir eventual uso multiempresa, condicionado a autorização e direitos de propriedade intelectual.

## Métricas de sucesso (a medir, não prometer)

- Tempo manual de referência por processo (medido antes e depois, com identificação da origem).
- Taxa de sucesso e de falha das automações.
- Número de divergências detectadas e corrigidas.
- Uso por módulo.

Economia de tempo só é reportada como resultado real quando medida; estimativas são rotuladas como estimativas.
