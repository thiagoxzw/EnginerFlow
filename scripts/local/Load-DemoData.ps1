# Gera os arquivos demonstrativos (sintéticos) em demo-data\ para importação manual pelo Data Studio.
# Não importa nada automaticamente: a importação é feita pela interface, como em uso real.
. (Join-Path $PSScriptRoot "_common.ps1")
$python = Join-Path $script:RepoRoot "apps\api\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Ambiente Python da API não encontrado. Rode: cd apps\api; uv sync --locked" }
$out = Join-Path $script:RepoRoot "demo-data"
& $python (Join-Path $script:RepoRoot "scripts\demo\generate_demo_data.py") --out $out | Out-Null
Write-Host "Arquivos demonstrativos em: $out"
Get-ChildItem $out | ForEach-Object { Write-Host "  $($_.Name)" }
Write-Host "Importe pelo Data Studio (Importar arquivo) na ordem sugerida em docs\operations\LOCAL_SETUP.md."
