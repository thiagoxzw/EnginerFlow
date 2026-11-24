# EngiFlow — Design system (diretrizes)

Status: **Proposta** (Fase 0). Tokens e componentes serão definidos na Fase 1.

## Princípios

Confiabilidade, organização, precisão, produtividade. Dados industriais são o foco: tabelas legíveis, contraste alto, pouca decoração.

Referências conceituais de qualidade (sem copiar identidade visual): Linear, Vercel, Notion, n8n e plataformas corporativas. Evitar animações excessivas e gradientes decorativos.

## Tokens

- Cores definidas como tokens semânticos (`--color-bg`, `--color-fg`, `--color-muted`, `--color-accent`, `--color-success`, `--color-warning`, `--color-danger`), com tema claro e escuro.
- Estados de erro, aviso e sucesso nunca dependem só de cor (ícone e texto também).
- Escala tipográfica com números tabulares em colunas numéricas.

## Componentes base

shadcn/ui sobre Tailwind. Adicionais previstos: `DataTable` (TanStack Table, virtualização acima de volume definido), `TreeView` (BOM), `FlowCanvas` (React Flow, Fase 6), `Stat` (indicadores), `EmptyState`, `ErrorState`, `LoadingState`, `CommandPalette`, `Breadcrumb`.

## Acessibilidade e teclado

- WCAG 2.2 AA como meta.
- Navegação por teclado completa em tabelas, árvores e command palette.
- Foco visível; ordem lógica; rótulos em todos os campos.

## Idioma

Português do Brasil como padrão; strings externalizadas para permitir inglês.

## Estados obrigatórios

Toda tela de dados: carregamento, vazio, erro, sem permissão, sucesso de operação com feedback.

## Validação

Validação de formulário com React Hook Form + Zod; mesmas regras de servidor quando possível (schemas compartilhados em `packages/contracts`).
