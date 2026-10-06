# OBS Stream Monitor for Home Assistant

A Home Assistant custom integration that pulls read-only stream/recording stats from [OBS Studio](https://obsproject.com/) via its built-in [obs-websocket v5](https://github.com/obsproject/obs-websocket) server, plus optional extras: a switch to launch OBS on the remote machine (or close it again, gracefully), switches to start/stop the stream and recording, dropdowns to switch OBS's profile and scene collection, a service to push raw source/filter settings from automations, and a click-through dashboard card for OBS's scenes/sources/filters with visibility and filter toggles.

## Requirements

- OBS Studio 28+ (ships with obs-websocket v5 built in)
- OBS -> Tools -> WebSocket Server Settings: server enabled, note the port and password
- Home Assistant must be able to reach the machine running OBS on the configured port (same LAN, or routed)

## Installation (HACS)

1. HACS -> the three-dot menu (top right) -> Custom repositories
2. Add this repository URL, category "Integration"
3. Install "OBS Stream Monitor", restart Home Assistant

## Installation (manual)

Copy `custom_components/obs_stream_monitor/` into your Home Assistant `config/custom_components/` folder and restart.

## Setup

Settings -> Devices & Services -> Add Integration -> "OBS Stream Monitor"

| Field | Value |
|---|---|
| Host | IP address of the machine running OBS |
| Port | From OBS WebSocket Server Settings (default `4455`) |
| Password | From OBS WebSocket Server Settings |

## Entities

| Entity | Type | Description |
|---|---|---|
| Livestream | binary_sensor | On while OBS is actively streaming |
| Aufnahme | binary_sensor | On while OBS is actively recording |
| OBS läuft | binary_sensor | On while OBS is reachable over obs-websocket - unlike every other entity here, stays a clean on/off instead of going "not available" when OBS is down, so automations can react to it directly |
| Aktuelle Szene | sensor | Name of the active program scene |
| Stream-Dauer | sensor | Seconds since the current stream started |
| Bitrate | sensor | Output bitrate in kbit/s, derived between polls (see note below) |
| Dropped Frames | sensor | Percentage of output frames dropped so far this stream |
| Aufnahme-Dauer | sensor | Seconds since the current recording started |
| CPU-Auslastung (OBS) | sensor | OBS-reported CPU usage, percent |
| Freier Speicherplatz | sensor | Free space on OBS's recording output disk, GB |
| Aktuelle FPS | sensor | OBS's currently active render FPS |
| Aktuelles Profil | sensor | Name of OBS's currently active profile |
| Aktuelle Szenensammlung | sensor | Name of OBS's currently active scene collection |

| OBS | switch | Launches OBS via a Windows Scheduled Task, or asks it to close normally (not a forced kill) - only appears once SSH is configured, see below. Like "OBS läuft" above, stays usable even while OBS is unreachable |
| Stream | switch | Starts/stops the live stream (only appears once "OBS-Steuerung aktivieren" is on, see below) |
| Aufnahme | switch | Starts/stops recording (only appears once "OBS-Steuerung aktivieren" is on, see below) |
| OBS Profil | select | Switches OBS's active profile (only appears once "OBS-Steuerung aktivieren" is on, see below) |
| OBS Szenensammlung | select | Switches OBS's active scene collection (only appears once "OBS-Steuerung aktivieren" is on, see below) |
| *(dynamic, one per scene/source)* | switch | Shows/hides a source within one scene (only appears once "Szenen-Baum aktivieren" is on, see below) |
| *(dynamic, one per source/filter)* | switch | Enables/disables one filter on a source (only appears once "Szenen-Baum aktivieren" is on, see below) |

Entities are polled every 10 seconds. The select and stream/recording/scene-tree switch entities go "not available" whenever OBS itself does, since switching only makes sense while it's actually running - the "OBS" power switch and the "OBS läuft" sensor are the deliberate exception (see their descriptions above).

### A note on bitrate

obs-websocket v5 does not expose a direct bitrate field. This integration derives one from the change in `outputBytes` between two polls, divided by the elapsed time. It's a close approximation of what OBS's own stats dock shows, not a value read directly from OBS.

## Optional: starting (and gracefully stopping) OBS from Home Assistant

obs-websocket can only talk to OBS once it's already running, so starting OBS cold - and closing it down again - needs a different path: Home Assistant opens an SSH connection to the machine. Turning the "OBS" switch on triggers a Windows Scheduled Task that launches OBS (running it as a Scheduled Task, rather than spawning the process directly over SSH, is deliberate — only a task configured to run in the logged-on user's session shows up on screen; a bare SSH-launched process runs invisibly in its own session). Turning it off sends a plain, non-forced `taskkill` for OBS's process name, which asks OBS to close normally (its own exit handling runs - saving the current recording, asking for confirmation if a stream/recording is still active) rather than killing it outright.

Leave the SSH fields in the integration's Configure dialog empty to keep this integration monitoring-only.

**Full step-by-step setup (including the two gotchas that actually bite — firewall network profile, and Microsoft-account password sign-in — and how the graceful-stop side works) is in [docs/ssh-start-button-setup.md](docs/ssh-start-button-setup.md).**

## Optional: starting/stopping stream and recording, switching profile / scene collection

The sensors "Livestream", "Aufnahme", "Aktuelles Profil" and "Aktuelle Szenensammlung" are always there. The matching switches/dropdowns to actually control them are a separate, off-by-default control feature — this is what to do to turn it on:

1. **Settings -> Devices & Services -> OBS Stream Monitor -> Configure**
2. Scroll to the bottom and check **"OBS-Steuerung aktivieren (Stream/Aufnahme, Profil/Szenensammlung)"**
3. Submit — the entry reloads itself, no restart needed
4. Four new entities now show up under the device's "Steuerung" card: switches **"Stream"** and **"Aufnahme"**, and selects **"OBS Profil"** and **"OBS Szenensammlung"** (the latter two populated live from whatever profiles/scene collections currently exist in OBS)

Toggling the switches or picking a value in either select acts in OBS immediately, the same as using OBS's own UI. All four go "not available" whenever OBS itself does, since none of this makes sense while it's unreachable.

This is actual control, not monitoring, so it's off by default like the SSH-based "OBS" switch — leave the checkbox unticked to keep the integration read-only.

## Optional: scene/source/filter dashboard card

Turn on "Szenen-Baum aktivieren" in the integration's Configure dialog to get switch entities for every source's visibility within each scene, and for every filter on every source — plus a bundled dashboard card ("OBS Szenen-Baum") that presents them as a click-through tree: scenes → that scene's sources (with a visibility toggle) → that source's filters (with an enable toggle).

This needs two one-time setup steps (adding the card's resource, then adding the card to a dashboard) that Home Assistant doesn't allow an integration to do for you automatically.

**Full step-by-step setup, including the resource/dashboard steps and a troubleshooting table, is in [docs/scene-tree-dashboard-setup.md](docs/scene-tree-dashboard-setup.md).**

This is actual control, not monitoring, so it's off by default like the other extras — leave the checkbox unticked to keep the integration read-only. Note: this adds extra obs-websocket requests per poll (one per scene, plus one per source for its filters), which is negligible for a normal streaming setup but worth knowing if you have an unusually large number of scenes.

### Multiple OBS installations

Used one at a time (not simultaneously): give each installation its own obs-websocket port (even though they never run together — HA tells entries apart by host+port, so a shared port means a shared, colliding entry), create a separate Scheduled Task per installation, and add a separate Home Assistant integration entry per installation with its own task name under Configure. Whichever one isn't currently running just shows "not available" sensors, which is correct.

Running two instances at once is a different, more involved OBS-side setup (`--multi` flag, separate `--profile`/portable config dirs) and isn't covered here.

## Icon

Ships its own brand icon (`custom_components/obs_stream_monitor/brand/`) - a generic original camera/live-dot mark, not OBS's own logo/trademark, so there's no licensing question around redistributing it.

## License

MIT, see [LICENSE](LICENSE).
