# Ambiente local do EngiFlow (demonstração e uso individual)

Este guia sobe o EngiFlow no seu Windows com Docker Desktop. Tudo roda em `127.0.0.1`: nada é exposto na rede.
Os dados ficam em volumes Docker (`engiflow-pgdata` e `engiflow-data`) e são preservados ao parar ou atualizar.

## Pré-requisitos

- Docker Desktop instalado e em execução.
- PowerShell na pasta do projeto (`C:\Dev\EngiFlow`).

## Endereços

| O quê | Onde |
|---|---|
| Aplicação (Data Studio) | `http://127.0.0.1:3000/data-studio` |
| API (documentação interativa) | `http://127.0.0.1:8000/docs` |
| PostgreSQL | `127.0.0.1:5432` (usuário `engiflow`) |

## Operação do dia a dia

Todos os scripts ficam em `scripts\local` e não apagam volumes.

```powershell
scripts\local\Start-EngiFlow.ps1      # sobe postgres, api e web e aguarda ficarem saudáveis
scripts\local\Get-EngiFlowStatus.ps1  # estado dos serviços e resposta HTTP
scripts\local\Get-EngiFlowLogs.ps1 -Service api   # logs de um serviço
scripts\local\Stop-EngiFlow.ps1       # para os serviços; dados preservados
scripts\local\Update-EngiFlow.ps1     # reconstrói as imagens do código atual e aplica migrações
scripts\local\Backup-EngiFlow.ps1     # dump do banco e cópia dos arquivos originais
```

`Update-EngiFlow.ps1` aplica as migrações automaticamente, porque a API executa `alembic upgrade head` ao iniciar.

## Usuário de demonstração

```powershell
scripts\local\New-DemoUser.ps1
```

O script cria o usuário e grava e-mail e senha em `.env.local`, que é ignorado pelo git. A senha não é exibida no terminal: abra o arquivo para consultá-la.

## Dados sintéticos para teste

```powershell
scripts\local\Load-DemoData.ps1
```

Gera arquivos determinísticos em `demo-data\` (todos com nomes `SYN-*`, sem dados reais):

| Arquivo | Conteúdo | Uso sugerido |
|---|---|---|
| `SYN-cadastro-materiais.csv` | cadastro com códigos e unidades | cadastro para junção e comparação |
| `SYN-protheus-produtos.csv` | exportação com `B1_COD` e `B1_UM` | chave composta com o estoque |
| `SYN-estoque-componentes.csv` | saldo por código e unidade | chave composta com o Protheus |
| `SYN-kits.csv` | kit e código do componente | junção por código |
| `SYN-bom-valvula-vx100-revA.xlsx` e `revB.xlsx` | duas revisões de lista de materiais, com linhas de título | comparação entre revisões e cabeçalho |
| `SYN-relatorio-estoque.xlsx` | relatório com título acima do cabeçalho | seleção manual de cabeçalho |

Importe pelo Data Studio, em **Importar arquivos**. Você pode arrastar vários arquivos de uma vez; planilhas com várias abas aparecem com uma caixa por aba.

## Roteiro de teste do cruzamento (2B.3)

1. **Super-PROCV**: abra `SYN-protheus-produtos`, expanda **Cruzar com outra tabela (PROCV)**, escolha `SYN-estoque-componentes` e use as chaves `B1_COD = Código` e `B1_UM = Unidade`. Gere a prévia e confira as contagens. Zeros à esquerda devem aparecer preservados.
2. **Junção**: na mesma tabela, use **Juntar com outra tabela (junção)**. A prévia mostra a cardinalidade antes de criar a tabela; junções N:M pedem confirmação.
3. **Comparação por chave**: use **Comparar linhas por chave (avançado)** para ver adicionados, removidos, alterados (com coluna, antes e depois) e idênticos.
4. **Agregação**: use **Agrupar e agregar** para somar ou contar por coluna. Números usam precisão decimal; texto que não é número aparece como inválido.

Em cada criação de tabela derivada, o aviso mostra o nome, o número de linhas, a execução e o hash do resultado. As tabelas de origem não mudam.

## Exportação

Na prévia do PROCV, use **Exportar CSV** ou **Exportar XLSX**. O arquivo usa o mesmo cálculo da prévia.

## Atualização e reversão

- Atualizar: `scripts\local\Update-EngiFlow.ps1`. Se algo der errado, use `scripts\local\Backup-EngiFlow.ps1` antes de qualquer operação arriscada.
- Versões anteriores ficam no histórico do Git. Tabelas derivadas e versões de dados não são apagadas; a exclusão de tabela é lógica e pode ser desfeita em **Tabelas excluídas**.

## Limites e cuidados

- O ambiente é para uso individual e demonstração. Não há exposição pública nem múltiplos usuários.
- Tabelas muito grandes podem demorar; a prévia mostra apenas uma amostra, mas a tabela derivada e a exportação contêm o resultado completo.
- Não use dados reais em testes automatizados. Os testes E2E usam somente os arquivos `SYN-*`.
