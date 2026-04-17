---
mode: agent
description: Implement the complete FC75 OTA subsystem for an ESP-IDF project, one command at a time, following the reference Arduino firmware design.
---

# FC75 OTA Subsystem — ESP-IDF Implementation

You are implementing the OTA (Over-The-Air update) subsystem for an ESP32 product called **FC75**. The reference implementation is written in Arduino/ESP32-Arduino. You must port it to **ESP-IDF** (native, no Arduino core).

Follow this prompt step by step. After each step, confirm what was created and wait for the next instruction before proceeding. Do not implement all steps at once.

---

## Context & Constraints

- **Target framework**: ESP-IDF (C, FreeRTOS, native ESP-IDF components only)
- **No Arduino APIs**: Replace all Arduino APIs with their ESP-IDF equivalents (see mapping table at the end of this prompt)
- **File layout**: Create a dedicated `ota/` component directory inside the project's `components/` folder
- **Coding style**: C (not C++), modular, one `.c/.h` pair per responsibility
- **Thread safety**: All file I/O must be protected. Downloads run in a dedicated FreeRTOS task, not inlined in the MQTT callback
- **Error handling**: Every `esp_err_t` call must be checked. Log errors via `ESP_LOGE`. Never silently fail

---

## System Architecture Overview

The FC75 device is an ESP32 + STM32 dual-MCU product:
- **ESP32** handles Wi-Fi, MQTT, HTTPS downloads, and flashing itself via `esp_ota_ops`
- **STM32** handles drawer control hardware. The ESP32 triggers its bootloader over UART

OTA is driven by **4 MQTT commands**:

| Command | Purpose | Needs network | Auto-decides |
|---|---|---|---|
| `ESP_CHECKFORUPDATES` | Fetch version.json, compare versions, auto-dispatch | Yes | Yes |
| `ESP_DOWNLOADASSETS` | Force re-download all assets from local list | Yes (S3) | No |
| `STM_INSTALLFIRMWARE` | Trigger STM32 bootloader via UART | No | No |
| `STM_FORCEFIRMWAREINSTALL` | Download a specific `.bin` then trigger STM32 bootloader | Yes (S3) | No |

---

## MQTT Entry Point

All commands arrive on:
```
Subscribe: foodcycle/<MAC_ADDRESS>/command
```

Payload (JSON, parse with `cJSON`):
```json
{ "command": "ESP_CHECKFORUPDATES" }
{ "command": "ESP_DOWNLOADASSETS" }
{ "command": "STM_INSTALLFIRMWARE" }
{ "command": "STM_FORCEFIRMWAREINSTALL", "value": "STM02.18.1.8.bin" }
```

Response to publish after command is accepted (send before starting any long operation):
```json
{
  "mac":       "<device_mac>",
  "type":      "response",
  "timestamp": "<iso8601_timestamp>",
  "command":   "<COMMAND_NAME>",
  "mode":      "DEV",
  "status":    "EXECUTED"
}
```

Response topic:
```
PROD: fc75/tx/response
DEV:  fc75/dev/response
```

In the MQTT event handler (`MQTT_EVENT_DATA`):
1. Parse JSON payload with `cJSON`
2. Extract `command` (string), uppercase it
3. For `STM_FORCEFIRMWAREINSTALL`, also extract `value` (the `.bin` filename)
4. Do **NOT** run the OTA logic directly in the MQTT callback — post a message to a FreeRTOS queue that the OTA task reads

---

## File Storage (SPIFFS)

Mount SPIFFS under `/spiffs`. All paths below are absolute from the VFS root.

| Path | Purpose | Access |
|---|---|---|
| `/spiffs/ca.pem` | Root CA cert for HTTPS (pre-provisioned) | Read |
| `/spiffs/ASSETS_full.txt` | Master asset list, written by `ESP_CHECKFORUPDATES` | Read/Write |
| `/spiffs/ASSETS_queue.txt` | Current download queue, consumed during download | Read/Write |
| `/spiffs/assets/<filename>` | Downloaded display/UI assets | Write |
| `/spiffs/stm32/package.bin` | STM32 firmware binary (always this canonical name) | Write |

### Queue file format

Each line: `<retry_count>|<filename>\n`
```
0|button1.raw
0|POWER.raw
0|DONE.raw
0|STM02.18.1.8.bin
```

Rules:
- `retry_count` starts at `0`
- After a failed download attempt: increment retry_count and rewrite the line
- After a successful download: delete the line from the queue
- If `retry_count >= 3`: skip the file (delete its line, log a warning)

### Atomic file write pattern (mandatory for all downloads)

```c
// 1. Write to <target>.tmp
// 2. Verify bytes_written == Content-Length from HTTP header
// 3. rename("/spiffs/...<name>.tmp", "/spiffs/...<name>")  — atomic on SPIFFS
```

---

## URL Construction

### version.json (ESP_CHECKFORUPDATES only)

| Mode | Full URL |
|---|---|
| PROD | `https://fc75firmware.s3.ca-central-1.amazonaws.com/version.json` |
| DEV | `https://fc75firmwaredev.s3.ca-central-1.amazonaws.com/version.json` |

- Uses HTTPS port 443
- Must pass CA cert loaded from `/spiffs/ca.pem` as `cert_pem` in `esp_http_client_config_t`

### Asset files (ESP_DOWNLOADASSETS + ESP_CHECKFORUPDATES + STM_FORCEFIRMWAREINSTALL)

Asset URL = `assethost` + `filename`

| Mode | assethost (trailing slash included) |
|---|---|
| PROD | `https://fc75assets.s3.ca-central-1.amazonaws.com/` |
| DEV | `https://fc75assetsdev.s3.ca-central-1.amazonaws.com/` |

Example: `https://fc75assets.s3.ca-central-1.amazonaws.com/button1.raw`

- Uses HTTPS but **no CA cert required** (set `.skip_cert_common_name_check = true`)

### ESP32 firmware binary (from ESP_CHECKFORUPDATES → firmware update branch)

URL = `"https://"` + `host` + `path`  (both fields parsed from version.json):
```json
"primary": { "host": "fc75firmware.s3.ca-central-1.amazonaws.com", "path": "/ESP32-PROD-1.0.63.bin" }
```
→ `https://fc75firmware.s3.ca-central-1.amazonaws.com/ESP32-PROD-1.0.63.bin`

- Requires CA cert (same `/spiffs/ca.pem`)

---

## version.json Schema

```json
{
  "fc75": {
    "devices": {
      "primary": {
        "version": "1.0.63",
        "host": "fc75firmware.s3.ca-central-1.amazonaws.com",
        "path": "/ESP32-PROD-1.0.63.bin",
        "assets": "button1.raw,POWER.raw,DONE.raw,WARNING.raw,PAUSE.raw,infinity.raw,cooling.raw"
      },
      "stm32": {
        "version": "07.01.44",
        "localfwversion": "2.18.1.8",
        "filename": "STM02.18.1.8.bin"
      }
    }
  }
}
```

---

## Version Comparison Logic

```c
// Returns true if an update is needed (remote version > local version)
// Version format: "MAJOR.MINOR.PATCH"  (string split on '.')
bool ota_compare_versions(const char *local, const char *remote) {
    int l[3] = {0}, r[3] = {0};
    sscanf(local,  "%d.%d.%d", &l[0], &l[1], &l[2]);
    sscanf(remote, "%d.%d.%d", &r[0], &r[1], &r[2]);
    for (int i = 0; i < 3; i++) {
        if (r[i] > l[i]) return true;
        if (r[i] < l[i]) return false;
    }
    return false;  // equal — no update
}
```

Local version sources:
- **ESP32 version**: compile-time constant defined in `config.h` (e.g., `"1.0.60"`)
- **STM32 version**: loaded from NVS on boot (key: `stm32_fw_ver`), defaults to compile-time constant if not set

---

## Step-by-Step Implementation Plan

### STEP 1 — Create the OTA component skeleton

Create `components/ota/` with:
- `ota.h` — public API (function declarations, enums for OTA states, event queue message types)
- `ota.c` — main OTA task and dispatcher
- `ota_http.h` / `ota_http.c` — HTTPS download helper (used by all commands that fetch files)
- `ota_files.h` / `ota_files.c` — queue and file helpers (parse/write `ASSETS_queue.txt`, `ASSETS_full.txt`)
- `ota_uart.h` / `ota_uart.c` — STM32 UART frame builder and sender
- `ota_version.h` / `ota_version.c` — version string comparison, version.json parser
- `CMakeLists.txt` — registers the component; links `esp_http_client`, `esp-tls`, `nvs_flash`, `spiffs`, `esp_ota`

The OTA task (`ota_task`) runs on a dedicated FreeRTOS task. It blocks on a `QueueHandle_t ota_cmd_queue` waiting for command messages posted by the MQTT handler.

**Deliverable**: All files created with correct headers, empty function stubs, and a working `CMakeLists.txt`. Confirm with a build that the component compiles cleanly.

---

### STEP 2 — Implement `ota_files` (queue + SPIFFS helpers)

Implement these functions in `ota_files.c`:

```c
// Initialize (clear) the queue file
esp_err_t ota_queue_init(void);

// Returns number of entries in the queue file
int ota_queue_count(void);

// Copy all lines from ASSETS_full.txt to ASSETS_queue.txt with retry=0
esp_err_t ota_queue_copy_from_full(void);

// Read the first (head) entry from the queue: fills out_filename and out_retries
esp_err_t ota_queue_peek_head(char *out_filename, size_t len, int *out_retries);

// Remove the head entry (called on successful download)
esp_err_t ota_queue_remove_head(void);

// Increment retry count for the head entry
esp_err_t ota_queue_increment_head_retry(void);

// Write a fresh ASSETS_full.txt from a CSV asset list string
esp_err_t ota_full_write(const char *csv_assets);

// Append a single filename to ASSETS_full.txt with retry=0
esp_err_t ota_full_append(const char *filename);

// Load CA cert from /spiffs/ca.pem into a caller-provided buffer
esp_err_t ota_load_ca_cert(char *buf, size_t buf_len);
```

**Deliverable**: Full implementation + unit-testable logic. Each function logs what it does. No global state.

---

### STEP 3 — Implement `ota_version` (version.json fetch + parse + compare)

Implement:

```c
// Compare two "MAJOR.MINOR.PATCH" version strings
// Returns true if remote_version > local_version
bool ota_compare_versions(const char *local_version, const char *remote_version);

// Fetch and parse version.json over HTTPS.
// Fills the provided ota_remote_versions_t struct.
// ca_cert: PEM string loaded from /spiffs/ca.pem
// use_dev: true = use DEV bucket, false = PROD bucket
esp_err_t ota_fetch_version_json(
    const char *ca_cert,
    bool use_dev,
    ota_remote_versions_t *out
);
```

`ota_remote_versions_t` struct:
```c
typedef struct {
    char esp32_version[32];       // e.g., "1.0.63"
    char esp32_host[128];         // hostname for firmware binary
    char esp32_path[128];         // path for firmware binary
    char stm32_version[32];       // e.g., "07.01.44"
    char stm32_filename[64];      // e.g., "STM02.18.1.8.bin"
    char assets_csv[512];         // comma-separated asset filenames
} ota_remote_versions_t;
```

Use `esp_http_client` with `HTTP_TRANSPORT_OVER_SSL` and `cert_pem` set. Read the full response body, then parse with `cJSON`.

**Deliverable**: Working fetch + parse. Test with a known-good version.json URL. Log the parsed struct values.

---

### STEP 4 — Implement `ota_http` (generic HTTPS file downloader)

Implement:

```c
// Download a file from url and save it to local_path (atomic via .tmp)
// ca_cert: PEM cert string, or NULL to skip cert check (for assets)
// Returns ESP_OK on success, error code otherwise
esp_err_t ota_http_download_file(
    const char *url,
    const char *local_path,
    const char *ca_cert   // NULL = skip cert validation
);
```

Implementation requirements:
1. `esp_http_client_open()` → read headers → get `Content-Length`
2. Write to `<local_path>.tmp` in streaming chunks (8 KB buffer)
3. Compare total bytes written against `Content-Length`
4. On success: `rename("<local_path>.tmp", local_path)`
5. On failure: `unlink("<local_path>.tmp")`, return error
6. Log progress every ~10 chunks (avoid flooding the log)

**Deliverable**: Works for both CA-verified (version.json, firmware) and no-cert (assets) scenarios.

---

### STEP 5 — Implement `ESP_CHECKFORUPDATES` command handler

This is the most complex command. Implement it as a sub-flow in `ota.c`:

```
ota_cmd_check_for_updates()
  1. Publish MQTT EXECUTED response
  2. Load CA cert from /spiffs/ca.pem
  3. Call ota_fetch_version_json() → ota_remote_versions_t
  4. Compare versions:
       need_esp32  = ota_compare_versions(LOCAL_ESP32_VERSION, remote.esp32_version)
       need_stm32  = ota_compare_versions(nvs_stm32_version,   remote.stm32_version)
  5. Overwrite /spiffs/ASSETS_full.txt with remote.assets_csv
     (append stm32 filename if need_stm32 AND drawer == 1)
  6. Decision tree (priority order):
       a. ota_queue_count() > 0            → go to STEP 6 (asset download loop)
       b. first_provisioning               → ota_queue_copy_from_full() → STEP 6
       c. force_asset_download NVS flag    → ota_queue_copy_from_full() → STEP 6
       d. need_esp32                       → ota_flash_esp32_firmware(remote.esp32_host,
                                              remote.esp32_path, ca_cert)
       e. need_stm32                       → ota_queue_copy_from_full() → STEP 6
       f. (nothing)                        → log "All up to date", return
```

Notes:
- `first_provisioning` = read NVS key `provisioned` (0 = never provisioned)
- `force_asset_download` = read NVS key `force_asset_dl` (1 = force)
- After decision, clear `force_asset_dl` NVS flag

**Deliverable**: Full function with all 6 decision branches implemented and logged.

---

### STEP 6 — Implement the asset download loop (shared by multiple commands)

This loop is used by `ESP_CHECKFORUPDATES`, `ESP_DOWNLOADASSETS`, and `STM_FORCEFIRMWAREINSTALL`.

```c
// Process the entire ASSETS_queue.txt until empty
// Runs synchronously within the OTA task (not a separate task)
esp_err_t ota_run_asset_download_loop(const char *assethost, const char *ca_cert);
```

Logic:
```
while ota_queue_count() > 0:
    ota_queue_peek_head(filename, retries)
    
    if retries >= 3:
        log warning "Skipping <filename> after 3 failed attempts"
        ota_queue_remove_head()
        continue
    
    // Determine local save path
    if filename ends with ".bin":
        local_path = "/spiffs/stm32/package.bin"
        is_stm32_bin = true
    else:
        local_path = "/spiffs/assets/<filename>"
        is_stm32_bin = false
    
    url = assethost + filename
    
    result = ota_http_download_file(url, local_path, NULL)  // no CA for assets
    
    if result == ESP_OK:
        ota_queue_remove_head()
        if is_stm32_bin:
            nvs_set_str(nvs, "startup_bootload", "1")
            trigger_stm_after_download = true
    else:
        ota_queue_increment_head_retry()
        vTaskDelay(pdMS_TO_TICKS(5000))  // 5-second retry delay

if trigger_stm_after_download:
    esp_restart()
```

**Deliverable**: Working loop, handles retries, handles `.bin` vs regular file path routing, restarts if STM32 firmware was downloaded.

---

### STEP 7 — Implement `ESP_DOWNLOADASSETS` command handler

```c
esp_err_t ota_cmd_download_assets(void);
```

Steps:
1. Publish MQTT `EXECUTED` response
2. Call `ota_queue_copy_from_full()` — copies `ASSETS_full.txt` → `ASSETS_queue.txt`
3. If queue is empty (ASSETS_full.txt not yet populated), log error and return
4. Call `ota_run_asset_download_loop(assethost, NULL)`

**Deliverable**: Concise handler that delegates to already-implemented helpers.

---

### STEP 8 — Implement `ota_uart` (STM32 bootloader trigger)

```c
// Initialize UART2 for STM32 communication (call once at startup)
esp_err_t ota_uart_init(int tx_pin, int rx_pin, int baud_rate);

// Send a command frame to STM32
// Sends the 11-byte frame 4 times with 1-second gaps
esp_err_t ota_uart_send_bootloader_trigger(uint8_t drawer);
```

11-byte frame format:
```
[0x8F][0x66][0x10][drawer][msg_id_high][msg_id_low][0x01][0x11][0x01][checksum][0x8E]
```

Where:
- `drawer`: `0x01` or `0x02`
- `msg_id_high / msg_id_low`: incrementing 16-bit counter (high byte, low byte)
- `0x11`: `STM32_START_BOOTLOADER` command code
- `checksum`: XOR of bytes `[1]` through `[8]` (indices 1-8 inclusive, 0-indexed)
- Frame is sent exactly **4 times**, with `vTaskDelay(pdMS_TO_TICKS(1000))` between each

```c
// Checksum calculation:
uint8_t cs = 0;
for (int i = 1; i <= 8; i++) cs ^= frame[i];
frame[9] = cs;
```

**Deliverable**: Correct frame assembly with checksum verification. Log each transmission with the frame bytes in hex.

---

### STEP 9 — Implement `STM_INSTALLFIRMWARE` command handler

```c
esp_err_t ota_cmd_install_stm_firmware(void);
```

Steps:
1. Publish MQTT `EXECUTED` response
2. Write NVS key `startup_bootload` = `"1"`
3. Call `ota_uart_send_bootloader_trigger(drawer_number)` — sends 4× with 1-second gaps

No file download, no network call. This assumes `/spiffs/stm32/package.bin` already exists from a prior download.

**Deliverable**: Simple 3-step handler.

---

### STEP 10 — Implement `STM_FORCEFIRMWAREINSTALL` command handler

```c
esp_err_t ota_cmd_force_stm_firmware(const char *filename);
```

Steps:
1. Validate `filename` ends with `.bin` — if not, publish MQTT `ERROR-wrong file type` and return
2. Publish MQTT `EXECUTED` response
3. Initialize queue: `ota_queue_init()`
4. Append filename to queue: `ota_full_append(filename)`; then copy to queue: `ota_queue_copy_from_full()`
5. Call `ota_run_asset_download_loop(assethost, NULL)`
   - The `.bin` file will be saved as `/spiffs/stm32/package.bin`
   - After download, NVS key `startup_bootload` = `"1"` is set and `esp_restart()` is called

**Deliverable**: Includes the `.bin` extension validation and the full download → bootload chain.

---

### STEP 11 — Implement ESP32 self-update via `esp_ota_ops`

```c
// Called from ESP_CHECKFORUPDATES when need_esp32 == true
esp_err_t ota_flash_esp32_firmware(
    const char *host,
    const char *path,
    const char *ca_cert
);
```

Implementation:
1. Get the next OTA partition: `esp_ota_get_next_update_partition(NULL)`
2. Begin OTA: `esp_ota_begin(update_partition, OTA_WITH_SEQUENTIAL_WRITES, &ota_handle)`
3. Download the firmware streaming from HTTPS:
   - Build URL: `"https://" + host + path`
   - Stream with `esp_http_client_read()` in 4 KB chunks
   - Write each chunk: `esp_ota_write(ota_handle, chunk, chunk_len)`
4. End OTA: `esp_ota_end(ota_handle)`
5. Set boot partition: `esp_ota_set_boot_partition(update_partition)`
6. Call `esp_restart()`

**Deliverable**: Full streaming OTA flash. No intermediate file on SPIFFS needed.

---

### STEP 12 — Wire everything into the OTA task and hook the MQTT handler

In `ota.c`, create the main OTA task:

```c
void ota_task(void *pvParameters) {
    ota_cmd_msg_t msg;
    while (true) {
        if (xQueueReceive(ota_cmd_queue, &msg, portMAX_DELAY) == pdTRUE) {
            switch (msg.type) {
                case OTA_CMD_CHECK_FOR_UPDATES:  ota_cmd_check_for_updates(); break;
                case OTA_CMD_DOWNLOAD_ASSETS:    ota_cmd_download_assets();   break;
                case OTA_CMD_INSTALL_STM:        ota_cmd_install_stm_firmware(); break;
                case OTA_CMD_FORCE_STM:          ota_cmd_force_stm_firmware(msg.value); break;
            }
        }
    }
}
```

In the MQTT event handler (wherever `MQTT_EVENT_DATA` is processed):
```c
// Parse cJSON, uppercase the command string, then:
ota_cmd_msg_t msg = {0};
if      (strcmp(cmd, "ESP_CHECKFORUPDATES")    == 0) msg.type = OTA_CMD_CHECK_FOR_UPDATES;
else if (strcmp(cmd, "ESP_DOWNLOADASSETS")     == 0) msg.type = OTA_CMD_DOWNLOAD_ASSETS;
else if (strcmp(cmd, "STM_INSTALLFIRMWARE")    == 0) msg.type = OTA_CMD_INSTALL_STM;
else if (strcmp(cmd, "STM_FORCEFIRMWAREINSTALL") == 0) {
    msg.type = OTA_CMD_FORCE_STM;
    strlcpy(msg.value, value_field, sizeof(msg.value));
}
xQueueSend(ota_cmd_queue, &msg, 0);  // non-blocking; drop if queue full
```

**Deliverable**: OTA task registered in `app_main()`, MQTT handler posts to the queue, end-to-end flow validated with a test MQTT publish.

---

## Arduino → ESP-IDF API Translation Table

| Arduino (reference code) | ESP-IDF equivalent |
|---|---|
| `WiFiClientSecure` + `HTTPClient` | `esp_http_client` with `HTTP_TRANSPORT_OVER_SSL` |
| `Update.h` (OTA flash) | `esp_ota_ops.h` (`esp_ota_begin/write/end`) |
| `SPIFFS.open/read/write` | `fopen/fread/fwrite` after `esp_vfs_spiffs_register()` |
| `ArduinoJson` | `cJSON` (built into ESP-IDF) |
| `PubSubClient` MQTT | `esp-mqtt` component (`esp_mqtt_client_*`) |
| `Serial2.write()` (UART) | `uart_write_bytes(UART_NUM_2, ...)` |
| `delay(ms)` | `vTaskDelay(pdMS_TO_TICKS(ms))` |
| `String` class | `char[]` + `strlcpy/snprintf/strcmp` |
| `millis()` | `esp_timer_get_time() / 1000` (gives ms) |
| `ESP.restart()` | `esp_restart()` |
| `Preferences` (NVS) | `nvs_flash.h` + `nvs_open/get_str/set_str` |

---

## NVS Keys Used by OTA

| Key | Type | Purpose |
|---|---|---|
| `stm32_fw_ver` | string | Stored STM32 firmware version (loaded at boot) |
| `startup_bootload` | string | `"1"` = trigger STM32 bootloader on next boot |
| `provisioned` | u8 | `1` = device has been provisioned at least once |
| `force_asset_dl` | u8 | `1` = force a full asset re-download on next check |

---

## Periodic Auto-Check (12-Hour Timer)

In addition to MQTT-triggered commands, `ESP_CHECKFORUPDATES` must also fire automatically every **12 hours** when the device is in `ONLINE` state.

```c
#define OTA_CHECK_INTERVAL_MS  (12UL * 60 * 60 * 1000)

// At startup: record the boot time
last_ota_check_ms = esp_timer_get_time() / 1000;

// In a periodic supervisor task (e.g., every 10 seconds):
uint64_t now_ms = esp_timer_get_time() / 1000;
if (device_is_online() && (now_ms - last_ota_check_ms) >= OTA_CHECK_INTERVAL_MS) {
    last_ota_check_ms = now_ms;
    ota_cmd_msg_t msg = { .type = OTA_CMD_CHECK_FOR_UPDATES };
    xQueueSend(ota_cmd_queue, &msg, 0);
}
```

Note: The timer starts **at boot**, so the first automatic check does not fire until 12 hours after power-on. This is intentional.

---

## Definition of Done

Each step is complete when:
1. The code compiles cleanly under ESP-IDF (`idf.py build`)
2. The behavior matches the specification in that step
3. All error paths are handled and logged
4. No memory leaks (static or stack-allocated buffers only; free any `cJSON` objects)

Do not proceed to the next step until the current step compiles and the implementation is confirmed correct.
