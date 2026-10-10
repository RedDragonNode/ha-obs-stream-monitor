"""Editierbare Zaehler (Saison / Aufnahmen in Saison / Gesamt)."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SpielpartnerConfigEntry
from .const import SUBENTRY_PARTNER
from .entity import SpielpartnerEntity, partner_device
from .manager import PartnerCfg, SpielpartnerManager

COUNTERS = {
    "saison": ("saison", "mdi:calendar-range"),
    "aufnahmen_in_saison": ("aufnahmen", "mdi:video-box"),
    "gesamt": ("gesamt", "mdi:counter"),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: SpielpartnerConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    m = entry.runtime_data
    for sid, sub in entry.subentries.items():
        if sub.subentry_type == SUBENTRY_PARTNER:
            p = m.partners[sub.data["kennung"]]
            async_add_entities(
                [CounterNumber(m, p, key, field, icon) for key, (field, icon) in COUNTERS.items()],
                config_subentry_id=sid,
            )


class CounterNumber(SpielpartnerEntity, NumberEntity):
    _attr_native_min_value = 0
    _attr_native_max_value = 9999
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, m: SpielpartnerManager, p: PartnerCfg, key: str, field: str, icon: str) -> None:
        super().__init__(m)
        self.partner, self.field = p, field
        self._attr_unique_id = f"{m.entry.entry_id}_{p.kennung}_{key}"
        self._attr_translation_key = key
        self._attr_icon = icon
        self._attr_device_info = partner_device(m, p)
        self._service_key = key

    @property
    def native_value(self) -> float:
        return self.manager.state_of(self.partner.kennung)[self.field]

    async def async_set_native_value(self, value: float) -> None:
        kwargs = {"saison": None, "aufnahmen": None, "gesamt": None}
        kwargs[self.field] = int(value)
        await self.manager.async_set_counters(self.partner.kennung, **kwargs)
