"""Config-Flow, Optionen und Subentries (Spielpartner / Cams)."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryData,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

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
    CONF_INIT_AUFNAHMEN,
    CONF_INIT_GESAMT,
    CONF_INIT_SAISON,
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
    DEFAULT_CAMERAS,
    DEFAULT_CAMS,
    DEFAULT_OPTIONS,
    DOMAIN,
    MODES,
    SUBENTRY_CAM,
    SUBENTRY_PARTNER,
)

_TEXT = selector.TextSelector()
_SECRET = selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))


def _ent(*domains: str) -> selector.EntitySelector:
    return selector.EntitySelector(selector.EntitySelectorConfig(domain=list(domains)))


def _num(lo: int, hi: int) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(min=lo, max=hi, step=1, mode=selector.NumberSelectorMode.BOX)
    )


def _suggest(schema: vol.Schema, values: dict[str, Any]) -> vol.Schema:
    """Vorbelegung als 'suggested_value' (Felder lassen sich so wieder leeren)."""
    return vol.Schema(
        {
            (type(k)(k.schema, default=k.default, description={"suggested_value": values.get(k.schema)}) if k.schema in values else k): v
            for k, v in schema.schema.items()
        }
    )


SETTINGS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_DISCORD_TOKEN): _SECRET,
        vol.Required(CONF_BASE_UNIX): _TEXT,
        vol.Required(CONF_BASE_WIN): _TEXT,
        vol.Required(CONF_FOLDER_PREFIX): _TEXT,
        vol.Optional(CONF_FORMAT_SUFFIX): _TEXT,
        vol.Optional(CONF_MODE): selector.SelectSelector(
            selector.SelectSelectorConfig(options=MODES, translation_key="modus", mode=selector.SelectSelectorMode.DROPDOWN)
        ),
        vol.Optional(CONF_RECORDING_ENTITY): _ent("binary_sensor", "switch"),
        vol.Optional(CONF_RECORDER_URL): _TEXT,
        vol.Optional(CONF_RECORDER_KEY): _SECRET,
        vol.Optional(CONF_RECORDER_FOLLOW): selector.BooleanSelector(),
        vol.Required(CONF_POST_DELAY): _num(1, 120),
        vol.Optional(CONF_POST_GAP): _num(0, 300),
        vol.Optional(CONF_SWING_ENTITY): _ent("cover"),
        vol.Optional(CONF_TOOL_BASE_BTN): _ent("button"),
        vol.Optional(CONF_TOOL_ENTER_BTN): _ent("button"),
        vol.Optional(CONF_TOOL_NAME_TEXT): _ent("text"),
        vol.Optional(CONF_TOOL_PATH_SENSOR): _ent("sensor"),
        vol.Optional(CONF_TOOL_FOLDER_SELECT): _ent("select"),
        vol.Optional(CONF_TOOL_STATUS_SENSOR): _ent("sensor"),
        vol.Optional(CONF_TOOL_TIMEOUT): _num(3, 120),
    }
)


def _clean(user_input: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in user_input.items() if v not in (None, "")}
    for key in (CONF_POST_DELAY, CONF_POST_GAP, CONF_TOOL_TIMEOUT):
        if key in out:
            out[key] = int(out[key])
    return out


def _recorder_fields(user_input: dict[str, Any]) -> dict[str, Any]:
    return {
        CONF_CAM_RECORD: bool(user_input.get(CONF_CAM_RECORD, True)),
        CONF_CAM_STREAM: user_input.get(CONF_CAM_STREAM, "") or "",
        CONF_CAM_RTSP: (user_input.get(CONF_CAM_RTSP, "") or "").strip(),
    }


def _default_subentries() -> list[ConfigSubentryData]:
    return [
        ConfigSubentryData(
            subentry_type=SUBENTRY_CAM,
            title=name,
            unique_id=logic.norm(name),
            data={
                CONF_CAM_NAME: name,
                CONF_CAM_KUERZEL: kuerzel,
                CONF_CAM_CAMERA: DEFAULT_CAMERAS.get(name, ""),
                CONF_CAM_POST: name in DEFAULT_CAMERAS,
                CONF_CAM_RECORD: True,
                CONF_CAM_STREAM: "",
                CONF_CAM_RTSP: "",
            },
        )
        for name, kuerzel in DEFAULT_CAMS.items()
    ]


class SpielpartnerConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(
                title="Spielpartner Aufnahme",
                data={},
                options=_clean(user_input),
                subentries=_default_subentries(),
            )
        return self.async_show_form(step_id="user", data_schema=_suggest(SETTINGS_SCHEMA, DEFAULT_OPTIONS))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SpielpartnerOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_PARTNER: PartnerSubentryFlow, SUBENTRY_CAM: CamSubentryFlow}


class SpielpartnerOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=_clean(user_input))
        current = {**DEFAULT_OPTIONS, **self.config_entry.options}
        return self.async_show_form(step_id="init", data_schema=_suggest(SETTINGS_SCHEMA, current))


# --------------------------------------------------------------- Spielpartner
class PartnerSubentryFlow(ConfigSubentryFlow):
    """Spielpartner anlegen / bearbeiten."""

    def _existing(self) -> dict[str, str]:
        return {
            s.data[CONF_KENNUNG]: sid
            for sid, s in self._get_entry().subentries.items()
            if s.subentry_type == SUBENTRY_PARTNER
        }

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            kennung = user_input[CONF_KENNUNG].strip().lower()
            if not logic.valid_kennung(kennung):
                errors[CONF_KENNUNG] = "invalid_kennung"
            elif kennung in self._existing():
                errors[CONF_KENNUNG] = "already_configured"
            else:
                anzeige = (user_input.get(CONF_ANZEIGE) or logic.default_anzeige(kennung)).strip()
                initial = {
                    "saison": user_input.get(CONF_INIT_SAISON),
                    "aufnahmen": user_input.get(CONF_INIT_AUFNAHMEN),
                    "gesamt": user_input.get(CONF_INIT_GESAMT),
                }
                data = {
                    CONF_KENNUNG: kennung,
                    CONF_ANZEIGE: anzeige,
                    CONF_ORDNER_NR: int(user_input.get(CONF_ORDNER_NR) or 1),
                    CONF_FORUM_ID: str(user_input.get(CONF_FORUM_ID) or "").strip(),
                    CONF_INITIAL: {k: v for k, v in initial.items() if v not in (None, "")},
                }
                return self.async_create_entry(title=anzeige, data=data, unique_id=kennung)
        schema = vol.Schema(
            {
                vol.Required(CONF_KENNUNG): _TEXT,
                vol.Optional(CONF_ANZEIGE): _TEXT,
                vol.Optional(CONF_ORDNER_NR): _num(1, 99),
                vol.Optional(CONF_FORUM_ID): _TEXT,
                vol.Optional(CONF_INIT_SAISON): _num(1, 999),
                vol.Optional(CONF_INIT_AUFNAHMEN): _num(1, 9999),
                vol.Optional(CONF_INIT_GESAMT): _num(1, 9999),
            }
        )
        return self.async_show_form(step_id="user", data_schema=_suggest(schema, user_input or {}), errors=errors)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        sub = self._get_reconfigure_subentry()
        if user_input is not None:
            data = {
                **sub.data,
                CONF_ANZEIGE: (user_input.get(CONF_ANZEIGE) or sub.data[CONF_ANZEIGE]).strip(),
                CONF_ORDNER_NR: int(user_input[CONF_ORDNER_NR]),
                CONF_FORUM_ID: str(user_input.get(CONF_FORUM_ID) or "").strip(),
            }
            return self.async_update_and_abort(
                self._get_entry(), sub, title=data[CONF_ANZEIGE], data=data
            )
        schema = vol.Schema(
            {
                vol.Required(CONF_ANZEIGE): _TEXT,
                vol.Required(CONF_ORDNER_NR): _num(1, 99),
                vol.Optional(CONF_FORUM_ID): _TEXT,
            }
        )
        return self.async_show_form(step_id="reconfigure", data_schema=_suggest(schema, dict(sub.data)))


# ----------------------------------------------------------------------- Cams
class CamSubentryFlow(ConfigSubentryFlow):
    """Cam mit Kuerzel anlegen / bearbeiten."""

    @staticmethod
    def _schema(with_name: bool, post_default: bool = False) -> vol.Schema:
        fields: dict[Any, Any] = {}
        if with_name:
            fields[vol.Required(CONF_CAM_NAME)] = _TEXT
        fields[vol.Required(CONF_CAM_KUERZEL)] = _TEXT
        fields[vol.Optional(CONF_CAM_POST, default=post_default)] = selector.BooleanSelector()
        fields[vol.Optional(CONF_CAM_CAMERA)] = _ent("camera")
        fields[vol.Optional(CONF_CAM_RECORD, default=True)] = selector.BooleanSelector()
        fields[vol.Optional(CONF_CAM_STREAM)] = _ent("camera")
        fields[vol.Optional(CONF_CAM_RTSP)] = _SECRET
        return vol.Schema(fields)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_CAM_NAME].strip()
            taken = {
                logic.norm(s.data[CONF_CAM_NAME])
                for s in self._get_entry().subentries.values()
                if s.subentry_type == SUBENTRY_CAM
            }
            if logic.norm(name) in taken:
                errors[CONF_CAM_NAME] = "already_configured"
            elif not user_input[CONF_CAM_KUERZEL].strip():
                errors[CONF_CAM_KUERZEL] = "kuerzel_required"
            else:
                data = {
                    CONF_CAM_NAME: name,
                    CONF_CAM_KUERZEL: user_input[CONF_CAM_KUERZEL].strip(),
                    CONF_CAM_CAMERA: user_input.get(CONF_CAM_CAMERA, "") or "",
                    CONF_CAM_POST: bool(user_input.get(CONF_CAM_POST, False)),
                    **_recorder_fields(user_input),
                }
                return self.async_create_entry(title=name, data=data, unique_id=logic.norm(name))
        return self.async_show_form(
            step_id="user", data_schema=_suggest(self._schema(True), user_input or {}), errors=errors
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        sub = self._get_reconfigure_subentry()
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input[CONF_CAM_KUERZEL].strip():
                errors[CONF_CAM_KUERZEL] = "kuerzel_required"
            else:
                data = {k: v for k, v in sub.data.items() if k != "filter_entity"}
                data.update(
                    {
                        CONF_CAM_KUERZEL: user_input[CONF_CAM_KUERZEL].strip(),
                        CONF_CAM_CAMERA: user_input.get(CONF_CAM_CAMERA, "") or "",
                        CONF_CAM_POST: bool(user_input.get(CONF_CAM_POST, False)),
                        **_recorder_fields(user_input),
                    }
                )
                return self.async_update_and_abort(self._get_entry(), sub, data=data)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_suggest(
                self._schema(False, bool(sub.data.get(CONF_CAM_POST, bool(sub.data.get(CONF_CAM_CAMERA))))),
                user_input or dict(sub.data),
            ),
            errors=errors,
        )
