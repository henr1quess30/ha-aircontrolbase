"""Constantes da integração AirControlBase (CCM21)."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "aircontrolbase"

# Base e endpoints do AirControlBase
BASE_URL = "https://www.aircontrolbase.com"
EP_LOGIN          = "/web/user/login"
EP_GET_DETAILS    = "/web/userGroup/getDetails"
EP_CONTROL        = "/web/device/control"
EP_CONTROL_LOG    = "/web/record/controlLog"
EP_DEVICE_LOG     = "/web/record/deviceLog"
EP_LOGIN_LOG      = "/web/record/login"
EP_SCHEDULE_ALL   = "/web/schedule/getAll"
EP_SCHEDULE_UPDATE = "/web/schedule/update"

# Polling
DEFAULT_POLL_INTERVAL = timedelta(seconds=20)
LOG_POLL_INTERVAL     = timedelta(minutes=5)
LOG_PAGE_SIZE         = 50  # quantos eventos pegar por chamada

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

# Storage de coordinators no hass.data
DATA_COORDINATOR = "coordinator"
DATA_API         = "api"

# Dias da semana para schedule (segue ISO: 1=segunda ... 7=domingo)
WEEK_DAYS = [1, 2, 3, 4, 5, 6, 7]
