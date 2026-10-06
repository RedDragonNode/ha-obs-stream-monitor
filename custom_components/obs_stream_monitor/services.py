"""Custom service: push raw OBS source/filter settings from an automation
or script.

This is the automation-facing counterpart to the dashboard card's settings
dialog (see websocket_api.py, which the card's gear-icon dialog calls
instead) - same underlying obs-websocket calls (SetInputSettings /
SetSourceFilterSettings with overlay=True, i.e. only the fields you give
are changed, everything else is left as-is), just reachable as a normal
Home Assistant service so it can run from an automation or script and not
only by hand from the dialog.

Rather than taking a raw entry_id/source_name/filter_name triple, the
service targets one of the existing "OBS Szenen-Baum" switch entities
(switch.obs_sceneitem_* for a source, switch.obs_filter_* for a filter -
see switch.py) - exactly the entity_id the card's copy-icon already gives
you. The entry_id/source/filter the OBS call actually needs are read back
off that entity's own obs_role/obs_entry_id/source/filter attributes, so
there's nothing extra to look up or type by hand.
"""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .websocket_api import _ObsCommandError, _push_filter_settings, _push_input_settings

_LOGGER = logging.getLogger(__name__)

SERVICE_SET_SETTINGS = "set_settings"

SET_SETTINGS_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_ids,
        vol.Required("settings"): dict,
    }
)


async def _async_set_settings(hass: HomeAssistant, call: ServiceCall) -> None:
    entity_ids: list[str] = call.data["entity_id"]
    settings: dict = call.data["settings"]
    errors: list[str] = []

    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        if state is None:
            errors.append(f"{entity_id}: Entität nicht gefunden.")
            continue

        attrs = state.attributes
        role = attrs.get("obs_role")
        entry_id = attrs.get("obs_entry_id")
        source_name = attrs.get("source")

        if role not in ("scene_item", "filter") or not entry_id or not source_name:
            errors.append(
                f"{entity_id}: keine OBS-Quellen-/Filter-Einstellungen für diese Entität - "
                "nur die Schalter der 'Szenen-Baum'-Funktion (switch.obs_sceneitem_* für "
                "Quellen, switch.obs_filter_* für Filter) werden unterstützt."
            )
            continue

        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            errors.append(f"{entity_id}: zugehöriger OBS-Stream-Monitor-Eintrag nicht gefunden.")
            continue

        host = entry.data[CONF_HOST]
        port = entry.data[CONF_PORT]
        password = entry.data[CONF_PASSWORD]

        try:
            if role == "filter":
                filter_name = attrs.get("filter")
                if not filter_name:
                    errors.append(f"{entity_id}: Filtername fehlt an der Entität.")
                    continue
                await hass.async_add_executor_job(
                    _push_filter_settings,
                    host,
                    port,
                    password,
                    source_name,
                    filter_name,
                    settings,
                )
            else:
                await hass.async_add_executor_job(
                    _push_input_settings, host, port, password, source_name, settings
                )
        except _ObsCommandError as err:
            errors.append(f"{entity_id}: {err}")

    if errors:
        raise HomeAssistantError(" | ".join(errors))


def async_register_services(hass: HomeAssistant) -> None:
    """Register the set_settings service. Safe to call more than once."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_SETTINGS):
        return

    async def _handle_set_settings(call: ServiceCall) -> None:
        await _async_set_settings(hass, call)

    hass.services.async_register(
        DOMAIN, SERVICE_SET_SETTINGS, _handle_set_settings, schema=SET_SETTINGS_SCHEMA
    )
