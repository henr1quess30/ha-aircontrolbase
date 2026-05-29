"""Integração AirControlBase (CCM21) para Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .api import AirControlBaseClient, AirControlBaseError
from .const import CONF_ACCOUNT, CONF_PASSWORD, CONF_USER_ID, DOMAIN
from .coordinator import AirControlBaseCoordinator
from .services import async_register_services, async_unregister_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.SENSOR, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    account = entry.data[CONF_ACCOUNT]
    password = entry.data[CONF_PASSWORD]
    user_id = entry.data.get(CONF_USER_ID)

    client = AirControlBaseClient(account, password, user_id)
    try:
        await client.login()
    except AirControlBaseError as err:
        await client.close()
        _LOGGER.error("Falha no login inicial: %s", err)
        raise

    coordinator = AirControlBaseCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        data = hass.data[DOMAIN].pop(entry.entry_id, None)
        if data:
            client: AirControlBaseClient = data["client"]
            await client.close()
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN, None)
            async_unregister_services(hass)
    return unloaded
