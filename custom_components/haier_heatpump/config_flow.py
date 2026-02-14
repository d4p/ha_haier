"""Config flow for Haier Heat Pump integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
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
    CURVE_BASE_TEMP_MAX,
    CURVE_BASE_TEMP_MIN,
    CURVE_OFFSET_MAX,
    CURVE_OFFSET_MIN,
    CURVE_SETPOINT_MAX,
    CURVE_SETPOINT_MIN,
    CURVE_SLOPE_MAX,
    CURVE_SLOPE_MIN,
    CURVE_TYPE_FORMULA,
    CURVE_TYPE_POINTS,
    DEFAULT_ANTIFREEZE_CRITICAL_TEMP,
    DEFAULT_ANTIFREEZE_EMERGENCY_CH_TEMP,
    DEFAULT_ANTIFREEZE_RECOVERY_TEMP,
    DEFAULT_ANTIFREEZE_WARNING_TEMP,
    DEFAULT_CURVE_BASE_TEMP,
    DEFAULT_CURVE_OFFSET,
    DEFAULT_CURVE_SETPOINT,
    DEFAULT_CURVE_SLOPE,
    DEFAULT_CURVE_TYPE,
    DEFAULT_DEVICE_ID,
    DEFAULT_IP,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .heating_curve import (
    format_curve_points_string,
    generate_curve_svg,
    parse_curve_points_string,
    DEFAULT_CURVE_POINTS,
)
from .modbus_client import HaierModbusClient

_LOGGER = logging.getLogger(__name__)


class HaierHeatPumpConfigFlow(
    config_entries.ConfigFlow, domain=DOMAIN
):
    """Handle a config flow for Haier Heat Pump."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the connection step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Test connection
            client = HaierModbusClient(
                hass=self.hass,
                host=user_input[CONF_IP],
                port=user_input[CONF_PORT],
                device_id=user_input[CONF_DEVICE_ID],
            )

            if await client.async_connect():
                # Try reading core registers to verify
                core = await client.async_read_core()
                await client.async_disconnect()

                if core is not None:
                    self._data.update(user_input)
                    return await self.async_step_heating_curve()
                else:
                    errors["base"] = "cannot_read"
            else:
                errors["base"] = "cannot_connect"

        data_schema = vol.Schema(
            {
                vol.Required(CONF_IP, default=DEFAULT_IP): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Required(CONF_DEVICE_ID, default=DEFAULT_DEVICE_ID): int,
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): vol.All(int, vol.Range(min=10, max=300)),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_heating_curve(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the heating curve configuration step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            curve_type = user_input.get(CONF_CURVE_TYPE, DEFAULT_CURVE_TYPE)

            # Validate point-based curve
            if curve_type == CURVE_TYPE_POINTS:
                points_str = user_input.get(CONF_CURVE_POINTS, "")
                try:
                    points = parse_curve_points_string(points_str)
                    user_input[CONF_CURVE_POINTS] = str(points)
                except ValueError as exc:
                    errors[CONF_CURVE_POINTS] = "invalid_curve_points"
                    _LOGGER.debug("Invalid curve points: %s", exc)

            if not errors:
                self._data.update(user_input)
                return await self.async_step_antifreeze()

        # Generate SVG preview with defaults
        curve_params = {
            "slope": DEFAULT_CURVE_SLOPE,
            "base_temp": DEFAULT_CURVE_BASE_TEMP,
            "offset": DEFAULT_CURVE_OFFSET,
            "setpoint": DEFAULT_CURVE_SETPOINT,
        }
        svg = generate_curve_svg(DEFAULT_CURVE_TYPE, curve_params)

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_EXTERNAL_TEMP_SENSOR
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor",
                        device_class="temperature",
                    )
                ),
                vol.Required(
                    CONF_DEMAND_SWITCH
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["switch", "input_boolean"]),
                ),
                vol.Required(
                    CONF_CURVE_TYPE, default=DEFAULT_CURVE_TYPE
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=CURVE_TYPE_FORMULA, label="Formula-based"
                            ),
                            selector.SelectOptionDict(
                                value=CURVE_TYPE_POINTS, label="Point-based"
                            ),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_CURVE_SLOPE, default=DEFAULT_CURVE_SLOPE
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=CURVE_SLOPE_MIN,
                        max=CURVE_SLOPE_MAX,
                        step=0.1,
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Optional(
                    CONF_CURVE_BASE_TEMP, default=DEFAULT_CURVE_BASE_TEMP
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=CURVE_BASE_TEMP_MIN,
                        max=CURVE_BASE_TEMP_MAX,
                        step=0.5,
                        unit_of_measurement="°C",
                    )
                ),
                vol.Optional(
                    CONF_CURVE_OFFSET, default=DEFAULT_CURVE_OFFSET
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=CURVE_OFFSET_MIN,
                        max=CURVE_OFFSET_MAX,
                        step=0.5,
                        unit_of_measurement="°C",
                    )
                ),
                vol.Optional(
                    CONF_CURVE_SETPOINT, default=DEFAULT_CURVE_SETPOINT
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=CURVE_SETPOINT_MIN,
                        max=CURVE_SETPOINT_MAX,
                        step=0.5,
                        unit_of_measurement="°C",
                    )
                ),
                vol.Optional(
                    CONF_CURVE_POINTS,
                    default=format_curve_points_string(DEFAULT_CURVE_POINTS),
                ): str,
            }
        )

        return self.async_show_form(
            step_id="heating_curve",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"curve_svg": svg},
        )

    async def async_step_antifreeze(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle antifreeze protection configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate: warning > critical
            warning = user_input.get(
                CONF_ANTIFREEZE_WARNING, DEFAULT_ANTIFREEZE_WARNING_TEMP
            )
            critical = user_input.get(
                CONF_ANTIFREEZE_CRITICAL, DEFAULT_ANTIFREEZE_CRITICAL_TEMP
            )
            recovery = user_input.get(
                CONF_ANTIFREEZE_RECOVERY, DEFAULT_ANTIFREEZE_RECOVERY_TEMP
            )

            if critical >= warning:
                errors[CONF_ANTIFREEZE_CRITICAL] = "critical_above_warning"
            elif recovery <= warning:
                errors[CONF_ANTIFREEZE_RECOVERY] = "recovery_below_warning"
            else:
                self._data.update(user_input)
                return self.async_create_entry(
                    title="Haier Heat Pump",
                    data=self._data,
                )

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_ANTIFREEZE_WARNING,
                    default=DEFAULT_ANTIFREEZE_WARNING_TEMP,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=15,
                        step=0.5,
                        unit_of_measurement="°C",
                    )
                ),
                vol.Required(
                    CONF_ANTIFREEZE_CRITICAL,
                    default=DEFAULT_ANTIFREEZE_CRITICAL_TEMP,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=-5,
                        max=10,
                        step=0.5,
                        unit_of_measurement="°C",
                    )
                ),
                vol.Required(
                    CONF_ANTIFREEZE_EMERGENCY_TEMP,
                    default=DEFAULT_ANTIFREEZE_EMERGENCY_CH_TEMP,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=25,
                        max=45,
                        step=0.5,
                        unit_of_measurement="°C",
                    )
                ),
                vol.Required(
                    CONF_ANTIFREEZE_RECOVERY,
                    default=DEFAULT_ANTIFREEZE_RECOVERY_TEMP,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=10,
                        max=30,
                        step=0.5,
                        unit_of_measurement="°C",
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="antifreeze",
            data_schema=data_schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> HaierOptionsFlow:
        """Get the options flow handler."""
        return HaierOptionsFlow(config_entry)


class HaierOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Haier Heat Pump."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options — heating curve parameters."""
        errors: dict[str, str] = {}
        current = {**self._config_entry.data, **self._config_entry.options}

        if user_input is not None:
            curve_type = user_input.get(
                CONF_CURVE_TYPE, current.get(CONF_CURVE_TYPE, DEFAULT_CURVE_TYPE)
            )

            if curve_type == CURVE_TYPE_POINTS:
                points_str = user_input.get(CONF_CURVE_POINTS, "")
                try:
                    parse_curve_points_string(points_str)
                except ValueError:
                    errors[CONF_CURVE_POINTS] = "invalid_curve_points"

            if not errors:
                return self.async_create_entry(title="", data=user_input)

        # Generate SVG with current params
        curve_type = current.get(CONF_CURVE_TYPE, DEFAULT_CURVE_TYPE)
        curve_params = self._get_curve_params(current)
        svg = generate_curve_svg(curve_type, curve_params)

        cur_points = current.get(CONF_CURVE_POINTS, "")
        if isinstance(cur_points, dict):
            cur_points = format_curve_points_string(cur_points)
        elif not cur_points:
            cur_points = format_curve_points_string(DEFAULT_CURVE_POINTS)

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_EXTERNAL_TEMP_SENSOR,
                    default=current.get(CONF_EXTERNAL_TEMP_SENSOR, ""),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor",
                        device_class="temperature",
                    )
                ),
                vol.Required(
                    CONF_DEMAND_SWITCH,
                    default=current.get(CONF_DEMAND_SWITCH, ""),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["switch", "input_boolean"]),
                ),
                vol.Required(
                    CONF_CURVE_TYPE,
                    default=curve_type,
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=CURVE_TYPE_FORMULA, label="Formula-based"
                            ),
                            selector.SelectOptionDict(
                                value=CURVE_TYPE_POINTS, label="Point-based"
                            ),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_CURVE_SLOPE,
                    default=current.get(CONF_CURVE_SLOPE, DEFAULT_CURVE_SLOPE),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=CURVE_SLOPE_MIN,
                        max=CURVE_SLOPE_MAX,
                        step=0.1,
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Optional(
                    CONF_CURVE_BASE_TEMP,
                    default=current.get(CONF_CURVE_BASE_TEMP, DEFAULT_CURVE_BASE_TEMP),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=CURVE_BASE_TEMP_MIN,
                        max=CURVE_BASE_TEMP_MAX,
                        step=0.5,
                        unit_of_measurement="°C",
                    )
                ),
                vol.Optional(
                    CONF_CURVE_OFFSET,
                    default=current.get(CONF_CURVE_OFFSET, DEFAULT_CURVE_OFFSET),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=CURVE_OFFSET_MIN,
                        max=CURVE_OFFSET_MAX,
                        step=0.5,
                        unit_of_measurement="°C",
                    )
                ),
                vol.Optional(
                    CONF_CURVE_SETPOINT,
                    default=current.get(CONF_CURVE_SETPOINT, DEFAULT_CURVE_SETPOINT),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=CURVE_SETPOINT_MIN,
                        max=CURVE_SETPOINT_MAX,
                        step=0.5,
                        unit_of_measurement="°C",
                    )
                ),
                vol.Optional(
                    CONF_CURVE_POINTS,
                    default=cur_points,
                ): str,
                vol.Required(
                    CONF_ANTIFREEZE_WARNING,
                    default=current.get(
                        CONF_ANTIFREEZE_WARNING, DEFAULT_ANTIFREEZE_WARNING_TEMP
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=15,
                        step=0.5,
                        unit_of_measurement="°C",
                    )
                ),
                vol.Required(
                    CONF_ANTIFREEZE_CRITICAL,
                    default=current.get(
                        CONF_ANTIFREEZE_CRITICAL, DEFAULT_ANTIFREEZE_CRITICAL_TEMP
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=-5,
                        max=10,
                        step=0.5,
                        unit_of_measurement="°C",
                    )
                ),
                vol.Required(
                    CONF_ANTIFREEZE_EMERGENCY_TEMP,
                    default=current.get(
                        CONF_ANTIFREEZE_EMERGENCY_TEMP,
                        DEFAULT_ANTIFREEZE_EMERGENCY_CH_TEMP,
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=25,
                        max=45,
                        step=0.5,
                        unit_of_measurement="°C",
                    )
                ),
                vol.Required(
                    CONF_ANTIFREEZE_RECOVERY,
                    default=current.get(
                        CONF_ANTIFREEZE_RECOVERY, DEFAULT_ANTIFREEZE_RECOVERY_TEMP
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=10,
                        max=30,
                        step=0.5,
                        unit_of_measurement="°C",
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"curve_svg": svg},
        )

    def _get_curve_params(self, current: dict) -> dict[str, Any]:
        """Build curve params from current config."""
        curve_type = current.get(CONF_CURVE_TYPE, DEFAULT_CURVE_TYPE)
        params: dict[str, Any] = {
            "slope": current.get(CONF_CURVE_SLOPE, DEFAULT_CURVE_SLOPE),
            "base_temp": current.get(CONF_CURVE_BASE_TEMP, DEFAULT_CURVE_BASE_TEMP),
            "offset": current.get(CONF_CURVE_OFFSET, DEFAULT_CURVE_OFFSET),
            "setpoint": current.get(CONF_CURVE_SETPOINT, DEFAULT_CURVE_SETPOINT),
        }
        if curve_type == CURVE_TYPE_POINTS:
            points_str = current.get(CONF_CURVE_POINTS, "")
            if isinstance(points_str, dict):
                params["points"] = points_str
            elif points_str:
                try:
                    params["points"] = parse_curve_points_string(points_str)
                except ValueError:
                    params["points"] = DEFAULT_CURVE_POINTS
            else:
                params["points"] = DEFAULT_CURVE_POINTS
        return params
