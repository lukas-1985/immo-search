# Ein Lauf der Immo-Suche: Sync -> Regeln -> Claude-Extraktion -> Bewertung -> Health-Pruefung.
#   powershell -ExecutionPolicy Bypass -File run.ps1 [-Profil mfh-kl]
#   powershell -ExecutionPolicy Bypass -File run.ps1 -Listing 42 -Reextract
#
# Die deterministischen Schritte laufen direkt; Claude wertet nur die Anzeigentexte aus
# (Skill immo-analyse mit --nur-extraktion) und darf nur, was .claude/run-settings.json erlaubt.
# Faellt Claude aus, laufen Sync und Bewertung trotzdem (Exit-Code 2 = Teilfehler).
param(
    [string]$Profil,
    [int]$Listing = 0,
    [switch]$Reextract,
    [int]$ClaudeMinuten = 30
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
$profilArgs = @()
if ($Profil) { $profilArgs = @("--profile", $Profil) }

function Schritt([string]$Name, [string[]]$Argumente) {
    Write-Host ""
    Write-Host "== $Name ($(Get-Date -Format 'HH:mm:ss')): uv run python $($Argumente -join ' ')"
    & uv run python @Argumente
    if ($LASTEXITCODE -eq 1) { throw "$Name fehlgeschlagen" }
    if ($LASTEXITCODE -ne 0) { $script:teilfehler = $true }
}

function Claude-Extraktion([string]$Prompt) {
    $claude = (Get-Command claude -ErrorAction SilentlyContinue).Source
    if (-not $claude) {
        Write-Host "WARNUNG: Claude-CLI nicht gefunden (winget install Anthropic.ClaudeCode) - Extraktion uebersprungen."
        $script:teilfehler = $true
        return
    }
    # Rueckfallebene: Token aus .env, falls die normale Anmeldung im unbeaufsichtigten Betrieb nicht haelt
    if (-not $env:CLAUDE_CODE_OAUTH_TOKEN -and (Test-Path .env)) {
        $zeile = Select-String -Path .env -Pattern '^\s*CLAUDE_CODE_OAUTH_TOKEN\s*=\s*(\S+)' | Select-Object -First 1
        if ($zeile) { $env:CLAUDE_CODE_OAUTH_TOKEN = $zeile.Matches[0].Groups[1].Value }
    }
    $logdatei = Join-Path $PSScriptRoot ("data\logs\claude-" + (Get-Date -Format 'yyyyMMdd-HHmmss') + ".log")
    New-Item -ItemType Directory -Force (Split-Path $logdatei) | Out-Null
    $argumente = "-p `"$Prompt`" --permission-mode dontAsk --settings .claude/run-settings.json " +
                 "--strict-mcp-config --no-session-persistence --output-format text"
    Write-Host ""
    Write-Host "== Claude ($(Get-Date -Format 'HH:mm:ss')): $Prompt  (Zeitlimit $ClaudeMinuten min, Log: $logdatei)"
    $p = Start-Process -FilePath $claude -ArgumentList $argumente -NoNewWindow -PassThru `
        -RedirectStandardOutput $logdatei -RedirectStandardError "$logdatei.err"
    $null = $p.Handle   # sonst liefert ExitCode unter PowerShell 5.1 nichts
    if (-not $p.WaitForExit($ClaudeMinuten * 60 * 1000)) {
        $p.Kill()
        Write-Host "WARNUNG: Claude nach $ClaudeMinuten min abgebrochen."
        $script:teilfehler = $true
    } elseif ($p.ExitCode -ne 0) {
        Write-Host "WARNUNG: Claude endete mit Exit-Code $($p.ExitCode)."
        $script:teilfehler = $true
    }
    Get-Content $logdatei, "$logdatei.err" -Encoding UTF8 -ErrorAction SilentlyContinue | Write-Host
}

function Health {
    # Nur protokollieren (run_log); ein Problem hier macht den Lauf nicht zum Teilfehler
    Write-Host ""
    Write-Host "== Health ($(Get-Date -Format 'HH:mm:ss')): uv run python scripts/health.py"
    & uv run python scripts/health.py
    if ($LASTEXITCODE -ne 0) { Write-Host "WARNUNG: Health-Pruefung fehlgeschlagen (Exit-Code $LASTEXITCODE)." }
}

try {
    if ($Listing -gt 0) {
        Claude-Extraktion "/immo-analyse --listing=$Listing --reextract --nur-extraktion"
    } else {
        Schritt "Sync" (@("scripts/sync.py") + $profilArgs)
        Schritt "Regeln" (@("scripts/parse_attrs.py") + $profilArgs)
        Claude-Extraktion ("/immo-analyse " + $Profil + " --nur-extraktion").Replace("  ", " ")
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
