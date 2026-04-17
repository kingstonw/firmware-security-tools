# AWS Remote Command Execution Map

## Scope

This document maps each requested remote command to its final runtime action in code:

- Parse and routing entry: `aws_defaultRemoteCommandCallback(...)` in AWS.cpp
- Deferred execution entry: `TRIGGERS_process()` in main.ino
- STM32 transport methods: `sendButtonEvent`, `writeSensorData`, `readSensorData` in HARDWARE.cpp

## Command Matrix

| Command | Parse Path | Trigger / State Set | Final Action | Classification | Implementation Status |
| --- | --- | --- | --- | --- | --- |
| ESP_SETTINGS | AWS.cpp:254 | immediate ACK + return | No runtime change (commented restart) | ESP32 local | Partial (ACK only) |
| STM_STARTDRAWER | AWS.cpp:258 | `gTriggerCMD = "STM_STARTDRAWER1"` | `sendButtonEvent(..., STM32_BTN1CLICK)` in main.ino:1136-1138 | Send event to STM32 | Implemented |
| ESP_DEVMODE | AWS.cpp:263 | `gTriggerCMD = "ESP_DEVMODE"` | Toggle `gVerbosePrints` in main.ino:1143-1144 | ESP32 local | Implemented |
| STM_RESET | AWS.cpp:267 | `gTriggerCMD = "STM_RESET"` | No matching branch in `TRIGGERS_process` | None (no STM dispatch) | Not implemented |
| STM_REBOOT | AWS.cpp:272 | `gTriggerCMD = "STM_REBOOT"` | `sendButtonEvent(..., STM32_REBOOT)` in main.ino:1133-1134 | Send event to STM32 | Implemented |
| ESP_BRIDGE_SEND | AWS.cpp:276 | `gTriggerCMD = "BRIDGE_SEND\|{payload}"` | `sendBridgeCommand(payload)` in main.ino:1160-1164 | ESP-ESP bridge command (not STM button event) | Implemented |
| ESP_STATUS | AWS.cpp:285 | immediate response | Return `READY` or `DEVICE BUSY` based on `gDeviceStatus` | ESP32 local | Implemented |
| ESP_RESTART | AWS.cpp:305 | `gOVERRIDEcommands = GOTO_RESTART` | `PROCESS_GOTOScreenCalls` -> `ESP.restart()` at main.ino:1263-1270 | ESP32 local | Implemented |
| ESP_REPROVISION | AWS.cpp:309 | `gOVERRIDEcommands = GOTO_PROVISIONING_FACTORYRESET` | Factory reset provisioning files then `GOTO_RESTART` at main.ino:1551-1557 | ESP32 local | Implemented |
| ESP_ACTIVATEBLE | AWS.cpp:313 | `gTriggerCMD = "BRIDGE_STARTBLE"` + `gOVERRIDEcommands = GOTO_BLE_START` | Start BLE flow locally and send bridge BLE start command | ESP32 local + ESP bridge | Implemented |
| ESP_CHECKFORUPDATES | AWS.cpp:318 | `gOVERRIDEcommands = GOTO_UI_CHECKVERSION` | Set OTA check trigger in main.ino:1252-1261 | ESP32 local | Implemented |
| ESP_DOWNLOADASSETS | AWS.cpp:322 | `gTriggerCMD = "ESP_DOWNLOADASSETS"` | Queue full asset list and `GOTO_ASSETS_DOWNLOAD` in main.ino:1112-1116 | ESP32 local | Implemented |
| STM_UPDATEFREQ | AWS.cpp:325 | none (reads value only) | Serial print only | None (no STM dispatch) | Not implemented |
| STM_UPDATEFREQ2 | AWS.cpp:330 | none (reads value only) | Serial print only | None (no STM dispatch) | Not implemented |
| STM_INSTALLFIRMWARE | AWS.cpp:335 | `gTriggerCMD = "STM_INSTALLFIRMWARE"` | Send STM bootloader event `STM32_START_BOOTLOADER` 4 times in main.ino:1123-1127 | Send event to STM32 | Implemented |
| STM_UPDATEFREQ1 | AWS.cpp:340 | none (reads value only) | Serial print only, response says NOT PROGRAMMED YET | None (no STM dispatch) | Not implemented |
| STM_WASTEREDUCTION | AWS.cpp:350 | none (reads value only) | Serial print only, response says NOT PROGRAMMED YET | None (no STM dispatch) | Not implemented |
| STM_TESTWATERPUMP | AWS.cpp:355 | `gTriggerCMD = "STM_TESTWATERPUMP"` | `sendButtonEvent(..., STM32_TEST_WTR_PUMP)` in main.ino:1130-1131 | Send event to STM32 | Implemented |
| STM_STARTSELFTEST | AWS.cpp:360 | `gTriggerCMD = "STM_STARTSELFTEST"` | `sendButtonEvent(..., STM32_SELF_TEST)` in main.ino:1157-1158 | Send event to STM32 | Implemented |
| STM_TESTGRINGINMOTOR | AWS.cpp:364 | `gTriggerCMD = "STM_TESTGRINGINMOTOR"` | `sendButtonEvent(..., STM32_BTN2CLICK)` in main.ino:1140-1141 | Send event to STM32 | Implemented |
| STM_PARAMETER_WRITE | AWS.cpp:368 | `gTriggerCMD = "STM_PARAMETER_WRITE\|{addr}\|{value}\|"` | `writeSensorData(addr, value)` in main.ino:1150-1151 -> HARDWARE.cpp:925 | Send write frame to STM32 | Implemented |
| STM_PARAMETER_READ | AWS.cpp:375 | `gTriggerCMD = "STM_PARAMETER_READ\|{addr}\|"` | `readSensorData(addr)` in main.ino:1152, then async read result sets `STM_RESULT\|...` in HARDWARE.cpp:1029/1075 and sends AWS response in main.ino:1154-1156 | Send read frame to STM32, then report back | Implemented |
| STM_FORCEFIRMWAREINSTALL | AWS.cpp:379 | `gTriggerCMD = "STM_FORCEFIRMWAREINSTALL\|{file}.bin\|"` (only if `.bin`) | Push file into asset queue + `GOTO_ASSETS_DOWNLOAD` in main.ino:1146-1148 | ESP32 local workflow (indirect STM via update pipeline) | Implemented |

## ESP32 Local vs STM32 Dispatch Summary

### ESP32 local execution

- ESP_SETTINGS (ACK only)
- ESP_DEVMODE
- ESP_STATUS
- ESP_RESTART
- ESP_REPROVISION
- ESP_ACTIVATEBLE (plus bridge sync)
- ESP_CHECKFORUPDATES
- ESP_DOWNLOADASSETS
- STM_FORCEFIRMWAREINSTALL (local queue/update orchestration)

### STM32 event/frame dispatch

- STM_STARTDRAWER -> `STM32_BTN1CLICK`
- STM_REBOOT -> `STM32_REBOOT`
- STM_INSTALLFIRMWARE -> `STM32_START_BOOTLOADER`
- STM_TESTWATERPUMP -> `STM32_TEST_WTR_PUMP`
- STM_STARTSELFTEST -> `STM32_SELF_TEST`
- STM_TESTGRINGINMOTOR -> `STM32_BTN2CLICK`
- STM_PARAMETER_WRITE -> register write frame (`writeSensorData`)
- STM_PARAMETER_READ -> register read frame (`readSensorData`) then `STM_RESULT`

### Not implemented (currently no runtime action)

- STM_RESET
- STM_UPDATEFREQ
- STM_UPDATEFREQ1
- STM_UPDATEFREQ2
- STM_WASTEREDUCTION

## Key Reference Locations

- AWS command parser: AWS.cpp:234-399
- Deferred trigger executor: main.ino:1095-1206
- Screen/state override executor: main.ino:1220-1625
- STM event transport: HARDWARE.cpp:728-776 (`sendButtonEvent`)
- STM register write: HARDWARE.cpp:925-968 (`writeSensorData`)
- STM register read + async result trigger: HARDWARE.cpp:970-1078 (`readSensorData`, `pollForSensorReadResponseNonBlocking`)
- STM event constants: config.h:437-443
