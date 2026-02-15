"""Switch platform for Haier Heat Pump."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DATA_CURVE_ENABLED,
    DOMAIN,
    MANUFACTURER,
)
from .coordinator import HaierDataCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Haier Heat Pump switch."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: HaierDataCoordinator = data["coordinator"]

    entities = [HaierHeatingCurveSwitch(coordinator, entry)]
    async_add_entities(entities)




class HaierHeatingCurveSwitch(CoordinatorEntity, SwitchEntity, RestoreEntity):
    """Switch to toggle Heating Curve vs Manual Mode."""

    _attr_has_entity_name = True
    _attr_name = "Enable Heating Curve"
    _attr_icon = "mdi:chart-bell-curve"

    def __init__(
        self,
        coordinator: HaierDataCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_heating_curve_switch"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Haier Heat Pump",
            manufacturer=MANUFACTURER,
            model="Heat Pump",
        )

    async def async_added_to_hass(self) -> None:
        """Restore state on startup."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state == "off":
            self.hass.data[DOMAIN][self._entry.entry_id][DATA_CURVE_ENABLED] = False
            _LOGGER.debug("Restored heating curve state: Disabled")
        else:
            self.hass.data[DOMAIN][self._entry.entry_id][DATA_CURVE_ENABLED] = True
            _LOGGER.debug("Restored heating curve state: Enabled")

    @property
    def is_on(self) -> bool:
        """Return True if heating curve is enabled."""
        return self.hass.data[DOMAIN][self._entry.entry_id].get(
            DATA_CURVE_ENABLED, True
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on heating curve."""
        self.hass.data[DOMAIN][self._entry.entry_id][DATA_CURVE_ENABLED] = True
        self.async_write_ha_state()
        # Trigger climate update so it recalculates target immediately
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off heating curve (Manual Mode)."""
        self.hass.data[DOMAIN][self._entry.entry_id][DATA_CURVE_ENABLED] = False
        self.async_write_ha_state()
        # Trigger climate update
        await self.coordinator.async_request_refresh()
