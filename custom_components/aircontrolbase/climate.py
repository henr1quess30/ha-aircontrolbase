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
    OPT_GROUP_AREAS,
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


def _default_group_areas(coordinator: AirControlBaseCoordinator) -> list[str]:
    """Padrão: todas as áreas com mais de 1 device."""
    data = coordinator.data or {}
    return [a["name"] for a in data.get("areas", []) if len(a.get("device_ids", [])) > 1]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    bucket = hass.data[DOMAIN][entry.entry_id]
    coordinator: AirControlBaseCoordinator = bucket["coordinator"]
    client: AirControlBaseClient = bucket["client"]

    known_devices: set[str] = set()
    known_groups: set[str] = set()

    def _selected_group_areas() -> list[str]:
        opts = entry.options.get(OPT_GROUP_AREAS)
        if opts is None:
            return _default_group_areas(coordinator)
        return list(opts)

    @callback
    def _discover() -> None:
        new: list[ClimateEntity] = []
        # devices individuais
        for dev_id in coordinator.data.get("devices", {}):
            if dev_id in known_devices:
                continue
            known_devices.add(dev_id)
            new.append(AirControlBaseClimate(coordinator, client, dev_id))
        # grupos por área
        selected = set(_selected_group_areas())
        for area in coordinator.data.get("areas", []):
            name = area.get("name") or ""
            if not name or name in known_groups or name not in selected:
                continue
            device_ids = area.get("device_ids") or []
            if len(device_ids) < 2:
                continue
            known_groups.add(name)
            new.append(
                AirControlBaseGroupClimate(coordinator, client, entry.entry_id, name)
            )
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
            if d.get("wind") in (None, "", "off"):
                changes["wind"] = "auto"
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
        _LOGGER.info("Device %s: turn_on", self._device_id)
        await self.async_set_hvac_mode(HVACMode.COOL)

    async def async_turn_off(self) -> None:
        _LOGGER.info("Device %s: turn_off", self._device_id)
        await self.async_set_hvac_mode(HVACMode.OFF)


# ────────────────────────────────────────────────────────────────────────────────
# Climate de grupo (agrega N ACs de uma área AirControlBase)
# ────────────────────────────────────────────────────────────────────────────────


def _slugify(s: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in s.lower()).strip("_")


class AirControlBaseGroupClimate(
    CoordinatorEntity[AirControlBaseCoordinator], ClimateEntity
):
    """Climate agregado por área (Ar Teto, Ar Parede, ...)."""

    _attr_has_entity_name = True
    _attr_name = None
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
        entry_id: str,
        area_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._client = client
        self._area_name = area_name
        self._slug = _slugify(area_name)
        self._attr_unique_id = f"{DOMAIN}_group_{entry_id}_{self._slug}"

    @property
    def _members(self) -> list[dict[str, Any]]:
        data = self.coordinator.data or {}
        devices = data.get("devices", {})
        member_ids: list[str] = []
        for area in data.get("areas", []):
            if area.get("name") == self._area_name:
                member_ids = area.get("device_ids") or []
                break
        return [devices[mid] for mid in member_ids if mid in devices]

    @property
    def _on_members(self) -> list[dict[str, Any]]:
        return [m for m in self._members if m.get("power") == "y"]

    @property
    def available(self) -> bool:
        return bool(self._members) and super().available

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"group_{self._slug}")},
            name=self._area_name,
            manufacturer="AirControlBase",
            model="Grupo (área)",
            suggested_area=self._area_name,
        )

    # ── estado agregado ───────────────────────────────────────────────────────

    @property
    def hvac_mode(self) -> HVACMode:
        on = self._on_members
        if not on:
            return HVACMode.OFF
        # se todos no mesmo modo → esse modo; senão → o do primeiro
        modes = {m.get("mode", "cool") for m in on}
        first = list(modes)[0] if len(modes) == 1 else on[0].get("mode", "cool")
        return HVACMode(ACB_TO_HA_MODE.get(first, "cool"))

    @property
    def fan_mode(self) -> str | None:
        on = self._on_members
        if not on:
            return "auto"
        winds = {m.get("wind") or "auto" for m in on}
        if len(winds) == 1:
            w = next(iter(winds))
        else:
            w = on[0].get("wind") or "auto"
        return w if w in HA_FAN_MODES else "auto"

    @property
    def current_temperature(self) -> float | None:
        temps = [m.get("factTemp") for m in self._members if m.get("factTemp")]
        if not temps:
            return None
        return round(sum(temps) / len(temps), 1)

    @property
    def target_temperature(self) -> float | None:
        on = self._on_members
        if not on:
            # mostra alguma referência mesmo desligado
            temps = [m.get("setTemp") for m in self._members if m.get("setTemp") is not None]
        else:
            temps = [m.get("setTemp") for m in on if m.get("setTemp") is not None]
        if not temps:
            return None
        # se todos iguais → esse valor; senão → média arredondada
        if len(set(temps)) == 1:
            return float(temps[0])
        return float(round(sum(temps) / len(temps)))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "members": [m.get("id") for m in self._members],
            "members_on": [m.get("id") for m in self._on_members],
        }

    # ── comandos: aplicam em todos os membros ─────────────────────────────────

    async def _apply_to_all(self, changes: dict[str, Any]) -> None:
        members = self._members
        _LOGGER.info(
            "Grupo %s: aplicando %s em %d membros (%s)",
            self._area_name,
            changes,
            len(members),
            [m.get("id") for m in members],
        )
        for m in members:
            try:
                resp = await self._client.control_device(
                    device_id=m["id"], current=m, changes=changes
                )
                _LOGGER.info(
                    "Grupo %s: device %s resposta %s", self._area_name, m.get("id"), resp
                )
            except Exception as err:
                _LOGGER.exception(
                    "Grupo %s: falha no device %s: %s", self._area_name, m.get("id"), err
                )
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        _LOGGER.info("Grupo %s: set_hvac_mode(%s)", self._area_name, hvac_mode)
        if hvac_mode == HVACMode.OFF:
            await self._apply_to_all({"power": "n"})
            return
        # ligando: por membro, força wind=auto se atual era off
        acb_mode = HA_TO_ACB_MODE.get(hvac_mode.value, "cool")
        members = self._members
        for m in members:
            changes: dict[str, Any] = {"power": "y", "mode": acb_mode}
            if (m.get("wind") in (None, "", "off")):
                changes["wind"] = "auto"
            try:
                resp = await self._client.control_device(
                    device_id=m["id"], current=m, changes=changes
                )
                _LOGGER.info(
                    "Grupo %s: device %s (turn_on) resposta %s",
                    self._area_name, m.get("id"), resp,
                )
            except Exception as err:
                _LOGGER.exception(
                    "Grupo %s: falha turn_on no device %s: %s",
                    self._area_name, m.get("id"), err,
                )
        await self.coordinator.async_request_refresh()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        _LOGGER.info("Grupo %s: set_fan_mode(%s)", self._area_name, fan_mode)
        await self._apply_to_all({"wind": fan_mode})

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        _LOGGER.info("Grupo %s: set_temperature(%s)", self._area_name, temp)
        await self._apply_to_all({"setTemp": int(temp)})

    async def async_turn_on(self) -> None:
        _LOGGER.info("Grupo %s: turn_on", self._area_name)
        await self.async_set_hvac_mode(HVACMode.COOL)

    async def async_turn_off(self) -> None:
        _LOGGER.info("Grupo %s: turn_off", self._area_name)
        await self.async_set_hvac_mode(HVACMode.OFF)
