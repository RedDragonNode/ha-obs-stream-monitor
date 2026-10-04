# OBS Stream Monitor for Home Assistant

A Home Assistant custom integration that pulls read-only stream/recording stats from [OBS Studio](https://obsproject.com/) via its built-in [obs-websocket v5](https://github.com/obsproject/obs-websocket) server, plus an optional button to launch OBS itself on the remote machine.

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

| OBS starten | button | Triggers a Windows Scheduled Task that launches OBS (only appears once SSH is configured, see below) |

Entities are polled every 10 seconds.

### A note on bitrate

obs-websocket v5 does not expose a direct bitrate field. This integration derives one from the change in `outputBytes` between two polls, divided by the elapsed time. It's a close approximation of what OBS's own stats dock shows, not a value read directly from OBS.

## Optional: starting OBS from Home Assistant

obs-websocket can only talk to OBS once it's already running, so starting OBS cold needs a different path: Home Assistant opens an SSH connection to the machine and triggers a Windows Scheduled Task that launches OBS. Running it as a Scheduled Task (rather than spawning the process directly over SSH) is deliberate — only a task configured to run in the logged-on user's session shows up on screen; a bare SSH-launched process runs invisibly in its own session.

One-time setup on the machine running OBS:

1. **Enable OpenSSH Server** (Windows): Settings -> System -> Optional Features -> Add a feature -> "OpenSSH Server". Then, in an admin PowerShell: `Start-Service sshd` and `Set-Service -Name sshd -StartupType Automatic`.
2. **Create a Scheduled Task** that starts OBS: Task Scheduler -> Create Task (not "Create Basic Task") -> name it (e.g. `StartOBS`) -> General tab: **"Run only when user is logged on"** -> Actions tab: Program = path to `obs64.exe`, Start in = the OBS folder. No trigger needed; it's only ever run remotely via `schtasks /run`.
3. In Home Assistant: open the integration -> Configure -> fill in the SSH username, password, port (default `22`) and the task name from step 2. The "OBS starten" button entity appears after saving (entry reloads automatically).

Leave the SSH fields empty to keep this integration monitoring-only.

## License

MIT, see [LICENSE](LICENSE).
