"""The Haier Heat Pump integration."""

from __future__ import annotations

import logging
from typing import Any

import PyHaier
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CH_TEMP_MAX,
    CH_TEMP_MIN,
    CONF_ANTIFREEZE_CRITICAL,
    CONF_ANTIFREEZE_EMERGENCY_TEMP,
    CONF_ANTIFREEZE_RECOVERY,
    CONF_ANTIFREEZE_WARNING,
    CONF_CURVE_BASE_TEMP,
    CONF_CURVE_OFFSET,
    CONF_CURVE_POINTS,
    CONF_CURVE_SETPOINT,
    CONF_CURVE_SLOPE,
    CONF_CURVE_TYPE,
    CONF_DEMAND_SWITCH,
    CONF_DEVICE_ID,
    CONF_EXTERNAL_TEMP_SENSOR,
    CONF_IP,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    DATA_ANTIFREEZE_ACTIVE,
    DATA_CH_TEMP,
    DATA_CORE_REGISTERS,
    DATA_CURVE_ENABLED,
    DATA_DHW_CURRENT,
    DATA_STATE,
    DATA_TWI,
    DATA_TWO,
    DEFAULT_ANTIFREEZE_CRITICAL_TEMP,
    DEFAULT_ANTIFREEZE_EMERGENCY_CH_TEMP,
    DEFAULT_ANTIFREEZE_RECOVERY_TEMP,
    DEFAULT_ANTIFREEZE_WARNING_TEMP,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
    REG_CORE_START,
)
from .coordinator import HaierDataCoordinator
from .heating_curve import calculate_target_temp, clamp_ch_temp
from .modbus_client import HaierModbusClient

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Haier Heat Pump from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    client = HaierModbusClient(
        hass=hass,
        host=entry.data[CONF_IP],
        port=entry.data[CONF_PORT],
        device_id=entry.data[CONF_DEVICE_ID],
    )

    if not await client.async_connect():
        _LOGGER.error("Failed to connect to Haier heat pump")
        return False

    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = HaierDataCoordinator(hass, client, scan_interval)

    # Do first refresh
    await coordinator.async_config_entry_first_refresh()

    # Create the antifreeze manager
    antifreeze_mgr = AntifreezeManager(hass, coordinator, client, entry)

    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
        "antifreeze": antifreeze_mgr,
        DATA_CURVE_ENABLED: True,
    }

    # Register listener for coordinator updates (antifreeze check)
    coordinator.async_add_listener(antifreeze_mgr.async_check)

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register options update listener
    entry.async_on_unload(entry.add_update_listener(_async_update_options))

    # Clean up on HA stop
    async def _async_shutdown(event: Event) -> None:
        await client.async_disconnect()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_shutdown)
    )

    return True


async def _async_update_options(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )

    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        client: HaierModbusClient = data["client"]
        await client.async_disconnect()

    return unload_ok


class AntifreezeManager:
    """Always-on antifreeze protection manager.

    Monitors water temperatures and activates pump as needed to prevent
    freezing. This is a safety feature that cannot be disabled.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: HaierDataCoordinator,
        client: HaierModbusClient,
        entry: ConfigEntry,
    ) -> None:
        """Initialize antifreeze manager."""
        self._hass = hass
        self._coordinator = coordinator
        self._client = client
        self._entry = entry
        self._active = False
        self._emergency = False
        self._saved_ch_temp: float | None = None
        self._saved_state: str | None = None

    @property
    def is_active(self) -> bool:
        """Return True if antifreeze protection is active."""
        return self._active

    @property
    def is_emergency(self) -> bool:
        """Return True if emergency mode (critical threshold reached)."""
        return self._emergency

    def _get_threshold(self, key: str, default: float) -> float:
        """Get configurable threshold from options or data."""
        value = self._entry.options.get(key, self._entry.data.get(key, default))
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @callback
    def async_check(self) -> None:
        """Check temperatures and manage antifreeze protection.

        Called after each coordinator update.
        """
        data = self._coordinator.data
        if not data:
            return

        warning_temp = self._get_threshold(
            CONF_ANTIFREEZE_WARNING, DEFAULT_ANTIFREEZE_WARNING_TEMP
        )
        critical_temp = self._get_threshold(
            CONF_ANTIFREEZE_CRITICAL, DEFAULT_ANTIFREEZE_CRITICAL_TEMP
        )
        emergency_ch = self._get_threshold(
            CONF_ANTIFREEZE_EMERGENCY_TEMP, DEFAULT_ANTIFREEZE_EMERGENCY_CH_TEMP
        )
        recovery_temp = self._get_threshold(
            CONF_ANTIFREEZE_RECOVERY, DEFAULT_ANTIFREEZE_RECOVERY_TEMP
        )

        # Collect water temperatures
        water_temps = []
        for key in (DATA_TWI, DATA_TWO, DATA_DHW_CURRENT):
            val = data.get(key)
            if val is not None and isinstance(val, (int, float)):
                water_temps.append(float(val))

        if not water_temps:
            _LOGGER.debug("No water temperatures available for antifreeze check")
            return

        min_temp = min(water_temps)

        if self._active:
            # Check for recovery
            if all(t > recovery_temp for t in water_temps):
                _LOGGER.info(
                    "Antifreeze recovery: all temps above %.1f°C, deactivating",
                    recovery_temp,
                )
                self._hass.async_create_task(self._async_deactivate())
            elif min_temp < critical_temp and not self._emergency:
                # Escalate to emergency
                _LOGGER.warning(
                    "Antifreeze EMERGENCY: temp %.1f°C below critical %.1f°C",
                    min_temp,
                    critical_temp,
                )
                self._emergency = True
                self._hass.async_create_task(
                    self._async_set_emergency_temp(emergency_ch)
                )
        else:
            # Check for activation
            if min_temp < critical_temp:
                _LOGGER.warning(
                    "Antifreeze EMERGENCY activation: temp %.1f°C below %.1f°C",
                    min_temp,
                    critical_temp,
                )
                self._emergency = True
                self._hass.async_create_task(
                    self._async_activate(emergency_ch)
                )
            elif min_temp < warning_temp:
                _LOGGER.warning(
                    "Antifreeze WARNING activation: temp %.1f°C below %.1f°C",
                    min_temp,
                    warning_temp,
                )
                self._hass.async_create_task(self._async_activate(None))

        # Update coordinator data
        data[DATA_ANTIFREEZE_ACTIVE] = self._active

    async def _async_activate(self, emergency_temp: float | None) -> None:
        """Activate antifreeze protection."""
        data = self._coordinator.data
        if not data:
            return

        # Save current state
        self._saved_ch_temp = data.get(DATA_CH_TEMP)
        self._saved_state = data.get(DATA_STATE)

        core = data.get(DATA_CORE_REGISTERS)
        if core is None:
            _LOGGER.error("Cannot activate antifreeze: core registers unavailable")
            return

        self._active = True

        # Turn on pump if off
        state = data.get(DATA_STATE, "")
        if state and "OFF" in str(state).upper():
            try:
                new_state = PyHaier.SetState(core, "HT")
                if isinstance(new_state, list):
                    await self._client.async_write_core(new_state)
                    _LOGGER.info("Antifreeze: turned on pump (HT mode)")
                    # Re-read core registers after write
                    new_core = await self._client.async_read_core()
                    if new_core:
                        core = new_core
                        data[DATA_CORE_REGISTERS] = core
            except Exception:
                _LOGGER.exception("Failed to turn on pump for antifreeze")

        # Set emergency temp if specified
        if emergency_temp is not None:
            await self._async_set_emergency_temp(emergency_temp)

    async def _async_set_emergency_temp(self, temp: float) -> None:
        """Set emergency CH temperature."""
        data = self._coordinator.data
        if not data:
            return

        core = data.get(DATA_CORE_REGISTERS)
        if core is None:
            return

        temp = clamp_ch_temp(temp)
        try:
            new_temp = PyHaier.SetCHTemp(core, temp)
            if isinstance(new_temp, list):
                await self._client.async_write_core(new_temp)
                _LOGGER.warning(
                    "Antifreeze: set emergency CH temp to %.1f°C", temp
                )
        except Exception:
            _LOGGER.exception("Failed to set emergency temperature")

    async def _async_deactivate(self) -> None:
        """Deactivate antifreeze protection."""
        data = self._coordinator.data
        if not data:
            return

        core = data.get(DATA_CORE_REGISTERS)
        if core is None:
            _LOGGER.error("Cannot deactivate antifreeze: core registers unavailable")
            self._active = False
            self._emergency = False
            return

        # Restore original temperature if we changed it
        if self._saved_ch_temp is not None and self._emergency:
            restored_temp = clamp_ch_temp(self._saved_ch_temp)
            try:
                # Re-read core first
                fresh_core = await self._client.async_read_core()
                if fresh_core:
                    core = fresh_core
                    data[DATA_CORE_REGISTERS] = core

                new_temp = PyHaier.SetCHTemp(core, restored_temp)
                if isinstance(new_temp, list):
                    await self._client.async_write_core(new_temp)
                    _LOGGER.info(
                        "Antifreeze: restored CH temp to %.1f°C",
                        restored_temp,
                    )
                    # Re-read after write
                    fresh_core = await self._client.async_read_core()
                    if fresh_core:
                        core = fresh_core
                        data[DATA_CORE_REGISTERS] = core
            except Exception:
                _LOGGER.exception("Failed to restore temperature after antifreeze")

        # Check if demand switch is off => turn off pump
        demand_switch = self._entry.options.get(
            CONF_DEMAND_SWITCH, self._entry.data.get(CONF_DEMAND_SWITCH)
        )
        should_turn_off = True
        if demand_switch:
            state = self._hass.states.get(demand_switch)
            if state and state.state == "on":
                should_turn_off = False

        if should_turn_off:
            try:
                fresh_core = await self._client.async_read_core()
                if fresh_core:
                    core = fresh_core
                new_state = PyHaier.SetState(core, "off")
                if isinstance(new_state, list):
                    await self._client.async_write_core(new_state)
                    _LOGGER.info("Antifreeze: turned off pump (no demand)")
            except Exception:
                _LOGGER.exception("Failed to turn off pump after antifreeze recovery")

        self._active = False
        self._emergency = False
        self._saved_ch_temp = None
        self._saved_state = None
        data[DATA_ANTIFREEZE_ACTIVE] = False
