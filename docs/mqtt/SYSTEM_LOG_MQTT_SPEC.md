# FC75 System Log MQTT Specification

This document explains how the FC75 firmware publishes system runtime status to MQTT using the system log topic.

It is intended to guide another ESP-IDF project so it can generate the same message format and compatible reporting behavior.

---

## 1. Purpose

The FC75 firmware uses the system log topic to report periodic runtime health and status snapshots such as:

- ESP32 firmware version
- free heap
- SPIFFS usage
- Wi-Fi RSSI
- uptime
- number of unsent error records

This is not a command topic and not a one-shot boot message.
It is a periodic telemetry/reporting channel with local buffering and retry-by-retention behavior.

---

## 2. MQTT Topics

The firmware selects the topic based on `FUNCTIONMODE`.

### Production

```text
fc75/tx/system/log
```

### Development

```text
fc75/dev/system/log
```

Source constants:

- `config::PATHS::AWS_LOG = "fc75/tx/system/log"`
- `config::PATHS::DEV_LOG = "fc75/dev/system/log"`

---

## 3. High-Level Flow

The message path is:

```text
TELEMETRY_scheduler()
  -> case LOG
  -> updateTimestamp()
  -> RECORD_assembler(LOG)
  -> Logger::log(LOGGER_SYSTEM, ...)
  -> append one record into /log.log
  -> RECORD_sendAWS("/log.log", "SYSTEM_LOG", ...)
  -> AWS_sendEvents(...)
  -> MQTT publish to fc75/tx/system/log or fc75/dev/system/log
  -> on publish success, delete the sent records from /log.log
```

Important behavior:

- A fresh system log record is created on each LOG telemetry cycle.
- The newly created record is stored locally first.
- The firmware then attempts to publish up to a batch limit.
- Only if publish succeeds are those local records deleted.
- If publish fails, the records remain in `/log.log` and will be retried later.

---

## 4. Publish Preconditions

System log publish is attempted only when all of the following are true:

1. `TELEMETRY_scheduler(sendOnline)` is being called by the main application state machine.
2. No UI button is currently pressed.
3. `gSYSTEM_WIFI != 0`.
4. `wifi.isConnected()` is true.
5. The scheduler has reached the `LOG` telemetry slot.

Additional notes:

- The scheduler processes only one telemetry type per call for fairness.
- Actual wall-clock send time is therefore approximately periodic, not hard real-time exact.
- In normal operation the target interval is 2 minutes 30 seconds.

---

## 5. Publish Period

The system log interval constant is:

```text
LOG_SEND_INTERVAL_MS = 150000 ms = 2 minutes 30 seconds
```

The telemetry interval array order is:

```text
HEARTBEAT
SENSOR
ERROR
OTA
LOG
```

So the LOG branch runs when:

```text
now - lastSent[LOG] >= LOG_SEND_INTERVAL_MS
```

---

## 6. MQTT Payload Format

The outer MQTT JSON payload is created by `AWS_sendEvents()`.

### JSON schema

```json
{
  "mac": "30:ED:A0:15:6D:A4",
  "type": "SYSTEM_LOG",
  "timestamp": "2026-04-07T12:34:56Z",
  "mode": "DEV",
  "events": "2026-04-07T12:34:56Z|1.0.60|184320|851968|1540096|-57|0,3,12,41|0"
}
```

### Field meanings

| JSON field | Meaning |
|---|---|
| `mac` | Device MAC address used when the MQTT client was initialized |
| `type` | Always `SYSTEM_LOG` for this topic |
| `timestamp` | Timestamp of this publish attempt, in UTC ISO 8601 |
| `mode` | `DEV` or `PROD` |
| `events` | One or more local system-log records joined by `~` |

### Notes

- `timestamp` is the outer message send timestamp.
- Each record inside `events` also contains its own record timestamp.
- The packet size limit uses `SENSOR_PACKET_SIZE = 4096` bytes.

---

## 7. `events` Field Format

The `events` field is a string, not a JSON array.

If only one local record is sent:

```text
events = "<record1>"
```

If multiple local records are batched together:

```text
events = "<record1>~<record2>~<record3>"
```

### Batch size

At most 3 system log records are sent in one MQTT publish:

```text
SYSTEMSEND_MAX_RECORDS = 3
```

So if `/log.log` contains 8 pending records, the firmware will publish them in multiple MQTT messages over multiple scheduler cycles.

---

## 8. Single Record Format Inside `events`

Each local system log record is stored as:

```text
<record_timestamp>|<version>|<heapFree>|<spiffsUsed>|<spiffsTotal>|<wifiRSSI>|<uptime>|<unsentErrors>
```

This is because:

1. `RECORD_assembler(LOG)` generates the runtime data portion:

```text
<version>|<heapFree>|<spiffsUsed>|<spiffsTotal>|<wifiRSSI>|<uptime>|<unsentErrors>
```

2. `Logger::log(LOGGER_SYSTEM, ...)` writes that raw string to `/log.log`.

3. `SPIFF_addRecord()` prepends the current `gTimestamp`:

```text
<timestamp>|<data>
```

### Example single record

```text
2026-04-07T12:34:56Z|1.0.60|184320|851968|1540096|-57|0,3,12,41|2
```

---

## 9. Meaning of Each Record Field

The fields inside one record are:

| Position | Field | Example | Meaning |
|---|---|---|---|
| 1 | `record_timestamp` | `2026-04-07T12:34:56Z` | UTC ISO 8601 time when the record was written locally |
| 2 | `version` | `1.0.60` | ESP32 firmware version from `config::DEVICE::VERSION` |
| 3 | `heapFree` | `184320` | Free heap bytes from `ESP.getFreeHeap()` |
| 4 | `spiffsUsed` | `851968` | Used SPIFFS bytes from `SPIFFS.usedBytes()` |
| 5 | `spiffsTotal` | `1540096` | Total SPIFFS bytes from `SPIFFS.totalBytes()` |
| 6 | `wifiRSSI` | `-57` | Wi-Fi RSSI from `WiFi.RSSI()` |
| 7 | `uptime` | `0,3,12,41` | Uptime as `days,hours,minutes,seconds` |
| 8 | `unsentErrors` | `2` | Count of pending records in `/error.log` |

### Field source details

#### `record_timestamp`

- Comes from global `gTimestamp`
- `gTimestamp` is updated by `updateTimestamp()`
- Format is UTC ISO 8601:

```text
YYYY-MM-DDTHH:MM:SSZ
```

#### `version`

- Compile-time ESP32 firmware version
- Source: `config::DEVICE::VERSION`

#### `heapFree`

- Current free heap in bytes
- Source API: `ESP.getFreeHeap()`

#### `spiffsUsed`

- Currently used SPIFFS bytes
- Source API: `SPIFFS.usedBytes()`

#### `spiffsTotal`

- Total mounted SPIFFS capacity in bytes
- Source API: `SPIFFS.totalBytes()`

#### `wifiRSSI`

- Current Wi-Fi received signal strength in dBm
- Source API: `WiFi.RSSI()`

#### `uptime`

- Built from `millis()`
- Format is not ISO duration; it is a comma-separated string:

```text
days,hours,minutes,seconds
```

Example:

```text
1,4,23,9
```

means 1 day, 4 hours, 23 minutes, 9 seconds.

#### `unsentErrors`

- Count of locally buffered error records still waiting in `/error.log`
- Source API: `spiff.SPIFF_getTotalRecords(config::PATHS::ERRORLOG)`

This is not the number of current runtime faults; it is the number of error log entries that have not yet been successfully published.

---

## 10. Local Buffering Behavior

System log records are buffered locally in:

```text
/log.log
```

Each line in `/log.log` is one complete record.

### Local file limit

```text
SYSTEMLOG_MAX_RECORDS = 1000
```

If the file already contains 1000 records, a new record is not written.

### Send/delete behavior

When sending:

1. Count total records in `/log.log`
2. Read up to `SYSTEMSEND_MAX_RECORDS` records
3. Join them with `~`
4. Publish one MQTT message
5. If publish succeeds, delete exactly that many records from the head of the file
6. If publish fails, delete nothing

This gives at-least-retained behavior until MQTT publish succeeds.

---

## 11. Timestamp Semantics

There are two timestamps involved:

### Outer payload timestamp

The outer JSON field:

```json
"timestamp": "2026-04-07T12:34:56Z"
```

represents when the MQTT message was assembled for transmission.

### Inner record timestamp

The first field of each event record:

```text
2026-04-07T12:34:56Z|1.0.60|...
```

represents when that individual local system record was created.

These two timestamps may be the same when a record is written and published immediately, but they can differ when buffered records are retried later.

---

## 12. Example Messages

### Example A: one record

Topic:

```text
fc75/tx/system/log
```

Payload:

```json
{
  "mac": "30:ED:A0:15:6D:A4",
  "type": "SYSTEM_LOG",
  "timestamp": "2026-04-07T12:35:00Z",
  "mode": "PROD",
  "events": "2026-04-07T12:35:00Z|1.0.60|184320|851968|1540096|-57|0,3,12,41|0"
}
```

### Example B: three buffered records in one publish

Topic:

```text
fc75/dev/system/log
```

Payload:

```json
{
  "mac": "30:ED:A0:15:6D:A4",
  "type": "SYSTEM_LOG",
  "timestamp": "2026-04-07T12:40:00Z",
  "mode": "DEV",
  "events": "2026-04-07T12:35:00Z|1.0.60|184320|851968|1540096|-57|0,3,12,41|0~2026-04-07T12:37:30Z|1.0.60|183640|852224|1540096|-59|0,3,15,11|1~2026-04-07T12:40:00Z|1.0.60|182912|852480|1540096|-58|0,3,17,41|1"
}
```

---

## 13. ESP-IDF Compatibility Guidance

To generate compatible `fc75/tx/system/log` messages in an ESP-IDF project, implement the following behavior exactly:

1. Maintain a local queue or file equivalent to `/log.log`.
2. Every 150 seconds, create one new runtime snapshot record.
3. Record format must be:

```text
<record_timestamp>|<version>|<heapFree>|<spiffsUsed>|<spiffsTotal>|<wifiRSSI>|<uptime_days,hours,minutes,seconds>|<unsentErrors>
```

4. Publish up to 3 pending records in one MQTT message.
5. Concatenate records with `~`.
6. Publish JSON fields exactly as:

```json
{
  "mac": "<mac>",
  "type": "SYSTEM_LOG",
  "timestamp": "<utc_iso8601>",
  "mode": "DEV or PROD",
  "events": "<record1>~<record2>..."
}
```

7. Use topic:

```text
PROD -> fc75/tx/system/log
DEV  -> fc75/dev/system/log
```

8. Delete sent records only after MQTT publish success.
9. If publish fails, preserve the unsent records for the next retry cycle.

### Suggested ESP-IDF API mapping

| Arduino implementation | ESP-IDF equivalent |
|---|---|
| `ESP.getFreeHeap()` | `esp_get_free_heap_size()` |
| `SPIFFS.usedBytes()` | `esp_spiffs_info()` |
| `SPIFFS.totalBytes()` | `esp_spiffs_info()` |
| `WiFi.RSSI()` | `esp_wifi_sta_get_ap_info()` |
| `millis()` | `esp_timer_get_time() / 1000` |
| `PubSubClient::publish()` | `esp_mqtt_client_publish()` |

---

## 14. Important Non-Obvious Details

1. `events` is a plain string, not a JSON array.
2. The inner record separator is `|`.
3. The batch separator between records is `~`.
4. `uptime` uses commas, not colons.
5. `unsentErrors` reflects pending error log queue depth, not active error state.
6. The system log message includes both outer and inner timestamps.
7. Topic selection depends on runtime mode, not compile target name.
8. The scheduler writes a new system log record before attempting publish.

---

## 15. Reference Behavior Summary

If you want another ESP-IDF project to behave like FC75, the exact reporting model is:

- Create one local runtime-status record every 2 minutes 30 seconds.
- Store it durably first.
- Attempt to send up to 3 pending records to `fc75/tx/system/log` or `fc75/dev/system/log`.
- Use one JSON message with `events` as a `~`-joined string.
- On success, delete the published local records.
- On failure, keep them for retry.

That is the compatible wire-level behavior for FC75 system log reporting.