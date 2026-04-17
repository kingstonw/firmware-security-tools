# ESP32 OTA Detailed Design

## Document Priority (Source of Truth)

1. `docs/AI_Guidelines.md`
2. `docs/Claude.md`
3. `docs/ai_prompts/base.md`
4. `docs/ai_prompts/analysis.md`
5. `docs/ai_prompts/verification.md`
6. Arduino firmware source files:
   - `config.h` — constants, paths, intervals, state enums
   - `OTA.h` / `OTA.cpp` — OTA class, version check, download, asset management
   - `main.ino` — state machine, OTA triggers, download manager, telemetry
   - `AWS.h` / `AWS.cpp` — MQTT connection, remote command handling, telemetry publish
   - `logger.h` / `logger.cpp` — log types and event codes

**Rule applied:** Do not guess missing logic. Explicitly mark unknowns.

---

## 1. Purpose

This document defines the complete over-the-air (OTA) update behavior of the Arduino firmware on the FC75 ESP32 device. It covers:

- All paths by which an OTA check is triggered (periodic, MQTT command, post-provisioning)
- How `version.json` is fetched and parsed from an AWS S3 bucket
- How local vs. remote firmware versions are compared
- The full decision tree for what action to take after a version check
- How the ESP32 firmware binary is downloaded and flashed
- How STM32 firmware and display assets are downloaded to SPIFFS
- All UI screens displayed before, during, and after OTA
- What MQTT/telemetry messages are sent
- How the device exits OTA and reboots

This document is the reference for porting this behavior to an ESP-IDF project.

---

## 2. Scope

**In scope:**
- ESP32 firmware OTA (self-update via `esp_ota` / Arduino `Update` library)
- STM32 firmware download (binary stored to SPIFFS, applied via bootloader protocol)
- Display asset download (fonts, icons, layout files to SPIFFS `/assets/`)
- OTA version check state machine
- UI state transitions during OTA
- MQTT remote OTA commands
- OTA telemetry and logging

**Out of scope:**
- BLE provisioning flow (separate document)
- STM32 internal bootloader protocol (see `HARDWARE.cpp`)
- Backend / AWS Lambda / S3 bucket configuration

---

## 3. Source of Truth

Derived exclusively from the following files. No behavior is invented or assumed.

| File | Role |
|---|---|
| `config.h` | S3 hosts, file paths, MQTT topics, timing intervals, state enums |
| `OTA.h` | OTA class interface, state variables |
| `OTA.cpp` | Version check state machine, firmware download, asset download |
| `main.ino` | Top-level state machine, OTA trigger, download manager, telemetry |
| `AWS.cpp` | MQTT connection management, remote command callback |
| `logger.h` | Log event types |

---

## 4. OTA High-Level Flow Overview

The OTA system has three distinct types of updates, each with its own path:

```
Type 1: ESP32 Firmware Update
  version.json → compareVersions → FIRMWARE_UPDATECONFIRM (screen 19)
    → FIRMWARE_DOWNLOAD → Update.begin/write/end → ESP.restart()

Type 2: STM32 Firmware Update
  version.json → compareVersions (STM32 only, drawer 1) → add to ASSET_QUEUE
    → download to /stm32/package.bin → buttonEventCb(0x11) × 3 → bootloader

Type 3: Asset Update
  version.json → assetsListCSV → populate /ASSETS_queue.txt
    → download each file to /assets/ → ASSETS_COMPLETE → GOTO_UI_IDLE
```

All three updates flow through a single version check state machine (`checkVersionNonBlocking`).
Asset updates always wait until ESP32 firmware is confirmed up to date.

---

## 5. MQTT Trigger Path

### 5.1 MQTT Connection

Source: `AWS.cpp`, `AWS::AWS_manageConnection()`

- The device subscribes to topic: `foodcycle/{mac}/command`
- MAC is the device MAC address (with colons, as stored in `subscribedMac`)
- Subscription is maintained by `AWS_manageConnection()`, called every main loop iteration
- On reconnect, `remoteSubscribed` is set to false to force re-subscription

```
MQTT broker: {aws_endpoint}:8883 (TLS, port 8883)
Subscribe topic: foodcycle/{mac}/command
```

### 5.2 MQTT Receive and Parse

Source: `AWS.cpp`, `aws_defaultRemoteCommandCallback()`

When a message arrives on the subscribed topic:
1. The PubSubClient callback `aws_defaultRemoteCommandCallback()` fires
2. The payload is parsed as JSON using `StaticJsonDocument<256>`
3. The `"command"` field is extracted, trimmed, and uppercased

```json
// Example incoming payload
{ "command": "ESP_CHECKFORUPDATES" }
```

### 5.3 OTA-Related MQTT Commands

The following commands are confirmed to affect OTA behavior:

| MQTT Command | Action | Where |
|---|---|---|
| `ESP_CHECKFORUPDATES` | `gOVERRIDEcommands = GOTO_UI_CHECKVERSION` | `AWS.cpp:338` |
| `ESP_DOWNLOADASSETS` | `gTriggerCMD = "ESP_DOWNLOADASSETS"` | `AWS.cpp:341-343` |
| `ESP_DOWNLOADFIRMWARE` | `gTriggerCMD = "ESP_DOWNLOADFIRMWARE"` | `TRIGGERS_process()` |
| `ESP_UPDATEON` | `gSkipVersionCheck = 0` (enables OTA checks) | `AWS.cpp:293` |
| `ESP_UPDATEOFF` | `gSkipVersionCheck = 1` (disables OTA checks) | `AWS.cpp:299` |
| `STM_INSTALLFIRMWARE` | `gTriggerCMD = "STM_INSTALLFIRMWARE"` → triggers bootloader | `AWS.cpp:354` |
| `STM_FORCEFIRMWAREINSTALL` | Adds specific `.bin` to asset queue → download | `AWS.cpp:398` |

### 5.4 Command Response on MQTT Trigger

After processing an OTA-related command, the device publishes a response:

```
Topic: fc75/tx/response (PROD) or fc75/dev/response (DEV)
Payload: { "mac": "...", "type": "response", "timestamp": "...", "command": "...", "status": "EXECUTED" }
```

Source: `AWS.cpp`, `AWS_sendCommandResponse()`

**Note:** `ESP_DOWNLOADFIRMWARE` and `STM_FORCEFIRMWAREINSTALL` also call `AWS_sendCommandResponse()` with `"EXECUTED"`.

### 5.5 Command Processing Path via `gTriggerCMD`

Source: `main.ino`, `TRIGGERS_process()`

For commands routed through `gTriggerCMD`:
- `ESP_DOWNLOADASSETS` → `ota.copyFullAssetListToTask(&spiff)` → `gOVERRIDEcommands = GOTO_ASSETS_DOWNLOAD`
- `ESP_DOWNLOADFIRMWARE` → `gOVERRIDEcommands = GOTO_FIRMWARE_DOWNLOAD`

---

## 6. OTA Check Trigger Conditions

An OTA version check is triggered by any of the following confirmed paths:

### 6.1 Periodic (Time-Based) — Every 12 Hours

Source: `main.ino`, `OTA_checkVersion()`, called from `ONLINE` state every 10 seconds

```cpp
static constexpr unsigned long OTA_CHECK_INTERVAL_MS = 12UL * 60UL * 60UL * 1000UL;
```

Conditions that must ALL be true:
1. `gDeviceStatus == ONLINE`
2. `millis() - lastOTACheck >= OTA_CHECK_INTERVAL_MS` (12 hours)
3. `myui.isButtonPressed() == false`
4. `gSYSTEM_WIFI != 0`
5. `wifi.isConnected() == true`
6. NTP time sync is complete (`gBaseEpoch != 0`), or 60-second timeout has elapsed

When triggered:
```cpp
gOVERRIDEcommands = GOTO_UPDATEMANAGER;
gUpdateManagerState = 1;
lastOTACheck = millis();
```

### 6.2 MQTT Remote Trigger — `ESP_CHECKFORUPDATES`

Source: `AWS.cpp`, `aws_defaultRemoteCommandCallback()`

```cpp
gOVERRIDEcommands = GOTO_UI_CHECKVERSION;
```

Note: This sets `GOTO_UI_CHECKVERSION` directly (not `GOTO_UPDATEMANAGER`). `GOTO_UI_CHECKVERSION` also sets `ota.checkVersionTrigger = 1` and transitions to `gUpdateManagerState = 2`.

### 6.3 Post-Provisioning / Post-WiFi-Test

Source: `main.ino`, `TESTWIFI` state

After BLE provisioning completes, the device enters `TESTWIFI`. When WiFi connects:
```cpp
ota.checkVersionTrigger = 1;
gOVERRIDEcommands = GOTO_UPDATEMANAGER;
```

### 6.4 Skip Condition

Source: `main.ino`, `UPDATEMANAGER` case

If `gSkipVersionCheck == true`:
```cpp
ota.checkVersionTrigger = 0;
lastOTACheck = millis();
gOVERRIDEcommands = GOTO_UI_IDLE;
return;
```

No version check is performed. Can be set persistently via SPIFFS or via `ESP_UPDATEOFF` MQTT command.

### 6.5 `checkDrawerUIPageIds()` Intercept

Source: `main.ino`, `checkDrawerUIPageIds()`

If `ota.checkVersionTrigger == 1` and `gSYSTEM_AWS == true` and device is not already in `UPDATEMANAGER`:
```cpp
gOVERRIDEcommands = GOTO_UPDATEMANAGER;
gUpdateManagerState = 1;
```

This ensures a version check triggered from any state is routed to the update manager before other state changes.

---

## 7. `version.json` Fetch Path

### 7.1 Host Selection

Source: `OTA.cpp`, `OTA::begin()`

At startup, the host is set based on `config::DEVICE::FUNCTIONMODE`:

| Mode | Version Host | Asset Host |
|---|---|---|
| `"DEV"` | `fc75firmwaredev.s3.ca-central-1.amazonaws.com` | `https://fc75assetsdev.s3.ca-central-1.amazonaws.com/` |
| `"PROD"` (default) | `fc75firmware.s3.ca-central-1.amazonaws.com` | `https://fc75assets.s3.ca-central-1.amazonaws.com/` |

### 7.2 HTTP Request

Source: `OTA.cpp`, `checkVersionNonBlocking()`, `VC_IDLE` state

```
GET /version.json HTTP/1.1
Host: {versionhost}
```

Port: 443 (HTTPS)
TLS: `WiFiClientSecure` with CA certificate from `spiff.getCA()`

### 7.3 Retry Logic

- Up to **5 attempts** (`vcAttempts >= 5`)
- **20-second wait** between attempts (`vcWaitUntil = now + 20000UL`)
- On 5th failure: `checkVersionTrigger = 0`, resets all state
- Header timeout: **10 seconds**
- Body timeout: **10 seconds** after first data received

---

## 8. `version.json` Schema and Parsing Logic

### 8.1 JSON Structure (Confirmed from Code)

Source: `OTA.cpp` lines 226–232, `OTA.h` doc comment

```json
{
  "fc75": {
    "devices": {
      "primary": {
        "version": "1.0.10",
        "path": "/fc75-primary-1.0.10.bin",
        "assets": "FONT1.bin,ICON1.raw,EN_Lang.json,"
      },
      "dev": {
        "version": "...",
        "path": "...",
        "assets": "..."
      },
      "stm32": {
        "version": "02.18.1.8",
        "path": "/STM02.18.1.8.bin",
        "localfwversion": "..."
      }
    }
  }
}
```

**Note:** A `"host"` field under `devices[deviceKey]` exists in the JSON schema (`doc["fc75"]["devices"][deviceKey]["host"]`) but is **commented out** in the parsing code. The firmware always uses `versionhost` as the download host.

### 8.2 Parsing Code

Source: `OTA.cpp`, `checkVersionNonBlocking()`, `VC_WAITING_BODY` state

```cpp
StaticJsonDocument<512> doc;
DeserializationError error = deserializeJson(doc, vcResponse);
```

Fields extracted after successful parse:

| Variable | JSON path | Description |
|---|---|---|
| `remoteVersion` | `fc75.devices[deviceKey].version` | Remote ESP32 firmware version |
| `firmwarePath` | `fc75.devices[deviceKey].path` | Remote firmware binary path |
| `assetsListCSV` | `fc75.devices[deviceKey].assets` | Comma-separated asset filenames |
| `stm32Version` | `fc75.devices.stm32.version` | Remote STM32 firmware version |
| `stm32Path` | `fc75.devices.stm32.path` | STM32 firmware binary path |
| `stm32localVersion` | `fc75.devices.stm32.localfwversion` | STM32 localized firmware version string |

### 8.3 Device Key Selection

Source: `OTA.cpp`, `getDeviceKey()`

```cpp
if (config::DEVICE::FUNCTIONMODE == "DEV")  return "dev";
if (config::DEVICE::FUNCTIONMODE == "PROD") return "primary";
return "primary";  // default
```

### 8.4 Language File Appended to Asset List

After parsing, the current language file is always appended to `assetsListCSV`:

```cpp
String safeLangFile = langFile + ".json";   // e.g., "EN_Lang.json"
assetsListCSV += "," + safeLangFile;
```

Then `writeAssetsFullFile(spiff, assetsListCSV)` writes the full list to `/ASSETS_full.txt`.

---

## 9. Local Firmware Version Source

### 9.1 ESP32 Local Version

Source: `config.h`, `main.ino`

```cpp
static constexpr const char* VERSION = "1.0.66";   // compile-time constant
```

This constant is used directly in `compareVersions()`:
```cpp
bool needESP32Update = compareVersions(String(config::DEVICE::VERSION), remoteVersion);
```

### 9.2 STM32 Local Version

Source: `main.ino` setup, `spiff.loadSystemDetails()`

`gSYSTEM_STM32_FIRMWARE` is loaded from SPIFFS on boot via `loadSystemDetails()`. Its initial value (if not stored in SPIFFS) is `config::DEVICE::STMVERSION` (currently set to `"99.01.32"` in the current build to prevent accidental STM32 updates).

```cpp
bool needSTM32Update = compareVersions(String(gSYSTEM_STM32_FIRMWARE), stm32Version)
                       && (gSYSTEM_drawer == 1);
```

**STM32 updates only happen on Drawer 1** (`gSYSTEM_drawer == 1`).

---

## 10. Version Comparison Logic

Source: `OTA.cpp`, `OTA::compareVersions(const String& currentVersion, const String& newVersion)`

```
Format: "MAJOR.MINOR.PATCH"
Comparison: Lexicographic-numeric, field by field left to right
```

```cpp
sscanf(newVersion.c_str(),    "%d.%d.%d", &remote[0],  &remote[1],  &remote[2]);
sscanf(currentVersion.c_str(), "%d.%d.%d", &current[0], &current[1], &current[2]);

for (int i = 0; i < 3; i++) {
    if (remote[i] > current[i]) return true;   // Update needed
    if (remote[i] < current[i]) return false;  // No update needed
}
return false;  // Equal — no update needed
```

- Returns `true` if `newVersion > currentVersion` → update required
- Returns `false` if equal or `currentVersion > newVersion` → no update
- **Downgrade protection:** if local version is higher than remote, no update is applied

---

## 11. OTA Decision Rules

Source: `OTA.cpp`, `checkVersionNonBlocking()`, after JSON parse

Decisions are evaluated **in this exact priority order**:

### Priority 1 — Pending Assets in Queue

```cpp
bool assetsInQueue = (spiff.SPIFF_getTotalRecords(config::PATHS::ASSETQUEUE) > 0);
if (assetsInQueue) {
    gOVERRIDEcommands = GOTO_ASSETS_DOWNLOAD;
}
```

If `/ASSETS_queue.txt` has any records (from a previous interrupted download), resume immediately.

### Priority 2 — First-Time Provision (No Assets Ever Downloaded)

```cpp
bool wasProvisioned = (totalAssets < 1);  // /ASSETS_full.txt has 0 records
if (wasProvisioned) {
    copyFullAssetListToTask(spiff);        // copy full list to queue
    if (needSTM32Update) { /* add stm32 bin to queue */ }
    spiff.setSystemDetailByField(SPIFF_Manager::PROVISIONED, "0");
    gSYSTEM_PROVISIONEDFLAG = 0;
    gSYSTEM_FORCEASSETDOWNLOAD = 0;
    gOVERRIDEcommands = GOTO_ASSETS_DOWNLOAD;
}
```

If `/ASSETS_full.txt` has zero records, this is the first provision. Download all assets.

**Note:** `config::PATHS::PROVATFACT` (`/spiffImaged.txt`) is checked. If this file exists, `SPIFF_initRecord(ASSETQUEUE)` is used (clears the queue) instead of copying the full asset list. If it does not exist, `copyFullAssetListToTask()` is called to populate the queue.

### Priority 3 — Re-Provision

```cpp
bool wasReprovision = (totalAssets > 0 && gSYSTEM_PROVISIONEDFLAG);
if (wasReprovision) {
    // Same logic as Priority 2
    gOVERRIDEcommands = GOTO_ASSETS_DOWNLOAD;
}
```

`gSYSTEM_PROVISIONEDFLAG` is set during provisioning completion (`GOTO_PROVISIONING_COMPLETEDSETUP`).

### Priority 4 — Forced Asset Download

```cpp
if (gSYSTEM_FORCEASSETDOWNLOAD) {
    copyFullAssetListToTask(spiff);
    if (needSTM32Update) { /* add stm32 bin to queue */ }
    gSYSTEM_FORCEASSETDOWNLOAD = 0;
    gOVERRIDEcommands = GOTO_ASSETS_DOWNLOAD;
}
```

Can be set persistently via SPIFFS or triggered remotely. Also set when WiFi test times out:
```cpp
spiff.setSystemDetailByField(SPIFF_Manager::FORCE_ASSET, "1");
```

### Priority 5 — ESP32 Firmware Update Available

```cpp
else if (needESP32Update) {
    gOVERRIDEcommands = GOTO_FIRMWARE_UPDATECONFIRM;
}
```

**No asset download occurs when an ESP32 update is needed.** Assets are queued for download after the device reboots with the new firmware.

### Priority 6 — STM32 Firmware Update Needed

```cpp
else if (needSTM32Update) {
    spiff.writeFile("/stm32/version.txt", versionData, len, false);
    if (stm32Path not already in queue) {
        spiff.SPIFF_addRecord(config::PATHS::ASSETQUEUE, stm32Path.c_str(), "0", 200);
        gOVERRIDEcommands = GOTO_ASSETS_DOWNLOAD;
    } else {
        gUpdateManagerState = 3;
        gOVERRIDEcommands = GOTO_UPDATEMANAGER;
    }
}
```

### Priority 7 — Everything Up to Date

```cpp
else {
    Serial.println(F("[OTA] EVERYTHING IS UP TO DATE"));
    gOVERRIDEcommands = GOTO_UPDATEMANAGER;
    gUpdateManagerState = 3;
}
```

`UPDATEMANAGER` state 3 checks if any assets remain in the queue; if not, goes to `GOTO_UI_IDLE`.

### Decision Summary Table

| Condition | Action |
|---|---|
| `gSkipVersionCheck == true` | Skip all checks → `GOTO_UI_IDLE` |
| Assets in `/ASSETS_queue.txt` | Resume asset download → `GOTO_ASSETS_DOWNLOAD` |
| First provision (no assets ever) | Queue all assets → `GOTO_ASSETS_DOWNLOAD` |
| Re-provision (`gSYSTEM_PROVISIONEDFLAG`) | Queue all assets → `GOTO_ASSETS_DOWNLOAD` |
| `gSYSTEM_FORCEASSETDOWNLOAD` | Queue all assets → `GOTO_ASSETS_DOWNLOAD` |
| `needESP32Update` (remote > local) | Show confirm screen → `GOTO_FIRMWARE_UPDATECONFIRM` |
| `needSTM32Update` (remote > local, drawer 1) | Queue STM32 bin → `GOTO_ASSETS_DOWNLOAD` |
| All versions match | `gUpdateManagerState = 3` → `GOTO_UI_IDLE` |

---

## 12. Firmware URL Selection Logic

### 12.1 ESP32 Firmware URL

Source: `OTA.cpp`, `firmwareDownload_START()`

The firmware binary is fetched from:
```
HTTPS GET https://{versionhost}{firmwarePath}
```

Where:
- `versionhost` = `fc75firmware.s3.ca-central-1.amazonaws.com` (PROD) or `fc75firmwaredev.s3.ca-central-1.amazonaws.com` (DEV)
- `firmwarePath` = value from `version.json`, e.g., `/fc75-primary-1.0.10.bin`

**Note:** The `"host"` field in the `version.json` JSON schema is commented out in the parsing code. The firmware always uses `versionhost` (the same host used for the version check) as the download server for the binary.

### 12.2 STM32 Firmware URL

Source: `OTA.cpp`, `downloadAssetsFromS3_LOOP()`

STM32 firmware binary path comes from `stm32Path` extracted from `version.json`. The download URL is constructed as:
```
{assethost}{stm32Path}
```
Where `assethost` = `https://fc75assets.s3.ca-central-1.amazonaws.com/` (PROD).

The downloaded binary is stored locally as `/stm32/package.bin`.

### 12.3 Asset URLs

```
{assethost}{assetFilename}
```
e.g., `https://fc75assets.s3.ca-central-1.amazonaws.com/FONT1.bin`

---

## 13. Firmware Download Process

### 13.1 `firmwareDownload_START(ca)` — Initiation

Source: `OTA.cpp`, `OTA::firmwareDownload_START()`

Called from `PROCESS_GOTOScreenCalls()` when `GOTO_FIRMWARE_DOWNLOAD` is processed.

Steps:
1. Guard: if `downloadInProgress` is already true → return false (prevent parallel sessions)
2. Allocate `WiFiClientSecure*` with CA cert from `spiff.getCA()`
3. Set timeout: `firmwareClient->setTimeout(120000)` (120 seconds)
4. Connect to `versionhost:443`
5. Send HTTP GET for `firmwarePath`
6. Read HTTP headers (10-second timeout):
   - Extract `Content-Length` header
   - Stop at blank line
7. If `contentLength <= 0`: use `firmwareClient->available()` as fallback
8. Validate: `contentLength > 0 && contentLength <= ESP.getFreeSketchSpace()`
9. Call `Update.begin(contentLength)` to initialize OTA partition
10. Set `downloadInProgress = true`, reset `written = 0`
11. Return `true` (download can proceed)

Failure returns `false` and cleans up the client.

### 13.2 `firmwareDownload_LOOP()` — Chunked Download

Source: `OTA.cpp`, `OTA::firmwareDownload_LOOP()`

Called every main loop iteration from `FIRMWAREDOWNLOADING` state in `OTA_downloadManager()`.

Chunk size: **4096 bytes**

Each call:
1. Guard: `downloadInProgress && firmwareClient != nullptr`
2. Calculate `toRead = min(bufferSize, contentLength - written)`
3. If data available: `firmwareClient->read(buffer, toRead)` → update `lastData`
4. If no data: `delay(10)`; if no data for **60 seconds** → timeout → abort
5. Progress report to Serial every 1 second: `written/contentLength` bytes and %
6. Write chunk: `Update.write(buffer, actuallyRead)` — on failure → abort
7. When `written >= contentLength`:
   - Call `Update.end()` — on failure → `updateError = true`
   - On success: check `Update.isFinished()`
     - If finished: `updateFinished = true` → `Logger::log(LOGGER_OTA, 0x11, "")`
     - If not finished: `updateError = true` → `Logger::log(LOGGER_OTA, 0x12, "")`
8. Clean up `firmwareClient`

### 13.3 Flash Storage

ESP32 firmware is written **directly to the OTA flash partition** via the Arduino `Update` library. It is **not stored to SPIFFS**. The write happens chunk by chunk in `Update.write()`.

---

## 14. OTA Apply/Install Process

Source: `OTA.cpp`, `firmwareDownload_LOOP()` + `main.ino`, `OTA_downloadManager()`

### 14.1 ESP32 Firmware Apply

```
Update.begin(contentLength)    → Initialize OTA partition
Update.write(buffer, size)     → Write firmware chunk to flash
Update.end()                   → Finalize: verify hash/integrity
Update.isFinished()            → Confirm success
```

On success: `updateFinished = true`
On failure: `updateError = true`

### 14.2 Post-Flash Actions

Source: `main.ino`, `OTA_downloadManager()`

```cpp
if (ota.updateFinished) {
    Serial.println(F("[MAIN] OTA update finished. Rebooting..."));
    ota.copyFullAssetListToTask(&spiff);   // queue assets for post-reboot download
    gOVERRIDEcommands = GOTO_RESTART;     // triggers ESP.restart()
}
```

Before rebooting, all assets from `/ASSETS_full.txt` are copied to `/ASSETS_queue.txt`. On the next boot, the version check will detect `assetsInQueue > 0` and immediately start downloading assets.

### 14.3 `runInstructions()` — Currently Stubbed

Source: `OTA.cpp`, `OTA::runInstructions()`

The `runInstructions()` method exists but its restart logic is **commented out**:

```cpp
void OTA::runInstructions(JsonVariant instructions) {
    /*
    if (instructions["restart"] | 0) {
        Serial.println(F("[OTA] Instruction: Restarting device..."));
        delay(1000);
        ESP.restart();
    }
    */
}
```

**Confirmed: `runInstructions()` is not called or used in the current implementation.** Restart is handled directly via `GOTO_RESTART` in `OTA_downloadManager()`.

### 14.4 STM32 Firmware Apply

Source: `OTA.cpp`, `downloadAssetsFromS3_LOOP()`, end of DL_DOWNLOADING case

After `/stm32/package.bin` is successfully downloaded:
1. Old STM32 files in `/stm32/` are removed (keeping only `package.bin`)
2. SPIFFS flags set: `UPDATE_STM_FIRMWARE = "1"`, `STARTUP_IN_BOOTLOAD = "1"`
3. `gSYSTEM_STM32_FIRMWARE` RAM variable updated
4. `triggerSTMAfterDownload = true`
5. After queue is empty: sanity-check `package.bin` exists and is non-empty
6. If valid: `buttonEventCb(gSYSTEM_drawer, 0x11)` is called **3 times** with 1-second delays

The `0x11` event (`STM32_START_BOOTLOADER`) is sent via the UART hardware callback registered in `main.ino`:
```cpp
ota.setButtonEventCallback([&myhardware](int drawer, uint8_t event)->bool {
    return myhardware.sendButtonEvent(drawer, event);
});
```

---

## 15. UI State and Screen Mapping

### 15.1 Normal Operation (Before OTA)

| Screen | Number | When shown |
|---|---|---|
| READY | 4 | `ONLINE`, `UNDER_STM32_CONTROL`, after idle return |
| Logo | 12 | First load on boot |

### 15.2 Version Check

| Event | Screen | State |
|---|---|---|
| Entering version check | Screen 6 ("CHECKING FOR UPDATES") | `UPDATEMANAGER` (state 2) |

Screen 6 is loaded in `PROCESS_GOTOScreenCalls()` → `GOTO_UI_CHECKVERSION`.

**Note:** `gOVERRIDEcommands = GOTO_UI_CHECKVERSION` inside `checkVersionNonBlocking()` is commented out. The version check screen is loaded once at transition, not repeatedly during the HTTPS check.

### 15.3 Firmware Update Confirm

| Event | Screen | State |
|---|---|---|
| Update available | Screen 19 ("INSTALL UPDATE?") | `FIRMWAREDOWNLOADDECISION` |

- Progress bar counts down from 30 seconds
- `SPRITE_updateText("counter", String(secondsLeft))`
- `updateProgressBar("progressbar", 30, secondsLeft)`
- After 30-second timeout → `GOTO_FIRMWARE_DOWNLOAD` (auto-installs)
- User action during this 30 seconds: **Needs clarification** — button actions on screen 19 not confirmed from reviewed files

### 15.4 During Firmware Download

| Event | Screen | State |
|---|---|---|
| Download starting | Screen 21 (loading/generic working template) | Transition |
| Download in progress | Screen 2 ("DOWNLOADING FIRMWARE") | `FIRMWAREDOWNLOADING` |

Progress bar updated every loop:
```cpp
percentDone = (int)((100.0 * ota.written) / ota.contentLength);
mydisplay.updateProgressBar("progressbar", 100, percentDone);
```

### 15.5 During Asset Download

| Event | Screen | State |
|---|---|---|
| Asset download starting | Screen 10 ("DOWNLOADING ASSETS") | `ASSETDOWNLOADING` |

Progress bar and file count updated every loop:
```cpp
mydisplay.updateProgressBar("progressbar", 100, percent);
mydisplay.SPRITE_updateText("status",
    "DOWNLOADING " + String(ota.downloadingAsset) + " OF " + String(ota.totalAssetsInQueue));
```

### 15.6 Success

| Outcome | Screen | What Happens |
|---|---|---|
| Asset download complete (success) | Screen 16 ("DOWNLOAD COMPLETE" / `langMap["059"]`) | 5-second `ALERT_DISPLAY` → `GOTO_UI_IDLE` or `GOTO_STM32_ALERT` |
| ESP32 firmware update complete | Screen 13 ("RESTARTING" / `langMap["041"]`) | `ESP.restart()` immediately |

### 15.7 Failure

| Outcome | Screen | What Happens |
|---|---|---|
| Asset download failed | Screen 15 ("DOWNLOAD FAILED" / `langMap["021"]`) | 5-second `ALERT_DISPLAY` → `GOTO_UI_IDLE` or `GOTO_STM32_ALERT` |
| ESP32 firmware download failed | Screen 4 (READY/idle) | `GOTO_UPDATEMANAGER` (retry on next check) |

### 15.8 WiFi Test Timeout During Post-Provisioning

| Event | Screen | State |
|---|---|---|
| WiFi test times out | Screen 20 (decision/timeout screen) | `DECISION_WITH_TIMEOUT` |

- 30-second countdown → `GOTO_RESTART`

---

## 16. Success / Failure / Skip Handling

### 16.1 No Update Needed

Path: `checkVersionNonBlocking()` priority 7

```
gUpdateManagerState = 3
gOVERRIDEcommands = GOTO_UPDATEMANAGER
```

In `UPDATEMANAGER` state 3:
- If assets are in queue → `GOTO_ASSETS_DOWNLOAD`
- If no assets → `GOTO_UI_IDLE` → device stays `ONLINE`

Serial output: `[OTA] EVERYTHING IS UP TO DATE`

### 16.2 Update Available → Confirm

Path: ESP32 update needed → `GOTO_FIRMWARE_UPDATECONFIRM`

- Screen 19 shown with 30-second auto-confirm timer
- After timeout: `GOTO_FIRMWARE_DOWNLOAD` (auto-proceeds)

### 16.3 Download Failed (ESP32 Firmware)

Source: `main.ino`, `OTA_downloadManager()`

```cpp
if (ota.updateError) {
    mydisplay.load_screen(4, myui, "", "", "");
    gOVERRIDEcommands = GOTO_UPDATEMANAGER;
}
```

Device returns to idle / update manager. No retry on the same boot. Retry occurs on next periodic OTA check (12 hours).

### 16.4 Download Failed (Asset)

Source: `OTA.cpp`, `downloadAssetsFromS3_LOOP()`, `DL_DOWNLOADING` case

On asset download failure:
- `assetDownloadFailed = true`
- Record re-queued with incremented fail count: `SPIFF_addRecord(ASSETQUEUE, filename, failCount+1)`
- After `AssetMaxRetries` (2) failures: record deleted from queue (asset is skipped)

At queue completion with failures: `ota.assetDownloadFailed == true` → screen 15 (download failed).

### 16.5 OTA Success → Reboot

Source: `main.ino`, `OTA_downloadManager()`

```cpp
ota.copyFullAssetListToTask(&spiff);    // queue assets for after reboot
gOVERRIDEcommands = GOTO_RESTART;       // → screen 13 → ESP.restart()
```

---

## 17. MQTT Report / Ack / Telemetry Messages

### 17.1 Command Acknowledgment

Every MQTT command processed by `aws_defaultRemoteCommandCallback()` receives a response:

```
Topic: fc75/tx/response (PROD) or fc75/dev/response (DEV)
Payload:
{
    "mac": "{device MAC}",
    "type": "response",
    "timestamp": "{ISO 8601}",
    "command": "{command name}",
    "mode": "DEV" | "PROD",
    "status": "EXECUTED" | "DEVICE BUSY" | "NOT RECOGNIZED"
}
```

### 17.2 OTA Log Telemetry

Source: `main.ino`, `TELEMETRY_scheduler()`, `OTA` case

OTA log events are written to `/ota.log` by `Logger::log(LOGGER_OTA, code, data)` and uploaded periodically:

- Upload interval: `OTA_SEND_INTERVAL_MS = (3 * 60 + 15) * 1000` ms (≈ 3 minutes 15 seconds)
- Max records per send: `OTASEND_MAX_RECORDS = 5`
- Topic (PROD): `fc75/tx/system/ota`
- Topic (DEV): `fc75/dev/system/ota`

Payload format (assembled by `RECORD_sendAWS()`):
```json
{
    "mac": "{mac}",
    "type": "OTA",
    "timestamp": "{ISO 8601}",
    "mode": "DEV" | "PROD",
    "events": "{tilde-separated log records}"
}
```

### 17.3 OTA-Specific Logger Codes Confirmed in OTA.cpp

| Logger call | Code | Event |
|---|---|---|
| `Logger::log(LOGGER_ERROR, 0x09, "")` | 0x09 | Firmware client unable to connect to host |
| `Logger::log(LOGGER_ERROR, 0x0B, "")` | 0x0B | Download exceeds free space or is empty |
| `Logger::log(LOGGER_ERROR, 0x0C, "")` | 0x0C | `Update.begin()` failed |
| `Logger::log(LOGGER_ERROR, 0x0D, "")` | 0x0D | Timeout waiting for firmware data |
| `Logger::log(LOGGER_ERROR, 0x0E, "")` | 0x0E | Error writing chunk to flash |
| `Logger::log(LOGGER_ERROR, 0x0F, "")` | 0x0F | `Update.end()` failed |
| `Logger::log(LOGGER_OTA, 0x11, "")` | 0x11 | Firmware update complete |
| `Logger::log(LOGGER_OTA, 0x12, "")` | 0x12 | Firmware update did not complete |

### 17.4 No Dedicated "OTA Complete" MQTT Message

**Confirmed:** There is no specific MQTT publish for "OTA succeeded", "version check result", "no update needed", or "OTA failed" sent directly at the point of the OTA event. All OTA events go through the standard Logger pipeline and are uploaded as batched log records via `TELEMETRY_scheduler`.

### 17.5 Error Telemetry

Error codes are written to `/error.log` and uploaded:
- Interval: `ERROR_SEND_INTERVAL_MS = (60 + 10) * 1000` ms (70 seconds)
- Topic (PROD): `fc75/tx/system/error`

---

## 18. Reboot / Post-OTA Behavior

### 18.1 ESP32 Firmware Update — Reboot Sequence

Source: `main.ino`, `PROCESS_GOTOScreenCalls()`, `GOTO_RESTART`

```
GOTO_RESTART
→ mydisplay.load_screen(13, "RESTARTING")
→ mydisplay.SPRITE_renderDirty()
→ myhardware.incrementCycle(1)  // safety: increment both drawer counters
→ myhardware.incrementCycle(2)
→ delay(100)
→ ESP.restart()
```

### 18.2 Post-Reboot State on First Boot After Firmware Update

On the next boot (new firmware running):
1. `spiff.loadSystemDetails()` loads all system flags
2. `spiff.clearDownloadArtifacts("/assets")` removes any `.tmp` files
3. `spiff.checkProvisionState()` confirms device is still provisioned
4. `/ASSETS_queue.txt` has records (queued before reboot by `copyFullAssetListToTask()`)
5. Device enters normal startup → provisioned → WiFi → `CONNECTION_test()` detects `ASSETQUEUE > 0`:

```cpp
if (spiff.SPIFF_getTotalRecords(config::PATHS::ASSETQUEUE) > 0) {
    gOVERRIDEcommands = GOTO_ASSETS_DOWNLOAD;
}
```

Assets are downloaded immediately after first successful WiFi + AWS connection.

### 18.3 Post-STM32 Firmware Update

After `package.bin` download completes and `buttonEventCb(0x11)` is sent:
- `SPIFF_Manager::STARTUP_IN_BOOTLOAD = "1"` is set in SPIFFS
- On next boot, `setup()` detects this flag:

```cpp
if (SYSTEM_STM_STARTBOOTLOADER) {
    gDeviceStatus = FIRMWARETRANSFERTOSTM;
    myhardware.startSTMBootloader();
    mydisplay.load_screen(31, myui, "", "", "");
}
```

- `STARTUP_IN_BOOTLOAD` is immediately cleared to `"0"` to prevent boot-loop
- The device enters firmware transfer mode and transfers `/stm32/package.bin` to the STM32

---

## 19. Differences Between Current Implementation and Desired ESP-IDF Architecture

| Item | Arduino Behavior | ESP-IDF Notes |
|---|---|---|
| OTA library | `Update.h` (Arduino) | Use `esp_ota_ops.h` (`esp_ota_begin`, `esp_ota_write`, `esp_ota_end`) |
| HTTPS client | `WiFiClientSecure` (Arduino) | Use `esp_http_client` with TLS |
| HTTP asset download | `HTTPClient` (Arduino) | Use `esp_http_client` |
| JSON parsing | `ArduinoJson` | Use `cJSON` (built into IDF) |
| SPIFFS | Arduino SPIFFS API | Use `esp_spiffs.h` |
| State machine | Global enum + switch/case in `loop()` | FreeRTOS task + event group or queue |
| OTA check trigger | Polled in `loop()` every 10s | Timer task or dedicated OTA task |
| Non-blocking HTTPS | Manual state machine (`vcState`) | `esp_http_client` with `HTTP_METHOD_GET` + async handling or task |
| Button event to STM32 | `sendButtonEvent()` via UART | Port `sendButtonEvent()` unchanged protocol |
| `gOVERRIDEcommands` | Global enum, set from any context | Equivalent: FreeRTOS queue or event group |
| Version check retry | Manual counter + `vcWaitUntil` | Use `xTaskDelayUntil` or timer |
| `Update.begin()` space check | `ESP.getFreeSketchSpace()` | `esp_ota_get_next_update_partition()` + partition size |
| Single-slot OTA | Confirmed — no rollback | ESP-IDF supports dual OTA partitions; rollback is available but not used here |
| `runInstructions()` | Stubbed (restart commented out) | Implement restart via `esp_restart()` after `esp_ota_end()` |
| Asset retry logic | `AssetMaxRetries = 2`, 10-second retry delay | Port directly |
| Progress bar update | Called in main loop from `FIRMWAREDOWNLOADING` | Post event/message to UI task |

---

## 20. Error / Unclear Points

### 20.1 `firmwareHost` Field Commented Out

In `OTA.cpp` line 227:
```cpp
//firmwareHost = doc["fc75"]["devices"][deviceKey]["host"] | "";
```

The `firmwareHost` class member exists but is never set. The firmware always uses `versionhost` (the S3 version check host) for binary download. Whether the `"host"` field in `version.json` was intended to allow a separate firmware download host is **Not clarified in current code**.

### 20.2 Screen 19 — User Action During 30-Second Confirm Window

Screen 19 ("INSTALL NOW?") is shown during `FIRMWAREDOWNLOADDECISION`. The 30-second countdown auto-proceeds to `GOTO_FIRMWARE_DOWNLOAD`. Whether the user can press a button to cancel or confirm earlier is **Not found in current reviewed files** (would require checking `SCREEN.cpp` button config for screen 19 / `setButtonConfigurationByID`).

### 20.3 `runInstructions()` Never Called

`OTA::runInstructions()` is defined but its code is commented out and is never called from `OTA_downloadManager()` or anywhere else. The JSON `"instructions"` field in `version.json` (e.g., `"restart": 1`) has no effect in the current firmware. **Confirmed as non-functional in current implementation.**

### 20.4 No Dedicated "OTA Complete" MQTT Publish

There is no point-in-time MQTT message for "OTA succeeded" or "version check result". All OTA events are batched in the telemetry pipeline. If real-time OTA status is needed in ESP-IDF, a dedicated publish must be added.

### 20.5 Asset Retry Delay (`DL_WAIT` State) Not Reached

In `downloadAssetsFromS3_LOOP()`, the `DL_WAIT` state exists but `assetDLState` is never set to `DL_WAIT` in the current code (failed assets are moved to the end of the queue via `SPIFF_deleteRecordAt + SPIFF_addRecord`). The 10-second retry delay defined by `AssetRetryDelay` and the `DL_WAIT` state appear **unused in the current code path**.

### 20.6 `StaticJsonDocument<512>` for `version.json`

The version.json is parsed into a `StaticJsonDocument<512>`. If the actual `version.json` body (including the asset CSV list) exceeds 512 bytes in deserialized size, parsing will fail silently (returning a JSON error). This is a potential risk if the asset list grows. **Needs verification against actual version.json file size.**

### 20.7 No HTTPS for Asset Downloads

Asset files (fonts, icons, language files) are downloaded using the plain `HTTPClient` class (not `WiFiClientSecure`). The asset host URL starts with `https://` but `HTTPClient.begin(url)` in Arduino handles the TLS via its own client selection. The CA certificate is **not explicitly set** for asset downloads (unlike firmware download which uses `WiFiClientSecure` with `setCACert()`). **Needs clarification** on whether CA validation is active for asset downloads.

### 20.8 Version Check JSON Buffer Size

`StaticJsonDocument<512>` is stack-allocated during the version check. If the device is memory-constrained, this may cause stack overflow on some builds. **Needs verification against available stack depth in the calling context.**

### 20.9 `gSYSTEM_FORCEASSETDOWNLOAD` Persistence

`gSYSTEM_FORCEASSETDOWNLOAD` is loaded from SPIFFS at boot. After use in the version check, it is cleared from RAM (`gSYSTEM_FORCEASSETDOWNLOAD = 0`) and from SPIFFS (`setSystemDetailByField(SPIFF_Manager::PROVISIONED, "0")`). However, the SPIFFS field cleared is `PROVISIONED`, not `FORCE_ASSET`. The FORCE_ASSET flag in SPIFFS is only explicitly cleared in `GOTO_ASSETS_COMPLETE`:

```cpp
spiff.setSystemDetailByField(SPIFF_Manager::FORCE_ASSET, "0");
```

Whether this means a power cycle during an asset download could re-trigger a force download is **Needs clarification**.

---

## 21. Implementation Guidance for ESP-IDF

This section provides mapping guidance only. **No implementation code is provided.**

### 21.1 OTA Trigger

- Implement a FreeRTOS timer or dedicated task that fires every 12 hours
- The task sets a flag or posts to a queue: equivalent to `checkVersionTrigger = 1`
- MQTT command handler posts equivalent of `GOTO_UI_CHECKVERSION` to the state machine queue

### 21.2 Version Check State Machine

Port `checkVersionNonBlocking()` as a task or event-driven state machine using `esp_http_client`:

```
States: VC_IDLE → VC_CONNECTING → VC_WAITING_HEADER → VC_WAITING_BODY → VC_DONE/VC_FAILED
Retry: up to 5 attempts, 20-second delay between
```

Use `cJSON` or `esp_json` to parse the response body.

### 21.3 Version Comparison

Port `compareVersions(currentVersion, newVersion)` directly:
- Parse both as MAJOR.MINOR.PATCH using `sscanf`
- Return true only if `newVersion > currentVersion` (field by field)

### 21.4 OTA Flash Write

Use `esp_ota_ops.h`:
```
esp_ota_begin(partition, OTA_SIZE_UNKNOWN, &handle)
esp_ota_write(handle, buffer, size)           // chunk by chunk
esp_ota_end(handle)
esp_ota_set_boot_partition(partition)
esp_restart()
```

Chunk size: 4096 bytes (port directly from `firmwareDownload_LOOP`).
Timeout: 60 seconds of no data.

### 21.5 Asset Download

Port `downloadAssetsFromS3_LOOP()` and `downloadFileNB()` using `esp_http_client`:
- Read from `/ASSETS_queue.txt` (first record = next to download)
- Download to temp path, then rename (atomic)
- Delete queue record on success, re-queue with incremented fail count on failure
- Max retries: 2

### 21.6 SPIFFS Queue Files

The following SPIFFS files are part of the OTA queue system:

| File | Purpose |
|---|---|
| `/ASSETS_full.txt` | Master list of all assets (always updated from `version.json`) |
| `/ASSETS_queue.txt` | Queue of assets remaining to download (consumed during download) |
| `/stm32/package.bin` | Downloaded STM32 firmware binary |
| `/stm32/version.txt` | STM32 version info: `"{stm32Version},{stm32localVersion}"` |
| `/spiffImaged.txt` | Marker: factory SPIFFS image was applied (do not re-copy full asset list) |

### 21.7 UI Decoupling

- Post screen-change events to a dedicated UI task queue
- Do not call LVGL from the OTA task
- Update progress bar by posting `{percent}` to UI queue each chunk

### 21.8 Decision Priority Order

Implement the decision tree in exactly this order (from `checkVersionNonBlocking()`):
1. Assets in queue → resume download
2. First provision (no assets ever) → download all
3. Re-provision flag set → download all
4. Force asset download flag → download all
5. ESP32 firmware newer → show confirm → download firmware → reboot
6. STM32 firmware newer (drawer 1 only) → download bin → trigger bootloader
7. All up to date → go to idle

### 21.9 Verification Test

1. Populate a test `version.json` with a higher `version` than the device currently has
2. Trigger `ESP_CHECKFORUPDATES` via MQTT
3. Expected: device shows "CHECKING FOR UPDATES" screen
4. Expected: `checkVersionNonBlocking()` fetches and parses `version.json`
5. Expected: `compareVersions()` returns true → `GOTO_FIRMWARE_UPDATECONFIRM` → screen 19
6. Expected: after 30 seconds, firmware download begins (screen 2), progress bar updates
7. Expected: on completion, device reboots
8. Expected: after reboot, asset download begins automatically

To verify no-update path:
1. Ensure `version.json` has same version as device
2. Trigger `ESP_CHECKFORUPDATES`
3. Expected: serial log shows `[OTA] EVERYTHING IS UP TO DATE`
4. Expected: device returns to idle (screen 4)
5. Expected: no firmware download, no asset download triggered

---

## 22. Quick File Index

| File | Function / Item | Purpose |
|---|---|---|
| `config.h` | `config::DEVICE::VERSION` | Compile-time ESP32 firmware version string |
| `config.h` | `config::DEVICE::STMVERSION` | Default STM32 version (initial value for `gSYSTEM_STM32_FIRMWARE`) |
| `config.h` | `config::DEVICE::OTA_CHECK_INTERVAL_MS` | Periodic OTA check interval (12 hours) |
| `config.h` | `config::DEVICE::FUNCTIONMODE` | `"DEV"` or `"PROD"` — controls host selection |
| `config.h` | `config::PATHS::VERSIONHOST` | Production S3 host for `version.json` |
| `config.h` | `config::PATHS::VERSIONHOSTDEV` | Dev S3 host for `version.json` |
| `config.h` | `config::PATHS::ASSETSHOST` | Production S3 base URL for assets |
| `config.h` | `config::PATHS::ASSETSHOSTDEV` | Dev S3 base URL for assets |
| `config.h` | `config::PATHS::VERSIONPATH` | Remote path to `version.json` (`/version.json`) |
| `config.h` | `config::PATHS::ASSETQUEUE` | SPIFFS path for pending asset queue |
| `config.h` | `config::PATHS::ASSETFULL` | SPIFFS path for full asset manifest |
| `config.h` | `config::PATHS::STM32DIR` | SPIFFS directory for STM32 firmware |
| `config.h` | `config::PATHS::ASSETDIR` | SPIFFS directory for display assets |
| `config.h` | `config::PATHS::PROVATFACT` | SPIFFS marker: factory SPIFFS image applied |
| `config.h` | `DeviceStatus` enum | All device state machine states |
| `config.h` | `GOTO_Command` enum | All state transition commands |
| `config.h` | `VersionCheckState` enum | OTA version check sub-states |
| `OTA.h` | `class OTA` | OTA class definition, all state variables |
| `OTA.h` | `OTA::checkVersionTrigger` | Flag: set to 1 to start a version check |
| `OTA.h` | `OTA::vcState` | Current version check state machine state |
| `OTA.h` | `OTA::remoteVersion` | Remote ESP32 version from `version.json` |
| `OTA.h` | `OTA::firmwarePath` | Remote firmware binary path |
| `OTA.h` | `OTA::stm32Version` | Remote STM32 version from `version.json` |
| `OTA.h` | `OTA::assetsListCSV` | Comma-separated asset list from `version.json` |
| `OTA.h` | `OTA::updateFinished` / `updateError` | ESP32 OTA result flags |
| `OTA.h` | `OTA::AssetDownloadActive` | Flag: asset download session active |
| `OTA.h` | `OTA::assetDLState` | Asset download state machine state |
| `OTA.cpp` | `OTA::begin()` | Initialize mode and host selection |
| `OTA.cpp` | `getDeviceKey()` | Returns `"dev"` or `"primary"` based on mode |
| `OTA.cpp` | `OTA::checkVersionNonBlocking()` | Main version check + decision state machine |
| `OTA.cpp` | `OTA::firmwareDownload_START()` | Initiate ESP32 firmware HTTPS download |
| `OTA.cpp` | `OTA::firmwareDownload_LOOP()` | Chunked firmware download + flash write |
| `OTA.cpp` | `OTA::runInstructions()` | Post-OTA instructions (currently stubbed) |
| `OTA.cpp` | `OTA::compareVersions()` | MAJOR.MINOR.PATCH version comparison |
| `OTA.cpp` | `OTA::downloadAssetsFromS3_LOOP()` | Asset download state machine (queue-based) |
| `OTA.cpp` | `OTA::downloadFileNB()` | Non-blocking single-file download to SPIFFS |
| `OTA.cpp` | `OTA::writeAssetsFullFile()` | Write `assetsListCSV` to `/ASSETS_full.txt` |
| `OTA.cpp` | `OTA::copyFullAssetListToTask()` | Copy `/ASSETS_full.txt` → `/ASSETS_queue.txt` |
| `OTA.cpp` | `OTA::startAssetDownload()` | Initialize asset download session |
| `OTA.cpp` | `OTA::resetAssetDownloadState()` | Reset all asset download state |
| `main.ino` | `OTA_checkVersion()` | Periodic 12-hour OTA trigger (from `ONLINE` state) |
| `main.ino` | `OTA_downloadManager()` | Drive `firmwareDownload_LOOP()`, handle result |
| `main.ino` | `PROCESS_GOTOScreenCalls()` | Handle all `gOVERRIDEcommands` including OTA |
| `main.ino` | `UPDATEMANAGER` case | OTA update manager state (states 1, 2, 3) |
| `main.ino` | `FIRMWAREDOWNLOADING` case | Drive download loop + progress bar |
| `main.ino` | `ASSETDOWNLOADING` case | Drive asset loop + progress bar + file count |
| `main.ino` | `FIRMWAREDOWNLOADDECISION` case | 30-second countdown for firmware confirm |
| `main.ino` | `TESTWIFI` case | Post-provision WiFi test → OTA trigger |
| `main.ino` | `checkDrawerUIPageIds()` | Intercepts `checkVersionTrigger` to route to `UPDATEMANAGER` |
| `main.ino` | `CONNECTION_test()` | On first online: routes to `GOTO_UPDATEMANAGER` or `GOTO_ASSETS_DOWNLOAD` |
| `main.ino` | `TELEMETRY_scheduler()` | Sends batched OTA/error logs to AWS on schedule |
| `main.ino` | `RECORD_sendAWS()` | Reads log records from SPIFFS, publishes via MQTT |
| `AWS.cpp` | `aws_defaultRemoteCommandCallback()` | MQTT receive handler, OTA command dispatch |
| `AWS.cpp` | `AWS::AWS_manageConnection()` | MQTT connection management and command subscription |
| `AWS.cpp` | `AWS::AWS_sendCommandResponse()` | Publish command ACK to `fc75/tx/response` |
| `AWS.cpp` | `AWS::AWS_sendEvents()` | Publish batched telemetry/log records |
| `logger.h` | `Logger::log()` | Write event to SPIFFS log file |

