"""Number platform for Haier Heat Pump."""

from __future__ import annotations

import logging
from typing import Any

import PyHaier
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CH_TEMP_MAX,
    CH_TEMP_MIN,
    CH_TEMP_STEP,
    DATA_CORE_REGISTERS,
    DATA_DHW_TEMP,
    DHW_TEMP_MAX,
    DHW_TEMP_MIN,
    DHW_TEMP_STEP,
    DOMAIN,
    MANUFACTURER,
)
from .coordinator import HaierDataCoordinator
from .modbus_client import HaierModbusClient

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Haier Heat Pump number entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: HaierDataCoordinator = data["coordinator"]
    client: HaierModbusClient = data["client"]

    async_add_entities([
        HaierDHWTempNumber(coordinator, client, entry),
    ])


class HaierDHWTempNumber(
    CoordinatorEntity[HaierDataCoordinator], NumberEntity
):
    """Number entity for DHW target temperature."""

    _attr_has_entity_name = True
    _attr_name = "DHW Target Temperature"
    _attr_icon = "mdi:water-thermometer"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = DHW_TEMP_MIN
    _attr_native_max_value = DHW_TEMP_MAX
    _attr_native_step = DHW_TEMP_STEP
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self,
        coordinator: HaierDataCoordinator,
        client: HaierModbusClient,
        entry: ConfigEntry,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_dhw_temp"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Haier Heat Pump",
            manufacturer=MANUFACTURER,
            model="Heat Pump",
        )

    @property
    def native_value(self) -> float | None:
        """Return current DHW target temperature."""
        if self.coordinator.data is None:
            return None
        val = self.coordinator.data.get(DATA_DHW_TEMP)
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        """Set DHW target temperature."""
        # Clamp to safe range
        value = max(DHW_TEMP_MIN, min(DHW_TEMP_MAX, value))
        # Round to step
        value = round(value / DHW_TEMP_STEP) * DHW_TEMP_STEP

        # Read fresh core registers
        core = await self._client.async_read_core()
        if core is None:
            _LOGGER.error("Cannot read core registers for DHW temp change")
            return

        new_temp = PyHaier.SetDHWTemp(core, value)
        if isinstance(new_temp, list):
            if await self._client.async_write_core(new_temp):
                _LOGGER.debug("Set DHW temp to %.0f°C", value)
                await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to create SetDHWTemp frame: %s", new_temp)
