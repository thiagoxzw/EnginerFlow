# Para os serviços. Mantém contêineres e volumes (dados preservados).
. (Join-Path $PSScriptRoot "_common.ps1")
Assert-Docker
Invoke-Compose stop
Write-Host "Serviços parados. Dados e volumes preservados. Para subir de novo: scripts\local\Start-EngiFlow.ps1"
