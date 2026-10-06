"""Shared SSH helpers to start or gracefully close OBS on the remote machine.

obs-websocket can only talk to OBS once it's already running, and the
official protocol has no "exit"/"shutdown" request either (by design - a
WebSocket client shouldn't be able to force-quit the whole application) -
so both directions go over a plain SSH connection to Windows instead,
exactly like the original SSH-start feature this module grew out of.

Starting runs a pre-configured Windows Scheduled Task (see start_obs()'s
own docstring for why that indirection: a task configured to run in the
logged-on user's session shows up on the real desktop, a bare SSH-spawned
process doesn't). Stopping sends a plain, non-forced `taskkill` for the
configured process name - see stop_obs().
"""
from __future__ import annotations

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


def stop_obs(host: str, ssh_port: int, username: str, password: str, process_name: str) -> None:
    """Connect over SSH and ask OBS to close normally - not a forced kill.

    `taskkill` without `/F` sends a close request to the process's windows
    (the same as clicking OBS's own close button), so OBS still runs its
    usual exit handling - saving the current recording properly, asking
    for confirmation if a stream/recording is still active - instead of
    `/F`, which terminates the process outright and can corrupt whatever
    it was writing to disk at that instant.

    If OBS does raise a confirmation dialog (stream/recording still
    active), it appears on the real desktop - the same interactive session
    the Scheduled Task above runs in - and needs a human click there to
    proceed; stopping the stream/recording first (e.g. via this
    integration's own switches) avoids that entirely.
    """
    _ssh_exec(host, ssh_port, username, password, f'taskkill /IM "{process_name}"')
