#!/usr/bin/env python3
"""
Script for testing connection and manual control of heatpump. Before using set GATEWAY_IP and GATEWAY_PORT. 
Controls Haier heat pump via Modbus TCP using PyHaier library
"""

import argparse
import sys
from pymodbus.client import ModbusTcpClient
import PyHaier

# Connection settings
GATEWAY_IP = "192.168.8.209"
GATEWAY_PORT = 8899
MODBUS_UNIT = 17  # Default Modbus unit ID (adjust if needed)


def connect_modbus():
    """Establish connection to Modbus gateway"""
    client = ModbusTcpClient(host=GATEWAY_IP, port=GATEWAY_PORT)
    if not client.connect():
        print("Error: Unable to connect to Modbus gateway")
        sys.exit(1)
    return client


def get_status(client):
    """Display current heat pump status"""
    print("\n=== Heat Pump Status ===")
    
    try:
        # Read registers 101-106 for state, CH temp, DHW temp
        payload = client.read_holding_registers(address=101, count=6, device_id=MODBUS_UNIT)
        if payload.isError():
            print("Error reading registers 101-106")
            return
        
        state = PyHaier.GetState(payload.registers)
        ch_temp = PyHaier.GetCHTemp(payload.registers)
        dhw_temp = PyHaier.GetDHWTemp(payload.registers)
        
        print(f"State:              {state}")
        print(f"Heating Water Temp: {ch_temp}°C")
        print(f"DHW Tank Temp:      {dhw_temp}°C")
        
        # Read register 201 for mode
        payload = client.read_holding_registers(address=201, count=1, device_id=MODBUS_UNIT)
        if not payload.isError():
            mode = PyHaier.GetMode(payload.registers)
            print(f"Mode:               {mode}")
        
        # Read registers 141-156 for current DHW tank temperature
        payload = client.read_holding_registers(address=141, count=16, device_id=MODBUS_UNIT)
        if not payload.isError():
            dhw_current = PyHaier.GetDHWCurTemp(payload.registers)
            print(f"DHW Current Temp:   {dhw_current}°C")
            
            twi_two = PyHaier.GetTwiTwo(payload.registers)
            print(f"Twi/Two:            {twi_two[0]}°C / {twi_two[1]}°C")
        
        print()
        
    except Exception as e:
        print(f"Error reading status: {e}")


def set_state(client, new_state):
    """Set heat pump state (on/off/C/H/T/CT/HT)"""
    try:
        # Read current state
        payload = client.read_holding_registers(address=101, count=6, device_id=MODBUS_UNIT)
        if payload.isError():
            print("Error reading current state")
            return
        
        current_state = PyHaier.GetState(payload.registers)
        print(f"Current state: {current_state}")
        
        # Generate new state frame
        new_frame = PyHaier.SetState(payload.registers, new_state)
        
        # Write new state
        result = client.write_registers(address=101, values=new_frame, device_id=MODBUS_UNIT)
        if result.isError():
            print("Error writing new state")
            return
        
        # Verify new state
        payload = client.read_holding_registers(address=101, count=6, device_id=MODBUS_UNIT)
        if not payload.isError():
            new_state_read = PyHaier.GetState(payload.registers)
            print(f"New state:     {new_state_read}")
        
    except Exception as e:
        print(f"Error setting state: {e}")


def set_mode(client, new_mode):
    """Set heat pump mode (eco/silent/turbo)"""
    try:
        # Read current mode
        payload = client.read_holding_registers(address=201, count=1, device_id=MODBUS_UNIT)
        if not payload.isError():
            current_mode = PyHaier.GetMode(payload.registers)
            print(f"Current mode: {current_mode}")
        
        # Generate new mode frame
        new_frame = PyHaier.SetMode(new_mode)
        
        # Write new mode
        result = client.write_registers(address=201, values=new_frame, device_id=MODBUS_UNIT)
        if result.isError():
            print("Error writing new mode")
            return
        
        # Verify new mode
        payload = client.read_holding_registers(address=201, count=1, device_id=MODBUS_UNIT)
        if not payload.isError():
            new_mode_read = PyHaier.GetMode(payload.registers)
            print(f"New mode:     {new_mode_read}")
        
    except Exception as e:
        print(f"Error setting mode: {e}")


def set_ch_temp(client, new_temp):
    """Set central heating water temperature"""
    try:
        # Read current state
        payload = client.read_holding_registers(address=101, count=6, device_id=MODBUS_UNIT)
        if payload.isError():
            print("Error reading current temperature")
            return
        
        current_temp = PyHaier.GetCHTemp(payload.registers)
        print(f"Current CH temp: {current_temp}°C")
        
        # Generate new temperature frame
        new_frame = PyHaier.SetCHTemp(payload.registers, new_temp)
        
        # Write new temperature
        result = client.write_registers(address=101, values=new_frame, device_id=MODBUS_UNIT)
        if result.isError():
            print("Error writing new temperature")
            return
        
        # Verify new temperature
        payload = client.read_holding_registers(address=101, count=6, device_id=MODBUS_UNIT)
        if not payload.isError():
            new_temp_read = PyHaier.GetCHTemp(payload.registers)
            print(f"New CH temp:     {new_temp_read}°C")
        
    except Exception as e:
        print(f"Error setting CH temperature: {e}")


def set_dhw_temp(client, new_temp):
    """Set DHW tank temperature"""
    try:
        # Read current state
        payload = client.read_holding_registers(address=101, count=6, device_id=MODBUS_UNIT)
        if payload.isError():
            print("Error reading current temperature")
            return
        
        current_temp = PyHaier.GetDHWTemp(payload.registers)
        print(f"Current DHW temp: {current_temp}°C")
        
        # Generate new temperature frame
        new_frame = PyHaier.SetDHWTemp(payload.registers, int(new_temp))
        
        # Write new temperature
        result = client.write_registers(address=101, values=new_frame, device_id=MODBUS_UNIT)
        if result.isError():
            print("Error writing new temperature")
            return
        
        # Verify new temperature
        payload = client.read_holding_registers(address=101, count=6, device_id=MODBUS_UNIT)
        if not payload.isError():
            new_temp_read = PyHaier.GetDHWTemp(payload.registers)
            print(f"New DHW temp:     {new_temp_read}°C")
        
    except Exception as e:
        print(f"Error setting DHW temperature: {e}")


def get_advanced_info(client):
    """Display advanced information"""
    print("\n=== Advanced Information ===")
    
    try:
        # Read registers 241-261 for compressor info
        payload = client.read_holding_registers(address=241, count=21, device_id=MODBUS_UNIT)
        if not payload.isError():
            comp_freq = PyHaier.GetCompFreq(payload.registers)
            print(f"Compressor Freq: Set={comp_freq[0]} Hz, Actual={comp_freq[1]} Hz")
            
            eev_level = PyHaier.GetEEVLevel(payload.registers)
            print(f"EEV Level:       {eev_level}")
            
            arch_errors = PyHaier.GetArchError(payload.registers)
            print(f"Archive Errors:  {arch_errors}")
        
        print()
        
    except Exception as e:
        print(f"Error reading advanced info: {e}")


def main():
    parser = argparse.ArgumentParser(
        description='Control Haier Heat Pump via Modbus TCP',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --status                    # Show current status
  %(prog)s --state on                  # Turn on heat pump
  %(prog)s --state off                 # Turn off heat pump
  %(prog)s --state H                   # Set to Heat mode
  %(prog)s --state T                   # Set to Tank mode
  %(prog)s --state HT                  # Set to Heat+Tank mode
  %(prog)s --mode eco                  # Set to ECO mode
  %(prog)s --mode silent               # Set to Silent mode
  %(prog)s --ch-temp 45.5              # Set heating water temp to 45.5°C
  %(prog)s --dhw-temp 50               # Set DHW tank temp to 50°C
  %(prog)s --advanced                  # Show advanced information
        """
    )
    
    parser.add_argument('--status', action='store_true',
                        help='Show current heat pump status')
    parser.add_argument('--state', type=str,
                        choices=['on', 'off', 'C', 'H', 'T', 'CT', 'HT'],
                        help='Set state (on/off/C=Cool/H=Heat/T=Tank/CT=Cool+Tank/HT=Heat+Tank)')
    parser.add_argument('--mode', type=str,
                        choices=['eco', 'silent', 'turbo'],
                        help='Set mode (eco/silent/turbo)')
    parser.add_argument('--ch-temp', type=float,
                        help='Set central heating water temperature (precision 0.5°C)')
    parser.add_argument('--dhw-temp', type=float,
                        help='Set DHW tank temperature (precision 1°C)')
    parser.add_argument('--advanced', action='store_true',
                        help='Show advanced information (compressor, EEV, errors)')
    
    args = parser.parse_args()
    
    # Show help if no arguments provided
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)
    
    # Connect to Modbus gateway
    client = connect_modbus()
    
    try:
        # Execute commands
        if args.status:
            get_status(client)
        
        if args.state:
            set_state(client, args.state)
        
        if args.mode:
            set_mode(client, args.mode)
        
        if args.ch_temp is not None:
            set_ch_temp(client, args.ch_temp)
        
        if args.dhw_temp is not None:
            set_dhw_temp(client, args.dhw_temp)
        
        if args.advanced:
            get_advanced_info(client)
        
    finally:
        client.close()


if __name__ == "__main__":
    main()
