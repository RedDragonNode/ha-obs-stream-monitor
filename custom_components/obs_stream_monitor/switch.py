"""Switch entities: stream/recording/OBS-power control, plus scene-item
visibility and filter enable state.

Three kinds of switch live here, each independently optional:

- ObsStreamSwitch / ObsRecordSwitch: start/stop the stream or recording.
  Only appear once "OBS-Steuerung aktivieren" is on - same control tier as
  the profile/scene-collection selects in select.py, and like those, a
  CoordinatorEntity (goes "not available" whenever OBS itself does, since
  switching only makes sense while it's reachable).
- ObsPowerSwitch: launches OBS on the remote machine over SSH, or asks it
  to close normally. Only appears once SSH credentials are configured (see
  ssh_control.py). Deliberately NOT gated by coordinator availability like
  the two above - "OBS isn't reachable" is exactly the situation turning
  this switch on exists to fix.
- ObsSceneItemSwitch / ObsFilterSwitch: per-scene source visibility and
  per-source filter enable state. Entirely optional and off by default
  ("Szenen-Baum aktivieren" in the integration's Configure dialog). These
  are also what the bundled "OBS Szenen-Baum" dashboard card
  (custom_components/obs_stream_monitor/www/) reads and operates on -
  they're tagged with obs_role/scene/source/filter attributes specifically
  so that card can find them without depending on entity_id naming.
  Discovered dynamically from the coordinator's scene_tree data and kept in
  sync with it on every poll - added as they first appear, and deregistered
  again (removed from Home Assistant entirely, not just left "not
  available") as soon as they're no longer in the tree - since OBS's own
  scenes/sources/filters can change at any time (added, removed, renamed)
  independently of Home Assistant. A rename looks identical to a removal
  from here (the new name shows up as a new entry, the old one disappears),
  so renaming one also produces a brand-new entity rather than updating the
  old one in place - unavoidable, since obs-websocket gives no stable ID
  that survives a rename to key the entity on instead of the name itself.
  This cleanup also sweeps up switches already sitting in the entity
  registry from before this setup run (a previous Home Assistant restart,
  or from before this cleanup feature existed at all) - not just ones that
  vanish while this run is live - see _seed_known_from_registry below.
"""
from __future__ import annotations

import logging

import obsws_python as obsws

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_ENABLE_CONTROL,
    CONF_ENABLE_SCENE_TREE,
    CONF_SSH_PASSWORD,
    CONF_SSH_PORT,
    CONF_SSH_USERNAME,
    CONF_STOP_TASK_NAME,
    CONF_TASK_NAME,
    CONNECT_TIMEOUT,
    DEFAULT_SSH_PORT,
    DEFAULT_STOP_TASK_NAME,
    DEFAULT_TASK_NAME,
    DOMAIN,
)
from .coordinator import ObsStreamMonitorCoordinator
from .ssh_control import start_obs, stop_obs

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


class _LegacyPlaceholder:
    """Stands in for a scene-item/filter switch found already registered at
    startup (see _seed_known_from_registry in async_setup_entry below), so
    the stale-entity cleanup can consider deregistering it without needing
    a live ObsSceneItemSwitch/ObsFilterSwitch instance for it.
    """

    __slots__ = ("unique_id",)

    def __init__(self, unique_id: str) -> None:
        self.unique_id = unique_id


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


def _call_client_method(host: str, port: int, password: str, method_name: str) -> None:
    """Connect, call a no-argument obsws-python ReqClient method by name, disconnect.

    Shared by the stream/recording switches below (start_stream/stop_stream/
    start_record/stop_record all have this exact shape).
    """
    client = obsws.ReqClient(host=host, port=port, password=password, timeout=CONNECT_TIMEOUT)
    try:
        getattr(client, method_name)()
    finally:
        try:
            client.disconnect()
        except Exception:  # noqa: BLE001 - best effort cleanup
            pass


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add the control switches that don't depend on the scene tree, then
    (only if "Szenen-Baum aktivieren" is on) the dynamic scene-item/filter
    switches.

    Off by default, independently of each other: the stream/recording
    switches need "OBS-Steuerung aktivieren"; the OBS power switch needs
    SSH credentials configured; the scene-item/filter switches need
    "Szenen-Baum aktivieren". All are toggled via the integration's
    "Configure" options (the entry reloads on options change).
    """
    coordinator: ObsStreamMonitorCoordinator = hass.data[DOMAIN][entry.entry_id]

    control_entities: list[SwitchEntity] = []
    if entry.options.get(CONF_ENABLE_CONTROL, False):
        control_entities.append(ObsStreamSwitch(coordinator, entry))
        control_entities.append(ObsRecordSwitch(coordinator, entry))
    if entry.options.get(CONF_SSH_USERNAME):
        control_entities.append(ObsPowerSwitch(coordinator, entry))
    if control_entities:
        async_add_entities(control_entities)

    if not entry.options.get(CONF_ENABLE_SCENE_TREE, False):
        return

    known_items: dict[object, ObsSceneItemSwitch | _LegacyPlaceholder] = {}
    known_filters: dict[object, ObsFilterSwitch | _LegacyPlaceholder] = {}

    def _deregister(entity: SwitchEntity) -> None:
        """Permanently remove a scene-item/filter switch whose source/filter
        is no longer in OBS's scene tree, instead of leaving it stuck
        "not available" forever (see the class docstring above).
        """
        registry = er.async_get(hass)
        entity_id = registry.async_get_entity_id("switch", DOMAIN, entity.unique_id)
        if entity_id:
            registry.async_remove(entity_id)

    def _seed_known_from_registry() -> None:
        """Pre-populate known_items/known_filters with scene-item/filter
        switches that are already in the entity registry from before this
        setup run - e.g. left over from before Home Assistant restarted, or
        from before this cleanup feature even existed.

        known_items/known_filters start empty on every setup (every HA
        restart, every reload), and _sync_entities below only ever adds an
        entry to them when it sees that item/filter in a *live* scene-tree
        poll. A stale switch that's already missing from the very first
        poll after restart would therefore never be added to either dict in
        the first place - and a diff can't notice something is gone if it
        was never in the "known" set to begin with. That's exactly the kind
        of karteileiche these dicts exist to catch, so it's seeded with
        whatever the registry already has for this config entry *before*
        the first _sync_entities() call: anything still genuinely live gets
        matched up with its real key once the first poll comes in (HA
        reuses the existing registry entry for a matching unique_id rather
        than duplicating it), while anything that stays unmatched - because
        its key is just the unique_id itself here, never a real (scene,
        source) tuple or "source\x1ffilter" string - falls out as stale on
        the very first successful poll and gets removed.
        """
        registry = er.async_get(hass)
        item_prefix = f"{entry.entry_id}_sceneitem_"
        filter_prefix = f"{entry.entry_id}_filter_"
        for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
            if reg_entry.domain != "switch" or not reg_entry.unique_id:
                continue
            if reg_entry.unique_id.startswith(item_prefix):
                known_items.setdefault(reg_entry.unique_id, _LegacyPlaceholder(reg_entry.unique_id))
            elif reg_entry.unique_id.startswith(filter_prefix):
                known_filters.setdefault(reg_entry.unique_id, _LegacyPlaceholder(reg_entry.unique_id))

    @callback
    def _sync_entities() -> None:
        # Guard against a transient poll failure wiping the tree: a failed
        # coordinator refresh leaves coordinator.data at its last *successful*
        # value (HA's DataUpdateCoordinator never clears it on failure), so
        # this only ever sees an empty/shrunk tree when OBS actually reported
        # one - never as a side effect of OBS being briefly unreachable.
        if not coordinator.last_update_success:
            return
        tree = (coordinator.data or {}).get("scene_tree") or {}
        new_entities: list[SwitchEntity] = []
        current_item_keys: set[tuple[str, str]] = set()
        current_filter_keys: set[str] = set()
        # Sources whose filter list couldn't be fetched this poll (see the
        # filters_unknown note in coordinator._fetch_scene_tree) - an empty
        # filters list for these is "unknown", not "none", so their already-
        # known filter switches must not be treated as stale below.
        unknown_filter_sources: set[str] = set()

        for scene_name, items in tree.items():
            for item in items:
                source_name = item["source_name"]

                item_key = (scene_name, source_name)
                current_item_keys.add(item_key)
                if item_key not in known_items:
                    ent = ObsSceneItemSwitch(coordinator, entry, scene_name, source_name)
                    known_items[item_key] = ent
                    new_entities.append(ent)

                if item.get("filters_unknown"):
                    unknown_filter_sources.add(source_name)

                for flt in item["filters"]:
                    filter_key = f"{source_name}\x1f{flt['name']}"
                    current_filter_keys.add(filter_key)
                    if filter_key not in known_filters:
                        fent = ObsFilterSwitch(coordinator, entry, source_name, flt["name"])
                        known_filters[filter_key] = fent
                        new_entities.append(fent)

        if new_entities:
            async_add_entities(new_entities)

        if unknown_filter_sources:
            for filter_key in known_filters:
                source_name = filter_key.split("\x1f", 1)[0]
                if source_name in unknown_filter_sources:
                    current_filter_keys.add(filter_key)

        for stale_key in set(known_items) - current_item_keys:
            _deregister(known_items.pop(stale_key))
        for stale_key in set(known_filters) - current_filter_keys:
            _deregister(known_filters.pop(stale_key))

    _seed_known_from_registry()
    entry.async_on_unload(coordinator.async_add_listener(_sync_entities))
    _sync_entities()


class _ObsControlSwitch(CoordinatorEntity[ObsStreamMonitorCoordinator], SwitchEntity):
    """Shared plumbing for the stream/recording on-off switches.

    Like the profile/scene-collection selects in select.py (and unlike
    ObsPowerSwitch below): a CoordinatorEntity, since starting/stopping the
    stream or recording only makes sense while OBS is actually reachable,
    so these should go "not available" exactly when the coordinator's
    polling does.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ObsStreamMonitorCoordinator,
        entry: ConfigEntry,
        key: str,
        data_key: str,
        start_method: str,
        stop_method: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._data_key = data_key
        self._start_method = start_method
        self._stop_method = stop_method
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = _device_info(entry)

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._data_key)

    async def async_turn_on(self, **kwargs) -> None:
        await self._call(self._start_method)

    async def async_turn_off(self, **kwargs) -> None:
        await self._call(self._stop_method)

    async def _call(self, method_name: str) -> None:
        entry = self._entry
        try:
            await self.hass.async_add_executor_job(
                _call_client_method,
                entry.data[CONF_HOST],
                entry.data[CONF_PORT],
                entry.data[CONF_PASSWORD],
                method_name,
            )
        except Exception as err:
            raise HomeAssistantError(f"Schalten fehlgeschlagen: {err}") from err
        # Reflect the new stream_active/record_active right away instead of
        # waiting up to SCAN_INTERVAL for the next poll.
        await self.coordinator.async_request_refresh()


class ObsStreamSwitch(_ObsControlSwitch):
    """Starts/stops the live stream."""

    _attr_translation_key = "obs_stream"
    _attr_icon = "mdi:broadcast"

    def __init__(self, coordinator: ObsStreamMonitorCoordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator, entry, "obs_stream_switch", "stream_active", "start_stream", "stop_stream"
        )


class ObsRecordSwitch(_ObsControlSwitch):
    """Starts/stops recording."""

    _attr_translation_key = "obs_record"
    _attr_icon = "mdi:record-rec"

    def __init__(self, coordinator: ObsStreamMonitorCoordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator, entry, "obs_record_switch", "record_active", "start_record", "stop_record"
        )


class ObsPowerSwitch(CoordinatorEntity[ObsStreamMonitorCoordinator], SwitchEntity):
    """Launches or gracefully closes OBS on the remote machine, each via its
    own Windows Scheduled Task triggered over SSH (see ssh_control.py).

    Deliberately NOT gated by coordinator availability like the two control
    switches above: unlike those, "OBS isn't reachable" is exactly the
    situation turning this switch on exists to fix, so it has to stay
    usable precisely when the coordinator's polling says it isn't - see
    `available` below. `is_on` reflects the same signal as
    binary_sensor.py's ObsRunningBinarySensor (the coordinator's last poll
    result), so this switch's own state tracks reality instead of just
    remembering which way it was last flipped.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "obs_power"
    _attr_icon = "mdi:power"

    def __init__(self, coordinator: ObsStreamMonitorCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_obs_power"
        self._attr_device_info = _device_info(entry)

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.last_update_success)

    async def async_turn_on(self, **kwargs) -> None:
        entry = self._entry
        host = entry.data[CONF_HOST]
        ssh_port = entry.options.get(CONF_SSH_PORT, DEFAULT_SSH_PORT)
        ssh_username = entry.options.get(CONF_SSH_USERNAME)
        ssh_password = entry.options.get(CONF_SSH_PASSWORD)
        task_name = entry.options.get(CONF_TASK_NAME, DEFAULT_TASK_NAME)
        try:
            await self.hass.async_add_executor_job(
                start_obs, host, ssh_port, ssh_username, ssh_password, task_name
            )
        except Exception as err:
            raise HomeAssistantError(f"OBS-Start über SSH fehlgeschlagen: {err}") from err
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        entry = self._entry
        host = entry.data[CONF_HOST]
        ssh_port = entry.options.get(CONF_SSH_PORT, DEFAULT_SSH_PORT)
        ssh_username = entry.options.get(CONF_SSH_USERNAME)
        ssh_password = entry.options.get(CONF_SSH_PASSWORD)
        stop_task_name = entry.options.get(CONF_STOP_TASK_NAME, DEFAULT_STOP_TASK_NAME)
        try:
            await self.hass.async_add_executor_job(
                stop_obs, host, ssh_port, ssh_username, ssh_password, stop_task_name
            )
        except Exception as err:
            raise HomeAssistantError(f"OBS-Beenden über SSH fehlgeschlagen: {err}") from err
        await self.coordinator.async_request_refresh()


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
