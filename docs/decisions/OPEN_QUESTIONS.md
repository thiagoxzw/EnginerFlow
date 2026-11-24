# Questões pendentes para revisão

Agrupadas para uma única rodada de respostas. Cada item indica o que trava e o que fica pendente sem resposta.

## A. Infraestrutura e ambiente
1. Onde a plataforma será hospedada (servidor interno, nuvem privada ou híbrido)? *Trava: DEPLOYMENT, Fase 1.*
2. Autorizar instalação de Node.js LTS, Docker Desktop e PostgreSQL nesta máquina? *Trava: Fase 1 local.*
3. Local do repositório: mover para fora do OneDrive? Hospedagem Git (GitHub privado, Azure DevOps ou outro)? *Trava: ADR-0011.*

## B. Identidade e acesso
4. Autenticação: SSO corporativo (qual provedor) ou usuários locais? MFA obrigatório? *Trava: F1-06.*
5. Papéis iniciais e quantidade aproximada de usuários. *Trava: RBAC.*

## C. CAD e Solid Edge
6. Versão do Solid Edge, licença e permissão de automação COM na estação. *Trava: Fase 4.*
7. A estação terá usuário logado (sessão interativa) para o agente? *Trava: LOCAL_AGENT_DESIGN.*
8. O código de codificação de peças atual (scripts que alteram bytes de montagens) deve ser tratado como ação manual até a integração COM existir? Confirme a decisão da ADR-0005. *Trava: uso dos scripts existentes.*

## D. ERP (TOTVS Protheus)
9. Quais exportações do Protheus estão disponíveis hoje (formato, layout, frequência)? *Trava: F5 e exportação de F3-11.*
10. Existe API ou serviço autorizado do Protheus? Quem é o responsável técnico? *Trava: ProtheusAPIConnector.*

## E. Regras de negócio
11. Política de kit: quando um kit e seus componentes aparecem, a compra é do kit, dos componentes ou o kit é só agrupamento? *Trava: I-08 e cálculo de compra.*
12. Regra de estoque reservado: quais saldos são considerados disponíveis? *Trava: CA-07.*
13. Classificação oficial de componentes (fabricado, comprado, submontagem, kit): quem aprova as regras? *Trava: F3-06.*
14. Unidades de medida com conversão são necessárias no MVP? *Trava: DOMAIN_MODEL.*

## F. Dados e IA
15. Classificação oficial dos dados industriais e quem autoriza o uso de serviços externos de IA. *Trava: Fase 7.*
16. Provedor de IA preferido (externo autorizado, local ou ambos) e hardware disponível para modelo local. *Trava: X-03, X-04.*
17. Retenção de dados: prazos para auditoria, execuções e arquivos originais. *Trava: DATABASE_SCHEMA.*

## G. Metas e operação
18. RPO, RTO e volume real de dados (linhas, arquivos, usuários simultâneos) para definir metas de desempenho. *Trava: metas não funcionais.*
19. Limites de tamanho de arquivo aceitáveis para planilhas e BOM. *Trava: SECURITY_MODEL.*

## H. Governança
20. Quem é o responsável técnico e quem aprova PRs e ADRs? *Trava: governança.*
21. Aprovação desta Fase 0: aceitar as ADRs como estão, alterar alguma, ou recusar alguma? *Trava: início da Fase 1.*
