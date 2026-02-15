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
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DATA_CORE_REGISTERS,
    DATA_OPERATION_MODE,
    DATA_STATE,
    DATA_MODE,
    DOMAIN,
    MANUFACTURER,
)
from .coordinator import HaierDataCoordinator

_LOGGER = logging.getLogger(__name__)

# Operation Modes map to Modbus State strings (when ON)
OPERATION_MODES = {
    "Heat": "H",
    "Cool": "C",
    "Tank": "T",
    "Heat + Tank": "HT",
    "Cool + Tank": "CT",
}
# Reverse map for lookup
OPERATION_MODES_REV = {v: k for k, v in OPERATION_MODES.items()}

# Performance Modes map to Reg 201 values
PERFORMANCE_MODES = {
    "None": "none",
    "Eco": "eco",
    "Silent": "silent",
    "Turbo": "turbo",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Haier Heat Pump select entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: HaierDataCoordinator = data["coordinator"]
    client = data["client"]

    entities = [
        HaierOperationModeSelect(coordinator, client, entry),
        HaierPerformanceModeSelect(coordinator, client, entry),
    ]
    async_add_entities(entities)


class HaierOperationModeSelect(CoordinatorEntity, SelectEntity, RestoreEntity):
    """Select entity for Heat Pump Operation Mode (Heat, Cool, Tank, etc)."""

    _attr_has_entity_name = True
    _attr_name = "Operation Mode"
    _attr_icon = "mdi:hvac"
    _attr_options = list(OPERATION_MODES.keys())

    def __init__(
        self,
        coordinator: HaierDataCoordinator,
        client: Any,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._client = client
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_operation_mode"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Haier Heat Pump",
            manufacturer=MANUFACTURER,
            model="Heat Pump",
        )
        self._selected_mode = "Heat + Tank"  # Default

    async def async_added_to_hass(self) -> None:
        """Restore state on startup."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state in self.options:
            self._selected_mode = last_state.state
            _LOGGER.debug("Restored operation mode: %s", self._selected_mode)
        
        # Initialize global state
        self.hass.data[DOMAIN][self._entry.entry_id][DATA_OPERATION_MODE] = OPERATION_MODES[self._selected_mode]

    @property
    def current_option(self) -> str | None:
        """Return the selected entity option to represent the entity state."""
        # We try to reflect actual state if unit is ON
        if self.coordinator.data:
            state = self.coordinator.data.get(DATA_STATE, "")
            # If state corresponds to a known mode (e.g. "H", "HT"), update selection transparently
            # BUT only if it's not "on" or "off" generic
            if state in OPERATION_MODES_REV:
                # Update our internal tracking to match reality
                current_real = OPERATION_MODES_REV[state]
                if current_real != self._selected_mode:
                     self._selected_mode = current_real
                     # Update global
                     self.hass.data[DOMAIN][self._entry.entry_id][DATA_OPERATION_MODE] = state
        
        return self._selected_mode

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        self._selected_mode = option
        target_mode_str = OPERATION_MODES[option]
        
        # Update global state for climate entity to use
        self.hass.data[DOMAIN][self._entry.entry_id][DATA_OPERATION_MODE] = target_mode_str

        # If unit is currently ON, switch mode immediately
        if self.coordinator.data:
            state = str(self.coordinator.data.get(DATA_STATE, "")).lower()
            if "off" not in state:
                # Limit: "on" might mean unknown mode, or it might mean we are running.
                # If we are running, we want to switch mode.
                core = self.coordinator.data.get(DATA_CORE_REGISTERS)
                if core:
                    _LOGGER.info("Switching operation mode to %s (%s)", option, target_mode_str)
                    new_state = PyHaier.SetState(core, target_mode_str)
                    if isinstance(new_state, list):
                        if await self._client.async_write_core(new_state):
                            await self.coordinator.async_request_refresh()
        
        self.async_write_ha_state()


class HaierPerformanceModeSelect(CoordinatorEntity, SelectEntity):
    """Select entity for Heat Pump Performance Mode (Turbo, Eco, Silent)."""

    _attr_has_entity_name = True
    _attr_name = "Performance Mode"
    _attr_icon = "mdi:speedometer"
    _attr_options = ["None", "Eco", "Silent", "Turbo"]

    def __init__(
        self,
        coordinator: HaierDataCoordinator,
        client: Any,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_performance_mode"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Haier Heat Pump",
            manufacturer=MANUFACTURER,
            model="Heat Pump",
        )

    @property
    def current_option(self) -> str | None:
        """Return the selected entity option."""
        if self.coordinator.data:
            mode = self.coordinator.data.get(DATA_MODE, "").lower()
            for name, val in PERFORMANCE_MODES.items():
                if val == mode:
                    return name
            # Handle empty/unknown
            if not mode or mode == "none":
                return "None"
        return "None"

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        target = PERFORMANCE_MODES.get(option, "none")
        _LOGGER.info("Setting performance mode to %s (%s)", option, target)
        
        # PyHaier.SetMode returns a list of registers (just one mostly)
        # Verify call signature from haier_sonet.py: new_frame = PyHaier.SetMode(new_mode)
        # haier_sonet.py registers 201 write.
        
        # We need to know where to write. Register 201.
        # modbus_client.async_write_mode(new_frame) is needed?
        # Let's check modbus_client.py. It has async_write_mode?
        # If not, I should use generic write or check if client has it.
        # But wait, haier_sonet.py does: client.write_registers(address=201, ...)
        
        # I'll check modbus_client.py next.
        # For now, I'll assume client has async_write_mode method or I should add it.
        # Earlier I edited async_write_mode in modbus_client.py! So it exists.
        
        frame = PyHaier.SetMode(target)
        if isinstance(frame, list):
             await self._client.async_write_mode(frame)
             await self.coordinator.async_request_refresh()
