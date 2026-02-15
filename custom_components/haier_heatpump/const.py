"""Constants for the Haier Heat Pump integration."""

DOMAIN = "haier_heatpump"
MANUFACTURER = "Haier"

# --- Connection defaults (from user's working script) ---
DEFAULT_IP = "192.168.8.209"
DEFAULT_PORT = 8899
DEFAULT_DEVICE_ID = 17
DEFAULT_SCAN_INTERVAL = 30  # seconds

# --- Modbus register blocks ---
REG_CORE_START = 101
REG_CORE_COUNT = 6        # 101-106
REG_STATUS_START = 141
REG_STATUS_COUNT = 16     # 141-156 (payload length 16 for v0.4.3+)
REG_MODE_START = 201
REG_MODE_COUNT = 1        # 201
REG_ADVANCED_START = 241
REG_ADVANCED_COUNT = 22   # 241-262

# --- Temperature safety limits ---
CH_TEMP_MIN = 25.0
CH_TEMP_MAX = 55.0
CH_TEMP_STEP = 0.5
DHW_TEMP_MIN = 30.0
DHW_TEMP_MAX = 55.0
DHW_TEMP_STEP = 1.0

# --- Antifreeze protection defaults ---
DEFAULT_ANTIFREEZE_WARNING_TEMP = 5.0
DEFAULT_ANTIFREEZE_CRITICAL_TEMP = 2.0
DEFAULT_ANTIFREEZE_EMERGENCY_CH_TEMP = 30.0
DEFAULT_ANTIFREEZE_RECOVERY_TEMP = 20.0

# --- Heating curve defaults ---
DEFAULT_CURVE_TYPE = "formula"
CURVE_TYPE_FORMULA = "formula"
CURVE_TYPE_POINTS = "points"

DEFAULT_CURVE_SLOPE = 1.5
DEFAULT_CURVE_BASE_TEMP = 30.0
DEFAULT_CURVE_OFFSET = 0.0
DEFAULT_CURVE_SETPOINT = 21.0

CURVE_SLOPE_MIN = 0.1
CURVE_SLOPE_MAX = 3.0
CURVE_BASE_TEMP_MIN = 25.0
CURVE_BASE_TEMP_MAX = 45.0
CURVE_OFFSET_MIN = -5.0
CURVE_OFFSET_MAX = 5.0
CURVE_SETPOINT_MIN = 18.0
CURVE_SETPOINT_MAX = 24.0

# Default point-based curve: outdoor_temp -> water_temp
DEFAULT_CURVE_POINTS = {
    -20: 50,
    -10: 45,
    0: 38,
    10: 32,
    20: 25,
}

# --- Write operation safety ---
MIN_WRITE_INTERVAL = 5.0  # seconds between consecutive writes
MAX_WRITE_RETRIES = 3
MODBUS_TIMEOUT = 10  # seconds
MODBUS_RETRIES = 3

# --- Config flow keys ---
CONF_IP = "ip_address"
CONF_PORT = "port"
CONF_DEVICE_ID = "device_id"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_EXTERNAL_TEMP_SENSOR = "external_temp_sensor"
CONF_DEMAND_SWITCH = "demand_switch"
CONF_CURVE_TYPE = "curve_type"
CONF_CURVE_SLOPE = "curve_slope"
CONF_CURVE_BASE_TEMP = "curve_base_temp"
CONF_CURVE_OFFSET = "curve_offset"
CONF_CURVE_SETPOINT = "curve_setpoint"
CONF_CURVE_POINTS = "curve_points"
CONF_ANTIFREEZE_WARNING = "antifreeze_warning_temp"
CONF_ANTIFREEZE_CRITICAL = "antifreeze_critical_temp"
CONF_ANTIFREEZE_EMERGENCY_TEMP = "antifreeze_emergency_ch_temp"
CONF_ANTIFREEZE_RECOVERY = "antifreeze_recovery_temp"

# --- Data keys in coordinator ---
DATA_STATE = "state"
DATA_MODE = "mode"
DATA_CH_TEMP = "ch_temp"
DATA_DHW_TEMP = "dhw_temp"
DATA_DHW_CURRENT = "dhw_current"
DATA_TWI = "twi"
DATA_TWO = "two"
DATA_THI = "thi"
DATA_THO = "tho"
DATA_TAO = "tao"
DATA_TD = "td"
DATA_TS = "ts"
DATA_TDEF = "tdef"
DATA_COMP_FREQ_SET = "comp_freq_set"
DATA_COMP_FREQ_ACTUAL = "comp_freq_actual"
DATA_COMP_CURRENT = "comp_current"
DATA_COMP_VOLTAGE = "comp_voltage"
DATA_COMP_TEMP = "comp_temp"
DATA_FAN1_RPM = "fan1_rpm"
DATA_FAN2_RPM = "fan2_rpm"
DATA_EEV_LEVEL = "eev_level"
DATA_PD_SET = "pd_set"
DATA_PD_ACTUAL = "pd_actual"
DATA_PS_SET = "ps_set"
DATA_PS_ACTUAL = "ps_actual"
DATA_TSAT_PD = "tsat_pd"
DATA_TSAT_PS = "tsat_ps"
DATA_THREE_WAY = "three_way"
DATA_PUMP_STATUS = "pump_status"
DATA_HEATER_STATUS = "heater_status"
DATA_TEMP_COMPENSATION = "temp_compensation"
DATA_ACTIVE_ERROR = "active_error"
DATA_LAST_ERROR = "last_error"
DATA_ARCH_ERRORS = "arch_errors"
DATA_FIRMWARE = "firmware"
DATA_ANTIFREEZE_HW = "antifreeze_hw"
DATA_DEFROST = "defrost"
DATA_ANTIFREEZE_ACTIVE = "antifreeze_active"
DATA_CORE_REGISTERS = "core_registers"
DATA_STATUS_REGISTERS = "status_registers"
DATA_CURVE_ENABLED = "curve_enabled"
DATA_OPERATION_MODE = "operation_mode"

# --- Platforms ---
PLATFORMS = ["sensor", "binary_sensor", "climate", "select", "number", "switch"]
