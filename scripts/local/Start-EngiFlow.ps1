# Sobe PostgreSQL 17, API e web. Constrói as imagens se necessário. Não apaga nada.
. (Join-Path $PSScriptRoot "_common.ps1")
Assert-Docker
Invoke-Compose 'up' '-d' '--build'
foreach ($svc in @("postgres", "api", "web")) {
    if (Wait-ServiceHealthy -Service $svc) { Write-Host "[ok] $svc" } else { Write-Warning "[atenção] $svc não ficou saudável. Veja: scripts\local\Get-EngiFlowLogs.ps1 -Service $svc" }
}
Write-Host ""
Write-Host "Acesse no navegador: http://127.0.0.1:3000  (login com o usuário de demonstração)"
Write-Host "API (documentação interativa): http://127.0.0.1:8000/docs"
