"""Binaersensoren des Recorders."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SpielpartnerConfigEntry
from .const import SUBENTRY_CAM
from .entity import SpielpartnerEntity, cam_device, hub_device
from .manager import CamCfg, SpielpartnerManager


async def async_setup_entry(
    hass: HomeAssistant, entry: SpielpartnerConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    m = entry.runtime_data
    async_add_entities([RecorderOnlineSensor(m), RecorderRunningSensor(m)])
    for sid, sub in entry.subentries.items():
        if sub.subentry_type == SUBENTRY_CAM:
            cam = next(c for c in m.cams if c.subentry_id == sid)
            async_add_entities([CamRecordingSensor(m, cam)], config_subentry_id=sid)


class RecorderOnlineSensor(SpielpartnerEntity, BinarySensorEntity):
    _attr_translation_key = "recorder_online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, m: SpielpartnerManager) -> None:
        super().__init__(m)
        self._attr_unique_id = f"{m.entry.entry_id}_recorder_online"
        self._attr_device_info = hub_device(m)

    @property
    def available(self) -> bool:
        return self.manager.uses_recorder

    @property
    def is_on(self) -> bool:
        return bool(self.manager.rec_online)

    @property
    def extra_state_attributes(self) -> dict:
        return {"version": self.manager.rec_status.get("version")}


class RecorderRunningSensor(SpielpartnerEntity, BinarySensorEntity):
    _attr_translation_key = "recorder_aufnahme"
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:record-rec"

    def __init__(self, m: SpielpartnerManager) -> None:
        super().__init__(m)
        self._attr_unique_id = f"{m.entry.entry_id}_recorder_aufnahme"
        self._attr_device_info = hub_device(m)

    @property
    def available(self) -> bool:
        return self.manager.uses_recorder

    @property
    def is_on(self) -> bool:
        return self.manager.recorder_running

    @property
    def extra_state_attributes(self) -> dict:
        r = self.manager.data.get("recorder") or {}
        return {"seit": r.get("start"), "spielpartner": r.get("partner")}


class CamRecordingSensor(SpielpartnerEntity, BinarySensorEntity):
    _attr_translation_key = "cam_aufnahme"
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, m: SpielpartnerManager, cam: CamCfg) -> None:
        super().__init__(m)
        self.cam = cam
        self._attr_unique_id = f"{m.entry.entry_id}_cam_{cam.subentry_id}_aufnahme"
        self._attr_device_info = cam_device(m, cam)

    @property
    def available(self) -> bool:
        return self.manager.uses_recorder

    def _info(self) -> dict:
        return (self.manager.rec_status.get("kameras") or {}).get(self.cam.subentry_id) or {}

    @property
    def is_on(self) -> bool:
        return self.manager.recorder_running and self._info().get("status") == "nimmt auf"

    @property
    def extra_state_attributes(self) -> dict:
        i = self._info()
        return {
            "status": i.get("status"),
            "datei": i.get("datei"),
            "teil": i.get("teil"),
            "neustarts": i.get("neustarts"),
            "groesse_mb": round((i.get("bytes") or 0) / 1e6, 1),
            "letzter_fehler": i.get("letzter_fehler") or None,
        }
