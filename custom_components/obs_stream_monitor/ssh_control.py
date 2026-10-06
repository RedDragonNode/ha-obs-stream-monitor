"""Shared SSH helpers to start or gracefully close OBS on the remote machine.

obs-websocket can only talk to OBS once it's already running, and the
official protocol has no "exit"/"shutdown" request either (by design - a
WebSocket client shouldn't be able to force-quit the whole application) -
so both directions go over a plain SSH connection to Windows instead,
exactly like the original SSH-start feature this module grew out of.

Starting runs a pre-configured Windows Scheduled Task (see start_obs()'s
own docstring for why that indirection: a task configured to run in the
logged-on user's session shows up on the real desktop, a bare SSH-spawned
process doesn't). Stopping asks OBS's window(s) to close, via PowerShell -
see stop_obs() for why plain `taskkill` (even without `/F`), and even
.NET's own `Process.CloseMainWindow()`, aren't reliable enough for this.
"""
from __future__ import annotations

import base64

import paramiko

from .const import SSH_TIMEOUT


def _decode_output(data: bytes) -> str:
    """Decode text coming back from a Windows SSH/console session.

    cmd.exe and a non-interactively-invoked PowerShell both default to the
    system's legacy OEM/ANSI codepage for console output, not UTF-8 - so a
    German message containing e.g. "ä" arrives as a single legacy-codepage
    byte rather than a valid UTF-8 sequence. Decoding that strictly as UTF-8
    raises; silently ignoring the bad byte (as a plain `errors="ignore"`
    decode would) just drops the character instead ("zählt" -> "zhlt").
    Falling back to cp1252 - the closest common match for Western-European
    Windows installs - recovers the character instead of losing it. (The
    script in stop_obs() also sets its own console output encoding to UTF-8
    explicitly, so *that* path decodes cleanly on the first try; this
    fallback mainly covers text Windows itself generates, like schtasks
    error messages, which this module doesn't control the encoding of.)
    """
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _ssh_exec(host: str, ssh_port: int, username: str, password: str, command: str) -> None:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=host,
            port=ssh_port,
            username=username,
            password=password,
            timeout=SSH_TIMEOUT,
            allow_agent=False,
            look_for_keys=False,
        )
        _stdin, stdout, stderr = client.exec_command(command, timeout=SSH_TIMEOUT)
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            error_output = _decode_output(stderr.read()).strip()
            raise RuntimeError(
                f"Befehl meldete Exit-Code {exit_status}: {error_output or 'keine Fehlermeldung'}"
            )
    finally:
        client.close()


def start_obs(host: str, ssh_port: int, username: str, password: str, task_name: str) -> None:
    """Connect over SSH and trigger the named Windows Scheduled Task.

    Running the task (instead of launching the .exe directly over SSH) is
    deliberate: a Scheduled Task configured as "only run when user is
    logged on" starts the process in the interactive desktop session, so
    OBS actually shows up on screen. A plain SSH-spawned process would run
    in a separate, invisible session.
    """
    _ssh_exec(host, ssh_port, username, password, f'schtasks /run /tn "{task_name}"')


def _encoded_powershell_command(script: str) -> str:
    """Wrap a PowerShell script as `powershell -EncodedCommand <base64>`.

    Avoids quoting hell: the remote SSH exec channel hands the command
    string to Windows' default shell (cmd.exe) first, and base64 contains
    none of the characters that are special to either cmd.exe or
    PowerShell, so nothing in `script` can be mis-parsed on the way
    through. -EncodedCommand expects UTF-16LE, not UTF-8.
    """
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return f"powershell -NoProfile -NonInteractive -EncodedCommand {encoded}"


# PowerShell script run by stop_obs(). "__PROCESS_STEM__" is replaced with
# the (escaped) bare process name before sending. Built as a plain string
# with a placeholder rather than an f-string/.format() template, since the
# embedded C# below is full of literal { } braces that an f-string would
# otherwise force doubling up everywhere.
#
# What it does, and why it's not just `Process.CloseMainWindow()` anymore:
# .NET's CloseMainWindow() picks "the" main window using its own heuristic
# (first top-level window that is visible, has no owner, and has a
# non-empty title) and sends it a close request. That heuristic can miss
# OBS entirely - most commonly when OBS is minimized to the system tray,
# where its window still exists but isn't "visible" by that heuristic's
# definition - and CloseMainWindow() then just returns false with no
# further detail, which is exactly the "kein normales Hauptfenster" error
# this integration showed before.
#
# This script instead enumerates every top-level window belonging to the
# process directly via the Win32 EnumWindows API (which, unlike .NET's
# heuristic, includes hidden/minimized-to-tray windows), narrows that down
# to windows that look like real application windows (have a title bar -
# WS_CAPTION - which internal/plumbing windows a GUI toolkit creates
# usually don't), and posts a WM_CLOSE to each one found - the same
# message a title bar's own close button sends. If OBS's window turns out
# to still not be reachable this way (e.g. a genuine elevation mismatch
# between the SSH session and an OBS explicitly run "as Administrator"),
# this still fails clearly with its own message rather than silently.
_STOP_OBS_SCRIPT = r"""
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $procs = Get-Process -Name '__PROCESS_STEM__' -ErrorAction SilentlyContinue
    if (-not $procs) { exit 0 }

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
        [Console]::Error.WriteLine('Kein Fenster für den Prozess gefunden (läuft evtl. komplett im Hintergrund/Tray ohne eigenes Fenster mit Titelleiste, oder die Sitzung hat wegen unterschiedlicher Rechte keinen Zugriff darauf - z. B. wenn OBS "als Administrator" gestartet wurde)')
        exit 1
    }

    $WM_CLOSE = 0x0010
    $sentCount = 0
    foreach ($hWnd in $found) {
        if ([ObsCloseHelper]::PostMessage($hWnd, $WM_CLOSE, [IntPtr]::Zero, [IntPtr]::Zero)) {
            $sentCount++
        }
    }

    if ($sentCount -gt 0) {
        exit 0
    } else {
        [Console]::Error.WriteLine('Schließen-Signal konnte an kein gefundenes Fenster gesendet werden')
        exit 1
    }
} catch {
    [Console]::Error.WriteLine("Unerwarteter Fehler: $($_.Exception.Message)")
    exit 1
}
"""


def stop_obs(host: str, ssh_port: int, username: str, password: str, process_name: str) -> None:
    """Connect over SSH and ask all of OBS's real windows to close - not a forced kill.

    Deliberately not `taskkill` (even without `/F`): Windows' own graceful-
    close heuristic in taskkill refuses outright for many ordinary GUI
    apps, OBS included, with "This process can only be terminated
    forcefully (with /F)" - it isn't a sign anything is wrong, taskkill's
    non-forced mode is just unreliable in practice. Also deliberately not
    .NET's `Process.CloseMainWindow()` (used by earlier versions of this
    integration): its "find the main window" heuristic can miss OBS
    outright - most commonly when OBS is minimized to the system tray -
    and then fails with no further detail. See `_STOP_OBS_SCRIPT` above for
    what this does instead: it finds every real top-level window (title
    bar included, so also while hidden/minimized to tray) belonging to the
    process directly via the Win32 API and posts each one a WM_CLOSE - the
    same request Windows sends when you click a window's own close button.
    OBS still runs its usual exit handling - saving the current recording
    properly, asking for confirmation if a stream/recording is still
    active - instead of being killed outright, which can corrupt whatever
    it was writing to disk at that instant.

    `process_name` is matched against the Task Manager "Name" column
    (e.g. "obs64.exe", trailing ".exe" stripped here since PowerShell's
    Get-Process wants the bare name). If OBS isn't running at all, this is
    a no-op, not an error. If OBS does raise a confirmation dialog
    (stream/recording still active), it appears on the real desktop - the
    same interactive session the Scheduled Task above runs in - and needs
    a human click there to proceed; stopping the stream/recording first
    (e.g. via this integration's own switches) avoids that entirely.
    """
    stem = process_name[:-4] if process_name.lower().endswith(".exe") else process_name
    stem_escaped = stem.replace("'", "''")  # PowerShell single-quote escaping
    script = _STOP_OBS_SCRIPT.replace("__PROCESS_STEM__", stem_escaped)
    _ssh_exec(host, ssh_port, username, password, _encoded_powershell_command(script))
