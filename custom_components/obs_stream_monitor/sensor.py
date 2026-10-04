"""Sensor entities for OBS Stream Monitor."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfInformation, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ObsStreamMonitorCoordinator


@dataclass(frozen=True, kw_only=True)
class ObsSensorEntityDescription(SensorEntityDescription):
    """Describes an OBS Stream Monitor sensor backed by a coordinator data key."""

    data_key: str = ""


SENSOR_DESCRIPTIONS: tuple[ObsSensorEntityDescription, ...] = (
    ObsSensorEntityDescription(
        key="scene",
        translation_key="scene",
        icon="mdi:movie-open-outline",
        data_key="scene",
    ),
    ObsSensorEntityDescription(
        key="stream_duration",
        translation_key="stream_duration",
        icon="mdi:timer-outline",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        data_key="stream_duration",
    ),
    ObsSensorEntityDescription(
        key="stream_bitrate",
        translation_key="stream_bitrate",
        icon="mdi:speedometer",
        native_unit_of_measurement="kbit/s",
        state_class=SensorStateClass.MEASUREMENT,
        data_key="stream_bitrate",
    ),
    ObsSensorEntityDescription(
        key="dropped_frames_pct",
        translation_key="dropped_frames_pct",
        icon="mdi:image-broken-variant",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        data_key="dropped_frames_pct",
    ),
    ObsSensorEntityDescription(
        key="record_duration",
        translation_key="record_duration",
        icon="mdi:record-circle-outline",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        data_key="record_duration",
    ),
    ObsSensorEntityDescription(
        key="cpu_usage",
        translation_key="cpu_usage",
        icon="mdi:chip",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        data_key="cpu_usage",
    ),
    ObsSensorEntityDescription(
        key="free_disk_gb",
        translation_key="free_disk_gb",
        icon="mdi:harddisk",
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        data_key="free_disk_gb",
    ),
    ObsSensorEntityDescription(
        key="active_fps",
        translation_key="active_fps",
        icon="mdi:filmstrip",
        native_unit_of_measurement="fps",
        state_class=SensorStateClass.MEASUREMENT,
        data_key="active_fps",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up OBS Stream Monitor sensors from a config entry."""
    coordinator: ObsStreamMonitorCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        ObsStreamMonitorSensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    )


class ObsStreamMonitorSensor(CoordinatorEntity[ObsStreamMonitorCoordinator], SensorEntity):
    """A single read-only OBS stat."""

    entity_description: ObsSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ObsStreamMonitorCoordinator,
        entry: ConfigEntry,
        description: ObsSensorEntityDescription,
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
    def native_value(self):
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self.entity_description.data_key)
