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

    def _fetch_data(self) -> dict:
        client = self._ensure_client()

        try:
            scene = client.get_current_program_scene()
            stream = client.get_stream_status()
            record = client.get_record_status()
            stats = client.get_stats()
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
        }

    async def _async_update_data(self) -> dict:
        try:
            return await self.hass.async_add_executor_job(self._fetch_data)
        except Exception as err:
            raise UpdateFailed(f"Error communicating with OBS at {self._host}:{self._port}: {err}") from err

    async def async_shutdown(self) -> None:
        await self.hass.async_add_executor_job(self._reset_client)
        await super().async_shutdown()
