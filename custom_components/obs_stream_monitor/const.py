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
# v0.7.5+: stopping OBS also runs a Scheduled Task now (see ssh_control.py's
# stop_obs() docstring for why a direct SSH-run script can never reliably
# reach OBS's windows) - CONF_OBS_PROCESS_NAME/DEFAULT_OBS_PROCESS_NAME were
# the old, now-unused "which process to close" option for that approach;
# the process name now lives in the local stop-obs.ps1 script instead.
CONF_STOP_TASK_NAME = "stop_task_name"

CONF_ENABLE_CONTROL = "enable_control"
CONF_ENABLE_SCENE_TREE = "enable_scene_tree"

DEFAULT_PORT = 4455
DEFAULT_NAME = "OBS Stream Monitor"
DEFAULT_SSH_PORT = 22
DEFAULT_TASK_NAME = "StartOBS"
DEFAULT_STOP_TASK_NAME = "StopOBS"
DEFAULT_ENABLE_CONTROL = False
DEFAULT_ENABLE_SCENE_TREE = False

SCAN_INTERVAL = timedelta(seconds=10)
CONNECT_TIMEOUT = 5
SSH_TIMEOUT = 10
