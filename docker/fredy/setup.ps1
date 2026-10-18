# Fredy einrichten bzw. aktualisieren (Phase 1).
#   powershell -ExecutionPolicy Bypass -File docker\fredy\setup.ps1 [-DataDir C:\E\docker\fredy]
param(
    [string]$DataDir = "C:\E\docker\fredy"
)
$ErrorActionPreference = "Stop"
$compose = Join-Path $PSScriptRoot "docker-compose.yml"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker ist nicht installiert: winget install -e --id Docker.DockerDesktop"
}
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw "Docker laeuft nicht - Docker Desktop starten und erneut versuchen." }

foreach ($sub in "conf", "db") {
    $p = Join-Path $DataDir $sub
    if (-not (Test-Path $p)) { New-Item -ItemType Directory -Path $p | Out-Null; Write-Host "angelegt: $p" }
}

$env:FREDY_DATA = ($DataDir -replace "\\", "/")
docker compose -f $compose up -d
if ($LASTEXITCODE -ne 0) { throw "docker compose up fehlgeschlagen" }

Write-Host "warte auf Fredy (http://localhost:9998) ..."
$deadline = (Get-Date).AddMinutes(3)
while ((Get-Date) -lt $deadline) {
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:9998" -UseBasicParsing -TimeoutSec 5
        if ($r.StatusCode -eq 200) {
            Write-Host "Fredy laeuft: http://localhost:9998 (Erstanmeldung admin/admin - Passwort sofort aendern)"
            docker inspect fredy --format "Image: {{.Config.Image}}  Restart: {{.HostConfig.RestartPolicy.Name}}"
            exit 0
        }
    } catch { Start-Sleep -Seconds 3 }
}
docker logs fredy --tail 50
throw "Fredy antwortet nicht nach 3 Minuten - Log oben pruefen."
