# EngiFlow — instruções do projeto

Este arquivo foi criado em 2026-11-26 (não havia `CLAUDE.md` antes). As regras da seção 1 são as instruções
permanentes que o responsável pelo projeto definiu durante o desenvolvimento. A seção 2 é o protocolo de
desenvolvimento com skills.

## 1. Instruções permanentes (registro das instruções anteriores)

- **Repositório público.** Nunca envie ao GitHub arquivos industriais, códigos reais, documentos internos,
  credenciais ou estruturas reais da empresa.
- **Dados sintéticos sempre.** Testes, fixtures, exemplos, documentação e demonstrações usam apenas dados
  sintéticos (prefixos `SYN-`, `BOM-SYN`, `TOP-SYN`, `CMP-SYN` etc.). Não usar arquivos reais em testes.
- **Nada de dados corporativos em serviços externos.** Não enviar dados industriais ou pessoais para serviços de
  IA, nem para GitHub público.
- **Merge só com autorização explícita.** Não fazer merge de PR sem autorização do responsável. Não alterar a
  visibilidade do repositório.
- **Não inventar resultados de testes.** Relatar apenas o que foi executado, com evidência. Se algo falhar, dizer.
- **Ambiente pessoal preservado.** Testes nunca alteram o ambiente pessoal. Stacks de teste são isolados (projeto
  Docker próprio, portas próprias) e descartáveis.
- **Sem limpeza global.** Não usar comandos globais de limpeza do Docker (`system prune`, `volume prune` etc.).
  Remover apenas recursos identificados e exclusivos do projeto, após confirmar dependências.
- **Backup antes de migração** no banco pessoal (`scripts/local/Backup-EngiFlow.ps1`), e preservar a possibilidade
  de recuperação.
- **Exclusão lógica primeiro.** Exclusões de tabelas são lógicas, reversíveis pela API. Exclusão física só com
  autorização explícita.
- **Fases não são subdivididas** sem necessidade: uma fase é uma entrega contínua, com commits organizados por
  responsabilidade.
- **Sem demonstrativo sem dados.** Atualizações do demonstrativo preservam dados, volumes e configurações.
- **Não iniciar a fase seguinte** sem autorização. Arquitetura de fases futuras pode ser preparada em branch
  separado, sem implementação.

## 2. Protocolo de desenvolvimento com skills

1. **Seleção.** No início de tarefas relevantes, usar `superpowers:using-superpowers` para identificar quais
   skills se aplicam. Não executar skills indiscriminadamente. Ler o conteúdo de cada skill antes de usá-la.
2. **Planejamento de módulos novos.** Quando aplicável: `superpowers:brainstorming`, `superpowers:writing-plans`,
   `engineering:architecture`, `engineering:system-design`. Considerar módulos existentes, contratos internos,
   reutilização, integridade dos dados e necessidades profissionais. Após autorização de uma fase, prosseguir
   autonomamente dentro do escopo aprovado, sem aprovações intermediárias.
3. **Desenvolvimento.** `superpowers:test-driven-development` principalmente para regras críticas: cálculos de
   quantidades, estruturas hierárquicas, correspondência de materiais, normalização de especificações, identificação
   de duplicatas, versionamento, importação e exportação, integridade de códigos industriais. Agentes paralelos
   só para tarefas independentes, sem alterar os mesmos arquivos. Git worktrees para trabalhar em branches diferentes.
4. **Investigação de erros.** `superpowers:systematic-debugging` em falhas relevantes. Identificar a causa raiz
   antes de alterar o código. Diferenciar defeito real da aplicação, defeito de teste, problema de ambiente,
   problema de sincronização e erro de configuração. Não aumentar timeouts, não enfraquecer asserções e não pular
   testes para obter aprovação.
5. **Revisão de código.** Antes da entrega de cada fase, uma skill de revisão adequada (`code-review` ou
   `engineering:code-review`). Priorizar segurança, integridade dos dados, correção dos cálculos, desempenho,
   manutenibilidade, reutilização, compatibilidade com módulos existentes e exposição de informações corporativas.
   `simplify` quando houver código complexo ou duplicado. Não repetir revisões equivalentes. Corrigir problemas
   críticos na hora; registrar melhorias não críticas.
6. **Validação.** `superpowers:verification-before-completion` antes de declarar uma fase concluída. Exigir
   evidência real. Testes direcionados durante o desenvolvimento e validação integrada ao final. `run` e
   `built-in-browser` para conferir fluxos no demonstrativo. `xlsx` para validar exportações, verificando zeros
   à esquerda, quantidades e unidades, caracteres especiais, hierarquia, precisão decimal, compatibilidade com
   Excel e proteção contra injeção de fórmulas.
7. **Autonomia e eficiência.** Não pedir autorização a cada skill. Não criar subdivisões de fase sem necessidade.
   Não produzir relatórios intermediários repetitivos. Não executar toda a suíte por alterações apenas documentais
   ou visuais, salvo necessidade. Não usar skills pagas sem autorização.
8. **Proibições.** Não executar `/ship` nem `/steward` automaticamente (são iniciadas só quando o responsável as
   digita). Não fazer merge sem autorização explícita. Não ampliar permissões indiscriminadamente. Não desabilitar
   mecanismos de segurança para reduzir confirmações.
9. **Prioridade do projeto.** O objetivo é automatizar atividades reais de engenharia, não acumular funcionalidades
   genéricas. Ordem: 1) BOM Manager; 2) Material Manager; 3) Solid Edge Connect; 4) preparação de estruturas para
   Protheus; 5) Inventory Manager; 6) PDI & Quality; 7) ERP Connect; 8) Workflow Studio; 9) AI Copilot. Decisões
   técnicas consideram redução de trabalho manual e confiabilidade das informações industriais.
10. **Códigos provisórios.** Códigos gerados por duplicação (sufixo `-CP`) são provisórios e nunca são tratados
    como códigos oficiais do ERP ou do cadastro.
11. **Correspondência de materiais.** Nunca atribuir código industrial oficial apenas por semelhança de descrição.
    Correspondências ambíguas permanecem pendentes de confirmação humana.
