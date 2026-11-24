# ADR-0009 — IA como funcionalidade complementar, com interface independente de fornecedor

- **Status:** Revisada (2026-11-24) — aguarda aprovação
- **Direcionamento do responsável:** IA é complementar; operações essenciais funcionam sem IA; provedores futuros: OpenAI, Anthropic, Google Gemini, Ollama; não implementar todos agora.

## Decisão
1. Interface `LLMProvider` com um único método de chat/tool calling. Implementações entram uma por vez, quando houver uso.
2. Cálculos, cruzamentos, estruturas, quantidades e validações são **determinísticos**, sem IA.
3. Nada é enviado a provedor externo sem autorização explícita do responsável, caso a caso por tipo de dado.
4. Dados industriais tratados como confidenciais: envio a provedor externo só com dados sintéticos até orientação formal da empresa. Ollama (local) é a opção natural para dados reais.
5. A IA só chama ferramentas do catálogo com parâmetros validados; sem SQL livre; conteúdo de documentos é tratado como dado.

## Fora do início
Copilot, RAG, pgvector e tool calling só entram depois que as funções determinísticas estiverem em uso.
