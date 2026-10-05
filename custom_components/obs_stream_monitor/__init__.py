"""The OBS Stream Monitor integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import ObsStreamMonitorCoordinator

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SELECT,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up OBS Stream Monitor from a config entry."""
    coordinator = ObsStreamMonitorCoordinator(
        hass,
        entry,
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        password=entry.data[CONF_PASSWORD],
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

    # Reload when options (SSH / start-button settings) change, so the
    # button entity appears or disappears without a manual restart.
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
