"""Switch entities for scene-item visibility and filter enable state.

Entirely optional and off by default ("Szenen-Baum aktivieren" in the
integration's Configure dialog). These entities are also what the bundled
"OBS Szenen-Baum" dashboard card (custom_components/obs_stream_monitor/www/)
reads and operates on - they're tagged with obs_role/scene/source/filter
attributes specifically so that card can find them without depending on
entity_id naming.

Entities are discovered dynamically from the coordinator's scene_tree data
and added as they first appear, since OBS's own scenes/sources/filters can
change at any time (added, removed, renamed) independently of Home
Assistant.
"""
from __future__ import annotations

import logging

import obsws_python as obsws

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ENABLE_SCENE_TREE, CONNECT_TIMEOUT, DOMAIN
from .coordinator import ObsStreamMonitorCoordinator

_LOGGER = logging.getLogger(__name__)


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="OBS Project",
        model="obs-websocket v5",
    )


def _slug(*parts: str) -> str:
    return "_".join(parts).lower().replace(" ", "_")


def _set_scene_item_enabled(
    host: str, port: int, password: str, scene_name: str, item_id: int, enabled: bool
) -> None:
    client = obsws.ReqClient(host=host, port=port, password=password, timeout=CONNECT_TIMEOUT)
    try:
        client.set_scene_item_enabled(scene_name, item_id, enabled)
    finally:
        try:
            client.disconnect()
        except Exception:  # noqa: BLE001 - best effort cleanup
            pass


def _set_source_filter_enabled(
    host: str, port: int, password: str, source_name: str, filter_name: str, enabled: bool
) -> None:
    client = obsws.ReqClient(host=host, port=port, password=password, timeout=CONNECT_TIMEOUT)
    try:
        client.set_source_filter_enabled(source_name, filter_name, enabled)
    finally:
        try:
            client.disconnect()
        except Exception:  # noqa: BLE001 - best effort cleanup
            pass


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add scene-item/filter switches, only if the scene tree is enabled.

    Off by default: nothing is added until "Szenen-Baum aktivieren" is
    switched on via the integration's "Configure" options (the entry
    reloads on options change, same as the other optional extras).
    """
    if not entry.options.get(CONF_ENABLE_SCENE_TREE, False):
        return

    coordinator: ObsStreamMonitorCoordinator = hass.data[DOMAIN][entry.entry_id]
    known_items: dict[tuple[str, str], ObsSceneItemSwitch] = {}
    known_filters: dict[str, ObsFilterSwitch] = {}

    @callback
    def _add_new_entities() -> None:
        tree = (coordinator.data or {}).get("scene_tree") or {}
        new_entities: list[SwitchEntity] = []

        for scene_name, items in tree.items():
            for item in items:
                source_name = item["source_name"]

                item_key = (scene_name, source_name)
                if item_key not in known_items:
                    ent = ObsSceneItemSwitch(coordinator, entry, scene_name, source_name)
                    known_items[item_key] = ent
                    new_entities.append(ent)

                for flt in item["filters"]:
                    filter_key = f"{source_name}\x1f{flt['name']}"
                    if filter_key not in known_filters:
                        fent = ObsFilterSwitch(coordinator, entry, source_name, flt["name"])
                        known_filters[filter_key] = fent
                        new_entities.append(fent)

        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_add_new_entities))
    _add_new_entities()


class ObsSceneItemSwitch(CoordinatorEntity[ObsStreamMonitorCoordinator], SwitchEntity):
    """Shows/hides a source within one specific scene (the "eye" icon in OBS)."""

    _attr_icon = "mdi:eye-outline"

    def __init__(
        self,
        coordinator: ObsStreamMonitorCoordinator,
        entry: ConfigEntry,
        scene_name: str,
        source_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._scene_name = scene_name
        self._source_name = source_name
        self._attr_unique_id = f"{entry.entry_id}_sceneitem_{_slug(scene_name, source_name)}"
        self._attr_name = f"{scene_name}: {source_name} sichtbar"
        self._attr_device_info = _device_info(entry)

    def _find_item(self) -> dict | None:
        tree = (self.coordinator.data or {}).get("scene_tree") or {}
        for item in tree.get(self._scene_name, []):
            if item["source_name"] == self._source_name:
                return item
        return None

    @property
    def available(self) -> bool:
        return super().available and self._find_item() is not None

    @property
    def is_on(self) -> bool | None:
        item = self._find_item()
        return item["enabled"] if item else None

    @property
    def extra_state_attributes(self) -> dict:
        item = self._find_item()
        return {
            "obs_role": "scene_item",
            "obs_entry_id": self._entry.entry_id,
            "scene": self._scene_name,
            "source": self._source_name,
            "source_kind": item["source_kind"] if item else None,
        }

    async def async_turn_on(self, **kwargs) -> None:
        await self._set_enabled(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set_enabled(False)

    async def _set_enabled(self, enabled: bool) -> None:
        item = self._find_item()
        if item is None:
            raise HomeAssistantError(
                f"'{self._source_name}' in Szene '{self._scene_name}' aktuell nicht bekannt."
            )
        entry = self._entry
        try:
            await self.hass.async_add_executor_job(
                _set_scene_item_enabled,
                entry.data[CONF_HOST],
                entry.data[CONF_PORT],
                entry.data[CONF_PASSWORD],
                self._scene_name,
                item["scene_item_id"],
                enabled,
            )
        except Exception as err:
            raise HomeAssistantError(f"Schalten fehlgeschlagen: {err}") from err
        await self.coordinator.async_request_refresh()


class ObsFilterSwitch(CoordinatorEntity[ObsStreamMonitorCoordinator], SwitchEntity):
    """Enables/disables one filter on a source.

    Filters belong to the source itself (not to a specific scene), so this
    is one entity per (source, filter) pair even if the source appears in
    several scenes.
    """

    _attr_icon = "mdi:filter-outline"

    def __init__(
        self,
        coordinator: ObsStreamMonitorCoordinator,
        entry: ConfigEntry,
        source_name: str,
        filter_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._source_name = source_name
        self._filter_name = filter_name
        self._attr_unique_id = f"{entry.entry_id}_filter_{_slug(source_name, filter_name)}"
        self._attr_name = f"{source_name}: Filter {filter_name}"
        self._attr_device_info = _device_info(entry)

    def _find_filter(self) -> dict | None:
        tree = (self.coordinator.data or {}).get("scene_tree") or {}
        for items in tree.values():
            for item in items:
                if item["source_name"] != self._source_name:
                    continue
                for flt in item["filters"]:
                    if flt["name"] == self._filter_name:
                        return flt
        return None

    @property
    def available(self) -> bool:
        return super().available and self._find_filter() is not None

    @property
    def is_on(self) -> bool | None:
        flt = self._find_filter()
        return flt["enabled"] if flt else None

    @property
    def extra_state_attributes(self) -> dict:
        flt = self._find_filter()
        return {
            "obs_role": "filter",
            "obs_entry_id": self._entry.entry_id,
            "source": self._source_name,
            "filter": self._filter_name,
            "filter_kind": flt["kind"] if flt else None,
        }

    async def async_turn_on(self, **kwargs) -> None:
        await self._set_enabled(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set_enabled(False)

    async def _set_enabled(self, enabled: bool) -> None:
        entry = self._entry
        try:
            await self.hass.async_add_executor_job(
                _set_source_filter_enabled,
                entry.data[CONF_HOST],
                entry.data[CONF_PORT],
                entry.data[CONF_PASSWORD],
                self._source_name,
                self._filter_name,
                enabled,
            )
        except Exception as err:
            raise HomeAssistantError(f"Schalten fehlgeschlagen: {err}") from err
        await self.coordinator.async_request_refresh()
