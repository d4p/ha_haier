"""Binary sensor platform for Haier Heat Pump."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DATA_ACTIVE_ERROR,
    DATA_ANTIFREEZE_ACTIVE,
    DATA_ANTIFREEZE_HW,
    DATA_DEFROST,
    DATA_DHW_CURRENT,
    DATA_TWI,
    DATA_TWO,
    DOMAIN,
    MANUFACTURER,
)
from .coordinator import HaierDataCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Haier Heat Pump binary sensors."""
    coordinator: HaierDataCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]

    entities: list[BinarySensorEntity] = [
        HaierAntifreezeBinarySensor(coordinator, entry),
        HaierAlarmBinarySensor(coordinator, entry),
        HaierDefrostBinarySensor(coordinator, entry),
        HaierHWAntifreezeBinarySensor(coordinator, entry),
    ]
    async_add_entities(entities)


class HaierBaseBinarySensor(
    CoordinatorEntity[HaierDataCoordinator], BinarySensorEntity
):
    """Base class for Haier binary sensors."""

    def __init__(
        self,
        coordinator: HaierDataCoordinator,
        entry: ConfigEntry,
        key: str,
        name: str,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_has_entity_name = True
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Haier Heat Pump",
            manufacturer=MANUFACTURER,
            model="Heat Pump",
        )


class HaierAntifreezeBinarySensor(HaierBaseBinarySensor):
    """Binary sensor for software antifreeze protection state."""

    def __init__(
        self, coordinator: HaierDataCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize."""
        super().__init__(
            coordinator, entry, "antifreeze_active", "Antifreeze Protection"
        )
        self._attr_device_class = BinarySensorDeviceClass.SAFETY
        self._attr_icon = "mdi:snowflake-alert"

    @property
    def is_on(self) -> bool | None:
        """Return True if antifreeze protection is active."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(DATA_ANTIFREEZE_ACTIVE, False)


class HaierAlarmBinarySensor(HaierBaseBinarySensor):
    """Binary sensor for alarm state (errors or out-of-range values)."""

    def __init__(
        self, coordinator: HaierDataCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, entry, "alarm", "Alarm")
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM
        self._attr_icon = "mdi:alert"

    @property
    def is_on(self) -> bool | None:
        """Return True if there is an active error or critical condition."""
        if self.coordinator.data is None:
            return None

        data = self.coordinator.data

        # Check active error code
        error = data.get(DATA_ACTIVE_ERROR)
        if error is not None and isinstance(error, (int, float)) and error != 0:
            return True

        # Check for critical water temperatures (below 0°C)
        for key in (DATA_TWI, DATA_TWO, DATA_DHW_CURRENT):
            val = data.get(key)
            if val is not None and isinstance(val, (int, float)) and val < 0:
                return True

        return False

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional alarm details."""
        if self.coordinator.data is None:
            return {}

        attrs: dict[str, Any] = {}
        error = self.coordinator.data.get(DATA_ACTIVE_ERROR)
        if error is not None and isinstance(error, (int, float)) and error != 0:
            attrs["error_code"] = error

        return attrs


class HaierDefrostBinarySensor(HaierBaseBinarySensor):
    """Binary sensor for defrost state."""

    def __init__(
        self, coordinator: HaierDataCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, entry, "defrost_active", "Defrost Active")
        self._attr_icon = "mdi:snowflake-melt"

    @property
    def is_on(self) -> bool | None:
        """Return True if defrost is active."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(DATA_DEFROST, False)

    @property
    def available(self) -> bool:
        """Return True if available."""
        if not super().available:
            return False
        return self.coordinator.data is not None and DATA_DEFROST in self.coordinator.data


class HaierHWAntifreezeBinarySensor(HaierBaseBinarySensor):
    """Binary sensor for hardware antifreeze state (from pump)."""

    def __init__(
        self, coordinator: HaierDataCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize."""
        super().__init__(
            coordinator, entry, "hw_antifreeze", "HW Antifreeze"
        )
        self._attr_device_class = BinarySensorDeviceClass.SAFETY
        self._attr_icon = "mdi:snowflake-alert"

    @property
    def is_on(self) -> bool | None:
        """Return True if hardware antifreeze is active."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(DATA_ANTIFREEZE_HW, False)

    @property
    def available(self) -> bool:
        """Return True if available."""
        if not super().available:
            return False
        return (
            self.coordinator.data is not None
            and DATA_ANTIFREEZE_HW in self.coordinator.data
        )
