"""DataUpdateCoordinator do AirControlBase."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AirControlBaseClient, AirControlBaseError, AuthError
from .const import DEFAULT_POLL_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class AirControlBaseCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Faz polling do getDetails e expõe estrutura parseada."""

    def __init__(self, hass: HomeAssistant, client: AirControlBaseClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_POLL_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            raw = await self.client.get_details()
        except AuthError as err:
            raise UpdateFailed(f"Auth: {err}") from err
        except AirControlBaseError as err:
            raise UpdateFailed(f"API: {err}") from err

        result = raw.get("result") or {}
        areas_raw = result.get("areas") or []
        device_case = result.get("deviceCase") or {}

        devices: dict[str, dict[str, Any]] = {}
        areas: list[dict[str, Any]] = []

        for area in areas_raw:
            area_name = area.get("name") or ""
            area_id = str(area.get("id") or area.get("aid") or "")
            device_ids: list[str] = []
            for d in area.get("data") or []:
                dev_id = str(d.get("id") or "")
                if not dev_id:
                    continue
                devices[dev_id] = {
                    "id": dev_id,
                    "name": d.get("name") or f"Device {dev_id}",
                    "area": area_name,
                    "area_id": area_id,
                    "power": d.get("power") or "n",
                    "mode": d.get("mode") or "cool",
                    "wind": d.get("wind") or "auto",
                    "setTemp": int(d.get("setTemp") or 24),
                    "factTemp": int(d.get("factTemp") or 0),
                    "lock": d.get("lock") or "",
                    "unlock": d.get("unlock") or "mode,cool,heat,wind,remote",
                    "swing": d.get("swing") or "n",
                    "modeLockValue": d.get("modeLockValue") or "",
                    "coolLockValue": d.get("coolLockValue") or "",
                    "heatLockValue": d.get("heatLockValue") or "",
                    "windLockValue": d.get("windLockValue") or "",
                    "raw": d,
                }
                device_ids.append(dev_id)
            areas.append({"id": area_id, "name": area_name, "device_ids": device_ids})

        return {
            "devices": devices,
            "areas": areas,
            "summary": {
                "cool": int(device_case.get("cool") or 0),
                "heat": int(device_case.get("heat") or 0),
                "fan": int(device_case.get("fan") or 0),
                "stop": int(device_case.get("stop") or 0),
                "lock": int(device_case.get("lock") or 0),
                "error": int(device_case.get("error") or 0),
            },
        }
