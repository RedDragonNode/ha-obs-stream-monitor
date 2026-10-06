"""The OBS Stream Monitor integration."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, Platform
from homeassistant.core import HomeAssistant

from .const import CONF_ENABLE_SCENE_TREE, DOMAIN
from .coordinator import ObsStreamMonitorCoordinator
from .websocket_api import async_register_websocket_commands

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SELECT,
    Platform.SWITCH,
]

# Served so the bundled "OBS Szenen-Baum" dashboard card is available
# without copying any file by hand. Still needs a one-time manual step in
# Settings -> Dashboards -> Resources (see docs/scene-tree-dashboard-setup.md)
# - Home Assistant doesn't let an integration register a Lovelace resource
# for the user automatically.
CARD_URL_PATH = "/obs_stream_monitor_card/obs-scene-tree-card.js"
CARD_FILE = Path(__file__).parent / "www" / "obs-scene-tree-card.js"

# Served alongside the card itself: the settings-editor dialog's field/kind
# label lookup table (see obs-settings-labels.js's own doc-comment). The
# card statically imports it by a plain relative URL
# ("./obs-settings-labels.js"), so it just needs to be reachable under the
# same URL prefix as the card - no separate Lovelace resource entry needed.
LABELS_URL_PATH = "/obs_stream_monitor_card/obs-settings-labels.js"
LABELS_FILE = Path(__file__).parent / "www" / "obs-settings-labels.js"


async def _async_register_frontend_card(hass: HomeAssistant) -> None:
    """Serve the dashboard card's JS files. Safe to call once per HA run."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get("_frontend_registered"):
        return
    domain_data["_frontend_registered"] = True

    try:
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(CARD_URL_PATH, str(CARD_FILE), cache_headers=False),
                StaticPathConfig(LABELS_URL_PATH, str(LABELS_FILE), cache_headers=False),
            ]
        )
    except ImportError:
        # Home Assistant Core older than 2024.7, before StaticPathConfig existed.
        await hass.async_add_executor_job(
            hass.http.register_static_path, CARD_URL_PATH, str(CARD_FILE), False
        )
        await hass.async_add_executor_job(
            hass.http.register_static_path, LABELS_URL_PATH, str(LABELS_FILE), False
        )
    except Exception:  # noqa: BLE001 - never block entity setup over the card
        _LOGGER.warning(
            "Konnte die 'OBS Szenen-Baum'-Dashboard-Karte nicht bereitstellen; "
            "Monitoring und Steuerung sind davon nicht betroffen.",
            exc_info=True,
        )


def _async_register_card_backend(hass: HomeAssistant) -> None:
    """Register the card's settings-editor WS commands. Safe to call once per run."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get("_ws_commands_registered"):
        return
    domain_data["_ws_commands_registered"] = True
    async_register_websocket_commands(hass)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up OBS Stream Monitor from a config entry."""
    await _async_register_frontend_card(hass)
    _async_register_card_backend(hass)

    coordinator = ObsStreamMonitorCoordinator(
        hass,
        entry,
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        password=entry.data[CONF_PASSWORD],
        enable_scene_tree=entry.options.get(CONF_ENABLE_SCENE_TREE, False),
    )

    # Deliberately NOT async_config_entry_first_refresh(): that raises
    # ConfigEntryNotReady and aborts the whole entry - including the
    # "OBS starten" button platform - whenever OBS/obs-websocket isn't
    # reachable yet. But "OBS isn't running" is exactly the situation the
    # button exists to fix, so a failed first poll must not block setup.
    # async_refresh() just records the failure; sensors then come up as
    # unavailable (via CoordinatorEntity) while the button stays usable.
    await coordinator.async_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload when options (SSH / control / scene-tree settings) change, so
    # entities appear or disappear without a manual restart.
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: ObsStreamMonitorCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
    return unload_ok
