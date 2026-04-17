# MQTT Logic Summary

## Scope

This report is based on confirmed MQTT-related logic found across the full workspace. Only topics and JSON fields that are explicitly parsed or subscribed in code are included. If a topic, field, or behavior is only mentioned in comments or examples but not confirmed by executable code, it is marked as `not confirmed in code`.

## Confirmed Subscribed Topics

- `foodcycle/{device-mac}/command`
  - Confirmed in `AWS::AWS_manageConnection()` where `expectedTopic = "foodcycle/" + subscribedMac + "/command"` and `client.subscribe(expectedTopic.c_str())` is called.
  - `subscribedMac` is initialized from `gSYSTEM_MAC` in `AWS::AWS_initialize()`.

## Topic and Payload Analysis

| Topic | JSON Field | Type | Meaning | Global Variable Updated | Function Triggered | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `foodcycle/{device-mac}/command` | `command` | `string` required | Selects which remote action to run. Confirmed values parsed in code: `ESP_SETTINGS`, `STM_STARTDRAWER`, `ESP_DEVMODE`, `STM_RESET`, `STM_REBOOT`, `ESP_BRIDGE_SEND`, `ESP_STATUS`, `ESP_RESTART`, `ESP_REPROVISION`, `ESP_ACTIVATEBLE`, `ESP_CHECKFORUPDATES`, `ESP_DOWNLOADASSETS`, `STM_UPDATEFREQ`, `STM_UPDATEFREQ2`, `STM_INSTALLFIRMWARE`, `STM_UPDATEFREQ1`, `STM_WASTEREDUCTION`, `STM_TESTWATERPUMP`, `STM_STARTSELFTEST`, `STM_TESTGRINGINMOTOR`, `STM_PARAMETER_WRITE`, `STM_PARAMETER_READ`, `STM_FORCEFIRMWAREINSTALL` | Command-dependent. Confirmed direct updates include `gTriggerCMD`, `gOVERRIDEcommands`, and `gVerbosePrints`. Some command values cause no direct global update beyond an immediate response. | `aws_defaultRemoteCommandCallback()` always handles this field first. Depending on the `command` value, downstream execution goes through `AWS_sendCommandResponse()`, `TRIGGERS_process()`, `PROCESS_GOTOScreenCalls()`, `myhardware.sendButtonEvent()`, `myhardware.writeSensorData()`, `myhardware.readSensorData()`, `ota.copyFullAssetListToTask()`, or OTA/UI state transitions. | Affects multiple domains depending on command value: remote control, OTA, parameter update, and status reporting. Device busy gating is enforced for most commands when `gDeviceStatus != PROVISIONED && gDeviceStatus != ONLINE`. `ESP_STATUS` is a status-reporting query and returns `READY` or `DEVICE BUSY`. |
| `foodcycle/{device-mac}/command` | `payload` | `string` optional | Additional payload for `ESP_BRIDGE_SEND`. Confirmed example behavior forwards the raw payload string across the inter-drawer bridge. | `gTriggerCMD` becomes `BRIDGE_SEND\|{payload}` | `aws_defaultRemoteCommandCallback()` parses `payload`; `TRIGGERS_process()` then calls `myhardware.sendBridgeCommand(tokens[1].c_str())` | Remote control behavior. Only confirmed for `ESP_BRIDGE_SEND`. Optional for all other commands. |
| `foodcycle/{device-mac}/command` | `parameter` | `string` optional | Register/address selector for `STM_PARAMETER_WRITE` | No standalone global is updated; the value is embedded into `gTriggerCMD` as `STM_PARAMETER_WRITE\|{parameter}\|{value}\|` | `aws_defaultRemoteCommandCallback()` parses it; `TRIGGERS_process()` then calls `myhardware.writeSensorData(tokens[1], tokens[2].toInt())` | Parameter update behavior. Optional and only confirmed for `STM_PARAMETER_WRITE`. |
| `foodcycle/{device-mac}/command` | `value` | `string` or `number` optional | Write value paired with `parameter` for `STM_PARAMETER_WRITE` | No standalone global is updated; the field is embedded into `gTriggerCMD` as `STM_PARAMETER_WRITE\|{parameter}\|{value}\|` | `aws_defaultRemoteCommandCallback()` parses it; `TRIGGERS_process()` then calls `myhardware.writeSensorData(tokens[1], tokens[2].toInt())` | Parameter update behavior. Confirmed write path only. |
| `foodcycle/{device-mac}/command` | `value` | `string` optional | Register/address to read for `STM_PARAMETER_READ` | No direct global in callback; `gTriggerCMD` becomes `STM_PARAMETER_READ\|{value}\|`. Later, `HARDWARE::pollForSensorReadResponseNonBlocking()` updates `gTriggerCMD` again to `STM_RESULT\|{addr}\|{result}\|` or timeout. | `aws_defaultRemoteCommandCallback()` parses it; `TRIGGERS_process()` calls `myhardware.readSensorData(tokens[1])`; later `TRIGGERS_process()` handles `STM_RESULT` and calls `AWS_sendCommandResponse()` | Parameter update and status reporting behavior. The MQTT request starts a read; the eventual result is returned on the response topic, not on the command topic. |
| `foodcycle/{device-mac}/command` | `value` | `string` optional | Firmware file name for `STM_FORCEFIRMWAREINSTALL` | `gTriggerCMD` becomes `STM_FORCEFIRMWAREINSTALL\|{filename}\|` if the filename ends with `.bin`; otherwise no trigger is set | `aws_defaultRemoteCommandCallback()` validates the suffix; `TRIGGERS_process()` then queues the filename into `ASSETQUEUE` and sets `gOVERRIDEcommands = GOTO_ASSETS_DOWNLOAD` | OTA-related behavior for STM32 firmware distribution. If the file type is not `.bin`, a response with `ERROR-wrong file type` is sent. |
| `foodcycle/{device-mac}/command` | `value` | `number` optional | Numeric value for `STM_UPDATEFREQ`, `STM_UPDATEFREQ2`, `STM_UPDATEFREQ1`, or `STM_WASTEREDUCTION` | `not confirmed in code` | Parsed in `aws_defaultRemoteCommandCallback()` only; no downstream action beyond serial print and command response is confirmed | Marked `not confirmed in code` for functional effect. These appear to be placeholders or partially implemented remote commands. |
| `foodcycle/{device-mac}/command` | `value` | `not confirmed in code` | A `value` field is shown in a comment example for `ESP_SETTINGS`, but the actual handler ignores it | `not confirmed in code` | `aws_defaultRemoteCommandCallback()` handles `ESP_SETTINGS` by immediately responding `EXECUTED`; no field access for `value` is present | Marked `not confirmed in code` for runtime effect. |

## Related Functions and File Locations

### Subscribed Topic Registration

- `AWS::AWS_initialize()` in [AWS.cpp](AWS.cpp)
  - Initializes `subscribedMac` from `gSYSTEM_MAC`
- `AWS::AWS_manageConnection()` in [AWS.cpp](AWS.cpp)
  - Reconnects MQTT and subscribes to `foodcycle/{mac}/command`
- `AWS::AWS_setCommandCallback()` in [AWS.cpp](AWS.cpp)
  - Registers the MQTT callback with `PubSubClient`
- `SETTINGS_load()` in [main.ino](main.ino)
  - Calls `myaws.AWS_setCommandCallback(nullptr)` to install the default command callback

### Incoming MQTT Command Handling

- `aws_defaultRemoteCommandCallback()` in [AWS.cpp](AWS.cpp)
  - Parses incoming JSON fields: `command`, `payload`, `parameter`, `value`
  - Sends immediate command responses
  - Sets `gTriggerCMD` and `gOVERRIDEcommands` for deferred actions

### Deferred Trigger Processing

- `TRIGGERS_process()` in [main.ino](main.ino)
  - Executes deferred actions from `gTriggerCMD`
  - Handles OTA asset downloads, firmware download triggers, STM button events, bridge forwarding, parameter write/read requests, and STM readback result responses
- `PROCESS_GOTOScreenCalls()` in [main.ino](main.ino)
  - Executes deferred UI/state transitions from `gOVERRIDEcommands`
  - Confirmed MQTT-driven flows include restart, BLE activation, OTA check, ESP32 firmware download, STM32 transfer screen, and asset download flow

### Hardware / Parameter / Bridge Actions Triggered by MQTT

- `HARDWARE::sendButtonEvent()` in [HARDWARE.cpp](HARDWARE.cpp)
  - Sends STM32 button/control events for commands such as reboot, self-test, start drawer, and bootloader start
- `HARDWARE::writeSensorData()` in [HARDWARE.cpp](HARDWARE.cpp)
  - Executes `STM_PARAMETER_WRITE`
- `HARDWARE::readSensorData()` in [HARDWARE.cpp](HARDWARE.cpp)
  - Starts `STM_PARAMETER_READ`
- `HARDWARE::pollForSensorReadResponseNonBlocking()` in [HARDWARE.cpp](HARDWARE.cpp)
  - Completes STM parameter reads by writing `STM_RESULT|...` into `gTriggerCMD`
- `HARDWARE::sendBridgeCommand()` in [HARDWARE.cpp](HARDWARE.cpp)
  - Executes forwarded payloads from `ESP_BRIDGE_SEND`
- `HARDWARE::sendBridgeCmd()` in [HARDWARE.cpp](HARDWARE.cpp)
  - Sends inter-drawer bridge control commands initiated through MQTT-triggered flows

### MQTT Response Publishing

- `AWS::AWS_sendCommandResponse()` in [AWS.cpp](AWS.cpp)
  - Publishes command responses to `fc75/tx/response`
- `AWS::AWS_sendHeartbeat()` in [AWS.cpp](AWS.cpp)
  - Publishes heartbeat telemetry
- `AWS::AWS_sendEvents()` in [AWS.cpp](AWS.cpp)
  - Publishes error, OTA, and system log events to their configured MQTT topics

## Notes

- No other inbound MQTT subscription topics were confirmed in executable code.
- Comment blocks mention example command payloads and a remote command topic format, but the only active subscribe logic confirmed in code is `foodcycle/{device-mac}/command`.
- `DEV_RESPONSE` is defined in configuration, but `AWS_sendCommandResponse()` currently publishes to `AWS_RESPONSE` unconditionally; this is a confirmed implementation detail, not a guess.
