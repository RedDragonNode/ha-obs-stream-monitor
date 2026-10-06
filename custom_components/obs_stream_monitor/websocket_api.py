"""Custom WebSocket API commands for the bundled "OBS Szenen-Baum" card.

Gives the card a way to read and write a source's or a filter's *raw* OBS
settings (text content, color values, crop, chroma-key thresholds, audio
filter parameters, ...) - the generic key/value blob obs-websocket returns
for GetInputSettings/GetSourceFilter, with no attempt to understand what any
individual field means. The card renders whatever comes back as a plain
form (string/number/boolean inputs, JSON text areas for anything nested)
and sends whatever the user edited straight back.

These are plain custom WebSocket commands (hass.connection.callWS from the
frontend), not services or entities: settings are only fetched when the
card's settings dialog is actually opened (not part of the regular 10s
poll), and there's no sensible way to represent an arbitrary, source-kind
specific settings blob as entity state anyway.

Registered once per Home Assistant run (see __init__.py), guarded the same
way the dashboard card's static path registration is.
"""
from __future__ import annotations

import logging

import obsws_python as obsws
import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT
from homeassistant.core import HomeAssistant

from .const import CONNECT_TIMEOUT, DOMAIN

_LOGGER = logging.getLogger(__name__)


class _ObsCommandError(Exception):
    """Raised for any failure talking to OBS; message is shown to the user."""


def _connection_info(hass: HomeAssistant, entry_id: str) -> tuple[str, int, str]:
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise _ObsCommandError("Unbekannter OBS-Stream-Monitor-Eintrag.")
    return entry.data[CONF_HOST], entry.data[CONF_PORT], entry.data[CONF_PASSWORD]


def _with_client(host: str, port: int, password: str):
    return obsws.ReqClient(host=host, port=port, password=password, timeout=CONNECT_TIMEOUT)


def _fetch_input_settings(host: str, port: int, password: str, source_name: str) -> dict:
    client = _with_client(host, port, password)
    try:
        resp = client.get_input_settings(source_name)
        return {
            "kind": getattr(resp, "input_kind", None),
            "settings": getattr(resp, "input_settings", None) or {},
        }
    except Exception as err:  # noqa: BLE001 - surfaced to the card as-is
        raise _ObsCommandError(str(err)) from err
    finally:
        try:
            client.disconnect()
        except Exception:  # noqa: BLE001 - best effort cleanup
            pass


def _push_input_settings(
    host: str, port: int, password: str, source_name: str, settings: dict
) -> None:
    client = _with_client(host, port, password)
    try:
        client.set_input_settings(source_name, settings, True)
    except Exception as err:  # noqa: BLE001
        raise _ObsCommandError(str(err)) from err
    finally:
        try:
            client.disconnect()
        except Exception:  # noqa: BLE001
            pass


def _fetch_filter_settings(
    host: str, port: int, password: str, source_name: str, filter_name: str
) -> dict:
    client = _with_client(host, port, password)
    try:
        resp = client.get_source_filter(source_name, filter_name)
        return {
            "kind": getattr(resp, "filter_kind", None),
            "settings": getattr(resp, "filter_settings", None) or {},
        }
    except Exception as err:  # noqa: BLE001
        raise _ObsCommandError(str(err)) from err
    finally:
        try:
            client.disconnect()
        except Exception:  # noqa: BLE001
            pass


def _push_filter_settings(
    host: str,
    port: int,
    password: str,
    source_name: str,
    filter_name: str,
    settings: dict,
) -> None:
    client = _with_client(host, port, password)
    try:
        client.set_source_filter_settings(source_name, filter_name, settings, True)
    except Exception as err:  # noqa: BLE001
        raise _ObsCommandError(str(err)) from err
    finally:
        try:
            client.disconnect()
        except Exception:  # noqa: BLE001
            pass


@websocket_api.websocket_command(
    {
        vol.Required("type"): "obs_stream_monitor/get_input_settings",
        vol.Required("entry_id"): str,
        vol.Required("source_name"): str,
    }
)
@websocket_api.async_response
async def ws_get_input_settings(hass, connection, msg):
    try:
        host, port, password = _connection_info(hass, msg["entry_id"])
        result = await hass.async_add_executor_job(
            _fetch_input_settings, host, port, password, msg["source_name"]
        )
    except _ObsCommandError as err:
        connection.send_error(msg["id"], "obs_error", str(err))
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "obs_stream_monitor/set_input_settings",
        vol.Required("entry_id"): str,
        vol.Required("source_name"): str,
        vol.Required("settings"): dict,
    }
)
@websocket_api.async_response
async def ws_set_input_settings(hass, connection, msg):
    try:
        host, port, password = _connection_info(hass, msg["entry_id"])
        await hass.async_add_executor_job(
            _push_input_settings, host, port, password, msg["source_name"], msg["settings"]
        )
    except _ObsCommandError as err:
        connection.send_error(msg["id"], "obs_error", str(err))
        return
    connection.send_result(msg["id"], {"success": True})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "obs_stream_monitor/get_filter_settings",
        vol.Required("entry_id"): str,
        vol.Required("source_name"): str,
        vol.Required("filter_name"): str,
    }
)
@websocket_api.async_response
async def ws_get_filter_settings(hass, connection, msg):
    try:
        host, port, password = _connection_info(hass, msg["entry_id"])
        result = await hass.async_add_executor_job(
            _fetch_filter_settings,
            host,
            port,
            password,
            msg["source_name"],
            msg["filter_name"],
        )
    except _ObsCommandError as err:
        connection.send_error(msg["id"], "obs_error", str(err))
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "obs_stream_monitor/set_filter_settings",
        vol.Required("entry_id"): str,
        vol.Required("source_name"): str,
        vol.Required("filter_name"): str,
        vol.Required("settings"): dict,
    }
)
@websocket_api.async_response
async def ws_set_filter_settings(hass, connection, msg):
    try:
        host, port, password = _connection_info(hass, msg["entry_id"])
        await hass.async_add_executor_job(
            _push_filter_settings,
            host,
            port,
            password,
            msg["source_name"],
            msg["filter_name"],
            msg["settings"],
        )
    except _ObsCommandError as err:
        connection.send_error(msg["id"], "obs_error", str(err))
        return
    connection.send_result(msg["id"], {"success": True})


def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register the card's custom WS commands. Safe to call more than once."""
    websocket_api.async_register_command(hass, ws_get_input_settings)
    websocket_api.async_register_command(hass, ws_set_input_settings)
    websocket_api.async_register_command(hass, ws_get_filter_settings)
    websocket_api.async_register_command(hass, ws_set_filter_settings)
