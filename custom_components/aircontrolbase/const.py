"""Constantes da integração AirControlBase (CCM21)."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "aircontrolbase"

# Base e endpoints do AirControlBase
BASE_URL = "https://www.aircontrolbase.com"
EP_LOGIN       = "/web/user/login"
EP_GET_DETAILS = "/web/userGroup/getDetails"
EP_CONTROL     = "/web/device/control"

# Polling
DEFAULT_POLL_INTERVAL = timedelta(seconds=20)

# Códigos de erro do AirControlBase
CODE_SESSION_EXPIRED = 40018

# Conexão
DEFAULT_TIMEOUT = 20  # segundos

# Mapeamentos HVAC (HA <-> AirControlBase)
# HA: off | cool | heat | auto | dry | fan_only
# ACB modes: cool | heat | auto | dry | fan      (power=y/n controla on/off)
HA_TO_ACB_MODE = {
    "cool": "cool",
    "heat": "heat",
    "auto": "auto",
    "dry": "dry",
    "fan_only": "fan",
}
ACB_TO_HA_MODE = {v: k for k, v in HA_TO_ACB_MODE.items()}

# Fan modes (HA <-> ACB)
HA_FAN_MODES = ["off", "low", "mid", "high", "auto"]

# Temperatura
MIN_TEMP = 17
MAX_TEMP = 30
TEMP_STEP = 1

# ConfigEntry data keys
CONF_ACCOUNT  = "account"
CONF_PASSWORD = "password"
CONF_USER_ID  = "user_id"

# Options keys
OPT_GROUP_AREAS = "group_areas"  # lista de nomes de áreas que terão climate de grupo
