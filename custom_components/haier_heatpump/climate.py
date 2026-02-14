"""Climate platform for Haier Heat Pump."""

from __future__ import annotations

import logging
from typing import Any

import PyHaier
from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CH_TEMP_MAX,
    CH_TEMP_MIN,
    CH_TEMP_STEP,
    CONF_CURVE_BASE_TEMP,
    CONF_CURVE_OFFSET,
    CONF_CURVE_POINTS,
    CONF_CURVE_SETPOINT,
    CONF_CURVE_SLOPE,
    CONF_CURVE_TYPE,
    CONF_DEMAND_SWITCH,
    CONF_EXTERNAL_TEMP_SENSOR,
    DATA_ANTIFREEZE_ACTIVE,
    DATA_CH_TEMP,
    DATA_CORE_REGISTERS,
    DATA_STATE,
    DATA_TWI,
    DATA_TWO,
    DEFAULT_CURVE_BASE_TEMP,
    DEFAULT_CURVE_OFFSET,
    DEFAULT_CURVE_SETPOINT,
    DEFAULT_CURVE_SLOPE,
    DEFAULT_CURVE_TYPE,
    DOMAIN,
    MANUFACTURER,
)
from .coordinator import HaierDataCoordinator
from .heating_curve import calculate_target_temp, clamp_ch_temp
from .modbus_client import HaierModbusClient

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Haier Heat Pump climate entity."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: HaierDataCoordinator = data["coordinator"]
    client: HaierModbusClient = data["client"]

    async_add_entities([HaierClimate(coordinator, client, entry)])


class HaierClimate(CoordinatorEntity[HaierDataCoordinator], ClimateEntity):
    """Climate entity for Haier Heat Pump with heating curve control."""

    _attr_has_entity_name = True
    _attr_name = "Heat Pump"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_min_temp = CH_TEMP_MIN
    _attr_max_temp = CH_TEMP_MAX
    _attr_target_temperature_step = CH_TEMP_STEP
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(
        self,
        coordinator: HaierDataCoordinator,
        client: HaierModbusClient,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self._client = client
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_climate"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Haier Heat Pump",
            manufacturer=MANUFACTURER,
            model="Heat Pump",
        )
        self._curve_target: float | None = None
        self._last_sent_temp: float | None = None
        self._unsub_demand: Any = None
        self._unsub_outdoor: Any = None

    async def async_added_to_hass(self) -> None:
        """Set up listeners when added to HA."""
        await super().async_added_to_hass()

        # Listen to demand switch changes
        config = {**self._entry.data, **self._entry.options}
        demand_entity = config.get(CONF_DEMAND_SWITCH)
        if demand_entity:
            self._unsub_demand = async_track_state_change_event(
                self.hass, [demand_entity], self._handle_demand_change
            )

        # Listen to outdoor temp sensor changes
        outdoor_entity = config.get(CONF_EXTERNAL_TEMP_SENSOR)
        if outdoor_entity:
            self._unsub_outdoor = async_track_state_change_event(
                self.hass, [outdoor_entity], self._handle_outdoor_temp_change
            )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up listeners."""
        if self._unsub_demand:
            self._unsub_demand()
        if self._unsub_outdoor:
            self._unsub_outdoor()

    @callback
    def _handle_demand_change(self, event: Any) -> None:
        """Handle demand switch state change."""
        self.hass.async_create_task(self._async_update_pump_state())

    @callback
    def _handle_outdoor_temp_change(self, event: Any) -> None:
        """Handle outdoor temperature change."""
        self.hass.async_create_task(self._async_update_curve_target())

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current HVAC mode."""
        if self.coordinator.data is None:
            return HVACMode.OFF

        state = self.coordinator.data.get(DATA_STATE, "")
        if state and "OFF" not in str(state).upper():
            return HVACMode.HEAT
        return HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction:
        """Return current HVAC action."""
        if self.coordinator.data is None:
            return HVACAction.OFF

        state = str(self.coordinator.data.get(DATA_STATE, ""))
        if "OFF" in state.upper():
            return HVACAction.OFF

        # Check if antifreeze is active
        if self.coordinator.data.get(DATA_ANTIFREEZE_ACTIVE, False):
            return HVACAction.HEATING

        # Check if demand is on
        if self._is_demand_on():
            return HVACAction.HEATING

        return HVACAction.IDLE

    @property
    def current_temperature(self) -> float | None:
        """Return current water temperature (average of Twi/Two)."""
        if self.coordinator.data is None:
            return None

        twi = self.coordinator.data.get(DATA_TWI)
        two = self.coordinator.data.get(DATA_TWO)

        if twi is not None and two is not None:
            try:
                return round((float(twi) + float(two)) / 2, 1)
            except (TypeError, ValueError):
                pass

        if twi is not None:
            try:
                return float(twi)
            except (TypeError, ValueError):
                pass

        return None

    @property
    def target_temperature(self) -> float | None:
        """Return target temperature (from curve or direct setting)."""
        if self._curve_target is not None:
            return self._curve_target

        if self.coordinator.data is not None:
            ch_temp = self.coordinator.data.get(DATA_CH_TEMP)
            if ch_temp is not None:
                try:
                    return float(ch_temp)
                except (TypeError, ValueError):
                    pass
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs: dict[str, Any] = {}
        if self._curve_target is not None:
            attrs["curve_target"] = self._curve_target

        config = {**self._entry.data, **self._entry.options}
        outdoor_temp = self._get_outdoor_temp()
        if outdoor_temp is not None:
            attrs["outdoor_temperature"] = outdoor_temp

        attrs["demand_active"] = self._is_demand_on()
        attrs["antifreeze_active"] = (
            self.coordinator.data.get(DATA_ANTIFREEZE_ACTIVE, False)
            if self.coordinator.data
            else False
        )

        return attrs

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode."""
        # Don't allow turning off if antifreeze is active
        if hvac_mode == HVACMode.OFF:
            if (
                self.coordinator.data
                and self.coordinator.data.get(DATA_ANTIFREEZE_ACTIVE)
            ):
                _LOGGER.warning(
                    "Cannot turn off: antifreeze protection is active"
                )
                return

        core = await self._get_fresh_core()
        if core is None:
            return

        if hvac_mode == HVACMode.HEAT:
            new_state = PyHaier.SetState(core, "HT")
        elif hvac_mode == HVACMode.OFF:
            new_state = PyHaier.SetState(core, "off")
        else:
            _LOGGER.warning("Unsupported HVAC mode: %s", hvac_mode)
            return

        if isinstance(new_state, list):
            if await self._client.async_write_core(new_state):
                await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target temperature."""
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return

        temp = clamp_ch_temp(float(temp))
        await self._async_send_ch_temp(temp)

    async def _async_send_ch_temp(self, temp: float) -> None:
        """Send CH temperature to the pump."""
        # Avoid sending same temp repeatedly
        if self._last_sent_temp is not None and abs(temp - self._last_sent_temp) < CH_TEMP_STEP:
            return

        core = await self._get_fresh_core()
        if core is None:
            return

        new_temp = PyHaier.SetCHTemp(core, temp)
        if isinstance(new_temp, list):
            if await self._client.async_write_core(new_temp):
                self._last_sent_temp = temp
                _LOGGER.debug("Set CH temp to %.1f°C", temp)
                await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to create SetCHTemp frame: %s", new_temp)

    async def _async_update_curve_target(self) -> None:
        """Recalculate target from heating curve."""
        outdoor_temp = self._get_outdoor_temp()
        if outdoor_temp is None:
            return

        config = {**self._entry.data, **self._entry.options}
        curve_type = config.get(CONF_CURVE_TYPE, DEFAULT_CURVE_TYPE)
        curve_params = {
            "slope": config.get(CONF_CURVE_SLOPE, DEFAULT_CURVE_SLOPE),
            "base_temp": config.get(CONF_CURVE_BASE_TEMP, DEFAULT_CURVE_BASE_TEMP),
            "offset": config.get(CONF_CURVE_OFFSET, DEFAULT_CURVE_OFFSET),
            "setpoint": config.get(CONF_CURVE_SETPOINT, DEFAULT_CURVE_SETPOINT),
        }
        if CONF_CURVE_POINTS in config:
            curve_params["points"] = config[CONF_CURVE_POINTS]

        new_target = calculate_target_temp(outdoor_temp, curve_type, curve_params)
        self._curve_target = new_target

        # Only send if demand is on and antifreeze isn't overriding
        if self._is_demand_on() and not (
            self.coordinator.data
            and self.coordinator.data.get(DATA_ANTIFREEZE_ACTIVE)
        ):
            await self._async_send_ch_temp(new_target)

        self.async_write_ha_state()

    async def _async_update_pump_state(self) -> None:
        """Update pump state based on demand switch."""
        # Don't touch pump if antifreeze is active
        if (
            self.coordinator.data
            and self.coordinator.data.get(DATA_ANTIFREEZE_ACTIVE)
        ):
            return

        if self._is_demand_on():
            # Turn on and apply curve target
            core = await self._get_fresh_core()
            if core is None:
                return

            state = self.coordinator.data.get(DATA_STATE, "") if self.coordinator.data else ""
            if "OFF" in str(state).upper():
                new_state = PyHaier.SetState(core, "HT")
                if isinstance(new_state, list):
                    await self._client.async_write_core(new_state)

            await self._async_update_curve_target()
        else:
            # Turn off
            core = await self._get_fresh_core()
            if core is None:
                return
            new_state = PyHaier.SetState(core, "off")
            if isinstance(new_state, list):
                await self._client.async_write_core(new_state)

        await self.coordinator.async_request_refresh()

    def _is_demand_on(self) -> bool:
        """Check if demand switch is on."""
        config = {**self._entry.data, **self._entry.options}
        demand_entity = config.get(CONF_DEMAND_SWITCH)
        if not demand_entity:
            return True  # No demand switch = always on

        state = self.hass.states.get(demand_entity)
        return state is not None and state.state == "on"

    def _get_outdoor_temp(self) -> float | None:
        """Get outdoor temperature from configured sensor."""
        config = {**self._entry.data, **self._entry.options}
        sensor_entity = config.get(CONF_EXTERNAL_TEMP_SENSOR)
        if not sensor_entity:
            return None

        state = self.hass.states.get(sensor_entity)
        if state is None or state.state in ("unknown", "unavailable"):
            return None

        try:
            return float(state.state)
        except (TypeError, ValueError):
            return None

    async def _get_fresh_core(self) -> list[int] | None:
        """Read fresh core registers for write operations."""
        core = await self._client.async_read_core()
        if core is None:
            _LOGGER.error("Cannot read core registers for write operation")
        return core
