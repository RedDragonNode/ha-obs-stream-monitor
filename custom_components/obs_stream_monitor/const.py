"""Constants for the OBS Stream Monitor integration."""
from datetime import timedelta

DOMAIN = "obs_stream_monitor"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_PASSWORD = "password"

DEFAULT_PORT = 4455
DEFAULT_NAME = "OBS Stream Monitor"

SCAN_INTERVAL = timedelta(seconds=10)
CONNECT_TIMEOUT = 5
