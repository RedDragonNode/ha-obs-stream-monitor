"""Tests mit echter Home-Assistant-Testumgebung."""
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (  # noqa: F401
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.spielpartner_aufnahme.config_flow import _default_subentries
from custom_components.spielpartner_aufnahme.const import (
    DOMAIN,
    SUBENTRY_CAM,
    SUBENTRY_PARTNER,
)

BASE_WIN = "X:\\#2.0 Meine Videos OBS aufnahmen"
OPTIONS = {
    "discord_token": "tok",
    "basis_pfad_obs": "X:/#2.0 Meine Videos OBS aufnahmen",
    "basis_pfad_windows": BASE_WIN,
    "ordner_praefix": "Spielen mit",
    "dateiformat_endung": " (4K) %DD.%MM.%CCYY",
    "aufnahme_entity": "binary_sensor.rec",
    "post_nach_minuten": 5,
    "werkzeug_timeout": 3,
}


async def _entry(hass: HomeAssistant, options=None) -> MockConfigEntry:
    from homeassistant.config_entries import ConfigSubentryData

    subs = _default_subentries()
    subs.append(
        ConfigSubentryData(
            subentry_type=SUBENTRY_PARTNER,
            title="Frank",
            unique_id="frank_visselff",
            data={
                "kennung": "frank_visselff",
                "anzeige": "Frank",
                "ordner_nr": 1,
                "forum_id": "555",
                "initial": {"saison": 2, "aufnahmen": 3, "gesamt": 14, "thread_id": "99", "thread_saison": "01"},
            },
        )
    )
    entry = MockConfigEntry(domain=DOMAIN, data={}, options=options or OPTIONS, subentries_data=subs, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    return entry


def _obs(hass):
    calls = []

    async def set_settings(call: ServiceCall):
        calls.append((call.data["entity_id"], call.data["settings"]))

    hass.services.async_register("obs_stream_monitor", "set_settings", set_settings)
    for eid, src in (
        ("switch.obs_filter_fuchsblick", "Quelle Fuchsblick Hauptstream"),
        ("switch.obs_filter_hoelenblick", "Quelle Hoelenblick Hauptstream"),
        ("switch.obs_filter_kesselcam", "Quelle Kesselcam"),
        ("switch.obs_filter_unbekannt", "Fremde Quelle"),
    ):
        hass.states.async_set(eid, "on" if "fuchs" in eid else "off", {"filter_kind": "source_record_filter", "source": src})
    return calls


async def test_setup_and_entities(hass: HomeAssistant) -> None:
    entry = await _entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    reg = er.async_get(hass)
    ids = {e.unique_id for e in er.async_entries_for_config_entry(reg, entry.entry_id)}
    for key in ("saison", "aufnahmen_in_saison", "gesamt", "vorbereiten", "dateiformat", "speicher_adresse"):
        assert f"{entry.entry_id}_frank_visselff_{key}" in ids
    assert sum(1 for i in ids if i.endswith("_format")) == 16  # eine pro Cam
    states = {s.entity_id: s.state for s in hass.states.async_all() if s.entity_id.startswith(("number.", "sensor."))}
    assert any(v in ("2", "2.0") for v in states.values())  # Saison aus Startwerten
    m = entry.runtime_data
    assert m.format_for("frank_visselff", None) == "#01.02.03.Cam ID.14 (4K) %DD.%MM.%CCYY"


async def test_prepare_without_folder_tool(hass: HomeAssistant) -> None:
    entry = await _entry(hass)
    calls = _obs(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    m = entry.runtime_data
    with patch("custom_components.spielpartner_aufnahme.manager.DiscordClient") as dc:
        dc.return_value.create_forum_thread = AsyncMock(return_value="777")
        result = await hass.services.async_call(
            DOMAIN, "aufnahme_vorbereiten", {"spielpartner": "frank_visselff"}, blocking=True, return_response=True
        )
    assert result["spielpartner"] == "frank_visselff"
    assert result["obs_pfad_gesetzt"] == 4
    assert result["obs_format_gesetzt"] == 3
    paths = [s for e, s in calls if "path" in s]
    assert all(s["path"].startswith("X:/#2.0 Meine Videos OBS aufnahmen/Spielen mit Frank #01/Saison 02 vom ") for s in paths)
    fmts = {e: s["filename_formatting"] for e, s in calls if "filename_formatting" in s}
    assert fmts["switch.obs_filter_fuchsblick"] == "#01.02.03.FB.14 (4K) %DD.%MM.%CCYY"
    assert fmts["switch.obs_filter_kesselcam"].startswith("#01.02.03.KC.14")
    assert any("Filter ohne Cam-Kuerzel" in h and "unbekannt" in h for h in result["hinweise"])
    assert hass.states.get("sensor.spielpartner_aufnahme_current_player").state == "frank_visselff"


async def test_prepare_with_folder_tool_new_season(hass: HomeAssistant) -> None:
    entry = await _entry(hass)
    _obs(hass)
    tool = {"name": "", "path": BASE_WIN}
    ids = dict(
        base="button.spielzimmer_pc_ordner_werkzeug_zur_basis_wechseln",
        enter="button.spielzimmer_pc_ordner_werkzeug_in_ordner_wechseln",
        name="text.spielzimmer_pc_ordner_werkzeug_neuer_ordner_name",
        path="sensor.spielzimmer_pc_ordner_werkzeug_aktueller_ordner_adresse",
        sel="select.spielzimmer_pc_ordner_werkzeug_ordner_auswaehlen_wechseln",
    )
    hass.states.async_set(ids["path"], "irgendwo")
    hass.states.async_set(ids["base"], "unknown")
    hass.states.async_set(ids["enter"], "unknown")
    hass.states.async_set(ids["name"], "")
    hass.states.async_set(ids["sel"], "x", {"options": ["Saison 02 vom 01,01,2026"]})

    async def set_text(call):
        tool["name"] = call.data["value"]

    async def press(call):
        if call.data["entity_id"] == ids["base"]:
            hass.states.async_set(ids["path"], BASE_WIN)
        else:
            hass.states.async_set(ids["path"], hass.states.get(ids["path"]).state + "\\" + tool["name"])

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    hass.services.async_register("text", "set_value", set_text)
    hass.services.async_register("button", "press", press)
    m = entry.runtime_data
    with patch("custom_components.spielpartner_aufnahme.manager.DiscordClient") as dc:
        dc.return_value.create_forum_thread = AsyncMock(return_value="777")
        result = await m.async_prepare("frank_visselff")
    assert result["neue_saison"] is True
    assert result["saison"] == 3 and result["aufnahme_in_saison"] == 1 and result["gesamt"] == 14
    assert "neuer Thread" in result["discord"]
    assert m.state_of("frank_visselff")["thread_id"] == "777"
    assert m.state_of("frank_visselff")["thread_saison"] == "03"
    assert not [h for h in result["hinweise"] if "Zeitueberschreitung" in h]
    # zweiter Lauf am selben Tag: gleiche Saison (Ordner existiert jetzt)
    from homeassistant.util import dt as dt_util

    heute = dt_util.now().strftime("%d,%m,%Y")
    hass.states.async_set(ids["sel"], "x", {"options": [f"Saison 03 vom {heute}"]})
    result = await m.async_prepare("frank_visselff")
    assert result["neue_saison"] is False and result["saison"] == 3


async def test_recording_cycle_counts_and_posts(hass: HomeAssistant) -> None:
    options = {**OPTIONS, "post_abstand_sekunden": 0}
    entry = await _entry(hass, options)
    calls = _obs(hass)
    hass.states.async_set("binary_sensor.rec", "off")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    m = entry.runtime_data
    m.data["active"] = "frank_visselff"
    posted = []

    class FakeImg:
        content = b"jpg"
        content_type = "image/jpeg"

    class FakeClient:
        async def post_message(self, channel, text, images=None):
            posted.append((channel, text, images))

    with patch.object(m, "_discord", return_value=FakeClient()), patch(
        "custom_components.spielpartner_aufnahme.manager.async_get_image", AsyncMock(return_value=FakeImg())
    ):
        r = await m.async_post_update()
        await m._post_task
    # nur Fuchsblick und Hoelenblick sind standardmaessig zum Posten angehakt
    assert r["gepostet"] and r["cams"] == ["Fuchsblick", "Hoelenblick"]
    assert all(p[0] == "99" for p in posted)
    assert posted[0][1].startswith("Aufnahme laeuft seit 5 Minuten.")
    # je Cam: erst das Bild, direkt darunter die ID
    assert posted[1][1] == "" and posted[1][2][0][0].startswith("Fuchsblick_")
    assert "Fuchsblick" in posted[2][1] and "#01.02.03.FB.14" in posted[2][1] and posted[2][2] is None
    assert posted[3][2][0][0].startswith("Hoelenblick_")
    assert "#01.02.03.HB.14" in posted[4][1]
    assert len(posted) == 5
    hass.states.async_set("binary_sensor.rec", "on")
    await hass.async_block_till_done()
    hass.states.async_set("binary_sensor.rec", "off")
    await hass.async_block_till_done()
    s = m.state_of("frank_visselff")
    assert (s["aufnahmen"], s["gesamt"]) == (4, 15)
    assert any(x[1].get("filename_formatting", "").startswith("#01.02.04.") for x in calls)


async def test_set_counters_service_and_unload(hass: HomeAssistant) -> None:
    entry = await _entry(hass)
    _obs(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await hass.services.async_call(
        DOMAIN, "zaehler_setzen", {"spielpartner": "frank_visselff", "saison": 5, "gesamt": 100}, blocking=True
    )
    s = entry.runtime_data.state_of("frank_visselff")
    assert (s["saison"], s["aufnahmen"], s["gesamt"]) == (5, 3, 100)
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_config_flow_and_subentry_flow(hass: HomeAssistant) -> None:
    res = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert res["type"] == "form"
    res = await hass.config_entries.flow.async_configure(
        res["flow_id"],
        {
            "basis_pfad_obs": "X:/v",
            "basis_pfad_windows": "X:\\v",
            "ordner_praefix": "Spielen mit",
            "aufnahme_entity": "binary_sensor.rec",
            "post_nach_minuten": 5,
        },
    )
    assert res["type"] == "create_entry"
    entry = res["result"]
    await hass.async_block_till_done()
    assert sum(1 for s in entry.subentries.values() if s.subentry_type == SUBENTRY_CAM) == 16
    flow = await hass.config_entries.subentries.async_init((entry.entry_id, SUBENTRY_PARTNER), context={"source": "user"})
    assert flow["type"] == "form"
    bad = await hass.config_entries.subentries.async_configure(flow["flow_id"], {"kennung": "Gross Klein"})
    assert bad["errors"]["kennung"] == "invalid_kennung"
    done = await hass.config_entries.subentries.async_configure(
        flow["flow_id"],
        {"kennung": "neu_a", "anzeige": "Neu A", "ordner_nr": 7, "start_saison": 4, "start_gesamt": 21},
    )
    assert done["type"] == "create_entry"
    await hass.async_block_till_done()
    sub = next(s for s in entry.subentries.values() if s.subentry_type == SUBENTRY_PARTNER)
    assert sub.data["anzeige"] == "Neu A" and sub.data["ordner_nr"] == 7
    assert sub.data["initial"] == {"saison": 4, "gesamt": 21}
    assert "alte_helfer_uebernehmen" not in sub.data
    m = entry.runtime_data
    assert m.state_of("neu_a")["saison"] == 4


async def test_options_flow_reloads(hass: HomeAssistant) -> None:
    entry = await _entry(hass)
    _obs(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    res = await hass.config_entries.options.async_init(entry.entry_id)
    assert res["type"] == "form"
    new = {**OPTIONS, "post_nach_minuten": 9}
    res = await hass.config_entries.options.async_configure(res["flow_id"], new)
    assert res["type"] == "create_entry"
    await hass.async_block_till_done()
    assert entry.options["post_nach_minuten"] == 9
    assert entry.runtime_data.opt("post_nach_minuten") == 9


async def test_cam_subentry_checkbox(hass: HomeAssistant) -> None:
    entry = await _entry(hass)
    _obs(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    sid, sub = next((i, s) for i, s in entry.subentries.items() if s.data.get("name") == "Kesselcam")
    assert sub.data["discord_posten"] is False
    flow = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_CAM), context={"source": "reconfigure", "subentry_id": sid}
    )
    assert flow["type"] == "form" and "filter_entity" not in {str(k) for k in flow["data_schema"].schema}
    res = await hass.config_entries.subentries.async_configure(
        flow["flow_id"], {"kuerzel": "KC", "discord_posten": True, "kamera_entity": "camera.kessel"}
    )
    await hass.async_block_till_done()
    assert res["type"] == "abort"
    assert entry.subentries[sid].data["discord_posten"] is True
    assert [c.name for c in entry.runtime_data.cams if c.post] == ["Fuchsblick", "Hoelenblick", "Kesselcam"]
