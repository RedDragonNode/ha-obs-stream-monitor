"""Config flow for OBS Stream Monitor."""
from __future__ import annotations

import logging
from typing import Any

import obsws_python as obsws
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_ENABLE_CONTROL,
    CONF_ENABLE_SCENE_TREE,
    CONF_SSH_PASSWORD,
    CONF_SSH_PORT,
    CONF_SSH_USERNAME,
    CONF_STOP_TASK_NAME,
    CONF_TASK_NAME,
    CONNECT_TIMEOUT,
    DEFAULT_ENABLE_CONTROL,
    DEFAULT_ENABLE_SCENE_TREE,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_SSH_PORT,
    DEFAULT_STOP_TASK_NAME,
    DEFAULT_TASK_NAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Required(CONF_PASSWORD): str,
    }
)


def _test_connection(host: str, port: int, password: str) -> str:
    """Connect once and return the OBS version string. Raises on failure."""
    client = obsws.ReqClient(host=host, port=port, password=password, timeout=CONNECT_TIMEOUT)
    try:
        version = client.get_version()
        return getattr(version, "obs_version", "unknown")
    finally:
        try:
            client.disconnect()
        except Exception:  # noqa: BLE001
            pass


class ObsStreamMonitorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OBS Stream Monitor."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> ObsStreamMonitorOptionsFlow:
        return ObsStreamMonitorOptionsFlow(config_entry)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            password = user_input[CONF_PASSWORD]

            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()

            try:
                await self.hass.async_add_executor_job(_test_connection, host, port, password)
            except obsws.error.OBSSDKError as err:
                _LOGGER.debug("OBS SDK error while connecting: %s", err)
                errors["base"] = "invalid_auth"
            except (ConnectionRefusedError, TimeoutError, OSError) as err:
                _LOGGER.debug("Connection error while connecting to OBS: %s", err)
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error testing OBS connection")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"{DEFAULT_NAME} ({host})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class ObsStreamMonitorOptionsFlow(config_entries.OptionsFlow):
    """Optional extras: the 'OBS' power switch (a Scheduled Task to start,
    a second Scheduled Task to close - see ssh_control.py's module
    docstring for why both directions need one), switchable stream/
    recording/profile/scene-collection controls, and the scene/source/
    filter switch tree used by the bundled dashboard card.

    All fields are optional and independent of each other: leaving the SSH
    username empty keeps the power switch off; leaving "OBS-Steuerung
    aktivieren" off keeps the stream/recording switches and the profile/
    scene-collection selects off; leaving "Szenen-Baum aktivieren" off
    keeps the scene-item/filter switches (and the dashboard card's data)
    off. Either way the base entry stays monitoring-only.
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self._config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SSH_USERNAME, default=current.get(CONF_SSH_USERNAME, "")
                ): str,
                vol.Optional(
                    CONF_SSH_PASSWORD, default=current.get(CONF_SSH_PASSWORD, "")
                ): str,
                vol.Optional(
                    CONF_SSH_PORT, default=current.get(CONF_SSH_PORT, DEFAULT_SSH_PORT)
                ): int,
                vol.Optional(
                    CONF_TASK_NAME, default=current.get(CONF_TASK_NAME, DEFAULT_TASK_NAME)
                ): str,
                vol.Optional(
                    CONF_STOP_TASK_NAME,
                    default=current.get(CONF_STOP_TASK_NAME, DEFAULT_STOP_TASK_NAME),
                ): str,
                vol.Optional(
                    CONF_ENABLE_CONTROL,
                    default=current.get(CONF_ENABLE_CONTROL, DEFAULT_ENABLE_CONTROL),
                ): bool,
                vol.Optional(
                    CONF_ENABLE_SCENE_TREE,
                    default=current.get(CONF_ENABLE_SCENE_TREE, DEFAULT_ENABLE_SCENE_TREE),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
