"""Switches de lock por AC.

O AirControlBase usa um CSV no campo `unlock` para indicar o que está
DESBLOQUEADO. Os tokens padrão são: mode, cool, heat, wind, remote.
- Token presente em `unlock` -> desbloqueado.
- Token ausente em `unlock` -> bloqueado.

Cada switch aqui mapeia um token. ON = bloqueado, OFF = desbloqueado.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import AirControlBaseClient
from .const import DOMAIN
from .coordinator import AirControlBaseCoordinator

LOCK_TOKENS = ["mode", "cool", "heat", "wind", "remote"]
ALL_UNLOCKED = ",".join(LOCK_TOKENS)


@dataclass(frozen=True, kw_only=True)
class LockSwitchDescription(SwitchEntityDescription):
    token: str


SWITCH_DESCRIPTIONS: tuple[LockSwitchDescription, ...] = (
    LockSwitchDescription(
        key="lock_remote",
        token="remote",
        translation_key="lock_remote",
        icon="mdi:remote-tv",
        entity_category=EntityCategory.CONFIG,
    ),
    LockSwitchDescription(
        key="lock_mode",
        token="mode",
        translation_key="lock_mode",
        icon="mdi:hvac-off",
        entity_category=EntityCategory.CONFIG,
    ),
    LockSwitchDescription(
        key="lock_cool",
        token="cool",
        translation_key="lock_cool",
        icon="mdi:snowflake-off",
        entity_category=EntityCategory.CONFIG,
    ),
    LockSwitchDescription(
        key="lock_heat",
        token="heat",
        translation_key="lock_heat",
        icon="mdi:fire-off",
        entity_category=EntityCategory.CONFIG,
    ),
    LockSwitchDescription(
        key="lock_wind",
        token="wind",
        translation_key="lock_wind",
        icon="mdi:fan-off",
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    bucket = hass.data[DOMAIN][entry.entry_id]
    coordinator: AirControlBaseCoordinator = bucket["coordinator"]
    client: AirControlBaseClient = bucket["client"]

    known: set[tuple[str, str]] = set()

    @callback
    def _discover() -> None:
        new: list[ACBLockSwitch] = []
        for dev_id in coordinator.data.get("devices", {}):
            for desc in SWITCH_DESCRIPTIONS:
                key = (dev_id, desc.key)
                if key in known:
                    continue
                known.add(key)
                new.append(ACBLockSwitch(coordinator, client, dev_id, desc))
        if new:
            async_add_entities(new)

    _discover()
    entry.async_on_unload(coordinator.async_add_listener(_discover))


def _parse_unlock(value: str) -> set[str]:
    return {t.strip() for t in (value or "").split(",") if t.strip()}


def _serialize_unlock(tokens: set[str]) -> str:
    return ",".join(t for t in LOCK_TOKENS if t in tokens)


class ACBLockSwitch(CoordinatorEntity[AirControlBaseCoordinator], SwitchEntity):
    """Switch que controla um token do CSV `unlock` de um device."""

    _attr_has_entity_name = True
    entity_description: LockSwitchDescription

    def __init__(
        self,
        coordinator: AirControlBaseCoordinator,
        client: AirControlBaseClient,
        device_id: str,
        description: LockSwitchDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._client = client
        self._device_id = device_id
        self._attr_unique_id = f"{DOMAIN}_{device_id}_{description.key}"

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

    @property
    def is_on(self) -> bool:
        """ON = bloqueado (token ausente do unlock)."""
        d = self._device or {}
        unlocked = _parse_unlock(d.get("unlock") or ALL_UNLOCKED)
        return self.entity_description.token not in unlocked

    async def _set_locked(self, locked: bool) -> None:
        d = self._device or {}
        unlocked = _parse_unlock(d.get("unlock") or ALL_UNLOCKED)
        token = self.entity_description.token
        if locked:
            unlocked.discard(token)
        else:
            unlocked.add(token)
        new_unlock = _serialize_unlock(unlocked)
        await self._client.control_device(
            device_id=self._device_id,
            current=d,
            changes={"unlock": new_unlock},
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set_locked(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set_locked(False)
