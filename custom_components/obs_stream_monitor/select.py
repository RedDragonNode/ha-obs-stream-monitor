"""Select entities to switch OBS's profile / scene collection (optional, control)."""
from __future__ import annotations

import logging

import obsws_python as obsws

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ENABLE_CONTROL, CONNECT_TIMEOUT, DOMAIN
from .coordinator import ObsStreamMonitorCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add the profile/scene-collection selects, only if control is enabled.

    Off by default: this integration is monitoring-only until "OBS-Steuerung
    aktivieren" is switched on via the integration's "Configure" options (the
    entry reloads on options change, same as the SSH start button).
    """
    if not entry.options.get(CONF_ENABLE_CONTROL, False):
        return

    coordinator: ObsStreamMonitorCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            ObsProfileSelect(coordinator, entry),
            ObsSceneCollectionSelect(coordinator, entry),
        ]
    )


def _set_current_profile(host: str, port: int, password: str, name: str) -> None:
    client = obsws.ReqClient(host=host, port=port, password=password, timeout=CONNECT_TIMEOUT)
    try:
        client.set_current_profile(name)
    finally:
        try:
            client.disconnect()
        except Exception:  # noqa: BLE001 - best effort cleanup
            pass


def _set_current_scene_collection(host: str, port: int, password: str, name: str) -> None:
    client = obsws.ReqClient(host=host, port=port, password=password, timeout=CONNECT_TIMEOUT)
    try:
        client.set_current_scene_collection(name)
    finally:
        try:
            client.disconnect()
        except Exception:  # noqa: BLE001 - best effort cleanup
            pass


class _ObsBaseSelect(CoordinatorEntity[ObsStreamMonitorCoordinator], SelectEntity):
    """Shared plumbing for the profile / scene-collection selects.

    Deliberately a CoordinatorEntity (unlike the "OBS starten" button, which
    is not): switching only makes sense while OBS is actually running and
    reachable, so these should go unavailable exactly when the coordinator's
    polling does, rather than staying usable like the start button does.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ObsStreamMonitorCoordinator,
        entry: ConfigEntry,
        key: str,
        list_key: str,
        current_key: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._list_key = list_key
        self._current_key = current_key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="OBS Project",
            model="obs-websocket v5",
        )

    @property
    def options(self) -> list[str]:
        if self.coordinator.data is None:
            return []
        return self.coordinator.data.get(self._list_key) or []

    @property
    def current_option(self) -> str | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._current_key)

    @staticmethod
    def _switch(host: str, port: int, password: str, option: str) -> None:
        raise NotImplementedError

    async def async_select_option(self, option: str) -> None:
        entry = self._entry
        try:
            await self.hass.async_add_executor_job(
                self._switch,
                entry.data[CONF_HOST],
                entry.data[CONF_PORT],
                entry.data[CONF_PASSWORD],
                option,
            )
        except Exception as err:
            raise HomeAssistantError(f"Wechsel fehlgeschlagen: {err}") from err
        # Reflect the new current_profile/current_scene_collection right away
        # instead of waiting up to SCAN_INTERVAL for the next poll.
        await self.coordinator.async_request_refresh()


class ObsProfileSelect(_ObsBaseSelect):
    """Switches OBS's current profile."""

    _attr_translation_key = "obs_profile"
    _attr_icon = "mdi:account-cog-outline"
    _switch = staticmethod(_set_current_profile)

    def __init__(self, coordinator: ObsStreamMonitorCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "obs_profile", "profile_list", "current_profile")


class ObsSceneCollectionSelect(_ObsBaseSelect):
    """Switches OBS's current scene collection."""

    _attr_translation_key = "obs_scene_collection"
    _attr_icon = "mdi:folder-multiple-image"
    _switch = staticmethod(_set_current_scene_collection)

    def __init__(self, coordinator: ObsStreamMonitorCoordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            "obs_scene_collection",
            "scene_collection_list",
            "current_scene_collection",
        )
