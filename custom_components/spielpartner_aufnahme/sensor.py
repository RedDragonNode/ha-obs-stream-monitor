"""Sensoren."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfInformation
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SpielpartnerConfigEntry
from .const import SUBENTRY_CAM, SUBENTRY_PARTNER
from .entity import SpielpartnerEntity, cam_device, hub_device, partner_device
from .manager import CamCfg, PartnerCfg, SpielpartnerManager


async def async_setup_entry(
    hass: HomeAssistant, entry: SpielpartnerConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    m = entry.runtime_data
    async_add_entities([ActivePartnerSensor(m), StatusSensor(m), RecorderSpaceSensor(m)])
    for sid, sub in entry.subentries.items():
        if sub.subentry_type == SUBENTRY_PARTNER:
            p = m.partners[sub.data["kennung"]]
            async_add_entities(
                [PathSensor(m, p), FormatSensor(m, p), ThreadSensor(m, p)], config_subentry_id=sid
            )
        elif sub.subentry_type == SUBENTRY_CAM:
            cam = next(c for c in m.cams if c.subentry_id == sid)
            async_add_entities([CamFormatSensor(m, cam)], config_subentry_id=sid)


class ActivePartnerSensor(SpielpartnerEntity, SensorEntity):
    _attr_translation_key = "aktueller_spielpartner"
    _attr_icon = "mdi:account-voice"

    def __init__(self, m: SpielpartnerManager) -> None:
        super().__init__(m)
        self._attr_unique_id = f"{m.entry.entry_id}_aktuell"
        self._attr_device_info = hub_device(m)

    @property
    def native_value(self) -> str | None:
        return self.manager.data.get("active")

    @property
    def extra_state_attributes(self) -> dict:
        p = self.manager.active
        if p is None:
            return {}
        s = self.manager.state_of(p.kennung)
        return {
            "anzeige": p.anzeige,
            "ordner_nr": p.ordner_nr,
            "saison": s["saison"],
            "aufnahmen_in_saison": s["aufnahmen"],
            "gesamt": s["gesamt"],
            "speicher_adresse": s["pfad"],
        }


class StatusSensor(SpielpartnerEntity, SensorEntity):
    _attr_translation_key = "status"
    _attr_icon = "mdi:information-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, m: SpielpartnerManager) -> None:
        super().__init__(m)
        self._attr_unique_id = f"{m.entry.entry_id}_status"
        self._attr_device_info = hub_device(m)

    @property
    def native_value(self) -> str | None:
        return (self.manager.data.get("status") or {}).get("text")

    @property
    def extra_state_attributes(self) -> dict:
        return {"zeit": (self.manager.data.get("status") or {}).get("zeit")}


class _PartnerSensor(SpielpartnerEntity, SensorEntity):
    key = ""

    def __init__(self, m: SpielpartnerManager, p: PartnerCfg) -> None:
        super().__init__(m)
        self.partner = p
        self._attr_unique_id = f"{m.entry.entry_id}_{p.kennung}_{self.key}"
        self._attr_translation_key = self.key
        self._attr_device_info = partner_device(m, p)

    @property
    def _s(self) -> dict:
        return self.manager.state_of(self.partner.kennung)


class PathSensor(_PartnerSensor):
    key = "speicher_adresse"
    _attr_icon = "mdi:folder-play"

    @property
    def native_value(self) -> str | None:
        return self._s.get("pfad") or None


class FormatSensor(_PartnerSensor):
    key = "dateiformat"
    _attr_icon = "mdi:file-video"

    @property
    def native_value(self) -> str:
        return self.manager.format_for(self.partner.kennung, None)


class ThreadSensor(_PartnerSensor):
    key = "discord_thread"
    _attr_icon = "mdi:forum"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> str | None:
        return self._s.get("thread_id") or None

    @property
    def extra_state_attributes(self) -> dict:
        return {"saison": self._s.get("thread_saison"), "forum_id": self.partner.forum_id}


class CamFormatSensor(SpielpartnerEntity, SensorEntity):
    _attr_translation_key = "cam_dateiformat"
    _attr_icon = "mdi:video-box"

    def __init__(self, m: SpielpartnerManager, cam: CamCfg) -> None:
        super().__init__(m)
        self.cam = cam
        self._attr_unique_id = f"{m.entry.entry_id}_cam_{cam.subentry_id}_format"
        self._attr_device_info = cam_device(m, cam)

    @property
    def native_value(self) -> str | None:
        p = self.manager.active
        return self.manager.format_for(p.kennung, self.cam) if p else None

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "kuerzel": self.cam.kuerzel,
            "obs_filter": self.manager.cam_filters(self.cam),
            "kamera": self.cam.camera_entity or None,
            "in_discord_posten": self.cam.post,
            "recorder_aufnehmen": self.cam.record,
            "recorder_quelle": "rtsp_url" if self.cam.rtsp_url else (self.cam.stream_entity or None),
        }


class RecorderSpaceSensor(SpielpartnerEntity, SensorEntity):
    """Freier Speicher am Aufnahme-Ort des Recorders."""

    _attr_translation_key = "recorder_frei"
    _attr_icon = "mdi:harddisk"
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_native_unit_of_measurement = UnitOfInformation.GIGABYTES
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, m: SpielpartnerManager) -> None:
        super().__init__(m)
        self._attr_unique_id = f"{m.entry.entry_id}_recorder_frei"
        self._attr_device_info = hub_device(m)

    @property
    def available(self) -> bool:
        return self.manager.uses_recorder and bool(self.manager.rec_online)

    @property
    def native_value(self) -> float | None:
        return (self.manager.rec_status.get("speicher") or {}).get("frei_gb")

    @property
    def extra_state_attributes(self) -> dict:
        sp = self.manager.rec_status.get("speicher") or {}
        return {"gesamt_gb": sp.get("gesamt_gb"), "ordner": self.manager.rec_status.get("wurzel")}
