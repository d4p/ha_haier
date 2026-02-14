"""Data update coordinator for Haier Heat Pump."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import PyHaier
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    DATA_ACTIVE_ERROR,
    DATA_ANTIFREEZE_ACTIVE,
    DATA_ANTIFREEZE_HW,
    DATA_ARCH_ERRORS,
    DATA_CH_TEMP,
    DATA_COMP_CURRENT,
    DATA_COMP_FREQ_ACTUAL,
    DATA_COMP_FREQ_SET,
    DATA_COMP_TEMP,
    DATA_COMP_VOLTAGE,
    DATA_CORE_REGISTERS,
    DATA_DEFROST,
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
    DATA_STATUS_REGISTERS,
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
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .modbus_client import HaierModbusClient

_LOGGER = logging.getLogger(__name__)


class HaierDataCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to poll Haier heat pump data via Modbus."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: HaierModbusClient,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self._consecutive_failures = 0

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the heat pump."""
        data: dict[str, Any] = {}

        # --- Required blocks ---
        core = await self.client.async_read_core()
        if core is None:
            self._consecutive_failures += 1
            if self._consecutive_failures > 5:
                raise UpdateFailed(
                    "Failed to read core registers after multiple attempts. "
                    "Check connection to heat pump."
                )
            _LOGGER.warning(
                "Failed to read core registers (failure %d)",
                self._consecutive_failures,
            )
            # Return previous data if available
            if self.data:
                return self.data
            raise UpdateFailed("Failed to read core registers")

        self._consecutive_failures = 0

        mode_reg = await self.client.async_read_mode()
        status = await self.client.async_read_status()

        # Store raw registers for Set operations
        data[DATA_CORE_REGISTERS] = core

        # --- Parse core block (101-106) ---
        try:
            data[DATA_STATE] = PyHaier.GetState(core)
        except Exception:
            _LOGGER.debug("Failed to parse state", exc_info=True)
            data[DATA_STATE] = None

        try:
            data[DATA_CH_TEMP] = PyHaier.GetCHTemp(core)
        except Exception:
            _LOGGER.debug("Failed to parse CH temp", exc_info=True)
            data[DATA_CH_TEMP] = None

        try:
            data[DATA_DHW_TEMP] = PyHaier.GetDHWTemp(core)
        except Exception:
            _LOGGER.debug("Failed to parse DHW temp", exc_info=True)
            data[DATA_DHW_TEMP] = None

        try:
            data[DATA_TEMP_COMPENSATION] = PyHaier.GetTempCompensation(core)
        except Exception:
            _LOGGER.debug("Failed to parse temp compensation", exc_info=True)
            data[DATA_TEMP_COMPENSATION] = None

        # --- Parse mode block (201) ---
        if mode_reg is not None:
            try:
                data[DATA_MODE] = PyHaier.GetMode(mode_reg)
            except Exception:
                _LOGGER.debug("Failed to parse mode", exc_info=True)
                data[DATA_MODE] = None
        else:
            _LOGGER.warning("Failed to read mode register")
            data[DATA_MODE] = None

        # --- Parse status block (141-156) ---
        if status is not None:
            data[DATA_STATUS_REGISTERS] = status
            self._parse_status_block(status, data)
        else:
            _LOGGER.warning("Failed to read status registers")
            data[DATA_STATUS_REGISTERS] = None
            self._set_status_unavailable(data)

        # --- Parse advanced block (241-262) - OPTIONAL ---
        advanced = await self.client.async_read_advanced()
        if advanced is not None:
            self._parse_advanced_block(advanced, data)
        else:
            _LOGGER.debug(
                "Advanced registers unavailable (this is normal for some models)"
            )
            self._set_advanced_unavailable(data)

        # Antifreeze active state (managed by __init__.py)
        if DATA_ANTIFREEZE_ACTIVE not in data:
            data[DATA_ANTIFREEZE_ACTIVE] = False

        return data

    def _parse_status_block(
        self, status: list[int], data: dict[str, Any]
    ) -> None:
        """Parse status register block 141-156."""
        try:
            data[DATA_DHW_CURRENT] = PyHaier.GetDHWCurTemp(status)
        except Exception:
            data[DATA_DHW_CURRENT] = None

        try:
            twi_two = PyHaier.GetTwiTwo(status)
            if isinstance(twi_two, list) and len(twi_two) >= 2:
                data[DATA_TWI] = twi_two[0]
                data[DATA_TWO] = twi_two[1]
            else:
                data[DATA_TWI] = None
                data[DATA_TWO] = None
        except Exception:
            data[DATA_TWI] = None
            data[DATA_TWO] = None

        try:
            thi_tho = PyHaier.GetThiTho(status)
            if isinstance(thi_tho, list) and len(thi_tho) >= 2:
                data[DATA_THI] = thi_tho[0]
                data[DATA_THO] = thi_tho[1]
            else:
                data[DATA_THI] = None
                data[DATA_THO] = None
        except Exception:
            data[DATA_THI] = None
            data[DATA_THO] = None

        try:
            pump = PyHaier.GetPump(status)
            data[DATA_PUMP_STATUS] = pump if pump != "Bad payload length" else None
        except Exception:
            data[DATA_PUMP_STATUS] = None

        try:
            heater = PyHaier.GetHeater(status)
            data[DATA_HEATER_STATUS] = heater if heater != "Bad payload length" else None
        except Exception:
            data[DATA_HEATER_STATUS] = None

        try:
            three_way = PyHaier.Get3way(status)
            data[DATA_THREE_WAY] = three_way if three_way != "Bad payload length" else None
        except Exception:
            data[DATA_THREE_WAY] = None

        try:
            antifreeze = PyHaier.GetAntifreeze(status)
            data[DATA_ANTIFREEZE_HW] = bool(antifreeze and antifreeze == "ANTIFREEZE")
        except Exception:
            data[DATA_ANTIFREEZE_HW] = None

        try:
            defrost = PyHaier.GetDefrost(status)
            data[DATA_DEFROST] = bool(defrost and defrost == "DEFROST")
        except Exception:
            data[DATA_DEFROST] = None

        try:
            error = PyHaier.GetError(status)
            data[DATA_ACTIVE_ERROR] = error if error != "Bad payload length" else None
        except Exception:
            data[DATA_ACTIVE_ERROR] = None

    def _parse_advanced_block(
        self, advanced: list[int], data: dict[str, Any]
    ) -> None:
        """Parse advanced register block 241-262."""
        try:
            comp_info = PyHaier.GetCompInfo(advanced)
            if isinstance(comp_info, list) and len(comp_info) >= 5:
                data[DATA_COMP_FREQ_SET] = comp_info[0]
                data[DATA_COMP_FREQ_ACTUAL] = comp_info[1]
                data[DATA_COMP_CURRENT] = comp_info[2]
                data[DATA_COMP_VOLTAGE] = comp_info[3]
                data[DATA_COMP_TEMP] = comp_info[4]
            else:
                self._set_comp_unavailable(data)
        except Exception:
            self._set_comp_unavailable(data)

        try:
            fan_rpm = PyHaier.GetFanRpm(advanced)
            if isinstance(fan_rpm, list) and len(fan_rpm) >= 2:
                data[DATA_FAN1_RPM] = fan_rpm[0]
                data[DATA_FAN2_RPM] = fan_rpm[1]
            else:
                data[DATA_FAN1_RPM] = None
                data[DATA_FAN2_RPM] = None
        except Exception:
            data[DATA_FAN1_RPM] = None
            data[DATA_FAN2_RPM] = None

        try:
            data[DATA_TAO] = PyHaier.GetTao(advanced)
            if data[DATA_TAO] == "Bad payload length":
                data[DATA_TAO] = None
        except Exception:
            data[DATA_TAO] = None

        try:
            td_ts = PyHaier.GetTdTs(advanced)
            if isinstance(td_ts, list) and len(td_ts) >= 2:
                data[DATA_TD] = td_ts[0]
                data[DATA_TS] = td_ts[1]
            else:
                data[DATA_TD] = None
                data[DATA_TS] = None
        except Exception:
            data[DATA_TD] = None
            data[DATA_TS] = None

        try:
            data[DATA_TDEF] = PyHaier.GetTdef(advanced)
            if data[DATA_TDEF] == "Bad payload length":
                data[DATA_TDEF] = None
        except Exception:
            data[DATA_TDEF] = None

        try:
            pd_ps = PyHaier.GetPdPs(advanced)
            if isinstance(pd_ps, list) and len(pd_ps) >= 4:
                data[DATA_PD_SET] = pd_ps[0]
                data[DATA_PD_ACTUAL] = pd_ps[1]
                data[DATA_PS_SET] = pd_ps[2]
                data[DATA_PS_ACTUAL] = pd_ps[3]
            else:
                data[DATA_PD_SET] = None
                data[DATA_PD_ACTUAL] = None
                data[DATA_PS_SET] = None
                data[DATA_PS_ACTUAL] = None
        except Exception:
            data[DATA_PD_SET] = None
            data[DATA_PD_ACTUAL] = None
            data[DATA_PS_SET] = None
            data[DATA_PS_ACTUAL] = None

        try:
            tsat_pd = PyHaier.GetTSatPd(advanced)
            if isinstance(tsat_pd, list) and len(tsat_pd) >= 2:
                data[DATA_TSAT_PD] = tsat_pd
            else:
                data[DATA_TSAT_PD] = None
        except Exception:
            data[DATA_TSAT_PD] = None

        try:
            tsat_ps = PyHaier.GetTSatPs(advanced)
            if isinstance(tsat_ps, list) and len(tsat_ps) >= 2:
                data[DATA_TSAT_PS] = tsat_ps
            else:
                data[DATA_TSAT_PS] = None
        except Exception:
            data[DATA_TSAT_PS] = None

        try:
            data[DATA_EEV_LEVEL] = PyHaier.GetEEVLevel(advanced)
            if data[DATA_EEV_LEVEL] == "Bad payload length":
                data[DATA_EEV_LEVEL] = None
        except Exception:
            data[DATA_EEV_LEVEL] = None

        try:
            errors = PyHaier.GetArchError(advanced)
            data[DATA_ARCH_ERRORS] = errors if errors != "Bad payload length" else None
        except Exception:
            data[DATA_ARCH_ERRORS] = None

        try:
            data[DATA_LAST_ERROR] = PyHaier.GetLastError(advanced)
            if data[DATA_LAST_ERROR] == "Bad payload length":
                data[DATA_LAST_ERROR] = None
        except Exception:
            data[DATA_LAST_ERROR] = None

        try:
            data[DATA_FIRMWARE] = PyHaier.GetFirmware(advanced)
            if data[DATA_FIRMWARE] == "Bad payload length":
                data[DATA_FIRMWARE] = None
        except Exception:
            data[DATA_FIRMWARE] = None

    def _set_status_unavailable(self, data: dict[str, Any]) -> None:
        """Set all status fields to None."""
        for key in (
            DATA_DHW_CURRENT, DATA_TWI, DATA_TWO, DATA_THI, DATA_THO,
            DATA_PUMP_STATUS, DATA_HEATER_STATUS, DATA_THREE_WAY,
            DATA_ANTIFREEZE_HW, DATA_DEFROST, DATA_ACTIVE_ERROR,
        ):
            data[key] = None

    def _set_advanced_unavailable(self, data: dict[str, Any]) -> None:
        """Set all advanced fields to None."""
        self._set_comp_unavailable(data)
        for key in (
            DATA_FAN1_RPM, DATA_FAN2_RPM, DATA_TAO, DATA_TD, DATA_TS,
            DATA_TDEF, DATA_PD_SET, DATA_PD_ACTUAL, DATA_PS_SET,
            DATA_PS_ACTUAL, DATA_TSAT_PD, DATA_TSAT_PS, DATA_EEV_LEVEL,
            DATA_ARCH_ERRORS, DATA_LAST_ERROR, DATA_FIRMWARE,
        ):
            data[key] = None

    def _set_comp_unavailable(self, data: dict[str, Any]) -> None:
        """Set compressor fields to None."""
        for key in (
            DATA_COMP_FREQ_SET, DATA_COMP_FREQ_ACTUAL,
            DATA_COMP_CURRENT, DATA_COMP_VOLTAGE, DATA_COMP_TEMP,
        ):
            data[key] = None
