# EngiFlow — Estratégia de integração

Status: **Proposta** (Fase 0). Nenhuma integração foi testada em ambiente real.

## Princípios

1. Núcleo de engenharia não conhece fornecedores. Conectores convertem dados externos para o **modelo canônico** do EngiFlow.
2. Ordem de preferência: (1) APIs oficiais ou serviços autorizados; (2) REST corporativo customizado; (3) importação/exportação de arquivos; (4) rotinas oficialmente suportadas; (5) RPA como último recurso.
3. Nenhum endpoint é presumido. Conectores reais só entram após confirmação de existência e acesso.
4. Nenhuma gravação direta em banco de ERP.
5. Gravação em produção só após validação em homologação, com aprovação explícita.

## Interfaces (portas)

```python
class CADConnector(Protocol):
    def extract_bom(self, request: BomExtractRequest) -> CanonicalBom: ...
    def get_properties(self, request: PropertyRequest) -> CanonicalProperties: ...
    def list_occurrences(self, request: OccurrenceRequest) -> list[Occurrence]: ...

class ERPConnector(Protocol):
    def get_material(self, request: MaterialRequest) -> CanonicalMaterial: ...
    def get_inventory(self, request: InventoryRequest) -> CanonicalInventory: ...
    def get_structure(self, request: StructureRequest) -> CanonicalBom: ...
    def prepare_export(self, request: ExportRequest) -> ExportArtifact: ...  # sem escrita
```

Modelo canônico vive em `packages/contracts`. Erros de conector são tipados (`ConnectorUnavailable`, `ConnectorContractViolation`, `AuthorizationDenied`) e nunca vazam detalhes internos de terceiros para o usuário.

## Conectores — status e plano

| Conector | Fase | Modo inicial | Status |
|---|---|---|---|
| `MockCADConnector` | 1–4 | dados sintéticos | Planejado |
| `SolidEdgeConnector` | 4 | somente leitura, via COM no agente | Planejado; bloqueado por licença/versão/acesso |
| `MockERPConnector` | 2–5 | dados sintéticos | Planejado |
| `ProtheusFileConnector` | 5 | importar/exportar arquivos | Planejado; layouts pendentes |
| `ProtheusAPIConnector` | 5+ | condicionado a integração autorizada | **Bloqueado por dependência externa** (endpoints desconhecidos) |
| `ExcelConnector` | 2 | leitura com OpenPyXL, texto forçado | Planejado |
| `CSVConnector` | 2 | leitura com detecção de encoding e separador | Planejado |
| `PDFConnector` | 7 | PyMuPDF, extração com referência de página | Planejado |

## Solid Edge

- Automação COM oficial (API do Solid Edge via PyWin32) no agente Windows.
- Requer sessão Windows interativa para a maioria das operações; avaliar execução como tarefa agendada em sessão de usuário (pendente).
- Versão do Solid Edge, licença e permissão de automação precisam ser confirmadas (pendente).
- **Somente leitura** até o fim da Fase 4. Alterações exigem backup, dry run, pré-visualização, aprovação, validação, auditoria e verificação posterior.
- **Não manipular estrutura binária** de `.asm`/`.par` para trocar nomes, códigos ou referências (ADR-0005).

## Protheus

- Estratégia inicial: importação de exportações do Protheus (arquivos) e exportação de arquivos compatíveis.
- Consulta de estoque e estrutura por API só após confirmação, pela área de ERP, de endpoint autorizado e conta de serviço com permissões mínimas.
- Credenciais reais não são usadas em desenvolvimento. Ambiente de homologação obrigatório antes de qualquer escrita.
- Layouts de exportação ainda não foram formalizados; pendência de levantamento com o time de ERP.

## Excel e CSV

- Leitura somente-leitura do arquivo original. Arquivo original é copiado para armazenamento com hash e nunca sobrescrito.
- Colunas de código sempre lidas como texto.
- Limites: tamanho máximo, número máximo de linhas e de colunas (valores a definir após medição).
- Fórmulas em células não são executadas; células com fórmula são tratadas como valor em cache ou erro.

## Matriz de risco de integração

| Risco | Mitigação |
|---|---|
| Layout de arquivo muda sem aviso | Mapeamento versionado + validação de cabeçalho + relatório de colunas ausentes |
| Conector real indisponível | Mock com contrato de testes de contrato idênticos ao real |
| Escrita acidental em produção | Ambiente separado, sem credencial de produção em dev, gate de aprovação |
| Dado industrial enviado a serviço externo | Política de dados (ver `SECURITY_MODEL.md`) |
