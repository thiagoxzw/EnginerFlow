# Funções comuns dos scripts locais do EngiFlow. Nenhum script aqui apaga volumes ou dados.
$ErrorActionPreference = "Stop"
$script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$script:ComposeFile = Join-Path $script:RepoRoot "docker-compose.yml"
$script:EnvLocal = Join-Path $script:RepoRoot ".env.local"

function Assert-Docker {
    docker info --format "{{.ServerVersion}}" *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker não está em execução. Abra o Docker Desktop e tente novamente."
    }
}

function Invoke-Compose {
    # docker escreve progresso no stderr; com ErrorActionPreference=Stop isso viraria exceção.
    # O critério de falha é o código de saída.
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & docker compose -f $script:ComposeFile @Args 2>&1 | ForEach-Object { "$_" }
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    if ($code -ne 0) { throw "docker compose $($Args -join ' ') falhou (código $code)." }
}

function Get-ServiceHealth {
    param([string]$Service)
    $id = (docker compose -f $script:ComposeFile ps -q $Service 2>$null)
    if (-not $id) { return "parado" }
    $status = docker inspect --format "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}" $id 2>$null
    if ($status) { return $status.Trim() }
    return "desconhecido"
}

function Wait-ServiceHealthy {
    param([string]$Service, [int]$TimeoutSeconds = 180)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $state = Get-ServiceHealth -Service $Service
        if ($state -eq "healthy" -or $state -eq "running") { return $true }
        if ($state -eq "unhealthy") { return $false }
        Start-Sleep -Seconds 3
    }
    return $false
}
