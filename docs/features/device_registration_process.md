# Device Registration Process

## Prerequisites
1. WiFi Connection
   - Device must be connected to WiFi network
   - IP address must be assigned
   - Network connectivity must be established

2. Time Synchronization
   - Device must synchronize with NTP server (pool.ntp.org)
   - System time must be valid (year >= 2023)

3. Hardware Requirements
   - PSRAM must be initialized
   - STM32 UUID must be available (either from NVS or UART)

## Registration Steps

### 1. Initial Setup
- Wait for WiFi connection and IP assignment
- Synchronize time with NTP server
- Verify PSRAM initialization
- Obtain STM32 UUID from NVS or UART

### 2. MQTT Client Configuration
- Generate unique client ID: `FCS75-{MAC_ADDRESS}`
- Configure MQTT connection parameters:
  - AWS IoT endpoint and port
  - SSL/TLS certificates
  - Keepalive settings
  - Buffer sizes
  - Auto-reconnect settings

### 3. Registration Message
- Create registration payload:
```json
{
  "stm32Uid": "<STM32_UUID>",
  "esp32Mac": "<MAC_ADDRESS>",
  "role": "esp32-d1" or "esp32-d2",
  "firmwareVersion": "v1.0.0"
}
```
- Publish to topic: `devices/register`
- Subscribe to acknowledgment topic: `devices/{MAC_ADDRESS}/register/ack`

### 4. Registration Response Handling
- Receive response on acknowledgment topic
- Parse response JSON:
```json
{
  "deviceId": "<ASSIGNED_DEVICE_ID>",
  "status": "<REGISTRATION_STATUS>"
}
```
- Store device ID:
  - Update global variable `g_deviceCode`
  - Save to NVS storage (namespace: "my-app", key: "devicecode")

### 5. Post-Registration Setup
- Report online status
- Subscribe to OTA update topics
- Report any pending OTA status
- Start periodic heartbeat reporting (60-second interval)

## Error Handling
- Retry registration if no response received
- Handle network disconnections
- Manage MQTT connection failures
- Handle invalid registration responses

## Storage
- Device ID stored in NVS
- Registration status tracked
- Connection state maintained
- OTA status tracked

## Monitoring
- Periodic heartbeat reports
- Online status monitoring
- Connection state tracking
- OTA update status reporting 