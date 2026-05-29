"""Serviços do AirControlBase (schedule + refresh)."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, callback
from homeassistant.helpers import config_validation as cv

from .api import AirControlBaseClient
from .const import DOMAIN, HA_TO_ACB_MODE, LOG_PAGE_SIZE
from .coordinator import AirControlBaseCoordinator
from .log_coordinator import AirControlBaseLogCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_CREATE_SCHEDULE = "create_schedule"
SERVICE_UPDATE_SCHEDULE = "update_schedule"
SERVICE_REFRESH = "refresh"
SERVICE_GET_CONTROL_LOG = "get_control_log"
SERVICE_REFRESH_LOGS = "refresh_logs"

_BASE_SCHEDULE_SCHEMA = {
    vol.Required("device_ids"): vol.All(cv.ensure_list, [cv.string]),
    vol.Required("timer"): cv.matches_regex(r"^\d{2}:\d{2}$"),
    vol.Required("mode"): vol.In(["cool", "heat", "auto", "dry", "fan_only", "off"]),
    vol.Optional("temperature", default=24): vol.All(vol.Coerce(int), vol.Range(min=17, max=30)),
    vol.Optional("fan_mode", default="auto"): vol.In(["low", "mid", "high", "auto"]),
    vol.Optional("weeks", default=[1, 2, 3, 4, 5, 6, 7]): vol.All(
        cv.ensure_list, [vol.All(vol.Coerce(int), vol.Range(min=1, max=7))]
    ),
    vol.Optional("cycle", default=True): cv.boolean,
}

CREATE_SCHEDULE_SCHEMA = vol.Schema(_BASE_SCHEDULE_SCHEMA)
UPDATE_SCHEDULE_SCHEMA = vol.Schema(
    {vol.Required("schedule_id"): cv.string, **_BASE_SCHEDULE_SCHEMA}
)

GET_CONTROL_LOG_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Optional("page", default=1): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Optional("page_size", default=LOG_PAGE_SIZE): vol.All(vol.Coerce(int), vol.Range(min=1, max=200)),
    }
)


def _all_buckets(hass: HomeAssistant) -> list[dict[str, Any]]:
    return list((hass.data.get(DOMAIN) or {}).values())


def _build_objs(
    coordinator: AirControlBaseCoordinator, device_ids: list[str]
) -> list[dict[str, Any]]:
    """Agrupa device_ids por área (aname/aid), no formato esperado pelo schedule/update."""
    data = coordinator.data or {}
    devices = data.get("devices", {})
    by_area: dict[str, dict[str, Any]] = {}
    for dev_id in device_ids:
        d = devices.get(str(dev_id))
        if not d:
            _LOGGER.warning("device_id %s não encontrado no cache", dev_id)
            continue
        aid = d.get("area_id") or ""
        aname = d.get("area") or ""
        bucket = by_area.setdefault(
            f"{aid}::{aname}",
            {"aname": aname, "aid": aid, "devices": []},
        )
        bucket["devices"].append({"deviceName": d.get("name"), "deviceId": str(dev_id)})
    return list(by_area.values())


def _build_control(mode: str, temperature: int, fan_mode: str) -> tuple[dict[str, Any], str]:
    if mode == "off":
        power = "n"
        acb_mode = "cool"
    else:
        power = "y"
        acb_mode = HA_TO_ACB_MODE.get(mode, mode)
    control = {
        "mode": acb_mode,
        "temp": str(int(temperature)),
        "wind": fan_mode,
        "power": power,
    }
    return control, power


def _pick_bucket(hass: HomeAssistant, device_ids: list[str]) -> dict[str, Any] | None:
    """Pega o bucket de integração que conhece esses device_ids."""
    buckets = _all_buckets(hass)
    for b in buckets:
        coord: AirControlBaseCoordinator = b["coordinator"]
        devices = (coord.data or {}).get("devices", {})
        if any(str(did) in devices for did in device_ids):
            return b
    return buckets[0] if buckets else None


@callback
def async_register_services(hass: HomeAssistant) -> None:
    """Registra os serviços do domínio (chamada idempotente)."""

    if hass.services.has_service(DOMAIN, SERVICE_CREATE_SCHEDULE):
        return

    async def _handle_create(call: ServiceCall) -> None:
        await _handle_schedule(call, schedule_id=None)

    async def _handle_update(call: ServiceCall) -> None:
        await _handle_schedule(call, schedule_id=call.data["schedule_id"])

    async def _handle_schedule(call: ServiceCall, schedule_id: str | None) -> None:
        device_ids = [str(d) for d in call.data["device_ids"]]
        bucket = _pick_bucket(hass, device_ids)
        if not bucket:
            _LOGGER.error("Nenhuma integração AirControlBase configurada")
            return
        client: AirControlBaseClient = bucket["client"]
        coordinator: AirControlBaseCoordinator = bucket["coordinator"]
        control, power = _build_control(
            call.data["mode"], call.data["temperature"], call.data["fan_mode"]
        )
        objs = _build_objs(coordinator, device_ids)
        if not objs:
            _LOGGER.error("Nenhum device válido para o schedule")
            return
        await client.update_schedule(
            schedule_id=schedule_id,
            control=control,
            timer=call.data["timer"],
            weeks=call.data["weeks"],
            objs=objs,
            cycle=call.data["cycle"],
            power=power,
        )
        await coordinator.async_request_refresh()

    async def _handle_refresh(call: ServiceCall) -> None:
        for b in _all_buckets(hass):
            coord: AirControlBaseCoordinator = b["coordinator"]
            await coord.async_request_refresh()

    async def _handle_refresh_logs(call: ServiceCall) -> None:
        for b in _all_buckets(hass):
            log_coord: AirControlBaseLogCoordinator | None = b.get("log_coordinator")
            if log_coord:
                await log_coord.async_request_refresh()

    async def _handle_get_control_log(call: ServiceCall) -> ServiceResponse:
        device_id = str(call.data["device_id"])
        bucket = _pick_bucket(hass, [device_id])
        if not bucket:
            return {"records": [], "error": "no_integration"}
        client: AirControlBaseClient = bucket["client"]
        try:
            raw = await client.get_control_log(
                device_id=device_id,
                page=call.data["page"],
                page_size=call.data["page_size"],
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("get_control_log falhou: %s", err)
            return {"records": [], "error": str(err)}
        return {"raw": raw}

    hass.services.async_register(
        DOMAIN, SERVICE_CREATE_SCHEDULE, _handle_create, schema=CREATE_SCHEDULE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_UPDATE_SCHEDULE, _handle_update, schema=UPDATE_SCHEDULE_SCHEMA
    )
    hass.services.async_register(DOMAIN, SERVICE_REFRESH, _handle_refresh)
    hass.services.async_register(DOMAIN, SERVICE_REFRESH_LOGS, _handle_refresh_logs)
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_CONTROL_LOG,
        _handle_get_control_log,
        schema=GET_CONTROL_LOG_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )


@callback
def async_unregister_services(hass: HomeAssistant) -> None:
    if (hass.data.get(DOMAIN) or {}):
        return  # ainda tem instâncias
    for svc in (
        SERVICE_CREATE_SCHEDULE,
        SERVICE_UPDATE_SCHEDULE,
        SERVICE_REFRESH,
        SERVICE_REFRESH_LOGS,
        SERVICE_GET_CONTROL_LOG,
    ):
        if hass.services.has_service(DOMAIN, svc):
            hass.services.async_remove(DOMAIN, svc)
