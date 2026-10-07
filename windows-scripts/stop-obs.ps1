# stop-obs.ps1 - schliesst OBS sauber (WM_CLOSE an jedes echte Fenster,
# KEIN hartes Abwuergen). Gedacht als Aktion der Scheduled Task "StopOBS",
# die wiederum per `schtasks /run` von Home Assistant aus ferngestartet
# wird (ueber den "OBS"-Schalter, Aus-Stellung) - siehe
# docs/ssh-start-button-setup.md fuer die komplette Einrichtung.
#
# Muss als Scheduled Task laufen, nicht direkt per SSH ausgefuehrt werden:
# eine Scheduled Task, die "nur ausfuehren, wenn der Benutzer angemeldet
# ist" eingestellt ist, laeuft in der echten, sichtbaren Desktop-Sitzung -
# nur von dort aus lassen sich OBS' eigene Fenster ueberhaupt finden
# (EnumWindows sieht nur Fenster der eigenen Fensterstation). Eine SSH-
# Sitzung laeuft in einer eigenen, nicht-interaktiven Sitzung und kann
# OBS' Fenster grundsaetzlich nicht sehen, egal ob OBS im Tray minimiert
# oder "als Administrator" gestartet ist oder nicht.

# Prozessname unten anpassen, falls keine normale 64-Bit-Installation
# vorliegt - Name OHNE ".exe", wie im Task-Manager (Reiter "Details",
# Spalte "Name") zu sehen.
$ProcessName = 'obs64'

$LogFile = Join-Path $PSScriptRoot 'stop-obs.log'
function Write-Log {
    param([string]$Message)
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message" | Out-File -FilePath $LogFile -Append -Encoding utf8
}

$ErrorActionPreference = 'Stop'
try {
    $procs = Get-Process -Name $ProcessName -ErrorAction SilentlyContinue
    if (-not $procs) {
        Write-Log "OBS ($ProcessName) laeuft nicht - nichts zu tun."
        exit 0
    }

    Add-Type @'
using System;
using System.Runtime.InteropServices;
public class ObsCloseHelper {
    public delegate bool EnumProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumProc enumProc, IntPtr lParam);
    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
    [DllImport("user32.dll")]
    public static extern bool PostMessage(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll")]
    public static extern IntPtr GetWindowLongPtr(IntPtr hWnd, int nIndex);
}
'@

    $targetIds = New-Object 'System.Collections.Generic.HashSet[uint32]'
    foreach ($p in $procs) { [void]$targetIds.Add([uint32]$p.Id) }

    # WS_CAPTION - nur Fenster mit Titelleiste zaehlen als "echtes" Fenster
    # (interne Plumbing-/Helper-Fenster eines GUI-Toolkits haben meist keine).
    $WS_CAPTION = 0xC00000
    $found = New-Object 'System.Collections.Generic.List[IntPtr]'
    $callback = {
        param($hWnd, $lParam)
        $procId = [uint32]0
        [void][ObsCloseHelper]::GetWindowThreadProcessId($hWnd, [ref]$procId)
        if ($targetIds.Contains($procId)) {
            $style = [ObsCloseHelper]::GetWindowLongPtr($hWnd, -16).ToInt64()
            if (($style -band $WS_CAPTION) -ne 0) {
                $found.Add($hWnd)
            }
        }
        return $true
    }
    [void][ObsCloseHelper]::EnumWindows($callback, [IntPtr]::Zero)

    if ($found.Count -eq 0) {
        Write-Log "Kein Fenster mit Titelleiste fuer $ProcessName gefunden (laeuft evtl. komplett im Hintergrund ohne eigenes Fenster)."
        exit 1
    }

    $WM_CLOSE = 0x0010
    $sentCount = 0
    foreach ($hWnd in $found) {
        if ([ObsCloseHelper]::PostMessage($hWnd, $WM_CLOSE, [IntPtr]::Zero, [IntPtr]::Zero)) {
            $sentCount++
        }
    }

    Write-Log "Schliessen-Signal an $sentCount von $($found.Count) Fenster(n) gesendet."
    if ($sentCount -eq 0) { exit 1 }
    exit 0
} catch {
    Write-Log "Unerwarteter Fehler: $($_.Exception.Message)"
    exit 1
}
