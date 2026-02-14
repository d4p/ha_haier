"""Modbus TCP client wrapper for Haier heat pump communication via PyHaier."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

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
        if not self.connected:
            if not self._connect():
                return None

        for attempt in range(MODBUS_RETRIES):
            try:
                resp = self._client.read_holding_registers(
                    address=address,
                    count=count,
                    slave=self._device_id,
                )
                if resp is None or resp.isError():
                    _LOGGER.warning(
                        "Modbus read error at %d-%d (attempt %d/%d): %s",
                        address,
                        address + count - 1,
                        attempt + 1,
                        MODBUS_RETRIES,
                        resp,
                    )
                    time.sleep(0.5 * (attempt + 1))
                    continue
                return resp.registers
            except ModbusException as exc:
                _LOGGER.warning(
                    "Modbus exception reading %d-%d (attempt %d/%d): %s",
                    address,
                    address + count - 1,
                    attempt + 1,
                    MODBUS_RETRIES,
                    exc,
                )
                time.sleep(0.5 * (attempt + 1))
            except Exception:
                _LOGGER.exception(
                    "Unexpected error reading registers %d-%d",
                    address,
                    address + count - 1,
                )
                return None

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
        if not self.connected:
            if not self._connect():
                return False

        # Rate limiting
        elapsed = time.monotonic() - self._last_write_time
        if elapsed < MIN_WRITE_INTERVAL:
            time.sleep(MIN_WRITE_INTERVAL - elapsed)

        try:
            resp = self._client.write_registers(
                address=address,
                values=values,
                slave=self._device_id,
            )
            self._last_write_time = time.monotonic()

            if resp is None or resp.isError():
                _LOGGER.error(
                    "Modbus write error at %d: %s", address, resp
                )
                return False

            # Read-back verification
            time.sleep(0.5)
            verify = self._client.read_holding_registers(
                address=address,
                count=len(values),
                slave=self._device_id,
            )
            if verify is None or verify.isError():
                _LOGGER.warning(
                    "Could not verify write at %d (read-back failed)",
                    address,
                )
                return True  # Write may have succeeded

            if verify.registers != values:
                _LOGGER.warning(
                    "Write verification mismatch at %d: wrote %s, read %s",
                    address,
                    values,
                    verify.registers,
                )
                # Some bits may be set by the pump itself, don't fail
                return True

            _LOGGER.debug(
                "Successfully wrote and verified registers at %d", address
            )
            return True

        except ModbusException as exc:
            _LOGGER.error("Modbus write exception at %d: %s", address, exc)
            return False
        except Exception:
            _LOGGER.exception(
                "Unexpected error writing registers at %d", address
            )
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
        return await self.async_write_registers(REG_CORE_START, values)

    async def async_write_mode(self, values: list[int]) -> bool:
        """Write mode register 201."""
        if len(values) != REG_MODE_COUNT:
            _LOGGER.error("Invalid mode register count")
            return False
        return await self.async_write_registers(REG_MODE_START, values)
