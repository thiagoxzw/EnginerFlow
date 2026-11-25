# Mostra os logs recentes de um serviço (padrão: todos). Use -Follow para acompanhar.
param(
    [ValidateSet("postgres", "api", "web")][string]$Service,
    [int]$Tail = 200,
    [switch]$Follow
)
. (Join-Path $PSScriptRoot "_common.ps1")
Assert-Docker
$args = @("logs", "--tail", "$Tail")
if ($Follow) { $args += "--follow" }
if ($Service) { $args += $Service }
Invoke-Compose @args
