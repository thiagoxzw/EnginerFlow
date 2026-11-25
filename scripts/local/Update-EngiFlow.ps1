# Atualiza a aplicação: faz backup do banco, reconstrói as imagens e reinicia. Não apaga volumes.
. (Join-Path $PSScriptRoot "_common.ps1")
Assert-Docker
& (Join-Path $PSScriptRoot "Backup-EngiFlow.ps1")
Invoke-Compose build
Invoke-Compose up -d
foreach ($svc in @("postgres", "api", "web")) {
    if (Wait-ServiceHealthy -Service $svc) { Write-Host "[ok] $svc" } else { Write-Warning "[atenção] $svc: veja os logs" }
}
