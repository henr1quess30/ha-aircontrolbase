"""Sensores de resumo do AirControlBase."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AirControlBaseCoordinator


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
    coordinator: AirControlBaseCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        AirControlBaseSummarySensor(coordinator, entry, desc) for desc in SUMMARY_SENSORS
    )


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
