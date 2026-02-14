"""Sensor platform for Haier Heat Pump."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfFrequency,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DATA_ACTIVE_ERROR,
    DATA_ARCH_ERRORS,
    DATA_CH_TEMP,
    DATA_COMP_CURRENT,
    DATA_COMP_FREQ_ACTUAL,
    DATA_COMP_FREQ_SET,
    DATA_COMP_TEMP,
    DATA_COMP_VOLTAGE,
    DATA_DHW_CURRENT,
    DATA_DHW_TEMP,
    DATA_EEV_LEVEL,
    DATA_FAN1_RPM,
    DATA_FAN2_RPM,
    DATA_FIRMWARE,
    DATA_HEATER_STATUS,
    DATA_LAST_ERROR,
    DATA_MODE,
    DATA_PD_ACTUAL,
    DATA_PD_SET,
    DATA_PS_ACTUAL,
    DATA_PS_SET,
    DATA_PUMP_STATUS,
    DATA_STATE,
    DATA_TAO,
    DATA_TD,
    DATA_TDEF,
    DATA_TEMP_COMPENSATION,
    DATA_THI,
    DATA_THO,
    DATA_THREE_WAY,
    DATA_TS,
    DATA_TSAT_PD,
    DATA_TSAT_PS,
    DATA_TWI,
    DATA_TWO,
    DOMAIN,
    MANUFACTURER,
)
from .coordinator import HaierDataCoordinator


@dataclass(frozen=True, kw_only=True)
class HaierSensorEntityDescription(SensorEntityDescription):
    """Describe a Haier sensor entity."""

    data_key: str
    array_index: int | None = None


SENSOR_DESCRIPTIONS: list[HaierSensorEntityDescription] = [
    # --- Core sensors ---
    HaierSensorEntityDescription(
        key="state",
        name="State",
        data_key=DATA_STATE,
        icon="mdi:heat-pump-outline",
    ),
    HaierSensorEntityDescription(
        key="mode",
        name="Mode",
        data_key=DATA_MODE,
        icon="mdi:cog-outline",
    ),
    HaierSensorEntityDescription(
        key="ch_target_temp",
        name="CH Target Temperature",
        data_key=DATA_CH_TEMP,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    HaierSensorEntityDescription(
        key="dhw_target_temp",
        name="DHW Target Temperature",
        data_key=DATA_DHW_TEMP,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    HaierSensorEntityDescription(
        key="dhw_current_temp",
        name="DHW Current Temperature",
        data_key=DATA_DHW_CURRENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    HaierSensorEntityDescription(
        key="temp_compensation",
        name="Temperature Compensation",
        data_key=DATA_TEMP_COMPENSATION,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # --- Water temps ---
    HaierSensorEntityDescription(
        key="water_inlet_temp",
        name="Water Inlet (Twi)",
        data_key=DATA_TWI,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    HaierSensorEntityDescription(
        key="water_outlet_temp",
        name="Water Outlet (Two)",
        data_key=DATA_TWO,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    HaierSensorEntityDescription(
        key="thi",
        name="Thi",
        data_key=DATA_THI,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    HaierSensorEntityDescription(
        key="tho",
        name="Tho",
        data_key=DATA_THO,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    # --- Outdoor & defrost temps ---
    HaierSensorEntityDescription(
        key="outdoor_temp",
        name="Outdoor Temperature (Tao)",
        data_key=DATA_TAO,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    HaierSensorEntityDescription(
        key="td",
        name="Td",
        data_key=DATA_TD,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    HaierSensorEntityDescription(
        key="ts",
        name="Ts",
        data_key=DATA_TS,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    HaierSensorEntityDescription(
        key="tdef",
        name="Defrost Temperature",
        data_key=DATA_TDEF,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    # --- Compressor ---
    HaierSensorEntityDescription(
        key="comp_freq_set",
        name="Compressor Frequency (Set)",
        data_key=DATA_COMP_FREQ_SET,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:sine-wave",
    ),
    HaierSensorEntityDescription(
        key="comp_freq_actual",
        name="Compressor Frequency (Actual)",
        data_key=DATA_COMP_FREQ_ACTUAL,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:sine-wave",
    ),
    HaierSensorEntityDescription(
        key="comp_current",
        name="Compressor Current",
        data_key=DATA_COMP_CURRENT,
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    HaierSensorEntityDescription(
        key="comp_voltage",
        name="Compressor Voltage",
        data_key=DATA_COMP_VOLTAGE,
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    HaierSensorEntityDescription(
        key="comp_temp",
        name="Compressor Temperature",
        data_key=DATA_COMP_TEMP,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # --- Fans ---
    HaierSensorEntityDescription(
        key="fan1_rpm",
        name="Fan 1 RPM",
        data_key=DATA_FAN1_RPM,
        native_unit_of_measurement="rpm",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fan",
    ),
    HaierSensorEntityDescription(
        key="fan2_rpm",
        name="Fan 2 RPM",
        data_key=DATA_FAN2_RPM,
        native_unit_of_measurement="rpm",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fan",
        entity_registry_enabled_default=False,
    ),
    # --- EEV ---
    HaierSensorEntityDescription(
        key="eev_level",
        name="EEV Level",
        data_key=DATA_EEV_LEVEL,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:valve",
    ),
    # --- Pressure ---
    HaierSensorEntityDescription(
        key="pd_set",
        name="Pd Set",
        data_key=DATA_PD_SET,
        native_unit_of_measurement="bar",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gauge",
        entity_registry_enabled_default=False,
    ),
    HaierSensorEntityDescription(
        key="pd_actual",
        name="Pd Actual",
        data_key=DATA_PD_ACTUAL,
        native_unit_of_measurement="bar",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gauge",
        entity_registry_enabled_default=False,
    ),
    HaierSensorEntityDescription(
        key="ps_set",
        name="Ps Set",
        data_key=DATA_PS_SET,
        native_unit_of_measurement="bar",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gauge",
        entity_registry_enabled_default=False,
    ),
    HaierSensorEntityDescription(
        key="ps_actual",
        name="Ps Actual",
        data_key=DATA_PS_ACTUAL,
        native_unit_of_measurement="bar",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gauge",
        entity_registry_enabled_default=False,
    ),
    # --- Saturation temps ---
    HaierSensorEntityDescription(
        key="tsat_pd_target",
        name="TSat Pd Target",
        data_key=DATA_TSAT_PD,
        array_index=0,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    HaierSensorEntityDescription(
        key="tsat_pd_actual",
        name="TSat Pd Actual",
        data_key=DATA_TSAT_PD,
        array_index=1,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    HaierSensorEntityDescription(
        key="tsat_ps_target",
        name="TSat Ps Target",
        data_key=DATA_TSAT_PS,
        array_index=0,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    HaierSensorEntityDescription(
        key="tsat_ps_actual",
        name="TSat Ps Actual",
        data_key=DATA_TSAT_PS,
        array_index=1,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    # --- Status ---
    HaierSensorEntityDescription(
        key="three_way",
        name="3-Way Valve",
        data_key=DATA_THREE_WAY,
        icon="mdi:valve",
    ),
    HaierSensorEntityDescription(
        key="pump_status",
        name="Circulation Pump",
        data_key=DATA_PUMP_STATUS,
        icon="mdi:pump",
    ),
    HaierSensorEntityDescription(
        key="heater_status",
        name="Heater",
        data_key=DATA_HEATER_STATUS,
        icon="mdi:radiator",
    ),
    # --- Errors ---
    HaierSensorEntityDescription(
        key="active_error",
        name="Active Error",
        data_key=DATA_ACTIVE_ERROR,
        icon="mdi:alert-circle-outline",
    ),
    HaierSensorEntityDescription(
        key="last_error",
        name="Last Error",
        data_key=DATA_LAST_ERROR,
        icon="mdi:alert-circle-outline",
        entity_registry_enabled_default=False,
    ),
    HaierSensorEntityDescription(
        key="arch_errors",
        name="Archive Errors",
        data_key=DATA_ARCH_ERRORS,
        icon="mdi:alert-circle-outline",
        entity_registry_enabled_default=False,
    ),
    # --- Firmware ---
    HaierSensorEntityDescription(
        key="firmware",
        name="Firmware Version",
        data_key=DATA_FIRMWARE,
        icon="mdi:chip",
        entity_registry_enabled_default=False,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Haier Heat Pump sensors."""
    coordinator: HaierDataCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]

    entities = [
        HaierSensor(coordinator, description, entry)
        for description in SENSOR_DESCRIPTIONS
    ]
    async_add_entities(entities)


class HaierSensor(CoordinatorEntity[HaierDataCoordinator], SensorEntity):
    """Represent a Haier Heat Pump sensor."""

    entity_description: HaierSensorEntityDescription

    def __init__(
        self,
        coordinator: HaierDataCoordinator,
        description: HaierSensorEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_has_entity_name = True
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Haier Heat Pump",
            manufacturer=MANUFACTURER,
            model="Heat Pump",
        )

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        if self.coordinator.data is None:
            return None

        value = self.coordinator.data.get(self.entity_description.data_key)

        if value is None:
            return None

        # Handle array values
        if self.entity_description.array_index is not None:
            if isinstance(value, (list, tuple)):
                idx = self.entity_description.array_index
                if idx < len(value):
                    return value[idx]
                return None
            return None

        # Handle string error returns from PyHaier
        if isinstance(value, str) and value == "Bad payload length":
            return None

        # Handle list values (display as string)
        if isinstance(value, (list, tuple)):
            return str(value)

        return value

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if not super().available:
            return False
        if self.coordinator.data is None:
            return False
        value = self.coordinator.data.get(self.entity_description.data_key)
        return value is not None
