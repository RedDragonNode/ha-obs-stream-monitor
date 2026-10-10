"""Basisklassen der Entities."""
from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .manager import CamCfg, PartnerCfg, SpielpartnerManager


class SpielpartnerEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, manager: SpielpartnerManager) -> None:
        self.manager = manager

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, self.manager.signal, self._update))

    @callback
    def _update(self) -> None:
        self.async_write_ha_state()


def hub_device(manager: SpielpartnerManager) -> DeviceInfo:
    return DeviceInfo(identifiers={(DOMAIN, manager.entry.entry_id)})


def partner_device(manager: SpielpartnerManager, p: PartnerCfg) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, f"{manager.entry.entry_id}_p_{p.kennung}")},
        name=f"Spielpartner {p.anzeige}",
        manufacturer="RedDragonNode",
        model="Spielpartner",
    )


def cam_device(manager: SpielpartnerManager, c: CamCfg) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, f"{manager.entry.entry_id}_c_{c.subentry_id}")},
        name=f"Cam {c.name}",
        manufacturer="RedDragonNode",
        model="Cam",
    )
