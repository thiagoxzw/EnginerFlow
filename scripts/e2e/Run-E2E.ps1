# Executa os testes Playwright em um stack ISOLADO e descartável.
#
# Isolamento:
# - projeto Compose próprio ("engiflow-e2e"): contêineres e volumes com esse prefixo;
# - portas próprias (web 3210, api 8210, postgres 5542), diferentes do ambiente demonstrativo;
# - usuário e senha gerados aleatoriamente aqui, só em memória (nada é gravado em arquivo);
# - ao final o projeto "engiflow-e2e" é removido com seus volumes, para que a próxima execução
#   parta de um estado previsível. O ambiente demonstrativo nunca é referenciado.
#
# Uso: scripts\e2e\Run-E2E.ps1            (remove o stack ao final)
#      scripts\e2e\Run-E2E.ps1 -KeepStack (mantém o stack para inspeção)
param(
    [switch]$KeepStack,
    # Spec específico (ex.: e2e/visual-evidence.spec.ts). Vazio = suíte completa.
    [string]$Spec = ""
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$compose = Join-Path $root "docker-compose.yml"
$project = "engiflow-e2e"
$webDir = Join-Path $root "apps\web"

function Invoke-E2ECompose {
    # docker escreve progresso no stderr; com ErrorActionPreference=Stop isso viraria exceção.
    # Por isso o critério de falha é o código de saída, não o stderr.
    param([string[]]$ComposeArgs)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & docker compose -p $project -f $compose @ComposeArgs 2>&1 | ForEach-Object { "$_" }
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    if ($code -ne 0) { throw "docker compose falhou ($code): $($ComposeArgs -join ' ')" }
}

function New-Secret {
    $bytes = New-Object byte[] 24
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return [Convert]::ToBase64String($bytes).Replace("+", "A").Replace("/", "B").Replace("=", "")
}

# Portas e segredos só para este processo. Falha cedo se alguma porta já estiver em uso.
$env:ENGIFLOW_PG_PORT = "5542"
$env:ENGIFLOW_API_PORT = "8210"
$env:ENGIFLOW_WEB_PORT = "3210"
# Remove SOMENTE o projeto E2E (de execuções anteriores, inclusive com -KeepStack) antes de checar portas.
Invoke-E2ECompose @("down", "-v", "--remove-orphans")
foreach ($port in @($env:ENGIFLOW_PG_PORT, $env:ENGIFLOW_API_PORT, $env:ENGIFLOW_WEB_PORT)) {
    if (Get-NetTCPConnection -LocalPort ([int]$port) -State Listen -ErrorAction SilentlyContinue) {
        throw "A porta $port está em uso. Escolha outra em Run-E2E.ps1 (ENGIFLOW_*_PORT)."
    }
}
$env:ENGIFLOW_DB_PASSWORD = New-Secret
$e2eEmail = "e2e@example.com"
$e2ePassword = New-Secret

$exit = 1
try {
    # Estado previsível: começa sem volumes deste projeto.
    Invoke-E2ECompose @("down", "-v", "--remove-orphans")
    Invoke-E2ECompose @("up", "-d", "--build")

    # Aguarda os healthchecks (postgres, api com migrações, web).
    $deadline = (Get-Date).AddMinutes(8)
    do {
        Start-Sleep -Seconds 5
        $health = & docker compose -p $project -f $compose ps --format "{{.Service}} {{.Status}}" 2>$null
        $ready = ($health -match "healthy").Count -ge 3
    } until ($ready -or (Get-Date) -gt $deadline)
    if (-not $ready) { throw "Stack E2E não ficou saudável. Veja: docker compose -p $project logs" }

    # Usuário único do stack E2E (o banco é novo, então o comando é permitido).
    & docker compose -p $project -f $compose exec -T -e "E2E_PW=$e2ePassword" api `
        python -m engiflow_api.cli create-user --email $e2eEmail --name "E2E (sintético)" --password-env E2E_PW 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Não foi possível criar o usuário do stack E2E." }

    $env:E2E_BASE_URL = "http://127.0.0.1:$($env:ENGIFLOW_WEB_PORT)"
    $env:E2E_EMAIL = $e2eEmail
    $env:E2E_PASSWORD = $e2ePassword
    if (-not $env:E2E_CHROME_PATH -and (Test-Path "C:\Program Files\Google\Chrome\Application\chrome.exe")) {
        $env:E2E_CHROME_PATH = "C:\Program Files\Google\Chrome\Application\chrome.exe"
    }

    Push-Location $webDir
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        # Avisos de depreciação do Node não são falhas de teste: o critério é o código de saída.
        $env:NODE_NO_WARNINGS = "1"
        $playwrightArgs = @("exec", "playwright", "test", "--reporter=list")
        if ($Spec) { $playwrightArgs += $Spec }
        & pnpm @playwrightArgs 2>&1 | ForEach-Object { "$_" }
        $exit = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
        Pop-Location
    }
} finally {
    if (-not $KeepStack) {
        Invoke-E2ECompose @("down", "-v", "--remove-orphans")
    }
    Remove-Item Env:E2E_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:E2E_EMAIL -ErrorAction SilentlyContinue
}
exit $exit
