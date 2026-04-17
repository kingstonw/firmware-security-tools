# OTA Commands — ESP-IDF Implementation Guide

This document supplements the existing flow docs and provides the concrete
technical details needed to reimplement the 4 OTA commands in ESP-IDF.

---

## 1. Command Entry Point (MQTT Callback)

All 4 commands arrive on the MQTT topic:
```
Subscribe topic:  foodcycle/<MAC_ADDRESS>/command
Response topic:   fc75/tx/response   (PROD)
                  fc75/dev/response  (DEV)
```

Incoming JSON payload, parse with `cJSON`:
```c
// Incoming JSON
{ "command": "ESP_CHECKFORUPDATES" }
{ "command": "ESP_DOWNLOADASSETS" }
{ "command": "STM_INSTALLFIRMWARE" }
{ "command": "STM_FORCEFIRMWAREINSTALL", "value": "STM02.18.1.8.bin" }
```

Response JSON sent back (same shape for all 4 commands):
```json
{
  "mac":       "30:ED:A0:15:6D:A4",
  "type":      "response",
  "timestamp": "2026-04-06T12:00:00Z",
  "command":   "ESP_CHECKFORUPDATES",
  "mode":      "DEV",
  "status":    "EXECUTED"
}
```

ESP-IDF MQTT:
```c
// Use esp-mqtt component
esp_mqtt_client_subscribe(client, "foodcycle/30:ED:A0:15:6D:A4/command", 1);

// In MQTT_EVENT_DATA handler:
cJSON *root = cJSON_ParseWithLength(event->data, event->data_len);
cJSON *cmd  = cJSON_GetObjectItem(root, "command");
// uppercase cmd->valuestring, then dispatch
```

---

## 2. Network Layer: URL Construction

### 2a. version.json (used by ESP_CHECKFORUPDATES only)

| Mode | Host | Path | Protocol |
|------|------|------|----------|
| PROD | `fc75firmware.s3.ca-central-1.amazonaws.com` | `/version.json` | **HTTPS port 443, requires CA cert** |
| DEV  | `fc75firmwaredev.s3.ca-central-1.amazonaws.com` | `/version.json` | HTTPS port 443, requires CA cert |

```c
// esp_http_client example
esp_http_client_config_t config = {
    .host            = "fc75firmware.s3.ca-central-1.amazonaws.com",
    .path            = "/version.json",
    .transport_type  = HTTP_TRANSPORT_OVER_SSL,
    .cert_pem        = ca_cert_pem,   // read from /spiffs/ca.pem
};
```

### 2b. Asset files (used by ESP_DOWNLOADASSETS + ESP_CHECKFORUPDATES)

Asset URL = `assethost` + `filename`

| Mode | assethost (full prefix, trailing slash included) |
|------|--------------------------------------------------|
| PROD | `https://fc75assets.s3.ca-central-1.amazonaws.com/` |
| DEV  | `https://fc75assetsdev.s3.ca-central-1.amazonaws.com/` |

Example:
```
filename: "button1.raw"
full URL: "https://fc75assets.s3.ca-central-1.amazonaws.com/button1.raw"
```

```c
// Asset download uses HTTPS but NO mutual-TLS; simple GET, no CA required
// (The existing Arduino code uses plain HTTPClient without setCACert for assets)
esp_http_client_config_t config = {
    .url            = "https://fc75assets.s3.ca-central-1.amazonaws.com/button1.raw",
    .transport_type = HTTP_TRANSPORT_OVER_SSL,
    .skip_cert_common_name_check = true,   // matches existing behavior
};
```

### 2c. ESP32 firmware binary (used by ESP_CHECKFORUPDATES → firmware update path)

Firmware URL = `"https://"` + `host` + `path`  (both values come from version.json)

```json
"primary": {
  "host": "fc75firmware.s3.ca-central-1.amazonaws.com",
  "path": "/ESP32-PROD-1.0.63.bin"
}
```

Full URL: `https://fc75firmware.s3.ca-central-1.amazonaws.com/ESP32-PROD-1.0.63.bin`  
Requires CA cert (same `/spiffs/ca.pem`).

### 2d. STM32 firmware binary (used by STM_FORCEFIRMWAREINSTALL)

Filename comes from the MQTT command `"value"` field:
```json
{ "command": "STM_FORCEFIRMWAREINSTALL", "value": "STM02.18.1.8.bin" }
```

Full URL = `assethost` + `value`  (same bucket as assets):
```
https://fc75assets.s3.ca-central-1.amazonaws.com/STM02.18.1.8.bin
```

---

## 3. CA Certificate

- Stored in SPIFFS at: `/spiffs/ca.pem`  (path constant `CA = "/ca.pem"`)
- Used for: version.json fetch + ESP32 firmware download
- NOT used for: asset file downloads (existing code skips cert check)

```c
// Read CA cert from SPIFFS
FILE *f = fopen("/spiffs/ca.pem", "r");
// read into a char buffer, pass as cert_pem to esp_http_client_config_t
```

---

## 4. File Storage (SPIFFS)

### Key file paths
```
/spiffs/ca.pem           — Root CA certificate (R)
/spiffs/ASSETS_full.txt  — Master asset list, written by CHECKFORUPDATES (RW)
/spiffs/ASSETS_queue.txt — Download queue, consumed as assets are downloaded (RW)
/spiffs/assets/          — Downloaded display assets directory (W)
/spiffs/stm32/           — STM32 firmware directory (W)
/spiffs/stm32/package.bin — STM32 firmware binary, canonical name (W)
```

### ASSETS_full.txt and ASSETS_queue.txt format
Each line: `<retry_count>|<filename>\n`

```
0|button1.raw
0|POWER.raw
0|DONE.raw
0|WARNING.raw
0|PAUSE.raw
0|infinity.raw
0|cooling.raw
0|EN_Lang.json
```

- `retry_count` starts at `0`.
- Max retries before skipping: **3** (`AssetMaxRetries = 3`).
- On failed download, increment the counter and rewrite the line.
- On successful download, delete the line from the queue.

### Saving downloaded files
```
Asset type decision:
  filename.endsWith(".bin")  →  save to /spiffs/stm32/package.bin
  anything else              →  save to /spiffs/assets/<filename>

All downloads use atomic write:
  1. Write to <targetPath>.tmp
  2. Verify file size matches Content-Length header
  3. Rename .tmp → final path
```

---

## 5. STM32 UART Protocol (STM_INSTALLFIRMWARE)

The bootloader is triggered by sending an 11-byte UART frame **4 times** with 1-second gaps.

### Frame format
```
Byte  0: 0x8F          — Start of frame
Byte  1: 0x66          — Fixed header
Byte  2: 0x10          — Fixed header
Byte  3: drawer        — 0x01 = Drawer 1, 0x02 = Drawer 2
Byte  4: msg_id_high   — Message ID high byte (incrementing counter)
Byte  5: msg_id_low    — Message ID low byte
Byte  6: 0x01          — Fixed
Byte  7: eventTypeID   — Command code (see table below)
Byte  8: 0x01          — Fixed
Byte  9: checksum      — XOR of bytes 1..8
Byte 10: 0x8E          — End of frame
```

### Checksum
```c
uint8_t checksum = 0;
for (int i = 1; i <= 8; i++) checksum ^= msg[i];
msg[9] = checksum;
```

### Relevant command codes (eventTypeID, Byte 7)
```c
#define STM32_START_BOOTLOADER  0x11
#define STM32_REBOOT            0x03
#define STM32_BTN1CLICK         0x01
#define STM32_BTN2CLICK         0x04
#define STM32_TEST_WTR_PUMP     0x05
#define STM32_SELF_TEST         0x0F
```

### STM_INSTALLFIRMWARE execution
```c
// 1. Set "start in bootload" flag in NVS/SPIFFS so that after reboot ESP32
//    knows to let STM32 bootload rather than normal operation.
//    Key: "STARTUP_IN_BOOTLOAD", value: "1"

// 2. Send STM32_START_BOOTLOADER frame 4 times, 1 second apart:
for (int i = 0; i < 4; i++) {
    uart_write_bytes(UART_NUM_2, frame, 11);
    vTaskDelay(pdMS_TO_TICKS(1000));
}
```

UART config (from existing codebase):
- Serial2 (ESP32 UART2), 8N1
- Baud rate: check HARDWARE::begin() — typically 115200 or 9600
- RX/TX pins: check project-specific HARDWARE pin definitions

---

## 6. Version Comparison Logic

```c
// compareVersions(currentVersion, remoteVersion)
// Returns true if update needed (remote > current)
// Format: "MAJOR.MINOR.PATCH"

bool compare_versions(const char *current, const char *remote) {
    int c[3] = {0}, r[3] = {0};
    sscanf(current, "%d.%d.%d", &c[0], &c[1], &c[2]);
    sscanf(remote,  "%d.%d.%d", &r[0], &r[1], &r[2]);
    for (int i = 0; i < 3; i++) {
        if (r[i] > c[i]) return true;   // update needed
        if (r[i] < c[i]) return false;  // remote is older, no update
    }
    return false;  // equal, no update
}
```

Local ESP32 version → compile-time constant: `"1.0.60"`  
Local STM32 version → read from NVS/SPIFFS system detail file at boot

---

## 7. ESP_CHECKFORUPDATES — Full Decision Logic

After fetching and parsing version.json:

```c
bool need_esp32_update = compare_versions(LOCAL_ESP32_VERSION, remote_esp32_version);
bool need_stm32_update = compare_versions(local_stm32_version, remote_stm32_version)
                         && (drawer_number == 1);  // Only Drawer 1 updates STM32

int assets_in_queue    = count_lines("/spiffs/ASSETS_queue.txt");
int total_assets_known = count_lines("/spiffs/ASSETS_full.txt");
bool was_provisioned   = (total_assets_known < 1);
bool was_reprovisioned = (total_assets_known > 0) && provisioned_flag;
bool force_asset_dl    = read_nvs_flag("FORCE_ASSET");

// Always rewrite ASSETS_full.txt from version.json["assets"] + language file
write_assets_full_file(assets_csv_from_json + "," + lang_file);

// Priority order (highest to lowest):
if      (assets_in_queue)        → start_asset_download();
else if (was_provisioned)        → copy_full_to_queue(); start_asset_download();
else if (was_reprovisioned)      → copy_full_to_queue(); start_asset_download();
else if (force_asset_dl)         → copy_full_to_queue(); start_asset_download();
else if (need_esp32_update)      → show_firmware_confirm_screen();
                                   // user confirms → download + flash ESP32 → restart
else if (need_stm32_update)      → add_stm32_bin_to_queue(); start_asset_download();
else                             → return_to_idle();  // "EVERYTHING IS UP TO DATE"
```

---

## 8. Asset Download State Machine (Non-blocking)

The download runs as a FreeRTOS task or in a dedicated loop in ESP-IDF:

```
States: IDLE → GET_NEXT → DOWNLOADING → WAIT → (back to GET_NEXT)

IDLE / GET_NEXT:
  - Read first record from ASSETS_queue.txt
  - Parse: retry_count|filename
  - If retry_count >= 3: skip (delete record), stay in GET_NEXT
  - Build download URL: assethost + filename
  - Determine local path: .bin → /stm32/package.bin, else /assets/<filename>
  - Transition to DOWNLOADING

DOWNLOADING (called every loop tick / task iteration):
  - esp_http_client_read() → append to <targetPath>.tmp
  - Track bytesWritten vs Content-Length
  - When complete: verify size, rename .tmp → final
  - Delete record from ASSETS_queue.txt
  - If it was a .bin: set STARTUP_IN_BOOTLOAD flag, set triggerSTMAfterDownload = true
  - Transition to GET_NEXT

WAIT:
  - Used for retry delay after failure
  - Re-increment retry_count in queue record
  - Wait ~5 seconds, then GET_NEXT

Queue empty:
  - If triggerSTMAfterDownload: restart ESP32 (STM32 will bootload on next power-on)
  - Else: return to IDLE state of application
```

---

## 9. Periodic Auto-Check (12-Hour Timer)

```c
// Only triggers when device is ONLINE (provisioned + AWS connected + idle)
#define OTA_CHECK_INTERVAL_MS  (12UL * 60 * 60 * 1000)   // 12 hours

// At boot: set lastOTACheck = esp_timer_get_time() / 1000
// This intentionally delays first auto-check by 12 hours from boot.

// In main task / 10-second periodic worker:
if (device_status == ONLINE &&
    (millis() - lastOTACheck) >= OTA_CHECK_INTERVAL_MS) {
    trigger_check_for_updates();
    lastOTACheck = millis();
}
```

---

## 10. ESP-IDF API Equivalents

| Arduino (current) | ESP-IDF equivalent |
|-------------------|--------------------|
| `WiFiClientSecure` + `HTTPClient` | `esp_http_client` with `transport_type = HTTP_TRANSPORT_OVER_SSL` |
| `Update.h` (flash writes) | `esp_ota_ops.h` (`esp_ota_begin`, `esp_ota_write`, `esp_ota_end`) |
| `SPIFFS.open/read/write` | `fopen/fread/fwrite` via `esp_vfs_spiffs_register` |
| `ArduinoJson` | `cJSON` (built-in to ESP-IDF) |
| `PubSubClient` MQTT | `esp-mqtt` component (`esp_mqtt_client`) |
| `Serial2.write` (UART) | `uart_write_bytes(UART_NUM_2, ...)` |
| `delay(ms)` | `vTaskDelay(pdMS_TO_TICKS(ms))` |
| `String` class | `char[]` or `std::string` |
| `millis()` | `esp_timer_get_time() / 1000` |
| `ESP.restart()` | `esp_restart()` |

---

## 11. Command Summary for Implementation

### ESP_CHECKFORUPDATES
1. Send `EXECUTED` response via MQTT
2. GET `https://<versionhost>/version.json` (with CA cert)
3. Parse JSON, extract versions + asset list
4. Rewrite `/spiffs/ASSETS_full.txt` from parsed asset CSV + language filename
5. Run version comparison decision tree (Section 7)
6. Dispatch to appropriate sub-flow

### ESP_DOWNLOADASSETS
1. Send `EXECUTED` response via MQTT
2. Read `/spiffs/ASSETS_full.txt`, copy all entries to `/spiffs/ASSETS_queue.txt`
3. Start asset download state machine (Section 8)

### STM_INSTALLFIRMWARE
1. Send `EXECUTED` response via MQTT
2. Write `"1"` to NVS key `STARTUP_IN_BOOTLOAD`
3. Send UART `STM32_START_BOOTLOADER` (0x11) frame × 4, 1-second gaps (Section 5)

### STM_FORCEFIRMWAREINSTALL
1. Validate `"value"` field ends with `.bin`; if not, send `ERROR-wrong file type`
2. Send `EXECUTED` response via MQTT
3. Add `<value>` filename to `/spiffs/ASSETS_queue.txt` with retry count 0
4. Start asset download state machine — the `.bin` file will be saved as `/spiffs/stm32/package.bin`
5. After download: write `STARTUP_IN_BOOTLOAD = 1`, call `esp_restart()`
