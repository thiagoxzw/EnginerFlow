# Atualiza o demonstrativo na ordem segura:
# 1) verifica Docker e servicos; 2) backup e validacao do dump; 3) constroi imagens sem parar
# o demonstrativo; 4) substitui os conteineres; 5) aplica migracoes; 6) verifica saude e dados.
# Nao apaga volumes. Nenhum passo usa "down" ou "-v".
. (Join-Path $PSScriptRoot "_common.ps1")

function Get-DataCounts {
    # Contadores de dados usados para comparar antes e depois da atualizacao.
    $sql = "select (select count(*) from datasets)||'|'||(select count(*) from bom_structures)||'|'||(select count(*) from bom_lines)"
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $out = & docker compose -f $script:ComposeFile exec -T postgres psql -U engiflow -d engiflow -At -c $sql 2>$null
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    if ($code -ne 0) { throw "Nao foi possivel ler os contadores do banco (codigo $code)." }
    return ($out | Select-Object -Last 1).Trim()
}

# 1. Docker e servicos
Assert-Docker
Write-Host "[1/6] Docker em execucao."
Invoke-Compose 'up' '-d' 'postgres'
if (-not (Wait-ServiceHealthy -Service "postgres")) { throw "PostgreSQL nao ficou saudavel. Nada foi alterado." }
$before = Get-DataCounts
Write-Host "[1/6] Contadores antes (datasets|estruturas|linhas): $before"

# 2. Backup e validacao do dump
& (Join-Path $PSScriptRoot "Backup-EngiFlow.ps1")
$dump = Get-ChildItem (Join-Path $script:RepoRoot "backups") -Filter "engiflow-*.dump" |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $dump) { throw "Backup nao gerou arquivo de dump. Atualizacao interrompida." }
Invoke-Compose cp $dump.FullName "postgres:/tmp/validar.dump"
Invoke-Compose exec -T postgres pg_restore --list /tmp/validar.dump
Invoke-Compose exec -T postgres rm -f /tmp/validar.dump
Write-Host "[2/6] Backup validado: $($dump.Name)"

# 3. Construcao das imagens (os conteineres atuais continuam no ar)
Invoke-Compose build
Write-Host "[3/6] Imagens construidas sem parar o demonstrativo."

# 4. Substituicao dos conteineres que mudaram (volumes preservados)
Invoke-Compose 'up' '-d'
Write-Host "[4/6] Conteineres substituidos."

# 5. Migracoes (idempotente: aplica apenas o que falta)
if (-not (Wait-ServiceHealthy -Service "api")) { throw "API nao ficou saudavel apos a substituicao. Veja: scripts\local\Get-EngiFlowLogs.ps1 -Service api" }
Invoke-Compose exec -T api alembic upgrade head
Write-Host "[5/6] Migracoes aplicadas."

# 6. Saude e integridade dos dados
$ok = $true
foreach ($svc in @("postgres", "api", "web")) {
    if (Wait-ServiceHealthy -Service $svc) { Write-Host "[ok] $svc" } else { Write-Warning "[aviso] ${svc}: veja os logs"; $ok = $false }
}
$after = Get-DataCounts
if ($after -eq $before) {
    Write-Host "[ok] Contadores preservados: $after"
} else {
    Write-Warning "[aviso] Contadores mudaram: antes $before, depois $after. Confira antes de usar."
    $ok = $false
}
if ($ok) { Write-Host "[6/6] Atualizacao concluida." } else { Write-Warning "[6/6] Atualizacao concluida com avisos." }
