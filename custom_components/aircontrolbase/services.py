"""Serviços do AirControlBase."""
from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant, ServiceCall, callback

from .const import DOMAIN
from .coordinator import AirControlBaseCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_REFRESH = "refresh"


def _all_buckets(hass: HomeAssistant) -> list[dict]:
    return list((hass.data.get(DOMAIN) or {}).values())


@callback
def async_register_services(hass: HomeAssistant) -> None:
    """Registra os serviços do domínio (chamada idempotente)."""

    if hass.services.has_service(DOMAIN, SERVICE_REFRESH):
        return

    async def _handle_refresh(call: ServiceCall) -> None:
        for b in _all_buckets(hass):
            coord: AirControlBaseCoordinator = b["coordinator"]
            await coord.async_request_refresh()

    hass.services.async_register(DOMAIN, SERVICE_REFRESH, _handle_refresh)


@callback
def async_unregister_services(hass: HomeAssistant) -> None:
    if hass.data.get(DOMAIN):
        return  # ainda tem instâncias
    if hass.services.has_service(DOMAIN, SERVICE_REFRESH):
        hass.services.async_remove(DOMAIN, SERVICE_REFRESH)
