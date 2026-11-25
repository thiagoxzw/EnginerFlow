# Auditoria de UX e funcional do Data Studio

**Escopo:** inventário pelo código-fonte (`apps/web/src/components/data-studio/*.tsx`), avaliação visual no navegador
e testes funcionais com dados **exclusivamente sintéticos**.
**Ambientes usados:**
- *Demonstrativo* (`http://127.0.0.1:3000`): usuário de demonstração. Contém a tabela "Codigos totus - separado",
  do proprietário, que **não foi alterada**, apenas aberta para leitura. Também contém duas tabelas sintéticas que
  importei na primeira captura (`SYN-cadastro-materiais` e `SYN-bom-valvula-vx100-revA`); seguem lá e podem ser
  removidas a seu pedido.
- *Auditoria isolada* (`http://127.0.0.1:3100`, projeto Docker `engiflow-audit`, portas e volumes próprios): onde
  foram feitos os testes funcionais de escrita. Usuário e senha ficam em `.env.audit`, fora do repositório.

Capturas e resultados brutos ficam fora do repositório, em `C:\Dev\EngiFlow-dados\audit\` e
`C:\Dev\EngiFlow-dados\audit-funcional\`.

## 1. Resultados funcionais verificados (ambiente isolado, dados sintéticos)

| Fluxo | Resultado observado | Situação |
|---|---|---|
| Login | entrou com o usuário de auditoria | aprovado |
| Importação de CSV e XLSX (3 arquivos) | 3 tabelas criadas com contagens corretas (15, 13 e 10 linhas) | aprovado |
| Importação de arquivo binário não reconhecido | mensagem "Conteúdo binário não reconhecido. Envie um XLSX ou CSV de texto." exibida sob o nome do arquivo | aprovado, com ressalva (ver UX-10) |
| Filtro "contém" sem distinção de acento e caixa | "PARAFUSO" retornou 2 linhas, com "Parafuso" | aprovado |
| Filtros combinados (dois critérios) | 2 linhas, coerente com os dados | aprovado |
| Pesquisa global ("m8") | pesquisa executada | aprovado |
| Ordenação por coluna numérica | cabeçalho com `aria-sort="ascending"` | aprovado |
| Substituição em lote com prévia | prévia "2 linha(s) e 2 célula(s) serão alteradas" e 2 ocorrências após aplicar | aprovado |
| Desfazer / refazer da substituição | desfazer removeu as ocorrências (0); refazer restaurou (2) | aprovado |
| Exclusão lógica de linha com confirmação | 15 → 14 linhas; desfazer → 15 | aprovado |
| Comparação entre duas tabelas (códigos) | exige mapear a coluna de código antes; mensagem clara | aprovado, com ressalva (UX-11) |
| Exportação CSV | arquivo gerado `SYN-cadastro-materiais_dados.csv` | aprovado |
| Persistência após reiniciar os contêineres | as 3 tabelas e as contagens permaneceram | aprovado |
| Erros no servidor (HTTP 5xx) durante os testes | nenhum | aprovado |

## 2. Origem do erro 404

- **URL:** `http://127.0.0.1:3000/favicon.ico` (e, por tentativa, `/icon.png` e `/apple-icon.png`).
- **Causa:** a aplicação não tem ícone; o navegador o solicita sozinho ao abrir qualquer página.
- **Impacto:** nenhum na funcionalidade. Só aparece no console do navegador.
- **Correção sugerida:** adicionar um ícone ao projeto. Prioridade P3.

## 3. Classificação das funcionalidades

| Funcionalidade | Classificação |
|---|---|
| Importação por seletor de arquivo (CSV/XLSX) | Implementada e acessível |
| Importação por arrastar e soltar | Não implementada |
| Seleção de aba Excel | Implementada, mas pouco intuitiva (campo de texto) |
| Detecção de abas Excel na interface | Implementada somente no backend (`POST /api/v1/datasets/inspect`) |
| Progresso da importação | Não implementada |
| Importação de múltiplos arquivos de uma vez | Parcialmente implementada: um por vez, repetindo o envio |
| Mapeamento de colunas | Implementada e acessível |
| Seleção manual de cabeçalho | Implementada, mas pouco intuitiva (prévia em texto unido por `|`) |
| Prévia, filtros, pesquisa, ordenação | Implementada e acessível |
| Substituição em lote com prévia | Implementada e acessível |
| Seleção e exclusão lógica de linhas | Implementada e acessível |
| Desfazer / refazer e histórico | Implementada e acessível; versões aparecem só como contagem |
| Modelos de mapeamento | Implementada e acessível |
| Renomear, excluir e restaurar tabelas | Implementada e acessível |
| Exportação | Implementada e acessível (CSV e XLSX) |
| Duplicatas | Implementada e acessível |
| Comparação de códigos | Implementada, escopo limitado |
| Comparação avançada | Planejada para 2B.3; não exposta na interface |
| Super-PROCV e junções | Implementadas somente no backend; sem tela |
| Agrupamento e consolidação | Não implementada (2B.3) |
| Dashboard | Implementada, com atividade recente e link para o Data Studio |
| Menu lateral entre módulos | Não implementada |

## 4. Problemas identificados

| ID | Funcionalidade | Comportamento atual | Comportamento esperado | Prioridade | Complexidade | Fase |
|---|---|---|---|---|---|---|
| UX-01 | Organização da tela | Mapeamento, histórico, gerenciamento, cabeçalho e modelos ficam acima da tabela; a tabela começa após ~2.800 px de rolagem | Tabela como elemento central, visível sem rolagem longa | P0 | média | Reorganização pontual agora |
| UX-02 | Importação | Sem arrastar e soltar | Arrastar e soltar sobre a área de importação | P1 | baixa | Agora (melhoria autorizada) |
| UX-03 | Importação de Excel | Aba digitada em texto livre | Lista de abas detectadas, com seleção de uma ou várias | P1 | média | Agora (usa `inspect`) |
| UX-04 | Importação | Sem progresso de envio | Progresso real do envio; indicador indeterminado no processamento | P2 | média | Agora |
| UX-05 | Cabeçalho | Prévia em texto unido por `|` | Tabela com colunas alinhadas | P2 | baixa | Agora (prévia tabular) |
| UX-06 | Comparação | Só compara códigos; exige mapear antes sem indicação no fluxo | Comparação por chave composta, com indicação do que falta mapear | P1 | alta | 2B.3 |
| UX-07 | Super-PROCV e junções | Sem tela | Telas com seleção, prévia, contagens e exportação | P0 para a 2B.3 | alta | 2B.3 |
| UX-08 | Histórico | Versões só como contagem | Lista de versões com data e operação | P2 | média | 2B.4 |
| UX-09 | Navegação | Dashboard com um único caminho | Menu lateral entre módulos | P2 | média | 2B.4 |
| UX-10 | Erro de importação | Mensagem aparece como texto comum, não como alerta | Mensagem em destaque, com papel de alerta | P2 | baixa | Agora |
| UX-11 | Comparação | Erro de mapeamento aparece só depois do clique | Indicar na própria seção que é preciso mapear o código | P2 | baixa | Agora |
| UX-12 | Favicon | 404 para `/favicon.ico` | Ícone do projeto | P3 | baixa | Agora |

## 5. Notas (0 a 10)

| Dimensão | Nota | Justificativa |
|---|---|---|
| Interface | 5 | componentes bem definidos, mas a página é uma coluna longa; dados ficam longe |
| Usabilidade | 5 | fluxos completos funcionam; importação e cabeçalho exigem passos extras |
| Funcionalidades | 7 | cobertura ampla e verificada; Super-PROCV e junções ainda sem tela |
| Desempenho | 5 | medido em 100 mil e 500 mil linhas; substituição e ordenação carregam a tabela inteira |
| Integridade | 8 | desfazer/refazer, exclusão lógica e persistência verificados; versões imutáveis |
| Acessibilidade | 4 | não medida com ferramenta; poucos destaques de erro com papel de alerta |
| Maturidade geral | 6 | fluxos verificados de ponta a ponta; falta organização visual e importação mais fluida |

## 6. Proposta de reorganização (autorizada; aplicada em etapa separada)

- Cabeçalho compacto com nome, registros, colunas e versão atual.
- Tabela de dados no centro da página, com pesquisa, filtros e ordenação na barra acima dela.
- Abas ou painéis para **Transformar**, **Cruzar tabelas**, **Mapeamento** e **Histórico**.
- Gerenciamento da tabela em menu contextual; cabeçalho em painel dedicado.
- Preservar todas as funções e regras de negócio.

## 7. Próximas etapas

1. Reorganização visual pontual (UX-01), com capturas antes e depois.
2. Importação: arrastar e soltar, lista de abas, prévia tabular, progresso (UX-02 a UX-05, UX-10).
3. Ajustes pequenos de comparação e favicon (UX-11, UX-12).
4. Commit do código de inspeção de arquivos, ainda não commitado, após testes.
5. Continuação da 2B.3 (Super-PROCV e junções com tela, comparação avançada, agrupamento).

Itens fora desta etapa: editor completo de células, virtualização, cálculos e otimização de armazenamento (2B.4).

## Medições pós-reorganização (dados sintéticos, isolated E2E)

| Resolução | Topo da tabela antes (px) | depois (px) | Altura da página antes | depois | Overflow horizontal |
|---|---|---|---|---|---|
| 1920×1080 | 137 | 141 | 1697 | 1080 | 0 / 0 |
| 1440×900 | 137 | 141 | 1861 | 900 | 0 / 0 |
| 1366×768 | 137 | 141 | 1861 | 811 | 0 / 0 |
| 390×844 | 1031 (primeira linha fora da tela) | 249 (visível) | 3117 | 1849 | 0 / 0 |

Capturas e métricas ficam no diretório de evidências local (não versionado), com dados sintéticos.

### Problemas encontrados nesta etapa
- Mobile: lateral de importação e lista antes da tabela (corrigido pela ordem visual no celular).
- Título duplicado na lateral (corrigido).
- Ações de linha ocupando espaço vazio (agora contextuais).
- Confirmação de ação sumia com a seleção (agora na barra da tabela).

### Pendências de experiência para a Fase 3
- Reordenar e redimensionar colunas; fixação de colunas.
- Seleção de intervalos com Shift+setas; Ctrl+A e Delete.
