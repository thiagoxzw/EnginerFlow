# Cria o usuário de demonstração LOCAL de forma segura:
# - a senha é gerada aleatoriamente aqui e gravada somente em .env.local (ignorado pelo git);
# - a senha nunca é impressa nem passada por argumento de linha de comando;
# - o EngiFlow é de uso individual: se já existir um usuário, o script informa e não altera nada.
. (Join-Path $PSScriptRoot "_common.ps1")
Assert-Docker

$email = "demo@example.com"   # endereço fictício, reservado para documentação
$name = "Demonstração (sintético)"

if (Test-Path $script:EnvLocal) {
    $existing = Get-Content $script:EnvLocal -Raw
    if ($existing -match "ENGIFLOW_DEMO_PASSWORD=") {
        Write-Host "Usuário de demonstração já configurado. Senha em: $($script:EnvLocal) (não é exibida aqui)."
        exit 0
    }
}

$bytes = New-Object byte[] 24
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$password = [Convert]::ToBase64String($bytes).Replace("+", "A").Replace("/", "B").Replace("=", "")

# Passa a senha ao contêiner por variável de ambiente (não por argumento).
$output = docker compose -f $script:ComposeFile exec -T -e "ENGIFLOW_DEMO_PASSWORD=$password" api `
    python -m engiflow_api.cli create-user --email $email --name $name --password-env ENGIFLOW_DEMO_PASSWORD 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Não foi possível criar o usuário: $output"
    Write-Host "Se já existe um usuário (uso individual), use a senha já guardada em .env.local."
    exit 1
}
Add-Content -Path $script:EnvLocal -Value "ENGIFLOW_DEMO_EMAIL=$email"
Add-Content -Path $script:EnvLocal -Value "ENGIFLOW_DEMO_PASSWORD=$password"
Write-Host "Usuário de demonstração criado: $email"
Write-Host "Senha gravada em: $($script:EnvLocal) (arquivo ignorado pelo git). Abra o arquivo para consultá-la."
