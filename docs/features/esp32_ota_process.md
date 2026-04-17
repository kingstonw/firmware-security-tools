ESP32 OTA Process Documentation
==============================

1. Overview
-----------
The ESP32 OTA (Over-The-Air) update process is a two-stage system that handles both ESP32 and STM32 firmware updates. The process is managed by two main tasks: OTA Management Task and OTA Flash Task.

2. System Architecture
---------------------
2.1 OTA Management Task
    Purpose: Handles the initial OTA command reception and firmware download
    Key Components:
    • MQTT subscription for OTA commands
    • HTTP client for firmware download
    • SPIFFS storage for temporary firmware storage
    • Progress tracking and status reporting

2.2 OTA Flash Task
    Purpose: Manages the actual firmware flashing process
    Key Components:
    • ESP32 native OTA handling
    • STM32 firmware update protocol
    • Status reporting and acknowledgment
    • Error handling and recovery

3. OTA Process Flow
------------------
3.1 Command Reception
    1. OTA command received via MQTT in JSON format:
       {
         "deviceCode": "string",
         "targetComponent": "string",
         "jobId": number,
         "firmwareUrl": "string",
         "version": "string"
       }

    2. Target components supported:
       • stm32: STM32 microcontroller firmware
       • esp32-d1: ESP32 device 1 firmware
       • esp32-d2: ESP32 device 2 firmware

3.2 Firmware Download
    1. HTTP client configuration:
       • Uses Amazon Root CA for SSL verification
       • Configurable timeout (15 seconds)
       • Buffer size: 1024 bytes
       • Keep-alive enabled

    2. Download process:
       • Downloads firmware to SPIFFS storage
       • Progress tracking with percentage updates
       • Error handling for network issues
       • Duplicate job detection

3.3 Firmware Flashing

    A. For ESP32 Updates:
       1. Partition selection:
          • Uses next available update partition
          • Handles OTA size dynamically

       2. Flashing process:
          • Reads firmware in 1024-byte chunks
          • Writes to OTA partition
          • Verifies write operations
          • Commits update on success

    B. For STM32 Updates:
       1. Protocol implementation:
          • Frame-based communication
          • CRC32 verification
          • Acknowledgment handling
          • Retry mechanism

       2. Frame structure:
          [4 bytes SOF] + [4 bytes FrameID] + [2 bytes Length] + 
          [16 bytes Data] + [4 bytes CRC] + [4 bytes EOF]

3.4 Status Reporting
    1. Success reporting:
       • Updates NVS storage
       • Sends MQTT acknowledgment
       • Includes timestamp and job ID

    2. Failure handling:
       • Error code and message reporting
       • Automatic retry mechanism
       • Timeout handling
       • Recovery procedures

4. Error Handling
----------------
4.1 Download Errors
    • Network connectivity issues
    • HTTP status code errors
    • File system errors
    • Memory allocation failures

4.2 Flash Errors
    • Partition errors
    • Write verification failures
    • Communication timeouts
    • CRC verification failures

4.3 Recovery Mechanisms
    • Automatic retries for failed operations
    • State preservation in NVS
    • Watchdog timer integration
    • Error logging and reporting

5. Security Considerations
-------------------------
5.1 SSL/TLS Verification
    • Amazon Root CA certificate validation
    • Secure firmware download
    • Encrypted communication

5.2 Firmware Verification
    • CRC32 checksums
    • Partition validation
    • Write verification

6. Performance Considerations
----------------------------
6.1 Memory Management
    • PSRAM usage for large buffers
    • Dynamic allocation for MQTT messages
    • Efficient buffer handling

6.2 Timing
    • Download timeout: 15 seconds
    • Flash operation timeouts
    • Watchdog timer integration

7. Integration Points
--------------------
7.1 MQTT Topics
    • ota/ack: OTA acknowledgment
    • devices/{deviceCode}/stm32/ota/ack: STM32-specific acknowledgment

7.2 Storage
    • SPIFFS for temporary firmware storage
    • NVS for OTA status and configuration

7.3 Communication
    • UART for STM32 communication
    • HTTP for firmware download
    • MQTT for command and status

8. Best Practices
----------------
8.1 Pre-update Checks
    • Verify available space
    • Check network connectivity
    • Validate firmware integrity

8.2 During Update
    • Monitor progress
    • Handle interruptions
    • Maintain system stability

8.3 Post-update
    • Verify successful update
    • Clean up temporary files
    • Report final status 