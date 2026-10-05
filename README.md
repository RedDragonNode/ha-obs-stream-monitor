# OBS Stream Monitor for Home Assistant

A Home Assistant custom integration that pulls read-only stream/recording stats from [OBS Studio](https://obsproject.com/) via its built-in [obs-websocket v5](https://github.com/obsproject/obs-websocket) server, plus two optional extras: a button to launch OBS itself on the remote machine, and dropdowns to switch OBS's profile and scene collection.

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

| OBS starten | button | Triggers a Windows Scheduled Task that launches OBS (only appears once SSH is configured, see below) |
| OBS Profil | select | Switches OBS's active profile (only appears once "OBS-Steuerung aktivieren" is on, see below) |
| OBS Szenensammlung | select | Switches OBS's active scene collection (only appears once "OBS-Steuerung aktivieren" is on, see below) |

Entities are polled every 10 seconds. The two select entities go "not available" whenever OBS itself does, since switching only makes sense while it's actually running.

### A note on bitrate

obs-websocket v5 does not expose a direct bitrate field. This integration derives one from the change in `outputBytes` between two polls, divided by the elapsed time. It's a close approximation of what OBS's own stats dock shows, not a value read directly from OBS.

## Optional: starting OBS from Home Assistant

obs-websocket can only talk to OBS once it's already running, so starting OBS cold needs a different path: Home Assistant opens an SSH connection to the machine and triggers a Windows Scheduled Task that launches OBS. Running it as a Scheduled Task (rather than spawning the process directly over SSH) is deliberate — only a task configured to run in the logged-on user's session shows up on screen; a bare SSH-launched process runs invisibly in its own session.

Leave the SSH fields in the integration's Configure dialog empty to keep this integration monitoring-only.

**Full step-by-step setup (including the two gotchas that actually bite — firewall network profile, and Microsoft-account password sign-in) is in [docs/ssh-start-button-setup.md](docs/ssh-start-button-setup.md).**

## Optional: switching profile / scene collection from Home Assistant

The two sensors "Aktuelles Profil" and "Aktuelle Szenensammlung" are always there. The matching dropdowns to actually switch them are a separate, off-by-default control feature — this is what to do to turn them on:

1. **Settings -> Devices & Services -> OBS Stream Monitor -> Configure**
2. Scroll to the bottom and check **"OBS-Steuerung aktivieren (Profil/Szenensammlung wechseln)"**
3. Submit — the entry reloads itself, no restart needed
4. Two new select entities now show up under the device's "Steuerung" card: **"OBS Profil"** and **"OBS Szenensammlung"**, populated live from whatever profiles/scene collections currently exist in OBS

Picking a value in either one switches it in OBS immediately, the same as picking it from OBS's own menus. Both go "not available" whenever OBS itself does, since switching only makes sense while it's actually running.

This is actual control, not monitoring, so it's off by default like the SSH start button — leave the checkbox unticked to keep the integration read-only.

### Multiple OBS installations

Used one at a time (not simultaneously): give each installation its own obs-websocket port (even though they never run together — HA tells entries apart by host+port, so a shared port means a shared, colliding entry), create a separate Scheduled Task per installation, and add a separate Home Assistant integration entry per installation with its own task name under Configure. Whichever one isn't currently running just shows "not available" sensors, which is correct.

Running two instances at once is a different, more involved OBS-side setup (`--multi` flag, separate `--profile`/portable config dirs) and isn't covered here.

## Icon

Ships its own brand icon (`custom_components/obs_stream_monitor/brand/`) - a generic original camera/live-dot mark, not OBS's own logo/trademark, so there's no licensing question around redistributing it.

## License

MIT, see [LICENSE](LICENSE).
