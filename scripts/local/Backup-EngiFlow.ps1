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

$volume = (docker volume ls -q --filter "name=engiflow-data" | Select-Object -First 1)
if ($volume) {
    $tar = "engiflow-originais-$stamp.tar"
    docker run --rm -v "${volume}:/data:ro" -v "${dir}:/backup" alpine tar -cf "/backup/$tar" -C /data . | Out-Null
    Write-Host "Arquivos originais: $(Join-Path $dir $tar)"
}
