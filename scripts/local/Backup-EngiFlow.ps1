# Backup local: dump do PostgreSQL (formato custom) e cópia do volume de arquivos originais.
# Grava em backups\ (ignorada pelo git). Não altera nem apaga nada no ambiente.
. (Join-Path $PSScriptRoot "_common.ps1")
Assert-Docker
$dir = Join-Path $script:RepoRoot "backups"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"

# O dump é gerado dentro do contêiner e copiado em binário (nunca capturado como texto).
Invoke-Compose exec -T postgres sh -c "pg_dump -U engiflow -d engiflow -Fc -f /tmp/engiflow-backup.dump"
$dump = Join-Path $dir "engiflow-$stamp.dump"
Invoke-Compose cp "postgres:/tmp/engiflow-backup.dump" $dump
Invoke-Compose exec -T postgres sh -c "rm -f /tmp/engiflow-backup.dump"
Write-Host "Dump do banco: $dump"

# Nome EXATO do volume deste projeto ("engiflow" + "_engiflow-data"). Um filtro por substring
# poderia pegar o volume de outro projeto (auditoria, E2E) e copiar os arquivos errados.
$volume = (docker volume ls -q | Where-Object { $_ -eq "engiflow_engiflow-data" } | Select-Object -First 1)
if ($volume) {
    $tar = "engiflow-originais-$stamp.tar"
    # docker escreve a baixa da imagem no stderr: o critério é o código de saída.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        docker run --rm -v "${volume}:/data:ro" -v "${dir}:/backup" alpine tar -cf "/backup/$tar" -C /data . 2>&1 | ForEach-Object { "$_" } | Out-Null
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    if ($code -ne 0) { throw "Cópia dos arquivos originais falhou (código $code)." }
    Write-Host "Arquivos originais: $(Join-Path $dir $tar)"
}
