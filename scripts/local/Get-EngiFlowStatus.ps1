# Mostra o estado dos serviços, a saúde de cada um e se as URLs respondem.
. (Join-Path $PSScriptRoot "_common.ps1")
Assert-Docker
Invoke-Compose ps
Write-Host ""
foreach ($svc in @("postgres", "api", "web")) { Write-Host ("{0,-10} {1}" -f $svc, (Get-ServiceHealth -Service $svc)) }
foreach ($url in @("http://127.0.0.1:8000/health/live", "http://127.0.0.1:3000/login")) {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 5
        Write-Host ("{0} -> HTTP {1}" -f $url, $r.StatusCode)
    } catch {
        Write-Host ("{0} -> sem resposta" -f $url)
    }
}
