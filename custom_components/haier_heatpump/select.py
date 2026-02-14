"""Select platform for Haier Heat Pump."""

from __future__ import annotations

import logging
from typing import Any

import PyHaier
from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DATA_MODE,
    DOMAIN,
    MANUFACTURER,
    REG_MODE_START,
)
from .coordinator import HaierDataCoordinator
from .modbus_client import HaierModbusClient

_LOGGER = logging.getLogger(__name__)

MODE_OPTIONS = ["eco", "quiet", "turbo"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Haier Heat Pump select entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: HaierDataCoordinator = data["coordinator"]
    client: HaierModbusClient = data["client"]

    async_add_entities([HaierModeSelect(coordinator, client, entry)])


class HaierModeSelect(CoordinatorEntity[HaierDataCoordinator], SelectEntity):
    """Select entity for heat pump mode (eco/quiet/turbo)."""

    _attr_has_entity_name = True
    _attr_name = "Mode"
    _attr_icon = "mdi:cog-outline"
    _attr_options = MODE_OPTIONS

    def __init__(
        self,
        coordinator: HaierDataCoordinator,
        client: HaierModbusClient,
        entry: ConfigEntry,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_mode_select"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Haier Heat Pump",
            manufacturer=MANUFACTURER,
            model="Heat Pump",
        )

    @property
    def current_option(self) -> str | None:
        """Return the current mode."""
        if self.coordinator.data is None:
            return None
        mode = self.coordinator.data.get(DATA_MODE)
        if mode is None:
            return None
        mode_str = str(mode).lower()
        # Map 'silent' to 'quiet' for compatibility
        if mode_str == "silent":
            mode_str = "quiet"
        if mode_str in MODE_OPTIONS:
            return mode_str
        return None

    async def async_select_option(self, option: str) -> None:
        """Set the mode."""
        if option not in MODE_OPTIONS:
            _LOGGER.error("Invalid mode: %s", option)
            return

        new_mode = PyHaier.SetMode(option)
        if isinstance(new_mode, list):
            if await self._client.async_write_mode(new_mode):
                _LOGGER.debug("Set mode to %s", option)
                await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to create SetMode frame: %s", new_mode)
