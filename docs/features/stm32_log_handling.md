STM32 Log Handling Process
=========================

1. Overview
-----------
The ESP32 device receives and processes various types of data from the STM32 microcontroller through UART communication. This document specifically details the log handling process, which is crucial for monitoring device status, sensor readings, and system states.

2. Communication Protocol
------------------------
2.1 Log Data Frame Structure
    • Start Marker: 1 byte
    • Command: 2 bytes (SYNC_LOG = 0x0001)
    • Device ID: 1 byte
    • Message ID: 2 bytes
    • Data Length: 1 byte
    • Log Data: 83 bytes
    • Version: 1 byte
    • Checksum: 1 byte

2.2 Data Fields in Log
    A. Sensor Readings (16-bit values, divided by 10 for actual reading)
       • EVP sensor
       • Compressor sensor
       • BB1 sensor
       • BB2 sensor
       • Heater1 sensor
       • Heater2 sensor

    B. RPM Measurements (16-bit values)
       • PA1 RPM
       • PA2 RPM
       • Filter fan RPM
       • Motor1 RPM
       • Motor2 RPM

    C. Current Measurements (8-bit values, divided by 10 for actual reading)
       • AC input current
       • Motor1 current
       • Motor2 current
       • Heater1 current
       • Heater2 current
       • C2 fan1 current
       • C2 fan2 current
       • Damper1-4 currents

    D. State Information
       • State Byte 1 (8 bits):
         - Bit 0: C2 fan1 state
         - Bit 1: C2 fan2 state
         - Bit 2: Damper12 state
         - Bit 3: Damper34 state
         - Bit 4: Drawer1 state
         - Bit 5: Drawer2 state
         - Bit 6: Motor1 state
         - Bit 7: Motor2 state

       • State Byte 2 (8 bits):
         - Bit 0: Drawer1 heat state
         - Bit 1: Drawer2 heat state
         - Bit 2: Drawer1 cool state
         - Bit 3: Drawer2 cool state
         - Bit 4: Compressor state
         - Bit 5: Water pump state
         - Bit 6: Drawer1 pause state
         - Bit 7: Drawer2 pause state

       • State Byte 3 (8 bits):
         - Bit 0: Pump state 1
         - Bit 1: Pump state 2
         - Bit 2: Pump state 3
         - Bit 3: PA1 direction
         - Bit 4: PA2 direction

    E. Device Information
       • STM32 UUID: 12 bytes
       • Error codes: 2 bytes each (errorcode1, errorcode2)
       • Machine states: 2 bytes each (machine_state1, machine_state2)
       • Cycle times: 2 bytes each (drawer1_cycletime, drawer2_cycletime)
       • Self-test results: 3 bytes

3. Processing Flow
-----------------
3.1 Initial Data Reception
    • ESP32 receives data in 256-byte UART buffer
    • Validates start marker (0xCC)
    • Verifies command type (SYNC_LOG)
    • Checks data length (93 bytes)

3.2 Device Identification
    • Extracts device ID (1 or 2)
    • Updates global device ID if changed
    • Stores device ID in NVS storage
    • Maintains device-specific state

3.3 UUID Management
    • Extracts 12-byte UUID from log data
    • Converts to hex string format
    • Stores in NVS if not previously stored
    • Triggers device registration process if new UUID

3.4 Data Processing
    • Converts raw sensor values to float (divide by 10)
    • Processes state bytes into individual flags
    • Extracts machine states and cycle times
    • Handles self-test results in error state

3.5 MQTT Publishing
    • Creates JSON payload with processed data
    • Publishes to topic: devices/{deviceCode}/logs/raw
    • Includes all sensor readings, states, and device info
    • Uses QoS 1 for reliable delivery

4. Special Handling
------------------
4.1 First Log Reception
    • Triggers SSID write process for device 1
    • Initializes device registration sequence
    • Sets up initial device state

4.2 Periodic Actions
    • Every 30 logs: Triggers SSID read for device 2
    • Updates screen with current status
    • Maintains connection state

4.3 Error State Processing
    • Processes self-test results when machine_state = 0x2019
    • Extracts component test results
    • Updates error display
    • Maintains error logging

5. Data Storage
--------------
5.1 Non-Volatile Storage (NVS)
    • Device ID: namespace "my-app", key "esp32_devid"
    • STM32 UUID: namespace "stm32-id", key "stm32_uniqueid"
    • WiFi credentials: namespace "wifi", keys "ssid" and "password"

5.2 Memory Storage
    • Current device state
    • Processing buffers
    • Temporary data structures

5.3 MQTT Publishing
    • All processed log data
    • Device status updates
    • Error reports

6. Error Handling
----------------
6.1 Data Validation
    • Length verification
    • Command type checking
    • Checksum validation
    • Data range validation

6.2 Storage Error Handling
    • NVS operation error handling
    • Memory allocation error handling
    • MQTT publishing error handling

6.3 Recovery Mechanisms
    • Automatic retry for failed operations
    • State recovery after errors
    • Connection re-establishment

7. Integration Points
--------------------
7.1 External Systems
    • MQTT broker for data publishing
    • Cloud services for data storage
    • Monitoring systems for status tracking

7.2 Internal Systems
    • Screen task for display updates
    • Main control task for system management
    • WiFi management for connectivity

8. Performance Considerations
---------------------------
8.1 Timing
    • UART buffer size: 256 bytes
    • Processing delay: < 100ms
    • MQTT publishing interval: As received

8.2 Resource Usage
    • Memory: Dynamic allocation for JSON
    • CPU: Minimal processing overhead
    • Storage: Efficient NVS usage 