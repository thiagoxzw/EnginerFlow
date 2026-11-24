# ADR-0006 — Protheus: importação manual de XLSX/CSV com mapeamento; API e escrita adiadas

- **Status:** Revisada (2026-11-24) — aguarda aprovação
- **Direcionamento do responsável:** importar XLSX e CSV exportados manualmente; API não confirmada, não bloquear; nunca alterar o banco do Protheus.

## Decisão
1. Importação de XLSX e CSV com:
   - mapeamento configurável de colunas e template reutilizável;
   - identificação automática de cabeçalho com confirmação;
   - detecção de delimitador (`;`, `,`, tabulação) e encoding (UTF-8, UTF-8 com BOM, Windows-1252);
   - códigos lidos e gravados como texto, preservando zeros à esquerda;
   - validação por coluna com relatório de linhas rejeitadas, sem descartar nada silenciosamente.
2. Conector `ProtheusFileConnector` real e `MockERPConnector` para testes.
3. `ProtheusAPIConnector` **não implementado**; fica registrado como possibilidade futura.
4. Proibido qualquer escrita no banco ou em arquivos do Protheus. Exportações geradas pelo EngiFlow são arquivos para importação manual pelo responsável.

## Pendências
Layouts reais serão fornecidos conforme forem identificados.
