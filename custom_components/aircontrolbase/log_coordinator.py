"""Coordinator de histórico — polling lento de deviceLog (operação e erros)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AirControlBaseClient, AirControlBaseError
from .const import DOMAIN, LOG_PAGE_SIZE, LOG_POLL_INTERVAL

_LOGGER = logging.getLogger(__name__)

# Chaves comuns onde APIs JSON colocam listas de registros
_LIST_KEYS = ("records", "list", "data", "rows", "content", "items", "result")
# Chaves comuns para o device_id dentro de cada registro
_DEVICE_ID_KEYS = ("deviceId", "did", "id", "device_id", "dId")
# Chaves comuns para timestamp
_TIME_KEYS = ("createTime", "time", "ts", "timestamp", "date", "createDate", "logTime")
# Chaves comuns para descrição/ação
_DESC_KEYS = ("desc", "description", "content", "msg", "message", "action", "operation", "event")


def _extract_records(payload: Any) -> list[dict[str, Any]]:
    """Tenta achar a lista de registros no payload, defensivamente."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return []
    # tenta direto no root
    for k in _LIST_KEYS:
        v = payload.get(k)
        if isinstance(v, list):
            return [r for r in v if isinstance(r, dict)]
    # tenta dentro de "result"
    result = payload.get("result")
    if isinstance(result, dict):
        for k in _LIST_KEYS:
            v = result.get(k)
            if isinstance(v, list):
                return [r for r in v if isinstance(r, dict)]
    if isinstance(result, list):
        return [r for r in result if isinstance(r, dict)]
    return []


def _record_device_id(record: dict[str, Any]) -> str | None:
    for k in _DEVICE_ID_KEYS:
        v = record.get(k)
        if v is not None:
            return str(v)
    return None


def _record_timestamp(record: dict[str, Any]) -> Any:
    for k in _TIME_KEYS:
        v = record.get(k)
        if v is not None:
            return v
    return None


def _record_summary(record: dict[str, Any]) -> str:
    for k in _DESC_KEYS:
        v = record.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    # fallback: stringificar campos chave
    parts = []
    for k in ("type", "status", "operation"):
        v = record.get(k)
        if v:
            parts.append(f"{k}={v}")
    return ", ".join(parts) or "evento"


class AirControlBaseLogCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll lento de deviceLog (type=r e type=m)."""

    def __init__(self, hass: HomeAssistant, client: AirControlBaseClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_logs",
            update_interval=LOG_POLL_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        ops_raw: Any = None
        err_raw: Any = None
        ops_err: Exception | None = None
        err_err: Exception | None = None

        try:
            ops_raw = await self.client.get_device_log(log_type="r", page=1, page_size=LOG_PAGE_SIZE)
        except Exception as err:  # noqa: BLE001
            ops_err = err
            _LOGGER.warning("deviceLog type=r falhou: %s: %s", type(err).__name__, err)

        try:
            err_raw = await self.client.get_device_log(log_type="m", page=1, page_size=LOG_PAGE_SIZE)
        except Exception as err:  # noqa: BLE001
            err_err = err
            _LOGGER.warning("deviceLog type=m falhou: %s: %s", type(err).__name__, err)

        if ops_raw is None and err_raw is None:
            raise UpdateFailed(
                f"deviceLog falhou — r={type(ops_err).__name__}: {ops_err}; "
                f"m={type(err_err).__name__}: {err_err}"
            )

        _LOGGER.debug("deviceLog type=r raw: %s", ops_raw)
        _LOGGER.debug("deviceLog type=m raw: %s", err_raw)

        ops = _extract_records(ops_raw) if ops_raw is not None else []
        errors = _extract_records(err_raw) if err_raw is not None else []

        # agrupa últimos eventos por device (op record mais recente vence — assumindo
        # que a API retorna por ordem decrescente; senão é só "algum recente")
        last_by_device: dict[str, dict[str, Any]] = {}
        for rec in ops:
            dev_id = _record_device_id(rec)
            if dev_id and dev_id not in last_by_device:
                last_by_device[dev_id] = {
                    "timestamp": _record_timestamp(rec),
                    "summary": _record_summary(rec),
                    "raw": rec,
                }

        return {
            "ops": ops,
            "errors": errors,
            "last_by_device": last_by_device,
            "ops_count": len(ops),
            "errors_count": len(errors),
        }
