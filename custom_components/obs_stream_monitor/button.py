"""Button entity to start OBS on the remote machine via SSH + Scheduled Task."""
from __future__ import annotations

import logging

import paramiko

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_SSH_PASSWORD,
    CONF_SSH_PORT,
    CONF_SSH_USERNAME,
    CONF_TASK_NAME,
    DEFAULT_SSH_PORT,
    DEFAULT_TASK_NAME,
    DOMAIN,
    SSH_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the 'OBS starten' button, only if SSH credentials are configured."""
    ssh_username = entry.options.get(CONF_SSH_USERNAME)
    if not ssh_username:
        # Monitoring-only setup, nothing to add yet. Entities appear
        # automatically once SSH is filled in via the integration's
        # "Configure" options (the entry reloads on options change).
        return

    async_add_entities([ObsStartButton(entry)])


class ObsStartButton(ButtonEntity):
    """Triggers a pre-configured Windows Scheduled Task that launches OBS."""

    _attr_has_entity_name = True
    _attr_translation_key = "start_obs"
    _attr_icon = "mdi:play-box-outline"

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_start_obs"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="OBS Project",
            model="obs-websocket v5",
        )

    async def async_press(self) -> None:
        entry = self._entry
        host = entry.data[CONF_HOST]
        ssh_port = entry.options.get(CONF_SSH_PORT, DEFAULT_SSH_PORT)
        ssh_username = entry.options.get(CONF_SSH_USERNAME)
        ssh_password = entry.options.get(CONF_SSH_PASSWORD)
        task_name = entry.options.get(CONF_TASK_NAME, DEFAULT_TASK_NAME)

        try:
            await self.hass.async_add_executor_job(
                _run_scheduled_task, host, ssh_port, ssh_username, ssh_password, task_name
            )
        except Exception as err:
            raise HomeAssistantError(
                f"OBS-Start über SSH fehlgeschlagen: {err}"
            ) from err


def _run_scheduled_task(
    host: str, ssh_port: int, username: str, password: str, task_name: str
) -> None:
    """Connect over SSH and trigger the named Windows Scheduled Task.

    Running the task (instead of launching the .exe directly over SSH)
    is deliberate: a Scheduled Task configured as "only run when user is
    logged on" starts the process in the interactive desktop session, so
    OBS actually shows up on screen. A plain SSH-spawned process would
    run in a separate, invisible session.
    """
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
        command = f'schtasks /run /tn "{task_name}"'
        _stdin, stdout, stderr = client.exec_command(command, timeout=SSH_TIMEOUT)
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            error_output = stderr.read().decode(errors="ignore").strip()
            raise RuntimeError(
                f"schtasks meldete Exit-Code {exit_status}: {error_output or 'keine Fehlermeldung'}"
            )
    finally:
        client.close()
