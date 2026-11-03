# Ein Lauf der Immo-Suche: Sync -> Regeln -> KI-Extraktion -> Bewertung -> Health-Pruefung.
#   powershell -ExecutionPolicy Bypass -File run.ps1 [-Profil mfh-kl]
#   powershell -ExecutionPolicy Bypass -File run.ps1 -Listing 42 -Reextract
#
# Die deterministischen Schritte laufen direkt; KI wertet nur die Anzeigentexte aus
# (scripts/extract.py); Python steuert die gepruefte Speicherung.
# Faellt KI aus, laufen Sync und Bewertung trotzdem (Exit-Code 2 = Teilfehler).
param(
    [string]$Profil,
    [int]$Listing = 0,
    [switch]$Reextract,
    [string]$Db,
    [string]$ConfigDir
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

if ($Profil -and $Profil -notmatch '^[a-z0-9][a-z0-9-]*$') { throw "Ungueltige Profil-ID: $Profil" }
if ($Reextract -and $Listing -le 0) { throw "-Reextract braucht -Listing <id>" }

New-Item -ItemType Directory -Force data | Out-Null
try {
    $lock = [IO.File]::Open((Join-Path $PSScriptRoot "data\run.lock"), 'OpenOrCreate', 'ReadWrite', 'None')
} catch {
    Write-Host "Ein anderer Lauf ist aktiv - Abbruch."
    exit 3
}

$teilfehler = $false
$kontextArgs = @()
if ($Db) { $kontextArgs += @("--db", $Db) }
if ($ConfigDir) { $kontextArgs += @("--config-dir", $ConfigDir) }
$profilArgs = @()
if ($Profil) { $profilArgs = @("--profile", $Profil) }

function Schritt([string]$Name, [string[]]$Argumente) {
    Write-Host ""
    Write-Host "== $Name ($(Get-Date -Format 'HH:mm:ss')): uv run python $($Argumente -join ' ')"
    & uv run python @Argumente @kontextArgs
    if ($LASTEXITCODE -eq 1) { throw "$Name fehlgeschlagen" }
    if ($LASTEXITCODE -ne 0) { $script:teilfehler = $true }
}

function KI-Extraktion([string[]]$Argumente) {
    Write-Host ""
    Write-Host "== Codex/ChatGPT-Extraktion ($(Get-Date -Format 'HH:mm:ss'))"
    & uv run python scripts/extract.py @Argumente @kontextArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host "WARNUNG: KI-Extraktion unvollstaendig (Exit-Code $LASTEXITCODE)."
        $script:teilfehler = $true
    }
}

function Health {
    # Nur protokollieren (run_log); ein Problem hier macht den Lauf nicht zum Teilfehler
    Write-Host ""
    Write-Host "== Health ($(Get-Date -Format 'HH:mm:ss')): uv run python scripts/health.py"
    & uv run python scripts/health.py @kontextArgs
    if ($LASTEXITCODE -ne 0) { Write-Host "WARNUNG: Health-Pruefung fehlgeschlagen (Exit-Code $LASTEXITCODE)." }
}

try {
    if ($Listing -gt 0) {
        KI-Extraktion @("--listing", "$Listing", "--reextract")
    } else {
        Schritt "Sync" (@("scripts/sync.py") + $profilArgs)
        Schritt "Regeln" (@("scripts/parse_attrs.py") + $profilArgs)
        KI-Extraktion $profilArgs
    }
    Schritt "Bewertung" (@("scripts/score.py") + $profilArgs)
    if ($Listing -le 0) { Health }
} finally {
    $lock.Close()
}

if ($teilfehler) { Write-Host ""; Write-Host "Lauf mit Teilfehlern beendet."; exit 2 }
Write-Host ""
Write-Host "Lauf fertig."
exit 0
