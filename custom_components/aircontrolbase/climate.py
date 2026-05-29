"""Plataforma climate do AirControlBase."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import AirControlBaseClient
from .const import (
    ACB_TO_HA_MODE,
    DOMAIN,
    HA_FAN_MODES,
    HA_TO_ACB_MODE,
    MAX_TEMP,
    MIN_TEMP,
    TEMP_STEP,
)
from .coordinator import AirControlBaseCoordinator

_LOGGER = logging.getLogger(__name__)

HVAC_MODES = [
    HVACMode.OFF,
    HVACMode.COOL,
    HVACMode.HEAT,
    HVACMode.AUTO,
    HVACMode.DRY,
    HVACMode.FAN_ONLY,
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    bucket = hass.data[DOMAIN][entry.entry_id]
    coordinator: AirControlBaseCoordinator = bucket["coordinator"]
    client: AirControlBaseClient = bucket["client"]

    known: set[str] = set()

    @callback
    def _discover() -> None:
        new = []
        for dev_id in coordinator.data.get("devices", {}):
            if dev_id in known:
                continue
            known.add(dev_id)
            new.append(AirControlBaseClimate(coordinator, client, dev_id))
        if new:
            async_add_entities(new)

    _discover()
    entry.async_on_unload(coordinator.async_add_listener(_discover))


class AirControlBaseClimate(CoordinatorEntity[AirControlBaseCoordinator], ClimateEntity):
    """Entidade climate de um AC."""

    _attr_has_entity_name = True
    _attr_name = None  # usa o nome do device
    _attr_translation_key = "ac"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = HVAC_MODES
    _attr_fan_modes = HA_FAN_MODES
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP
    _attr_target_temperature_step = TEMP_STEP
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(
        self,
        coordinator: AirControlBaseCoordinator,
        client: AirControlBaseClient,
        device_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._client = client
        self._device_id = device_id
        self._attr_unique_id = f"{DOMAIN}_{device_id}"

    # ── helpers ───────────────────────────────────────────────────────────────

    @property
    def _device(self) -> dict[str, Any] | None:
        return (self.coordinator.data or {}).get("devices", {}).get(self._device_id)

    @property
    def available(self) -> bool:
        return self._device is not None and super().available

    @property
    def device_info(self) -> DeviceInfo:
        d = self._device or {}
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=d.get("name") or f"AC {self._device_id}",
            manufacturer="AirControlBase",
            model="CCM21",
            suggested_area=d.get("area") or None,
        )

    # ── estado ────────────────────────────────────────────────────────────────

    @property
    def hvac_mode(self) -> HVACMode:
        d = self._device or {}
        if d.get("power") == "n":
            return HVACMode.OFF
        return HVACMode(ACB_TO_HA_MODE.get(d.get("mode", "cool"), "cool"))

    @property
    def fan_mode(self) -> str | None:
        d = self._device or {}
        wind = d.get("wind") or "auto"
        return wind if wind in HA_FAN_MODES else "auto"

    @property
    def current_temperature(self) -> float | None:
        d = self._device or {}
        v = d.get("factTemp")
        return float(v) if v not in (None, 0) else None

    @property
    def target_temperature(self) -> float | None:
        d = self._device or {}
        v = d.get("setTemp")
        return float(v) if v is not None else None

    # ── comandos ──────────────────────────────────────────────────────────────

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        d = self._device or {}
        if hvac_mode == HVACMode.OFF:
            changes = {"power": "n"}
        else:
            changes = {
                "power": "y",
                "mode": HA_TO_ACB_MODE.get(hvac_mode.value, "cool"),
            }
        await self._client.control_device(device_id=self._device_id, current=d, changes=changes)
        await self.coordinator.async_request_refresh()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        d = self._device or {}
        await self._client.control_device(
            device_id=self._device_id,
            current=d,
            changes={"wind": fan_mode},
        )
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        d = self._device or {}
        await self._client.control_device(
            device_id=self._device_id,
            current=d,
            changes={"setTemp": int(temp)},
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(HVACMode.COOL)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)
