"""Constants for the OBS Stream Monitor integration."""
from datetime import timedelta

DOMAIN = "obs_stream_monitor"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_PASSWORD = "password"

CONF_SSH_USERNAME = "ssh_username"
CONF_SSH_PASSWORD = "ssh_password"
CONF_SSH_PORT = "ssh_port"
CONF_TASK_NAME = "task_name"

DEFAULT_PORT = 4455
DEFAULT_NAME = "OBS Stream Monitor"
DEFAULT_SSH_PORT = 22
DEFAULT_TASK_NAME = "StartOBS"

SCAN_INTERVAL = timedelta(seconds=10)
CONNECT_TIMEOUT = 5
SSH_TIMEOUT = 10
