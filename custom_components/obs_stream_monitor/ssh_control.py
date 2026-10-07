"""Shared SSH helpers to start or gracefully close OBS on the remote machine.

obs-websocket can only talk to OBS once it's already running, and the
official protocol has no "exit"/"shutdown" request either (by design - a
WebSocket client shouldn't be able to force-quit the whole application) -
so both directions go over a plain SSH connection to Windows instead.

Both directions run a pre-configured Windows Scheduled Task (`schtasks
/run`) rather than acting directly inside the SSH session - see
start_obs()'s docstring for the original reasoning (a task configured to
run in the logged-on user's session shows up on the real, interactive
desktop; a bare SSH-spawned process runs in a separate, non-interactive
one instead) and stop_obs()'s docstring for why closing needed to move to
the exact same indirection in v0.7.5, after it turned out that limitation
applies to EnumWindows just as much as to CloseMainWindow(): a command run
directly over SSH can't enumerate (let alone message) windows belonging to
a process in the interactive session at all, elevated or not - it isn't a
"window not found" problem, it's a "this SSH session can't see that
desktop" one, with no window-API trick able to work around it from that
side. Routing the close through its own Scheduled Task puts the actual
EnumWindows/WM_CLOSE logic back in the one place (the interactive session)
where it can actually see OBS's windows, exactly like the start task
already did for launching it.
"""
from __future__ import annotations

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
    Windows installs - recovers the character instead of losing it.
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


def _run_scheduled_task(host: str, ssh_port: int, username: str, password: str, task_name: str) -> None:
    """Connect over SSH and fire the named Windows Scheduled Task.

    Shared by start_obs() and stop_obs() - both are, at the SSH level,
    exactly this one command with a different task name. `schtasks /run`
    only reports whether the task was *triggered* (exit code 0) here; it
    doesn't wait for the task's own script to finish or report whether
    that script ultimately succeeded, same as it always has for starting.
    Both switches already account for that: their actual effect shows up
    on the next coordinator poll (~10s), not synchronously from this call.
    """
    _ssh_exec(host, ssh_port, username, password, f'schtasks /run /tn "{task_name}"')


def start_obs(host: str, ssh_port: int, username: str, password: str, task_name: str) -> None:
    """Connect over SSH and trigger the named Windows Scheduled Task.

    Running the task (instead of launching the .exe directly over SSH) is
    deliberate: a Scheduled Task configured as "only run when user is
    logged on" starts the process in the interactive desktop session, so
    OBS actually shows up on screen. A plain SSH-spawned process would run
    in a separate, invisible session.
    """
    _run_scheduled_task(host, ssh_port, username, password, task_name)


def stop_obs(host: str, ssh_port: int, username: str, password: str, stop_task_name: str) -> None:
    """Connect over SSH and trigger the named "close OBS" Scheduled Task.

    Through v0.7.4 this ran a PowerShell script directly over the SSH
    session instead: enumerate OBS's real top-level windows via the Win32
    EnumWindows API (unlike .NET's `Process.CloseMainWindow()`, that finds
    a window minimized to the system tray too - see the v0.6.2 release
    notes) and post each one a WM_CLOSE, the same message a title bar's own
    close button sends. That worked for some setups but failed outright
    for others with "no window found for the process" even though OBS was
    running completely normally (not elevated, not tray-minimized) -
    because an SSH-spawned process and the interactive desktop session
    aren't just different privilege levels, they can be different window
    stations entirely, and EnumWindows only ever sees windows on its own
    caller's window station. No amount of Win32 API calls from inside the
    SSH session can cross that boundary - it has to run with a foot
    already on the interactive side instead.

    So, since v0.7.5, this does the exact same thing start_obs() always
    has: trigger a Scheduled Task (configured "only run when user is
    logged on", exactly like the start task) that runs that same
    EnumWindows/WM_CLOSE PowerShell logic from *inside* the interactive
    session, where it can actually see OBS's windows. See
    docs/ssh-start-button-setup.md for the local stop-obs.ps1 script this
    task needs to point at, and the exact Task Scheduler setup.

    Deliberately still not `taskkill` (even without `/F`): Windows' own
    graceful-close heuristic in taskkill refuses outright for many ordinary
    GUI apps, OBS included, with "This process can only be terminated
    forcefully (with /F)". OBS still runs its usual exit handling - saving
    the current recording properly, asking for confirmation if a stream/
    recording is still active - instead of being killed outright, which
    can corrupt whatever it was writing to disk at that instant.

    If OBS does raise a confirmation dialog (stream/recording still
    active), it appears on the real desktop - the same interactive session
    this task (like the start task) runs in - and needs a human click there
    to proceed; stopping the stream/recording first (e.g. via this
    integration's own switches) avoids that entirely.
    """
    _run_scheduled_task(host, ssh_port, username, password, stop_task_name)
