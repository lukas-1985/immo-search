# Legt die Aufgaben der Immo-Suche in der Windows-Aufgabenplanung an (Phase 6). Ohne Admin-Rechte, im eigenen Konto:
#   powershell -ExecutionPolicy Bypass -File scripts\install_tasks.ps1             # anlegen bzw. aktualisieren
#   powershell -ExecutionPolicy Bypass -File scripts\install_tasks.ps1 -WasWaere   # nur anzeigen, nichts aendern
#   powershell -ExecutionPolicy Bypass -File scripts\install_tasks.ps1 -Entfernen  # alle drei Aufgaben loeschen
#
# Aufgaben:
#   "immo-search lauf"    taeglich ab schedule.run.from alle schedule.run.every_hours Stunden bis schedule.run.to
#                         -> scripts\lauf.py -> run.ps1 (Sync, Regeln, Claude, Bewertung, Health)
#   "immo-search backup"  taeglich um schedule.backup.at -> scripts\backup.py
#   "immo-search server"  bei Anmeldung (1 min Verzoegerung) -> scripts\serve.py, Neustart nach Absturz
#
# Alle laufen nur, solange der Benutzer angemeldet ist (wie Docker Desktop; automatische Anmeldung mit
# gesperrtem Bildschirm einrichten), mit normalen Rechten und verstecktem Fenster. Verpasste Termine
# (PC aus) werden nachgeholt. Nach einer Aenderung von "schedule" in config\settings.yaml erneut ausfuehren.
param(
    [switch]$WasWaere,
    [switch]$Entfernen
)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$namen = @("immo-search lauf", "immo-search backup", "immo-search server")

if ($Entfernen) {
    foreach ($n in $namen) {
        if (Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue) {
            if ($WasWaere) { Write-Host "Wuerde entfernen: $n"; continue }
            Stop-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue
            Unregister-ScheduledTask -TaskName $n -Confirm:$false
            Write-Host "Entfernt: $n"
        }
    }
    exit 0
}

# Zeitplan aus settings.yaml (geprueft von Pydantic, wie ueberall im Projekt)
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw "uv nicht gefunden (winget install astral-sh.uv)" }
$json = & uv run python scripts\zeitplan.py | Out-String
if ($LASTEXITCODE -ne 0) { throw "scripts\zeitplan.py fehlgeschlagen - config\settings.yaml pruefen" }
$z = $json | ConvertFrom-Json
$von = [TimeSpan]::Parse($z.run.'from')
$bis = [TimeSpan]::Parse($z.run.'to')
$takt = New-TimeSpan -Hours $z.run.every_hours
if ($bis -lt $von) { throw "schedule.run: 'to' ($($z.run.'to')) liegt vor 'from' ($($z.run.'from'))" }
$zeiten = @()
for ($t = $von; $t -le $bis; $t = $t.Add($takt)) { $zeiten += $t.ToString("hh\:mm") }
$backupUm = [TimeSpan]::Parse($z.backup.at)

$benutzer = "$env:USERDOMAIN\$env:USERNAME"
$principal = New-ScheduledTaskPrincipal -UserId $benutzer -LogonType Interactive -RunLevel Limited

function Aktion([string]$Aufgabe) {
    New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $root -Argument (
        "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass " +
        "-File `"$root\scripts\aufgabe.ps1`" -Aufgabe $Aufgabe")
}

# 1) Laeufe: taeglicher Ausloeser mit Wiederholung; +1 min, damit der Termin genau um "to" noch startet
$heute = [DateTime]::Today
$tLauf = New-ScheduledTaskTrigger -Daily -At $heute.Add($von)
$tLauf.Repetition = (New-ScheduledTaskTrigger -Once -At $heute.Add($von) -RepetitionInterval $takt `
    -RepetitionDuration (($bis - $von) + (New-TimeSpan -Minutes 1))).Repetition
$sLauf = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)

# 2) Backup: taeglich
$tBackup = New-ScheduledTaskTrigger -Daily -At $heute.Add($backupUm)
$sBackup = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1)

# 3) Server: bei Anmeldung, ohne Zeitlimit. Neustarts nach Absturz macht aufgabe.ps1 (Schleife);
#    stirbt die Schleife selbst, startet die Aufgabenplanung sie neu.
$tServer = New-ScheduledTaskTrigger -AtLogOn -User $benutzer
$tServer.Delay = "PT1M"
$sServer = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)

$aufgaben = @(
    @{ Name = $namen[0]; Aufgabe = "lauf";   Trigger = $tLauf;   Settings = $sLauf
       Text = "Laeufe taeglich um $($zeiten -join ', ') Uhr (run.ps1 ueber scripts\lauf.py)" },
    @{ Name = $namen[1]; Aufgabe = "backup"; Trigger = $tBackup; Settings = $sBackup
       Text = "Backup taeglich um $($z.backup.at) Uhr (scripts\backup.py)" },
    @{ Name = $namen[2]; Aufgabe = "server"; Trigger = $tServer; Settings = $sServer
       Text = "immo-server bei Anmeldung von $benutzer, Port $($z.server_port), Neustart nach Absturz" }
)

foreach ($a in $aufgaben) {
    if ($WasWaere) { Write-Host "Wuerde anlegen: $($a.Name) - $($a.Text)"; continue }
    Register-ScheduledTask -TaskName $a.Name -Action (Aktion $a.Aufgabe) -Trigger $a.Trigger -Settings $a.Settings `
        -Principal $principal -Description "immo-search: $($a.Text). Angelegt von scripts\install_tasks.ps1." -Force | Out-Null
    Write-Host "Angelegt: $($a.Name) - $($a.Text)"
}
if ($WasWaere) { exit 0 }

Write-Host ""
Write-Host "Logs: data\logs\aufgabe-<lauf|backup|server>-JJJJMM.log, Laeufe zusaetzlich unter data\logs\job-<id>.log."
Write-Host "Sofort testen:  Start-ScheduledTask -TaskName 'immo-search backup'"
Write-Host "Server starten: Start-ScheduledTask -TaskName 'immo-search server'  (sonst erst bei der naechsten Anmeldung)"
