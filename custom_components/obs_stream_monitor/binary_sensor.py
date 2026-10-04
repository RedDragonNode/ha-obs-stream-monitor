"""Binary sensor entities for OBS Stream Monitor."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
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
    async_add_entities(
        ObsStreamMonitorBinarySensor(coordinator, entry, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
    )


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
