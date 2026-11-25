# Executa o benchmark 2B.3 em um PostgreSQL DEDICADO (projeto "engiflow-bench").
#
# Isolamento e proteções:
# - projeto Compose próprio (scripts\bench\docker-compose.bench.yml), volume próprio, porta própria;
# - senha gerada aleatoriamente aqui, só em memória;
# - o script Python recusa qualquer banco que não seja "engiflow_bench" em 127.0.0.1 ou a porta 5432;
# - o ambiente demonstrativo nunca é referenciado.
#
# Uso: scripts\bench\Run-Bench.ps1 -Rows 500000 -Scenario within-limit [-KeepStack]
# Cenários: duplicates (acima do limite, recusado) e within-limit (dentro do limite).
# Cada resultado é registrado no log assim que a operação termina (linhas "RESULTADO | ...").
param(
    [int]$Rows = 500000,
    [ValidateSet("duplicates", "within-limit")][string]$Scenario = "within-limit",
    [int]$Port = 5552,
    [switch]$KeepStack
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$benchCompose = Join-Path $PSScriptRoot "docker-compose.bench.yml"
$apiDir = Join-Path $root "apps\api"
$python = Join-Path $apiDir ".venv\Scripts\python.exe"
$log = Join-Path $env:TEMP "bench-$Scenario-$Rows.log"

if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    throw "A porta $Port está em uso. Escolha outra com -Port."
}

function Invoke-BenchCompose {
    param([string[]]$ComposeArgs)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & docker compose -f $benchCompose @ComposeArgs 2>&1 | ForEach-Object { "$_" }
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    if ($code -ne 0) { throw "docker compose (bench) falhou ($code): $($ComposeArgs -join ' ')" }
}

$bytes = New-Object byte[] 24
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$secret = [Convert]::ToBase64String($bytes).Replace("+", "A").Replace("/", "B").Replace("=", "")
$env:ENGIFLOW_BENCH_PASSWORD = $secret
$env:ENGIFLOW_BENCH_PORT = "$Port"

$exit = 1
try {
    Invoke-BenchCompose @("down", "-v", "--remove-orphans")
    Invoke-BenchCompose @("up", "-d")
    $deadline = (Get-Date).AddMinutes(3)
    do {
        Start-Sleep -Seconds 3
        $status = & docker compose -f $benchCompose ps --format "{{.Status}}" 2>$null
    } until (($status -match "healthy") -or (Get-Date) -gt $deadline)
    if (-not ($status -match "healthy")) { throw "PostgreSQL de benchmark não ficou saudável." }

    $env:ENGIFLOW_BENCH_DATABASE_URL = "postgresql+psycopg://bench:$secret@127.0.0.1:$Port/engiflow_bench"
    $env:PYTHONUNBUFFERED = "1"
    $env:PYTHONIOENCODING = "utf-8"

    # Execução síncrona: o código de saída do próprio Python é o critério.
    Push-Location $apiDir
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $resultsFile = Join-Path $env:TEMP "bench-results-$Scenario-$Rows.txt"
        if (Test-Path $resultsFile) { Remove-Item $resultsFile }
        & $python "scripts\bench_2b3_postgres.py" --rows $Rows --scenario $Scenario --results-file $resultsFile 2>"$log.err" |
            ForEach-Object { "$_" } | Out-File -FilePath $log -Encoding utf8
        $exit = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
        Pop-Location
    }

    Add-Content -Path $log -Value "[código de saída: $exit]" -Encoding utf8
    Get-Content $log -Encoding utf8
    if ((Test-Path "$log.err") -and ((Get-Item "$log.err").Length -gt 0)) {
        Write-Host "--- stderr do benchmark ---"
        Get-Content "$log.err" -Encoding utf8 | Select-Object -Last 40
    }
} finally {
    Remove-Item Env:ENGIFLOW_BENCH_DATABASE_URL -ErrorAction SilentlyContinue
    if (-not $KeepStack) {
        Invoke-BenchCompose @("down", "-v", "--remove-orphans")
    }
    Remove-Item Env:ENGIFLOW_BENCH_PASSWORD -ErrorAction SilentlyContinue
}
exit $exit
