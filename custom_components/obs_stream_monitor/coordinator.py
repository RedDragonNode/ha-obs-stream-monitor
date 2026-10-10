"""DataUpdateCoordinator for OBS Stream Monitor."""
from __future__ import annotations

import logging
import time

import obsws_python as obsws

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONNECT_TIMEOUT, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class ObsStreamMonitorCoordinator(DataUpdateCoordinator[dict]):
    """Polls an OBS instance over obs-websocket and exposes derived stats."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        host: str,
        port: int,
        password: str,
        enable_scene_tree: bool = False,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{entry.title} coordinator",
            update_interval=SCAN_INTERVAL,
        )
        self._host = host
        self._port = port
        self._password = password
        self._enable_scene_tree = enable_scene_tree
        self._client: obsws.ReqClient | None = None

        # State kept between polls to derive a bitrate from cumulative byte counts
        self._last_bytes: int | None = None
        self._last_time: float | None = None

    def _ensure_client(self) -> obsws.ReqClient:
        if self._client is None:
            self._client = obsws.ReqClient(
                host=self._host,
                port=self._port,
                password=self._password,
                timeout=CONNECT_TIMEOUT,
            )
        return self._client

    def _reset_client(self) -> None:
        if self._client is not None:
            try:
                self._client.disconnect()
            except Exception:  # noqa: BLE001 - best effort cleanup
                pass
        self._client = None

    def _fetch_scene_tree(self, client: obsws.ReqClient) -> dict[str, list[dict]]:
        """Build {scene_name: [{source_name, scene_item_id, enabled, source_kind, filters}]}.

        obsws-python only snake_cases the top-level response keys, not the
        items inside nested lists - so entries in scene_list.scenes,
        scene_item_list.scene_items and filter_list.filters keep OBS's
        original camelCase keys (sceneName, sourceName, sceneItemEnabled,
        filterEnabled, ...). Groups (nested scenes) are not recursed into.

        A single scene or source can become unresolvable to obs-websocket
        between one poll and the next (seen in practice with OBS's
        Multi-Canvas feature: GetSceneItemList/GetSourceFilterList can raise
        OBSSDKRequestError code 600 "No source was found... within the
        canvas 'X'" for a source that still exists but now lives on a
        different canvas). That used to take down the whole scene tree (and
        therefore the whole poll, since _fetch_data has no try/except around
        just this call) every single cycle - which in turn meant
        coordinator.last_update_success was never True, so switch.py's
        auto-cleanup of removed sources/filters could never run either. Each
        scene/source is now fetched defensively: a request error for one
        scene or source is logged and that one entry's items/filters are
        left empty for this poll instead of aborting the entire tree.

        An empty filter list here is ambiguous on its own - it either means
        the source genuinely has no filters, or that OBS couldn't be asked
        this cycle. switch.py's cleanup treats "absent from the tree" as
        "deregister it", so items are tagged with filters_unknown=True
        whenever the fetch failed, telling switch.py to leave that source's
        existing filter switches alone rather than deregistering them based
        on an empty-because-it-errored list.
        """
        tree: dict[str, list[dict]] = {}
        scenes = client.get_scene_list()
        for scene in getattr(scenes, "scenes", None) or []:
            scene_name = scene.get("sceneName")
            if not scene_name:
                continue
            items: list[dict] = []
            try:
                scene_items = client.get_scene_item_list(scene_name)
            except obsws.error.OBSSDKRequestError as err:
                _LOGGER.warning(
                    "OBS Stream Monitor: skipping scene %r for this poll, "
                    "could not list its items (%s)",
                    scene_name,
                    err,
                )
                tree[scene_name] = items
                continue
            for item in getattr(scene_items, "scene_items", None) or []:
                source_name = item.get("sourceName")
                if not source_name:
                    continue
                filters: list[dict] = []
                filters_unknown = False
                try:
                    filter_list = client.get_source_filter_list(source_name)
                except obsws.error.OBSSDKRequestError as err:
                    filters_unknown = True
                    _LOGGER.warning(
                        "OBS Stream Monitor: could not list filters for "
                        "source %r in scene %r this poll, leaving its "
                        "filter switches as they were (%s)",
                        source_name,
                        scene_name,
                        err,
                    )
                else:
                    for flt in getattr(filter_list, "filters", None) or []:
                        filters.append(
                            {
                                "name": flt.get("filterName"),
                                "enabled": bool(flt.get("filterEnabled")),
                                "kind": flt.get("filterKind"),
                            }
                        )
                items.append(
                    {
                        "source_name": source_name,
                        "scene_item_id": item.get("sceneItemId"),
                        "enabled": bool(item.get("sceneItemEnabled")),
                        "source_kind": item.get("inputKind") or item.get("sourceType"),
                        "filters": filters,
                        "filters_unknown": filters_unknown,
                    }
                )
            tree[scene_name] = items
        return tree

    def _fetch_data(self) -> dict:
        client = self._ensure_client()

        try:
            scene = client.get_current_program_scene()
            stream = client.get_stream_status()
            record = client.get_record_status()
            stats = client.get_stats()
            profiles = client.get_profile_list()
            scene_collections = client.get_scene_collection_list()
            scene_tree = self._fetch_scene_tree(client) if self._enable_scene_tree else None
        except Exception:
            # Connection likely dropped (OBS closed/restarted) - reconnect next poll
            self._reset_client()
            raise

        now = time.monotonic()
        bitrate_kbps = 0.0
        output_bytes = getattr(stream, "output_bytes", 0) or 0
        if stream.output_active and self._last_bytes is not None and self._last_time is not None:
            dt = now - self._last_time
            delta_bytes = output_bytes - self._last_bytes
            if dt > 0 and delta_bytes >= 0:
                bitrate_kbps = (delta_bytes * 8) / dt / 1000
        self._last_bytes = output_bytes
        self._last_time = now

        total_frames = getattr(stream, "output_total_frames", 0) or 0
        skipped_frames = getattr(stream, "output_skipped_frames", 0) or 0
        dropped_pct = (skipped_frames / total_frames * 100) if total_frames else 0.0

        available_disk_mb = getattr(stats, "available_disk_space", None)

        return {
            "scene": getattr(scene, "current_program_scene_name", None),
            "stream_active": bool(getattr(stream, "output_active", False)),
            "stream_duration": (getattr(stream, "output_duration", 0) or 0) / 1000,
            "stream_bitrate": round(bitrate_kbps, 1),
            "dropped_frames_pct": round(dropped_pct, 2),
            "record_active": bool(getattr(record, "output_active", False)),
            "record_paused": bool(getattr(record, "output_paused", False)),
            "record_duration": (getattr(record, "output_duration", 0) or 0) / 1000,
            "cpu_usage": round(getattr(stats, "cpu_usage", 0) or 0, 1),
            "free_disk_gb": round(available_disk_mb / 1024, 2) if available_disk_mb is not None else None,
            "active_fps": round(getattr(stats, "active_fps", 0) or 0, 2),
            "current_profile": getattr(profiles, "current_profile_name", None),
            "profile_list": list(getattr(profiles, "profiles", None) or []),
            "current_scene_collection": getattr(
                scene_collections, "current_scene_collection_name", None
            ),
            "scene_collection_list": list(
                getattr(scene_collections, "scene_collections", None) or []
            ),
            "scene_tree": scene_tree,
        }

    async def _async_update_data(self) -> dict:
        try:
            return await self.hass.async_add_executor_job(self._fetch_data)
        except Exception as err:
            raise UpdateFailed(f"Error communicating with OBS at {self._host}:{self._port}: {err}") from err

    async def async_shutdown(self) -> None:
        await self.hass.async_add_executor_job(self._reset_client)
        await super().async_shutdown()
