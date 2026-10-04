"""Config flow for OBS Stream Monitor."""
from __future__ import annotations

import logging
from typing import Any

import obsws_python as obsws
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT
from homeassistant.data_entry_flow import FlowResult

from .const import CONNECT_TIMEOUT, DEFAULT_NAME, DEFAULT_PORT, DOMAIN

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
