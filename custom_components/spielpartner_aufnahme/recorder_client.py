"""Client fuer das Add-on 'Spielpartner Recorder'."""
from __future__ import annotations

import asyncio
from typing import Any

import aiohttp
from homeassistant.exceptions import HomeAssistantError


class RecorderError(HomeAssistantError):
    """Recorder nicht erreichbar oder Anfrage abgelehnt."""


class RecorderClient:
    def __init__(self, session: aiohttp.ClientSession, url: str, key: str) -> None:
        self._session = session
        self._url = url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {key}"}

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            async with self._session.request(
                method, f"{self._url}{path}", headers=self._headers, timeout=aiohttp.ClientTimeout(total=30), **kwargs
            ) as resp:
                try:
                    data = await resp.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError):
                    data = {}
                if resp.status == 401:
                    raise RecorderError("Recorder: Schluessel (api_key) stimmt nicht mit dem Add-on ueberein")
                if resp.status >= 400:
                    raise RecorderError(f"Recorder: {(data or {}).get('fehler') or resp.status}")
                return data or {}
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise RecorderError(f"Recorder-Add-on nicht erreichbar ({self._url}): {err}") from err

    async def status(self) -> dict[str, Any]:
        return await self._request("GET", "/status")

    async def list_dirs(self, path: list[str]) -> list[str]:
        return (await self._request("GET", "/ls", params={"path": "/".join(path)})).get("ordner", [])

    async def make_dirs(self, path: list[str]) -> str:
        return (await self._request("POST", "/mkdir", json={"path": path})).get("pfad", "")

    async def start(self, path: list[str], cams: list[dict[str, str]], session: str) -> dict[str, Any]:
        return await self._request("POST", "/start", json={"path": path, "cams": cams, "session": session})

    async def stop(self) -> dict[str, Any]:
        return await self._request("POST", "/stop", json={})
