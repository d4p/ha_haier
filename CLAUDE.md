# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Home Assistant custom integration (HACS) for controlling Haier heat pumps over Modbus TCP. Uses [PyHaier](https://github.com/ktostam/PyHaier) for register decoding/encoding and `pymodbus` for the TCP transport.

## Development Setup

There is no build system or automated test suite. The integration runs inside Home Assistant. For quick testing against a real device without HA, use:

```bash
python scripts/pyHaier_test.py --status
python scripts/pyHaier_test.py --state HT
python scripts/pyHaier_test.py --ch-temp 40
```
Edit `GATEWAY_IP`/`GATEWAY_PORT` in that script first.

**Installation**: Copy `custom_components/haier_heatpump/` into your HA `custom_components/` folder and restart HA.

**Requirements**: PyHaier >= 0.4.4, pymodbus >= 3.5.0, Home Assistant >= 2024.1.0

## Architecture

```
__init__.py          Entry setup, AntifreezeManager (always-on safety)
coordinator.py       DataUpdateCoordinator, polls all Modbus registers every 30s
modbus_client.py     HaierModbusClient - async wrapper around sync pymodbus
heating_curve.py     Pure functions: calculate_target_temp(), generate_curve_svg(), parse helpers
config_flow.py       3-step config: connection → heating_curve → antifreeze
climate.py           ClimateEntity with heating curve + demand switch integration
sensor.py            ~35 sensor entities
binary_sensor.py     4 binary sensors (antifreeze, alarm, defrost, hw antifreeze)
select.py            Mode select: eco/quiet/turbo
number.py            DHW target temperature
switch.py            Heating curve enable/disable
const.py             All constants (DATA_*, CONF_*, defaults, register offsets)
```

## Key Patterns

### PyHaier library usage
`PyHaier.Get*()` functions take raw register lists and return parsed values. `PyHaier.Set*()` take raw registers + new value and return a modified register list to write back. Always pass the full register block (e.g., all 6 core registers) to Set functions.

### Async/sync boundary
`pymodbus` is synchronous. All Modbus I/O is run via `hass.async_add_executor_job()` in `HaierModbusClient`. All public methods on the client are `async`.

### Write safety (critical — do not skip)
Every write must:
1. Read current registers first (`async_write_core` does this automatically)
2. Preserve high bytes — some Haier models set `0xDD**` style high bytes that PyHaier strips. `async_write_core` and `async_write_mode` both patch these back before writing.
3. Respect the 5s rate limit enforced in `_write_registers`.

### Heating curve rate limit
Curve-driven temperature updates are rate-limited to **20 minutes** (`_last_curve_change_time` in `HaierClimate`). Do not remove this — it prevents excessive wear on the pump.

### Register blocks
| Block | Registers | Purpose |
|-------|-----------|---------|
| core  | 101–106   | State, CH temp, DHW setpoint, temp compensation |
| status | 141–156  | Current temps (Twi, Two, Thi, Tho, DHW), pump/heater/error flags |
| mode  | 201       | eco/quiet/turbo |
| advanced | 241–262 | Compressor, fans, EEV, pressures, errors, firmware (optional) |

### Config vs. options
All settings live in `entry.data` (set during config flow) and `entry.options` (editable post-setup). Always merge both: `config = {**entry.data, **entry.options}` to get effective values.

### DATA_* vs. CONF_* constants
`DATA_*` keys are used in the coordinator's data dict (runtime state). `CONF_*` keys are used in config/options entries (user configuration). Both are defined in `const.py`.

### Antifreeze manager
`AntifreezeManager` runs as a coordinator listener after every poll. It monitors `DATA_TWI`, `DATA_TWO`, `DATA_DHW_CURRENT` and activates/deactivates protection autonomously. It **cannot be disabled** and takes priority over all other control. When active, `DATA_ANTIFREEZE_ACTIVE` is set in coordinator data.

### pymodbus version compatibility
`modbus_client.py` tries `slave=`, then `unit=`, then `device_id=` keyword args to support pymodbus 2.x–3.x. Do not simplify this away.
