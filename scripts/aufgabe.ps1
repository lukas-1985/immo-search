# Einstieg fuer die Windows-Aufgabenplanung (angelegt von scripts\install_tasks.ps1), nur feste Aufgaben:
#   powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File scripts\aufgabe.ps1 -Aufgabe lauf|backup|server
#
#   lauf    scripts\lauf.py   -> run.ps1 als Job (in der Oberflaeche unter "Laeufe", Log data\logs\job-<id>.log)
#   backup  scripts\backup.py
#   server  scripts\serve.py, nach einem Absturz Neustart nach 30 s (nach 5 schnellen Abstuerzen in Folge: 5 min)
#
# Ausgaben landen in data\logs\aufgabe-<aufgabe>-<JJJJMM>.log.
param(
    [Parameter(Mandatory)][ValidateSet("lauf", "backup", "server")][string]$Aufgabe
)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:PYTHONUNBUFFERED = "1"   # Reihenfolge von stdout und stderr im Log erhalten
New-Item -ItemType Directory -Force (Join-Path $root "data\logs") | Out-Null

$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv) { $uv = "uv" }
if ($uv -match '\s') { $uv = "`"$uv`"" }

function Logdatei { "data\logs\aufgabe-$Aufgabe-" + (Get-Date -Format 'yyyyMM') + ".log" }

function Log([string]$Text) {
    Add-Content -Path (Logdatei) -Encoding UTF8 -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Text"
}

function Starte([string]$Skript) {
    $log = Logdatei
    Log "Start: uv run python $Skript"
    # cmd leitet stdout und stderr unveraendert in die Datei (PowerShell 5.1 wuerde stderr umformen)
    & cmd.exe /d /c "$uv run python $Skript >> $log 2>&1"
    $code = $LASTEXITCODE
    Log "Ende: Exit-Code $code"
    return $code
}

switch ($Aufgabe) {
    "lauf"   { exit (Starte "scripts\lauf.py") }
    "backup" { exit (Starte "scripts\backup.py") }
    "server" {
        $schnelle = 0
        while ($true) {
            $t0 = Get-Date
            $null = Starte "scripts\serve.py"
            if (((Get-Date) - $t0).TotalMinutes -lt 2) { $schnelle++ } else { $schnelle = 0 }
            $pause = 30
            if ($schnelle -ge 5) { $pause = 300 }
            Log "Server beendet - Neustart in $pause s"
            Start-Sleep -Seconds $pause
        }
    }
}
