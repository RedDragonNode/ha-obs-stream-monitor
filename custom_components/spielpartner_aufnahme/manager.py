"""Kern der Integration: Zustand, Aufnahme-Vorbereitung, Zaehler, OBS und Discord."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import logic
from .const import (
    CONF_ANZEIGE,
    CONF_BASE_UNIX,
    CONF_BASE_WIN,
    CONF_CAM_CAMERA,
    CONF_CAM_KUERZEL,
    CONF_CAM_NAME,
    CONF_CAM_POST,
    CONF_CAM_RECORD,
    CONF_CAM_RTSP,
    CONF_CAM_STREAM,
    CONF_DISCORD_TOKEN,
    CONF_FOLDER_PREFIX,
    CONF_FORMAT_SUFFIX,
    CONF_FORUM_ID,
    CONF_INITIAL,
    CONF_KENNUNG,
    CONF_MODE,
    CONF_ORDNER_NR,
    CONF_POST_DELAY,
    CONF_POST_GAP,
    CONF_RECORDER_FOLLOW,
    CONF_RECORDER_KEY,
    CONF_RECORDER_URL,
    CONF_RECORDING_ENTITY,
    CONF_SWING_ENTITY,
    CONF_TOOL_BASE_BTN,
    CONF_TOOL_ENTER_BTN,
    CONF_TOOL_FOLDER_SELECT,
    CONF_TOOL_NAME_TEXT,
    CONF_TOOL_PATH_SENSOR,
    CONF_TOOL_STATUS_SENSOR,
    CONF_TOOL_TIMEOUT,
    COUNTER_START,
    DEFAULT_OPTIONS,
    DOMAIN,
    MODE_OBS,
    MODE_RECORDER,
    SUBENTRY_CAM,
    SUBENTRY_PARTNER,
)
from .discord_client import DiscordClient, DiscordError
from .recorder_client import RecorderClient, RecorderError

_LOGGER = logging.getLogger(__name__)
STORAGE_VERSION = 1


async def async_get_stream_source(hass: HomeAssistant, entity_id: str) -> str | None:
    """RTSP-Adresse einer HA-Kamera holen (Camera-Komponente erst bei Bedarf laden)."""
    from homeassistant.components.camera import async_get_stream_source as _get

    return await _get(hass, entity_id)


async def async_get_image(hass: HomeAssistant, entity_id: str) -> Any:
    """Schnappschuss holen (Camera-Komponente erst bei Bedarf laden)."""
    from homeassistant.components.camera import async_get_image as _get

    return await _get(hass, entity_id)


@dataclass
class PartnerCfg:
    subentry_id: str
    kennung: str
    anzeige: str
    ordner_nr: int
    forum_id: str
    initial: dict[str, Any] = field(default_factory=dict)


@dataclass
class CamCfg:
    subentry_id: str
    name: str
    kuerzel: str
    camera_entity: str
    post: bool
    record: bool = True
    stream_entity: str = ""
    rtsp_url: str = ""


class SpielpartnerManager:
    """Haelt alle Daten eines Config-Entries."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.signal = f"{DOMAIN}_update_{entry.entry_id}"
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self.data: dict[str, Any] = {"active": None, "partners": {}, "status": {}}
        self._lock = asyncio.Lock()
        self._unsubs: list[CALLBACK_TYPE] = []
        self._post_cancel: CALLBACK_TYPE | None = None
        self._post_task: asyncio.Task[None] | None = None
        self._rec_lock = asyncio.Lock()
        self._rec_active = False  # Aufnahme-Ablauf (Statusbeitrag, Zaehlen) laeuft
        self._rec_running = False  # Recorder-Add-on nimmt auf (von uns gestartet)
        self._reattach = False
        self.rec_status: dict[str, Any] = {}
        self.rec_online: bool | None = None
        self.partners: dict[str, PartnerCfg] = {}
        self.cams: list[CamCfg] = []
        self._read_subentries()

    # ------------------------------------------------------------------ Setup
    def _read_subentries(self) -> None:
        for sid, sub in self.entry.subentries.items():
            d = sub.data
            if sub.subentry_type == SUBENTRY_PARTNER:
                p = PartnerCfg(
                    subentry_id=sid,
                    kennung=d[CONF_KENNUNG],
                    anzeige=d.get(CONF_ANZEIGE) or logic.default_anzeige(d[CONF_KENNUNG]),
                    ordner_nr=int(d.get(CONF_ORDNER_NR, 1)),
                    forum_id=str(d.get(CONF_FORUM_ID, "") or ""),
                    initial=dict(d.get(CONF_INITIAL, {})),
                )
                self.partners[p.kennung] = p
            elif sub.subentry_type == SUBENTRY_CAM:
                camera = d.get(CONF_CAM_CAMERA, "") or ""
                self.cams.append(
                    CamCfg(
                        subentry_id=sid,
                        name=d[CONF_CAM_NAME],
                        kuerzel=d[CONF_CAM_KUERZEL],
                        camera_entity=camera,
                        post=bool(d.get(CONF_CAM_POST, bool(camera))),
                        record=bool(d.get(CONF_CAM_RECORD, True)),
                        stream_entity=d.get(CONF_CAM_STREAM, "") or "",
                        rtsp_url=d.get(CONF_CAM_RTSP, "") or "",
                    )
                )
        self.cams.sort(key=lambda c: logic.norm(c.name))

    async def async_load(self) -> None:
        stored = await self._store.async_load()
        if stored:
            self.data.update(stored)
        self.data.setdefault("partners", {})
        for kennung, p in self.partners.items():
            if kennung not in self.data["partners"]:
                ini = p.initial
                self.data["partners"][kennung] = {
                    "saison": int(ini.get("saison") or COUNTER_START),
                    "aufnahmen": int(ini.get("aufnahmen") or COUNTER_START),
                    "gesamt": int(ini.get("gesamt") or COUNTER_START),
                    "thread_id": str(ini.get("thread_id") or ""),
                    "thread_saison": str(ini.get("thread_saison") or ""),
                    "pfad": "",
                    "vorbereitet": None,
                }
        if self.data.get("active") not in self.partners:
            self.data["active"] = None
        self._rec_running = self._reattach = bool((self.data.get("recorder") or {}).get("laeuft"))
        self._save_later()

    @callback
    def async_start(self) -> None:
        rec = self.opt(CONF_RECORDING_ENTITY)
        if rec:
            self._unsubs.append(async_track_state_change_event(self.hass, [rec], self._recording_changed))
        if self.uses_recorder and self.opt(CONF_RECORDER_URL):
            self._unsubs.append(async_track_time_interval(self.hass, self._poll_recorder, timedelta(seconds=15)))
            self.hass.async_create_background_task(self._poll_recorder(None), name=f"{DOMAIN}_poll")

    async def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._post_cancel:
            self._post_cancel()
            self._post_cancel = None
        if self._post_task and not self._post_task.done():
            self._post_task.cancel()
        await self._store.async_save(self.data)

    # ---------------------------------------------------------------- Helfer
    def opt(self, key: str) -> Any:
        val = self.entry.options.get(key)
        return DEFAULT_OPTIONS.get(key) if val is None and key in DEFAULT_OPTIONS else val

    @property
    def mode(self) -> str:
        return self.opt(CONF_MODE) or MODE_OBS

    @property
    def recorder_running(self) -> bool:
        return self._rec_running

    @property
    def uses_obs(self) -> bool:
        return self.mode != MODE_RECORDER

    @property
    def uses_recorder(self) -> bool:
        return self.mode != MODE_OBS

    def partner(self, kennung: str) -> PartnerCfg:
        if kennung in self.partners:
            return self.partners[kennung]
        norm = logic.norm(kennung)
        for p in self.partners.values():
            if norm in (logic.norm(p.kennung), logic.norm(p.anzeige)):
                return p
        raise ServiceValidationError(f"Spielpartner '{kennung}' ist nicht eingerichtet")

    def state_of(self, kennung: str) -> dict[str, Any]:
        return self.data["partners"][kennung]

    @property
    def active(self) -> PartnerCfg | None:
        return self.partners.get(self.data.get("active") or "")

    @callback
    def _save_later(self) -> None:
        self._store.async_delay_save(lambda: self.data, 2)

    @callback
    def notify(self) -> None:
        async_dispatcher_send(self.hass, self.signal)

    def _set_status(self, text: str) -> None:
        self.data["status"] = {"text": text, "zeit": dt_util.now().isoformat()}

    def _discord(self) -> DiscordClient | None:
        token = self.opt(CONF_DISCORD_TOKEN)
        if not token:
            return None
        return DiscordClient(async_get_clientsession(self.hass), token)

    def _recorder(self) -> RecorderClient:
        url, key = self.opt(CONF_RECORDER_URL), self.opt(CONF_RECORDER_KEY)
        if not self.uses_recorder:
            raise ServiceValidationError("Der Recorder ist aus - unter Einstellungen den Modus 'recorder' oder 'beide' waehlen")
        if not url or not key:
            raise ServiceValidationError("Recorder: Adresse und Schluessel fehlen in den Einstellungen")
        return RecorderClient(async_get_clientsession(self.hass), url, key)

    # --------------------------------------------------------------- Formate
    def video_id(self, kennung: str, cam: CamCfg | None, when: datetime | None = None) -> str:
        """Dateiname ohne Endung, mit echtem Datum (OBS-Platzhalter aufgeloest)."""
        return logic.render_tokens(self.format_for(kennung, cam), when or dt_util.now())

    def format_for(self, kennung: str, cam: CamCfg | None) -> str:
        p, s = self.partners[kennung], self.state_of(kennung)
        return logic.file_format(
            p.ordner_nr,
            s["saison"],
            s["aufnahmen"],
            cam.kuerzel if cam else "Cam ID",
            s["gesamt"],
            self.opt(CONF_FORMAT_SUFFIX) or "",
        )

    def _source_filters(self) -> list[tuple[str, str]]:
        res = []
        for st in self.hass.states.async_all("switch"):
            if st.attributes.get("filter_kind") != "source_record_filter":
                continue
            if st.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                continue
            res.append((st.entity_id, str(st.attributes.get("source", ""))))
        return res

    def cam_filters(self, cam: CamCfg) -> list[str]:
        """Source-Record-Filter der Cam (automatisch ueber den Cam-Namen)."""
        return logic.match_filters(cam.name, self._source_filters())

    # ------------------------------------------------------------------- OBS
    async def _obs_set(self, entity_id: str, settings: dict[str, Any]) -> None:
        await self.hass.services.async_call(
            "obs_stream_monitor",
            "set_settings",
            {"entity_id": entity_id, "settings": settings},
            blocking=True,
        )

    async def _apply_path(self, path: str) -> tuple[int, list[str]]:
        ok, errors = 0, []
        if not self.uses_obs:
            return ok, errors
        for entity_id, _ in self._source_filters():
            try:
                await self._obs_set(entity_id, {"path": path})
                ok += 1
            except HomeAssistantError as err:
                errors.append(f"{entity_id}: {err}")
        return ok, errors

    async def _apply_formats(self, kennung: str) -> tuple[int, list[str], list[str]]:
        ok, errors, without = 0, [], []
        if not self.uses_obs:
            return ok, errors, without
        for cam in self.cams:
            for entity_id in self.cam_filters(cam):
                try:
                    await self._obs_set(entity_id, {"filename_formatting": self.format_for(kennung, cam)})
                    ok += 1
                except HomeAssistantError as err:
                    errors.append(f"{entity_id}: {err}")
        mapped = {e for cam in self.cams for e in self.cam_filters(cam)}
        without = [e for e, _ in self._source_filters() if e not in mapped]
        return ok, errors, without

    async def async_apply_formats(self, kennung: str | None = None) -> dict[str, Any]:
        p = self.partner(kennung) if kennung else self.active
        if p is None:
            raise ServiceValidationError("Kein aktiver Spielpartner - zuerst 'Aufnahme vorbereiten' ausfuehren")
        if not self.uses_obs:
            return {"gesetzt": 0, "fehler": [], "ohne_kuerzel": [], "hinweis": "Modus 'recorder': OBS wird nicht verwendet"}
        ok, errors, without = await self._apply_formats(p.kennung)
        return {"gesetzt": ok, "fehler": errors, "ohne_kuerzel": without}

    # --------------------------------------------------------- Ordner-Werkzeug
    def _tool_ids(self) -> dict[str, str]:
        return {
            "base": self.opt(CONF_TOOL_BASE_BTN) or "",
            "enter": self.opt(CONF_TOOL_ENTER_BTN) or "",
            "name": self.opt(CONF_TOOL_NAME_TEXT) or "",
            "path": self.opt(CONF_TOOL_PATH_SENSOR) or "",
            "select": self.opt(CONF_TOOL_FOLDER_SELECT) or "",
            "status": self.opt(CONF_TOOL_STATUS_SENSOR) or "",
        }

    def _tool_available(self) -> bool:
        ids = self._tool_ids()
        for key in ("base", "enter", "name", "path", "select"):
            st = self.hass.states.get(ids[key])
            if st is None or st.state == STATE_UNAVAILABLE:
                return False
        return True

    async def _wait_state(self, entity_id: str, target: str) -> bool:
        """Wartet (bis Timeout), dass die Entity den Zielwert hat."""
        current = self.hass.states.get(entity_id)
        if current is not None and current.state == target:
            return True
        fut: asyncio.Future[bool] = self.hass.loop.create_future()

        @callback
        def _changed(event: Event[EventStateChangedData]) -> None:
            new = event.data["new_state"]
            if new is not None and new.state == target and not fut.done():
                fut.set_result(True)

        unsub = async_track_state_change_event(self.hass, [entity_id], _changed)
        try:
            await asyncio.wait_for(fut, timeout=float(self.opt(CONF_TOOL_TIMEOUT) or 15))
            return True
        except asyncio.TimeoutError:
            return False
        finally:
            unsub()

    async def _tool_enter(self, ids: dict[str, str], folder: str, expect_path: str) -> bool:
        await self.hass.services.async_call("text", "set_value", {"entity_id": ids["name"], "value": folder}, blocking=True)
        await self.hass.services.async_call("button", "press", {"entity_id": ids["enter"]}, blocking=True)
        return await self._wait_state(ids["path"], expect_path)

    # ------------------------------------------------------------- Vorbereiten
    async def async_prepare(self, kennung: str) -> dict[str, Any]:
        """Entspricht dem frueheren Skript 'Aufnahme Vorbereitung'."""
        async with self._lock:
            return await self._prepare(self.partner(kennung))

    async def _prepare(self, p: PartnerCfg) -> dict[str, Any]:
        s = self.state_of(p.kennung)
        hints: list[str] = []
        self.data["active"] = p.kennung
        base_win, base_unix = self.opt(CONF_BASE_WIN), self.opt(CONF_BASE_UNIX)
        ordner = logic.partner_folder(self.opt(CONF_FOLDER_PREFIX), p.anzeige, p.ordner_nr)
        datum = dt_util.now().strftime("%d,%m,%Y")

        # 1) Ordner: PC-Ordner-Werkzeug (OBS) und/oder Recorder; Saisonwechsel pruefen
        tool_status = "nicht genutzt"
        existing: list[str] | None = None
        tool_ok = False
        ids = self._tool_ids()
        if self.uses_obs:
            tool_status = "nicht verfuegbar (Ordner wurde NICHT angelegt)"
            if self._tool_available():
                tool_ok = True
                await self.hass.services.async_call("button", "press", {"entity_id": ids["base"]}, blocking=True)
                await self._wait_state(ids["path"], base_win)
                if not await self._tool_enter(ids, ordner, logic.join_win(base_win, ordner)):
                    hints.append("Spielpartner-Ordner: Zeitueberschreitung beim Wechseln")
                sel = self.hass.states.get(ids["select"])
                existing = list(sel.attributes.get("options") or []) if sel else []
            else:
                hints.append(
                    "Ordner-Werkzeug nicht erreichbar - Ordner nicht angelegt, Saisonwechsel nicht geprueft"
                )
        client = None
        if self.uses_recorder:
            try:
                client = self._recorder()
                self.rec_status = await client.status()
                self.rec_online = True
                await client.make_dirs([ordner])
                if existing is None:
                    existing = await client.list_dirs([ordner])
            except (RecorderError, ServiceValidationError) as err:
                self.rec_online = False if isinstance(err, RecorderError) else self.rec_online
                client = None
                hints.append(f"Recorder: Ordner nicht angelegt, Saisonwechsel nicht geprueft ({err})")
        neuer_tag = logic.is_new_day(existing, logic.season_folder(s["saison"], datum))
        if neuer_tag:
            s["saison"] += 1
            s["aufnahmen"] = COUNTER_START
        saison_ordner = logic.season_folder(s["saison"], datum)
        if tool_ok:
            if not await self._tool_enter(ids, saison_ordner, logic.join_win(base_win, ordner, saison_ordner)):
                hints.append("Saison-Ordner: Zeitueberschreitung beim Wechseln")
            st = self.hass.states.get(ids["status"]) if ids["status"] else None
            tool_status = st.state if st else "ok"
        rec_pfad = ""
        if client is not None:
            try:
                await client.make_dirs([ordner, saison_ordner])
                s["rec_rel"] = [ordner, saison_ordner]
                rec_pfad = "/".join([str(self.rec_status.get("wurzel") or "recorder").rstrip("/"), ordner, saison_ordner])
            except RecorderError as err:
                s["rec_rel"] = []
                hints.append(f"Recorder: Saison-Ordner nicht angelegt ({err})")
        s["rec_pfad"] = rec_pfad

        pfad = logic.join_unix(base_unix, ordner, saison_ordner) if self.uses_obs else rec_pfad
        s["pfad"] = pfad

        # 2) OBS
        n_pfad, err_pfad, n_fmt, err_fmt, ohne = 0, [], 0, [], []
        if self.uses_obs:
            n_pfad, err_pfad = await self._apply_path(pfad)
            n_fmt, err_fmt, ohne = await self._apply_formats(p.kennung)
            if n_pfad == 0:
                hints.append("Kein OBS-Filter erreichbar - laeuft OBS? Pfad/Dateiformat wurden NICHT gesetzt")
            hints += err_pfad + err_fmt
            if ohne:
                hints.append("Filter ohne Cam-Kuerzel (Pfad gesetzt, Dateiformat nicht): " + ", ".join(ohne))

        # 3) Discord
        discord_status = await self._ensure_thread(p, s, hints)

        s["vorbereitet"] = dt_util.now().isoformat()
        result = {
            "spielpartner": p.kennung,
            "anzeige": p.anzeige,
            "ordner": pfad,
            "neue_saison": neuer_tag,
            "saison": s["saison"],
            "aufnahme_in_saison": s["aufnahmen"],
            "gesamt": s["gesamt"],
            "dateiformat": self.format_for(p.kennung, None),
            "obs_pfad_gesetzt": n_pfad,
            "obs_format_gesetzt": n_fmt,
            "modus": self.mode,
            "recorder_ordner": rec_pfad,
            "discord": discord_status,
            "hinweise": hints,
        }
        self._set_status(f"{p.anzeige}: vorbereitet ({'neue Saison' if neuer_tag else 'gleiche Saison'})")
        self._save_later()
        self.notify()
        self._notification(p, result, tool_status, ohne)
        return result

    def _notification(self, p: PartnerCfg, r: dict[str, Any], tool_status: str, ohne: list[str]) -> None:
        lines = [
            f"Ordner: {r['ordner']}",
            f"Ordner-Werkzeug-Status: {tool_status}",
            f"Dateiformat: {r['dateiformat']}",
            *(
                [f"OBS: Pfad bei {r['obs_pfad_gesetzt']} Filtern, Dateiformat bei {r['obs_format_gesetzt']} Filtern gesetzt."]
                if self.uses_obs
                else []
            ),
            *([f"Recorder-Ordner: {r['recorder_ordner'] or 'NICHT angelegt'}"] if self.uses_recorder else []),
            (
                f"Saison {logic.pad(r['saison'])}, Aufnahme {logic.pad(r['aufnahme_in_saison'])} dieser Saison, "
                f"{logic.pad(r['gesamt'])} insgesamt."
            ),
            f"Neue Saison erkannt: {'ja' if r['neue_saison'] else 'nein'}",
            f"Discord: {r['discord']}",
        ]
        if r["hinweise"]:
            lines.append("ACHTUNG:\n- " + "\n- ".join(r["hinweise"]))
        persistent_notification.async_create(
            self.hass,
            "\n\n".join(lines),
            title=f"Aufnahme vorbereitet: {p.anzeige}",
            notification_id=f"{DOMAIN}_prepare_{p.kennung}",
        )

    # ----------------------------------------------------------------- Discord
    async def _ensure_thread(self, p: PartnerCfg, s: dict[str, Any], hints: list[str]) -> str:
        client = self._discord()
        if client is None:
            return "nicht eingerichtet (kein Bot-Token)"
        if not p.forum_id:
            return "kein Forum-Kanal fuer diesen Spielpartner hinterlegt"
        if s["thread_id"] and s["thread_saison"] == logic.pad(s["saison"]):
            return f"Thread vorhanden ({s['thread_id']})"
        saison = logic.pad(s["saison"])
        try:
            thread = await client.create_forum_thread(
                p.forum_id,
                f"Saison {saison}",
                title=f"Saison {saison}",
                description=f"Aufnahmen mit {p.anzeige} - Saison {saison}",
                message=f"Neue Saison gestartet: Saison {saison} mit {p.anzeige}.",
            )
        except DiscordError as err:
            hints.append(f"Discord-Thread konnte nicht angelegt werden: {err}")
            return "FEHLER beim Anlegen des Threads"
        s["thread_id"], s["thread_saison"] = thread, saison
        return f"neuer Thread angelegt ({thread})"

    async def async_post_update(self, kennung: str | None = None) -> dict[str, Any]:
        """Statusbeitrag starten: Kopfzeile, danach jede angehakte Cam einzeln und zeitlich versetzt."""
        p = self.partner(kennung) if kennung else self.active
        if p is None:
            raise ServiceValidationError("Kein aktiver Spielpartner")
        s = self.state_of(p.kennung)
        if self._discord() is None or not s["thread_id"]:
            persistent_notification.async_create(
                self.hass,
                f"Fuer {p.anzeige} gibt es keinen aktuellen Saison-Thread. Bitte zuerst 'Aufnahme vorbereiten' ausfuehren.",
                title="Kein Discord-Thread gefunden",
                notification_id=f"{DOMAIN}_kein_thread_{p.kennung}",
            )
            return {"gepostet": False, "grund": "kein Thread"}
        cams = [c for c in self.cams if c.post]
        if not cams:
            return {"gepostet": False, "grund": "bei keiner Cam ist 'In Discord posten' angehakt"}
        # IDs jetzt festhalten: sie gehoeren zu dieser Aufnahme, auch wenn sich Zaehler spaeter aendern
        now = dt_util.now()
        items = [(c, self.video_id(p.kennung, c, now)) for c in cams]
        if self._post_task and not self._post_task.done():
            self._post_task.cancel()
        self._post_task = self.hass.async_create_background_task(
            self._post_sequence(p, s["thread_id"], items), name=f"{DOMAIN}_post"
        )
        gap = int(self.opt(CONF_POST_GAP) or 0)
        return {"gepostet": True, "cams": [c.name for c in cams], "abstand_sekunden": gap}

    async def _post_sequence(self, p: PartnerCfg, thread_id: str, items: list[tuple[CamCfg, str]]) -> None:
        client = self._discord()
        if client is None:
            return
        gap = max(0, int(self.opt(CONF_POST_GAP) or 0))
        swing = None
        swing_entity = self.opt(CONF_SWING_ENTITY)
        if swing_entity and (st := self.hass.states.get(swing_entity)):
            swing = st.attributes.get("current_position", st.state)
        sent = 0
        try:
            await client.post_message(thread_id, logic.build_post_header(int(self.opt(CONF_POST_DELAY) or 5), swing))
            for i, (cam, video_id) in enumerate(items):
                if i and gap:
                    await asyncio.sleep(gap)
                images = []
                if cam.camera_entity:
                    try:
                        img = await async_get_image(self.hass, cam.camera_entity)
                        ext = "png" if "png" in (img.content_type or "") else "jpg"
                        stamp = dt_util.now().strftime("%Y%m%d_%H%M%S")
                        images.append((f"{cam.name}_{stamp}.{ext}", img.content, img.content_type or "image/jpeg"))
                    except HomeAssistantError as err:
                        _LOGGER.warning("Schnappschuss von %s fehlgeschlagen: %s", cam.camera_entity, err)
                if images:
                    await client.post_message(thread_id, "", images)  # erst das Bild ...
                await client.post_message(thread_id, logic.build_cam_caption(cam.name, video_id))  # ... direkt darunter die ID
                sent += 1
        except DiscordError as err:
            _LOGGER.error("Discord-Beitrag fehlgeschlagen: %s", err)
            self._set_status(f"Discord-Beitrag fehlgeschlagen: {err}")
        else:
            self._set_status(f"{p.anzeige}: Statusbeitrag gepostet ({sent} Cams)")
        self.notify()

    # ------------------------------------------------------------------ Zaehler
    async def async_count_recording(self, kennung: str | None = None) -> None:
        p = self.partner(kennung) if kennung else self.active
        if p is None:
            raise ServiceValidationError("Kein aktiver Spielpartner")
        s = self.state_of(p.kennung)
        s["aufnahmen"] += 1
        s["gesamt"] += 1
        self._set_status(f"{p.anzeige}: Aufnahme gezaehlt")
        self._save_later()
        self.notify()
        try:
            await self._apply_formats(p.kennung)
        except HomeAssistantError as err:
            _LOGGER.warning("Dateiformat konnte nach dem Zaehlen nicht gesetzt werden: %s", err)

    async def async_set_counters(
        self, kennung: str, saison: int | None, aufnahmen: int | None, gesamt: int | None
    ) -> None:
        p = self.partner(kennung)
        s = self.state_of(p.kennung)
        for key, val in (("saison", saison), ("aufnahmen", aufnahmen), ("gesamt", gesamt)):
            if val is not None:
                s[key] = max(0, int(val))
        self._save_later()
        self.notify()
        if self.data.get("active") == p.kennung:
            try:
                await self._apply_formats(p.kennung)
            except HomeAssistantError as err:
                _LOGGER.warning("Dateiformat konnte nicht aktualisiert werden: %s", err)

    # --------------------------------------------------------- Aufnahme-Ereignis
    @callback
    def _rec_started(self) -> None:
        """Aufnahme hat begonnen (egal ob OBS oder Recorder) - nur einmal."""
        if self._rec_active:
            return
        self._rec_active = True
        if self._post_cancel:
            self._post_cancel()
        delay = int(self.opt(CONF_POST_DELAY) or 5) * 60
        self._post_cancel = async_call_later(self.hass, delay, self._post_due)
        self.notify()

    async def _rec_stopped(self) -> None:
        """Aufnahme ist zu Ende - zaehlt genau einmal."""
        if not self._rec_active:
            return
        self._rec_active = False
        if self._post_cancel:
            self._post_cancel()
            self._post_cancel = None
        if self.active is not None:
            await self.async_count_recording()
        self.notify()

    @callback
    def _recording_changed(self, event: Event[EventStateChangedData]) -> None:
        old, new = event.data["old_state"], event.data["new_state"]
        if old is None or new is None:
            return
        on = old.state == STATE_OFF and new.state == STATE_ON
        off = old.state == STATE_ON and new.state == STATE_OFF
        if not (on or off):
            return
        if self.mode == MODE_RECORDER and not self.opt(CONF_RECORDER_FOLLOW):
            return
        if self.uses_obs:
            if on:
                self._rec_started()
            else:
                self.hass.async_create_task(self._rec_stopped())
        if self.uses_recorder:
            self.hass.async_create_task(self._follow_obs(on))

    async def _follow_obs(self, on: bool) -> None:
        try:
            if on:
                await self.async_recorder_start()
            else:
                await self.async_recorder_stop()
        except HomeAssistantError as err:
            _LOGGER.error("Recorder konnte OBS nicht folgen: %s", err)
            self._set_status(f"Recorder: {err}")
            self.notify()

    # ------------------------------------------------------------------ Recorder
    async def _stream_url(self, cam: CamCfg) -> str | None:
        if cam.rtsp_url:
            return cam.rtsp_url
        if cam.stream_entity:
            try:
                return await async_get_stream_source(self.hass, cam.stream_entity)
            except HomeAssistantError as err:
                _LOGGER.warning("Stream-Quelle von %s nicht lesbar: %s", cam.stream_entity, err)
        return None

    async def async_recorder_start(self, kennung: str | None = None) -> dict[str, Any]:
        async with self._rec_lock:
            client = self._recorder()
            p = self.partner(kennung) if kennung else self.active
            if p is None:
                raise ServiceValidationError("Kein aktiver Spielpartner - zuerst 'Aufnahme vorbereiten' ausfuehren")
            if self._rec_running:
                return {"gestartet": False, "grund": "Aufnahme laeuft bereits"}
            s = self.state_of(p.kennung)
            rel = s.get("rec_rel")
            if not rel:
                raise ServiceValidationError(
                    f"Fuer {p.anzeige} gibt es keinen Recorder-Ordner - 'Aufnahme vorbereiten' ausfuehren (Recorder erreichbar?)"
                )
            now = dt_util.now()
            cams: list[dict[str, str]] = []
            skipped: list[str] = []
            for cam in self.cams:
                if not cam.record:
                    continue
                url = await self._stream_url(cam)
                if not url:
                    skipped.append(cam.name)
                    continue
                cams.append({"id": cam.subentry_id, "name": cam.name, "url": url, "stem": self.video_id(p.kennung, cam, now)})
            if not cams:
                raise ServiceValidationError(
                    "Keine Cam mit Stream-Quelle - bei den Cams 'Stream-Kamera' oder 'RTSP-Adresse' eintragen"
                )
            session = f"#{logic.pad(p.ordner_nr)}.{logic.pad(s['saison'])}.{logic.pad(s['aufnahmen'])} Sitzung"
            try:
                await client.start(rel, cams, session)
            except RecorderError as err:
                self.rec_online = False if "nicht erreichbar" in str(err) else self.rec_online
                self._set_status(f"Recorder konnte nicht starten: {err}")
                persistent_notification.async_create(
                    self.hass, str(err), title="Recorder: Start fehlgeschlagen", notification_id=f"{DOMAIN}_rec_start"
                )
                self.notify()
                raise
            self._rec_running = True
            self.data["recorder"] = {"laeuft": True, "start": now.isoformat(), "partner": p.kennung}
            self._save_later()
            self._set_status(f"{p.anzeige}: Recorder nimmt auf ({len(cams)} Cams)")
            self._rec_started()
            persistent_notification.async_dismiss(self.hass, f"{DOMAIN}_rec_start")
            self.notify()
            return {"gestartet": True, "cams": [c["name"] for c in cams], "ohne_stream": skipped, "ordner": "/".join(rel)}

    async def async_recorder_stop(self) -> dict[str, Any]:
        async with self._rec_lock:
            client = self._recorder()
            if not self._rec_running:
                return {"gestoppt": False, "grund": "Es laeuft keine Aufnahme des Recorders"}
            try:
                await client.stop()
            except RecorderError as err:
                self._set_status(f"Recorder konnte nicht stoppen: {err}")
                persistent_notification.async_create(
                    self.hass, str(err), title="Recorder: Stoppen fehlgeschlagen", notification_id=f"{DOMAIN}_rec_stop"
                )
                self.notify()
                raise
            self._rec_running = False
            self.data["recorder"] = {"laeuft": False}
            self._save_later()
            self._set_status("Recorder: Aufnahme beendet")
            await self._rec_stopped()
            await self._poll_recorder(None)
            return {"gestoppt": True}

    async def _poll_recorder(self, _now: datetime | None) -> None:
        """Zustand des Add-ons holen; verlorene Aufnahmen (Absturz, Platte voll) erkennen."""
        try:
            client = self._recorder()
            st = await client.status()
        except (RecorderError, ServiceValidationError):
            if self.rec_online is not False:
                self.rec_online = False
                self.notify()
            return
        self.rec_status, self.rec_online = st, True
        if self._rec_running and not self._rec_lock.locked():
            if st.get("aufnahme"):
                if self._reattach:  # HA wurde neu gestartet, Aufnahme laeuft weiter
                    self._rec_active = True
                self._reattach = False
            else:
                self._reattach = False
                self._rec_running = False
                self.data["recorder"] = {"laeuft": False}
                self._save_later()
                reason = st.get("stop_grund") or "unbekannt (Add-on neu gestartet?)"
                persistent_notification.async_create(
                    self.hass,
                    f"Der Recorder hat die Aufnahme beendet. Grund: {reason}. Bereits geschriebene Dateien bleiben erhalten.",
                    title="Recorder: Aufnahme unerwartet beendet",
                    notification_id=f"{DOMAIN}_rec_lost",
                )
                self._rec_active = True  # genau einmal zaehlen
                await self._rec_stopped()
                self._set_status(f"Recorder: Aufnahme ist beendet worden - Grund: {reason}")
        self.notify()

    async def _post_due(self, _now: datetime) -> None:
        self._post_cancel = None
        if self.active is not None:
            try:
                await self.async_post_update()
            except HomeAssistantError as err:
                _LOGGER.error("Statusbeitrag fehlgeschlagen: %s", err)
