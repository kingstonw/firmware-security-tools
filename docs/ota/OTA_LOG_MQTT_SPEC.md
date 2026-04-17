# FC75 OTA Log MQTT Specification

This document describes how FC75 publishes OTA-related log records to MQTT using the OTA system topic.

It is intended to guide another ESP-IDF project so it can reproduce compatible OTA log messages.

---

## 1. Purpose

The OTA topic is used to report buffered OTA event records.

In the current FC75 project, this topic is much narrower than the name suggests:

- it does not log the entire OTA decision tree
- it does not log every asset or STM32 firmware action
- it mainly reports final ESP32 firmware OTA result events

This is important for compatibility: many OTA failures in this project go to `system/error`, not `system/ota`.

---

## 2. MQTT Topics

### Production

```text
fc75/tx/system/ota
```

### Development

```text
fc75/dev/system/ota
```

Source constants:

- `config::PATHS::AWS_OTA = "fc75/tx/system/ota"`
- `config::PATHS::DEV_OTA = "fc75/dev/system/ota"`

---

## 3. High-Level Flow

```text
Some OTA code path calls Logger::log(LOGGER_OTA, hexCode, data)
  -> logger writes one record into /ota.log
  -> TELEMETRY_scheduler()
  -> case OTA
  -> RECORD_sendAWS("/ota.log", "OTA", ...)
  -> AWS_sendEvents(...)
  -> MQTT publish to fc75/tx/system/ota or fc75/dev/system/ota
  -> on publish success, delete the sent records from /ota.log
```

Important behavior:

- OTA records are buffered locally in `/ota.log`
- Upload is periodic, not immediate
- On publish success, uploaded head records are deleted
- On publish failure, the records remain for retry

---

## 4. Publish Preconditions

OTA publish is attempted only when:

1. `TELEMETRY_scheduler(sendOnline)` is running
2. No UI button is pressed
3. `gSYSTEM_WIFI != 0`
4. `wifi.isConnected()` is true
5. The scheduler reaches the `OTA` telemetry slot

---

## 5. Publish Period

The OTA upload interval is:

```text
OTA_SEND_INTERVAL_MS = 195000 ms = 3 minutes 15 seconds
```

The scheduler processes one telemetry class per call, so actual send time is approximately periodic.

---

## 6. MQTT Payload Format

The outer MQTT payload is created by `AWS_sendEvents()`.

### JSON schema

```json
{
  "mac": "30:ED:A0:15:6D:A4",
  "type": "OTA",
  "timestamp": "2026-04-07T12:34:56Z",
  "mode": "DEV",
  "events": "2026-04-07T12:34:40Z|0x11||1.0.60|851968|1540096"
}
```

### Outer JSON field meanings

| JSON field | Meaning |
|---|---|
| `mac` | Device MAC address |
| `type` | Always `OTA` for this topic |
| `timestamp` | Timestamp of this publish attempt |
| `mode` | `DEV` or `PROD` |
| `events` | One or more local OTA records joined by `~` |

---

## 7. `events` Field Format

The `events` field is a string, not a JSON array.

If one record is sent:

```text
events = "<record1>"
```

If multiple records are sent:

```text
events = "<record1>~<record2>~<record3>"
```

### Batch size

At most 5 OTA records are sent in one MQTT publish:

```text
OTASEND_MAX_RECORDS = 5
```

---

## 8. Single OTA Record Format

Each OTA record inside `events` is stored as:

```text
<record_timestamp>|<hex_code>|<data>|<version>|<spiffsUsed>|<spiffsTotal>
```

This is produced in two steps:

1. `Logger::log(LOGGER_OTA, hexCode, data)` builds:

```text
<hex_code>|<data>|<version>|<spiffsUsed>|<spiffsTotal>
```

2. `SPIFF_addRecord()` prepends the timestamp:

```text
<record_timestamp>|<hex_code>|<data>|<version>|<spiffsUsed>|<spiffsTotal>
```

### Example

```text
2026-04-07T12:34:40Z|0x11||1.0.60|851968|1540096
```

---

## 9. Field Meanings

| Position | Field | Meaning |
|---|---|---|
| 1 | `record_timestamp` | UTC ISO 8601 time when the OTA record was written locally |
| 2 | `hex_code` | OTA event code from the log table |
| 3 | `data` | Optional detail string, currently usually empty |
| 4 | `version` | ESP32 firmware version |
| 5 | `spiffsUsed` | Used SPIFFS bytes at log time |
| 6 | `spiffsTotal` | Total SPIFFS bytes at log time |

---

## 10. Local Buffering Behavior

OTA records are buffered in:

```text
/ota.log
```

### Local file limit

```text
OTALOG_MAX_RECORDS = 300
```

### Send/delete behavior

1. Count records in `/ota.log`
2. Read up to 5 head records
3. Join them with `~`
4. Publish one MQTT message
5. If publish succeeds, delete those sent records
6. If publish fails, delete nothing

---

## 11. Current Actual OTA Log Producers In This Project

Current code scanning shows only two active `LOGGER_OTA` writes in the project:

| Hex | Meaning from log table | Source behavior |
|---|---|---|
| `0x11` | `Firmware update complete! Will run instructions and reboot if needed.` | ESP32 firmware OTA finished successfully |
| `0x12` | `[OTA] Firmware update did not complete.` | ESP32 firmware OTA reached end state but was not finished |

These writes occur in the ESP32 firmware download/write flow after `Update.end()` and `Update.isFinished()` checks.

---

## 12. Important Scope Limitation

The current project does **not** use `system/ota` as a full OTA audit stream.

Specifically:

- `ESP_CHECKFORUPDATES` decision branches mostly do not write `ota.log`
- asset download queue processing does not currently write `ota.log`
- `STM_INSTALLFIRMWARE` does not currently write `ota.log`
- `STM_FORCEFIRMWAREINSTALL` does not currently write `ota.log`

Many OTA-related failures are instead written to `system/error`.

### OTA-related failures that currently go to `system/error`

| Hex | Meaning |
|---|---|
| `0x09` | firmware client unable to connect to host |
| `0x0B` | download exceeds free space or is empty |
| `0x0C` | `Update.begin` failed |
| `0x0D` | timeout waiting for firmware download data |
| `0x0E` | flash/write failure |
| `0x0F` | `Update.end` failed |

So another project should not assume that all OTA failures are published on `fc75/tx/system/ota`.

---

## 13. Timestamp Semantics

Two timestamps exist:

### Outer payload timestamp

The JSON `timestamp` field is when the MQTT message was assembled for send.

### Inner record timestamp

The first field of each OTA record is when that specific OTA record was written locally.

These can differ when buffered records are retried later.

---

## 14. Example MQTT Messages

### Example A: one OTA success record

```json
{
  "mac": "30:ED:A0:15:6D:A4",
  "type": "OTA",
  "timestamp": "2026-04-07T12:35:00Z",
  "mode": "PROD",
  "events": "2026-04-07T12:34:40Z|0x11||1.0.60|851968|1540096"
}
```

### Example B: multiple buffered OTA records

```json
{
  "mac": "30:ED:A0:15:6D:A4",
  "type": "OTA",
  "timestamp": "2026-04-07T12:40:00Z",
  "mode": "DEV",
  "events": "2026-04-07T12:34:40Z|0x11||1.0.60|851968|1540096~2026-04-07T12:38:10Z|0x12||1.0.60|852224|1540096"
}
```

---

## 15. ESP-IDF Compatibility Guidance

If another ESP-IDF project needs to emulate FC75 OTA-topic behavior exactly:

1. Maintain a persistent local OTA log queue equivalent to `/ota.log`
2. Use record format:

```text
<timestamp>|<hex>|<data>|<version>|<spiffsUsed>|<spiffsTotal>
```

3. Every 195 seconds, attempt to send up to 5 queued records
4. Join multiple records with `~`
5. Publish JSON:

```json
{
  "mac": "<mac>",
  "type": "OTA",
  "timestamp": "<utc_iso8601>",
  "mode": "DEV or PROD",
  "events": "<record1>~<record2>..."
}
```

6. Publish to:

```text
PROD -> fc75/tx/system/ota
DEV  -> fc75/dev/system/ota
```

7. Delete sent records only after successful publish
8. Preserve records on publish failure

### Compatibility warning

If the target project wants to match FC75 exactly, it should only publish final OTA event records on this topic, not every OTA step.

If the target project wants a richer OTA audit stream, that would be an intentional extension beyond FC75 behavior.

---

## 16. Reference Behavior Summary

The FC75-compatible OTA reporting model is:

- write selected OTA events locally first
- publish buffered OTA records approximately every 3 minutes 15 seconds
- send at most 5 records per MQTT packet
- use `events` as a `~`-joined string
- preserve exact `|` field order even if `data` is empty
- delete only after successful publish
- note that many OTA failures are not on this topic and instead go to `system/error`

That is the actual wire-level behavior of the current FC75 project.