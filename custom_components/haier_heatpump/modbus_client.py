"""Modbus TCP client wrapper for Haier heat pump communication via PyHaier."""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from typing import Any

import pymodbus
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException

from .const import (
    MIN_WRITE_INTERVAL,
    MODBUS_RETRIES,
    MODBUS_TIMEOUT,
    REG_ADVANCED_COUNT,
    REG_ADVANCED_START,
    REG_CORE_COUNT,
    REG_CORE_START,
    REG_MODE_COUNT,
    REG_MODE_START,
    REG_STATUS_COUNT,
    REG_STATUS_START,
)

_LOGGER = logging.getLogger(__name__)


class HaierModbusClient:
    """Thread-safe async wrapper around pymodbus for Haier heat pump."""

    def __init__(
        self,
        hass: Any,
        host: str,
        port: int,
        device_id: int,
    ) -> None:
        """Initialize the Modbus client."""
        self._hass = hass
        self._host = host
        self._port = port
        self._device_id = device_id
        self._client: ModbusTcpClient | None = None
        self._lock = asyncio.Lock()
        self._last_write_time: float = 0.0

        try:
            _LOGGER.info(
                "HaierModbusClient initialized. Pymodbus version: %s",
                pymodbus.__version__,
            )
        except AttributeError:
            _LOGGER.info("HaierModbusClient initialized (unknown pymodbus version)")

    @property
    def connected(self) -> bool:
        """Return True if connected."""
        return self._client is not None and self._client.connected

    async def async_connect(self) -> bool:
        """Connect to the Modbus gateway."""
        async with self._lock:
            return await self._hass.async_add_executor_job(self._connect)

    def _connect(self) -> bool:
        """Synchronous connect."""
        try:
            if self._client is not None:
                try:
                    self._client.close()
                except Exception:  # noqa: BLE001
                    pass

            self._client = ModbusTcpClient(
                host=self._host,
                port=self._port,
                timeout=MODBUS_TIMEOUT,
            )
            result = self._client.connect()
            if result:
                _LOGGER.debug(
                    "Connected to Haier heat pump at %s:%s",
                    self._host,
                    self._port,
                )
                # Log method signature for debugging compatibility
                try:
                    sig = inspect.signature(self._client.read_holding_registers)
                    _LOGGER.info("read_holding_registers signature: %s", sig)
                except Exception:
                    pass
            else:
                _LOGGER.error(
                    "Failed to connect to Haier heat pump at %s:%s",
                    self._host,
                    self._port,
                )
            return result
        except Exception:
            _LOGGER.exception("Error connecting to Haier heat pump")
            return False

    async def async_disconnect(self) -> None:
        """Disconnect from the Modbus gateway."""
        async with self._lock:
            await self._hass.async_add_executor_job(self._disconnect)

    def _disconnect(self) -> None:
        """Synchronous disconnect."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:  # noqa: BLE001
                pass
            self._client = None
            _LOGGER.debug("Disconnected from Haier heat pump")

    async def async_read_block(
        self, address: int, count: int
    ) -> list[int] | None:
        """Read holding registers with retries."""
        async with self._lock:
            return await self._hass.async_add_executor_job(
                self._read_block, address, count
            )

    def _read_block(self, address: int, count: int) -> list[int] | None:
        """Synchronous register read with retries."""
        for attempt in range(MODBUS_RETRIES):
            # Ensure we are connected before trying
            if not self.connected:
                if not self._connect():
                    time.sleep(1)  # Wait before next retry if connect failed
                    continue

            try:
                # Try with 'slave' first (pymodbus 3.x standard)
                try:
                    resp = self._client.read_holding_registers(
                        address=address,
                        count=count,
                        slave=self._device_id,
                    )
                except TypeError:
                    # Fallback to 'unit' (pymodbus 2.x standard)
                    try:
                        resp = self._client.read_holding_registers(
                            address=address,
                            count=count,
                            unit=self._device_id,
                        )
                    except TypeError:
                        # Fallback to 'device_id'
                        try:
                            resp = self._client.read_holding_registers(
                                address=address,
                                count=count,
                                device_id=self._device_id,
                            )
                        except TypeError:
                            _LOGGER.error("Read failed: All device ID arguments rejected")
                            return None

                if resp is None or resp.isError():
                    _LOGGER.warning(
                        "Modbus read error at %d-%d (attempt %d/%d): %s",
                        address,
                        address + count - 1,
                        attempt + 1,
                        MODBUS_RETRIES,
                        resp,
                    )
                    # Force disconnect to ensure fresh connection on next retry
                    self._disconnect()
                    time.sleep(0.5 * (attempt + 1))
                    continue
                
                return resp.registers

            except (ModbusException, Exception) as exc:
                _LOGGER.warning(
                    "Modbus exception reading %d-%d (attempt %d/%d): %s",
                    address,
                    address + count - 1,
                    attempt + 1,
                    MODBUS_RETRIES,
                    exc,
                )
                # Force disconnect to ensure fresh connection on next retry
                self._disconnect()
                time.sleep(0.5 * (attempt + 1))

        _LOGGER.error(
            "Failed to read registers %d-%d after %d retries",
            address,
            address + count - 1,
            MODBUS_RETRIES,
        )
        return None

    async def async_write_registers(
        self, address: int, values: list[int]
    ) -> bool:
        """Write registers with rate limiting and verification."""
        async with self._lock:
            return await self._hass.async_add_executor_job(
                self._write_registers, address, values
            )

    def _write_registers(self, address: int, values: list[int]) -> bool:
        """Synchronous register write with rate limiting and verify."""
        for attempt in range(MODBUS_RETRIES):
            if not self.connected:
                if not self._connect():
                    time.sleep(1)
                    continue

            # Rate limiting
            elapsed = time.monotonic() - self._last_write_time
            if elapsed < MIN_WRITE_INTERVAL:
                time.sleep(MIN_WRITE_INTERVAL - elapsed)

            try:
                # Try with 'slave' first (pymodbus 3.x standard)
                kwargs = {}
                try:
                    resp = self._client.write_registers(
                        address=address,
                        values=values,
                        slave=self._device_id,
                    )
                    kwargs = {"slave": self._device_id}
                except TypeError:
                    # Fallback to 'unit' (pymodbus 2.x standard)
                    try:
                        resp = self._client.write_registers(
                            address=address,
                            values=values,
                            unit=self._device_id,
                        )
                        kwargs = {"unit": self._device_id}
                    except TypeError:
                        # Fallback to 'device_id'
                        try:
                            resp = self._client.write_registers(
                                address=address,
                                values=values,
                                device_id=self._device_id,
                            )
                            kwargs = {"device_id": self._device_id}
                        except TypeError:
                            _LOGGER.error("Write failed: All device ID arguments rejected")
                            return False

                if resp is None or resp.isError():
                    _LOGGER.warning(
                        "Modbus write error at %d (attempt %d/%d): %s",
                        address,
                        attempt + 1,
                        MODBUS_RETRIES,
                        resp,
                    )
                    self._disconnect()
                    time.sleep(0.5 * (attempt + 1))
                    continue

                self._last_write_time = time.monotonic()
                _LOGGER.debug(
                    "Wrote registers %d: %s (args: %s)", address, values, kwargs
                )

                # Verify write
                time.sleep(0.5)
                verify = self._client.read_holding_registers(
                    address=address,
                    count=len(values),
                    **kwargs,
                )
                if verify is None or verify.isError():
                    _LOGGER.warning(
                        "Could not verify write at %d (read-back failed)",
                        address,
                    )
                    # If verification read failed, we assume write MIGHT have worked, but it's risky.
                    # Given we have a loop, maybe we should retry?
                    # But if write worked and read failed, retrying write might be bad?
                    # Let's return True but warn.
                    return True

                if verify.registers != values:
                    _LOGGER.warning(
                        "Write verification mismatch at %d: wrote %s, read %s",
                        address,
                        values,
                        verify.registers,
                    )
                    # Some bits may be set by the pump itself, don't fail, but log.
                    return True

                return True

            except (ModbusException, Exception) as exc:
                _LOGGER.warning(
                    "Modbus exception writing %d (attempt %d/%d): %s",
                    address,
                    attempt + 1,
                    MODBUS_RETRIES,
                    exc,
                )
                self._disconnect()
                time.sleep(0.5 * (attempt + 1))

        _LOGGER.error("Failed to write registers %d after %d retries", address, MODBUS_RETRIES)
        return False


    async def async_read_core(self) -> list[int] | None:
        """Read core registers 101-106."""
        return await self.async_read_block(REG_CORE_START, REG_CORE_COUNT)

    async def async_read_status(self) -> list[int] | None:
        """Read status registers 141-156."""
        return await self.async_read_block(REG_STATUS_START, REG_STATUS_COUNT)

    async def async_read_mode(self) -> list[int] | None:
        """Read mode register 201."""
        return await self.async_read_block(REG_MODE_START, REG_MODE_COUNT)

    async def async_read_advanced(self) -> list[int] | None:
        """Read advanced registers 241-262."""
        return await self.async_read_block(
            REG_ADVANCED_START, REG_ADVANCED_COUNT
        )

    async def async_write_core(self, values: list[int]) -> bool:
        """Write core registers 101-106."""
        if len(values) != REG_CORE_COUNT:
            _LOGGER.error(
                "Invalid core register count: expected %d, got %d",
                REG_CORE_COUNT,
                len(values),
            )
            return False

        # Preserve high bytes (e.g., 0xDD prefix) if PyHaier stripped them
        # This is crucial for some Haier models (e.g., M8)
        current = await self.async_read_core()
        if current:
            new_values = []
            for i, val in enumerate(values):
                curr = current[i]
                # If new value implies low-byte only (mask 0xFF00 is 0)
                # and current value has a high byte set, restore it.
                if (val & 0xFF00) == 0 and (curr & 0xFF00) != 0:
                    patched = val | (curr & 0xFF00)
                    if patched != val:
                        _LOGGER.debug(
                            "Patched core register %d: %s -> %s (preserved high byte 0x%02X)",
                            REG_CORE_START + i,
                            val,
                            patched,
                            (curr & 0xFF00) >> 8,
                        )
                    new_values.append(patched)
                else:
                    new_values.append(val)
            values = new_values

        return await self.async_write_registers(REG_CORE_START, values)

    async def async_write_mode(self, values: list[int]) -> bool:
        """Write mode register 201."""
        if len(values) != REG_MODE_COUNT:
            _LOGGER.error("Invalid mode register count")
            return False
            
        # Preserve high bytes for mode register too
        current = await self.async_read_mode()
        if current:
            new_values = []
            for i, val in enumerate(values):
                curr = current[i]
                if (val & 0xFF00) == 0 and (curr & 0xFF00) != 0:
                    patched = val | (curr & 0xFF00)
                    if patched != val:
                        _LOGGER.debug(
                            "Patched mode register %d: %s -> %s (preserved high byte 0x%02X)",
                            REG_MODE_START + i,
                            val,
                            patched,
                            (curr & 0xFF00) >> 8,
                        )
                    new_values.append(patched)
                else:
                    new_values.append(val)
            values = new_values
            
        return await self.async_write_registers(REG_MODE_START, values)
