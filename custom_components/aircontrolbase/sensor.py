"""Sensores do AirControlBase — resumo + histórico."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AirControlBaseCoordinator
from .log_coordinator import AirControlBaseLogCoordinator


@dataclass(frozen=True, kw_only=True)
class ACBSummarySensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]


SUMMARY_SENSORS: tuple[ACBSummarySensorDescription, ...] = (
    ACBSummarySensorDescription(
        key="cool",
        translation_key="acs_cool",
        icon="mdi:snowflake",
        value_fn=lambda s: s["summary"]["cool"],
    ),
    ACBSummarySensorDescription(
        key="heat",
        translation_key="acs_heat",
        icon="mdi:fire",
        value_fn=lambda s: s["summary"]["heat"],
    ),
    ACBSummarySensorDescription(
        key="fan",
        translation_key="acs_fan",
        icon="mdi:fan",
        value_fn=lambda s: s["summary"]["fan"],
    ),
    ACBSummarySensorDescription(
        key="stop",
        translation_key="acs_stop",
        icon="mdi:power-off",
        value_fn=lambda s: s["summary"]["stop"],
    ),
    ACBSummarySensorDescription(
        key="lock",
        translation_key="acs_lock",
        icon="mdi:lock",
        value_fn=lambda s: s["summary"]["lock"],
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ACBSummarySensorDescription(
        key="error",
        translation_key="acs_error",
        icon="mdi:alert",
        value_fn=lambda s: s["summary"]["error"],
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ACBSummarySensorDescription(
        key="total",
        translation_key="acs_total",
        icon="mdi:air-conditioner",
        value_fn=lambda s: len(s.get("devices", {})),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    bucket = hass.data[DOMAIN][entry.entry_id]
    coordinator: AirControlBaseCoordinator = bucket["coordinator"]
    log_coordinator: AirControlBaseLogCoordinator = bucket["log_coordinator"]

    entities: list[SensorEntity] = [
        AirControlBaseSummarySensor(coordinator, entry, desc) for desc in SUMMARY_SENSORS
    ]
    entities.append(AirControlBaseRecentErrorsSensor(log_coordinator, entry))
    entities.append(AirControlBaseRecentOpsSensor(log_coordinator, entry))
    async_add_entities(entities)

    known: set[str] = set()

    @callback
    def _discover() -> None:
        new: list[SensorEntity] = []
        for dev_id in coordinator.data.get("devices", {}):
            if dev_id in known:
                continue
            known.add(dev_id)
            new.append(AirControlBaseLastEventSensor(coordinator, log_coordinator, dev_id))
        if new:
            async_add_entities(new)

    _discover()
    entry.async_on_unload(coordinator.async_add_listener(_discover))


class AirControlBaseSummarySensor(
    CoordinatorEntity[AirControlBaseCoordinator], SensorEntity
):
    """Sensor de resumo (contagem do deviceCase)."""

    _attr_has_entity_name = True
    entity_description: ACBSummarySensorDescription

    def __init__(
        self,
        coordinator: AirControlBaseCoordinator,
        entry: ConfigEntry,
        description: ACBSummarySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_summary_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_hub")},
            name="AirControlBase",
            manufacturer="AirControlBase",
            model="CCM21 Gateway",
        )

    @property
    def native_value(self) -> Any:
        try:
            return self.entity_description.value_fn(self.coordinator.data or {})
        except (KeyError, TypeError):
            return None


class _HubLogSensor(CoordinatorEntity[AirControlBaseLogCoordinator], SensorEntity):
    """Base para sensores do hub que vêm do log_coordinator."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        log_coordinator: AirControlBaseLogCoordinator,
        entry: ConfigEntry,
        key: str,
    ) -> None:
        super().__init__(log_coordinator)
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_log_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_hub")},
            name="AirControlBase",
            manufacturer="AirControlBase",
            model="CCM21 Gateway",
        )


class AirControlBaseRecentErrorsSensor(_HubLogSensor):
    _attr_translation_key = "recent_errors"
    _attr_icon = "mdi:alert-circle"

    def __init__(self, log_coordinator: AirControlBaseLogCoordinator, entry: ConfigEntry) -> None:
        super().__init__(log_coordinator, entry, "errors")

    @property
    def native_value(self) -> int | None:
        data = self.coordinator.data or {}
        return data.get("errors_count")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        return {"errors": (data.get("errors") or [])[:10]}


class AirControlBaseRecentOpsSensor(_HubLogSensor):
    _attr_translation_key = "recent_ops"
    _attr_icon = "mdi:history"

    def __init__(self, log_coordinator: AirControlBaseLogCoordinator, entry: ConfigEntry) -> None:
        super().__init__(log_coordinator, entry, "ops")

    @property
    def native_value(self) -> int | None:
        data = self.coordinator.data or {}
        return data.get("ops_count")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        return {"events": (data.get("ops") or [])[:10]}


class AirControlBaseLastEventSensor(
    CoordinatorEntity[AirControlBaseCoordinator], SensorEntity
):
    """Último evento de um AC, vindo do deviceLog."""

    _attr_has_entity_name = True
    _attr_translation_key = "last_event"
    _attr_icon = "mdi:history"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: AirControlBaseCoordinator,
        log_coordinator: AirControlBaseLogCoordinator,
        device_id: str,
    ) -> None:
        # Liga no coordinator principal pra acompanhar nome/área do device,
        # e escuta o log_coordinator manualmente.
        super().__init__(coordinator)
        self._log_coordinator = log_coordinator
        self._device_id = device_id
        self._attr_unique_id = f"{DOMAIN}_{device_id}_last_event"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._log_coordinator.async_add_listener(self.async_write_ha_state))

    @property
    def _device(self) -> dict[str, Any] | None:
        return (self.coordinator.data or {}).get("devices", {}).get(self._device_id)

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
    def available(self) -> bool:
        return self._device is not None

    @property
    def _last(self) -> dict[str, Any] | None:
        data = self._log_coordinator.data or {}
        return (data.get("last_by_device") or {}).get(self._device_id)

    @property
    def native_value(self) -> str | None:
        last = self._last
        if not last:
            return None
        return (last.get("summary") or "")[:255] or None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        last = self._last or {}
        return {
            "timestamp": last.get("timestamp"),
            "raw": last.get("raw"),
        }
