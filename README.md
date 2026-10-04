# OBS Stream Monitor for Home Assistant

A Home Assistant custom integration that pulls read-only stream/recording stats from [OBS Studio](https://obsproject.com/) via its built-in [obs-websocket v5](https://github.com/obsproject/obs-websocket) server. Monitoring only — no remote control of OBS.

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

Entities are polled every 10 seconds.

### A note on bitrate

obs-websocket v5 does not expose a direct bitrate field. This integration derives one from the change in `outputBytes` between two polls, divided by the elapsed time. It's a close approximation of what OBS's own stats dock shows, not a value read directly from OBS.

## License

MIT, see [LICENSE](LICENSE).
