"""Shared SSH helpers to start or gracefully close OBS on the remote machine.

obs-websocket can only talk to OBS once it's already running, and the
official protocol has no "exit"/"shutdown" request either (by design - a
WebSocket client shouldn't be able to force-quit the whole application) -
so both directions go over a plain SSH connection to Windows instead,
exactly like the original SSH-start feature this module grew out of.

Starting runs a pre-configured Windows Scheduled Task (see start_obs()'s
own docstring for why that indirection: a task configured to run in the
logged-on user's session shows up on the real desktop, a bare SSH-spawned
process doesn't). Stopping asks OBS's main window to close, via PowerShell
- see stop_obs() for why plain `taskkill` (even without `/F`) doesn't
reliably do this.
"""
from __future__ import annotations

import base64

import paramiko

from .const import SSH_TIMEOUT


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
            error_output = stderr.read().decode(errors="ignore").strip()
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


def stop_obs(host: str, ssh_port: int, username: str, password: str, process_name: str) -> None:
    """Connect over SSH and ask OBS's main window to close - not a forced kill.

    Deliberately NOT `taskkill` (even without `/F`): Windows' own graceful-
    close heuristic in taskkill refuses outright for many ordinary GUI
    apps, OBS included, with "This process can only be terminated
    forcefully (with /F)" - it isn't a sign anything is wrong, taskkill's
    non-forced mode is just unreliable in practice. Instead this sends a
    real close request directly to the process's main window via
    PowerShell's `Process.CloseMainWindow()` (the same request Windows
    sends when you click a window's own close button), so OBS still runs
    its usual exit handling - saving the current recording properly,
    asking for confirmation if a stream/recording is still active -
    instead of being killed outright, which can corrupt whatever it was
    writing to disk at that instant.

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
    script = (
        f"$procs = Get-Process -Name '{stem_escaped}' -ErrorAction SilentlyContinue; "
        "if (-not $procs) { exit 0 }; "
        "$ok = $true; "
        "foreach ($p in $procs) { if (-not $p.CloseMainWindow()) { $ok = $false } }; "
        "if ($ok) { exit 0 } else { "
        "[Console]::Error.WriteLine("
        "'CloseMainWindow fehlgeschlagen - Prozess hat evtl. kein normales Hauptfenster "
        "(z. B. minimiert in die Taskleiste zählt nicht dazu, aber ein Fenster ganz ohne "
        "sichtbaren Titel schon)'); exit 1 }"
    )
    _ssh_exec(host, ssh_port, username, password, _encoded_powershell_command(script))
