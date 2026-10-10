"""Minimaler Discord-REST-Client (Bot-Token) fuer Forum-Threads und Nachrichten."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp

from .const import DISCORD_API, DISCORD_COLOR_GREEN

_LOGGER = logging.getLogger(__name__)
_TIMEOUT = aiohttp.ClientTimeout(total=30)


class DiscordError(Exception):
    """Discord hat die Anfrage abgelehnt oder war nicht erreichbar."""


class DiscordClient:
    def __init__(self, session: aiohttp.ClientSession, token: str) -> None:
        self._session = session
        self._token = token.strip()

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bot {self._token}", "User-Agent": "DiscordBot (ha-spielpartner-aufnahme, 0.1)"}

    async def _request(self, method: str, path: str, *, json_body: Any = None, data: Any = None) -> dict[str, Any]:
        url = f"{DISCORD_API}{path}"
        for attempt in (1, 2):
            try:
                async with self._session.request(
                    method, url, headers=self._headers, json=json_body, data=data, timeout=_TIMEOUT
                ) as resp:
                    if resp.status == 429 and attempt == 1:
                        retry = 1.0
                        try:
                            retry = float((await resp.json()).get("retry_after", 1.0))
                        except Exception:  # noqa: BLE001
                            pass
                        await asyncio.sleep(min(retry, 10))
                        continue
                    text = await resp.text()
                    if resp.status >= 300:
                        raise DiscordError(f"Discord HTTP {resp.status}: {text[:300]}")
                    return json.loads(text) if text else {}
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                raise DiscordError(f"Discord nicht erreichbar: {err}") from err
        raise DiscordError("Discord: Rate-Limit")

    async def create_forum_thread(
        self, forum_id: str, name: str, *, title: str, description: str, message: str
    ) -> str:
        """Neuen Forum-Beitrag anlegen, liefert die Thread-ID."""
        body = {
            "name": name[:100],
            "message": {
                "content": message[:2000],
                "embeds": [{"title": title[:256], "description": description[:4000], "color": DISCORD_COLOR_GREEN}],
            },
        }
        result = await self._request("POST", f"/channels/{forum_id}/threads", json_body=body)
        thread_id = result.get("id")
        if not thread_id:
            raise DiscordError("Discord lieferte keine Thread-ID")
        return str(thread_id)

    async def post_message(
        self, channel_id: str, content: str, images: list[tuple[str, bytes, str]] | None = None
    ) -> None:
        """Nachricht (optional mit Bildern: Dateiname, Bytes, Content-Type) in Thread/Kanal."""
        payload = {"content": content[:2000]}
        if not images:
            await self._request("POST", f"/channels/{channel_id}/messages", json_body=payload)
            return
        form = aiohttp.FormData()
        form.add_field("payload_json", json.dumps(payload), content_type="application/json")
        for i, (filename, blob, ctype) in enumerate(images[:10]):
            form.add_field(f"files[{i}]", blob, filename=filename, content_type=ctype)
        await self._request("POST", f"/channels/{channel_id}/messages", data=form)
