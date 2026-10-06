"""Binary sensor entities for OBS Stream Monitor."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ObsStreamMonitorCoordinator


@dataclass(frozen=True, kw_only=True)
class ObsBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes an OBS Stream Monitor binary sensor backed by a coordinator data key."""

    data_key: str = ""


BINARY_SENSOR_DESCRIPTIONS: tuple[ObsBinarySensorEntityDescription, ...] = (
    ObsBinarySensorEntityDescription(
        key="stream_active",
        translation_key="stream_active",
        icon="mdi:broadcast",
        data_key="stream_active",
    ),
    ObsBinarySensorEntityDescription(
        key="record_active",
        translation_key="record_active",
        icon="mdi:record-rec",
        data_key="record_active",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up OBS Stream Monitor binary sensors from a config entry."""
    coordinator: ObsStreamMonitorCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[BinarySensorEntity] = [
        ObsStreamMonitorBinarySensor(coordinator, entry, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
    ]
    entities.append(ObsRunningBinarySensor(coordinator, entry))
    async_add_entities(entities)


class ObsStreamMonitorBinarySensor(
    CoordinatorEntity[ObsStreamMonitorCoordinator], BinarySensorEntity
):
    """A single OBS on/off state."""

    entity_description: ObsBinarySensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ObsStreamMonitorCoordinator,
        entry: ConfigEntry,
        description: ObsBinarySensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="OBS Project",
            model="obs-websocket v5",
        )

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self.entity_description.data_key)


class ObsRunningBinarySensor(
    CoordinatorEntity[ObsStreamMonitorCoordinator], BinarySensorEntity
):
    """Whether OBS itself is currently reachable over obs-websocket.

    Deliberately NOT like the sensors above: those (via CoordinatorEntity's
    default `available`) go "not available" whenever a poll fails - correct
    for "what's OBS's current scene", meaningless once OBS isn't reachable
    at all. This entity's entire purpose is reporting exactly that "OBS
    isn't reachable" state as a clean, always-available on/off rather than
    disappearing into "not available" itself, so it (and automations built
    on it, e.g. alongside the "OBS" power switch in switch.py) stay usable
    precisely when OBS is down.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "obs_running"
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:video-outline"

    def __init__(self, coordinator: ObsStreamMonitorCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_obs_running"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="OBS Project",
            model="obs-websocket v5",
        )

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.last_update_success)
