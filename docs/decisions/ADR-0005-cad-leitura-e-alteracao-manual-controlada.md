# ADR-0005 — CAD: leitura primeiro; alterações com confirmação manual; sem manipulação binária

- **Status:** Revisada (2026-11-24) — aguarda aprovação
- **Direcionamento do responsável:** operações somente leitura primeiro; alterações com pré-visualização, dry run, backup, confirmação manual, registro e verificação posterior. Sem sistema corporativo de aprovação.

## Decisão
1. Fase 4: leitura via API COM oficial do Solid Edge (quando a versão e a licença forem confirmadas). Enquanto isso, conector simulado com dados sintéticos.
2. **Proibido** alterar bytes de `.asm`, `.par` ou `.psm` fora da API oficial. Os scripts atuais de troca de nomes por manipulação binária ficam como **operação manual** do responsável, fora do produto, até a integração COM ser validada.
3. Alterações futuras via COM seguem este fluxo, sempre com confirmação manual do responsável:
   - pré-visualização do que será alterado;
   - dry run quando suportado;
   - cópia de backup antes da escrita;
   - confirmação manual explícita;
   - registro em histórico (antes/depois);
   - verificação posterior (reabrir e comparar).
4. Nenhuma alteração executa sem confirmação, mesmo quando iniciada por workflow.

## Motivo
Preserva a integridade dos arquivos CAD e a rastreabilidade sem criar um processo corporativo de aprovação, que não é necessário para uso individual.

## Pendências
- Versão do Solid Edge e permissão de automação COM (confirmar na estação).
- Mapa de quais scripts atuais continuam em uso manual.
