# MQTT Heartbeat Topic Summary

## Scope

This report documents the published MQTT logic for production heartbeat topic `fc75/tx/heartbeat`, traced from executable code only.

## Topic and Payload Analysis

| Topic | JSON Field | Type | Meaning | Global Variable Updated | Function Triggered | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `fc75/tx/heartbeat` | `mac` | string | Device MAC copied from `subscribedMac` | none | `AWS_sendHeartbeat()` | Set in heartbeat JSON before publish. |
| `fc75/tx/heartbeat` | `type` | string | Fixed value `heartbeat` | none | `AWS_sendHeartbeat()` | Always set to `heartbeat` in this publish path. |
| `fc75/tx/heartbeat` | `timestamp` | string | Timestamp argument passed in, typically global `gTimestamp` | none | `TELEMETRY_scheduler()` -> `updateTimestamp()` -> `AWS_sendHeartbeat()` | Updated before each send attempt in scheduler heartbeat case. |
| `fc75/tx/heartbeat` | `events` | string | Sensor/state snapshot assembled by hardware layer | none | `TELEMETRY_scheduler()` -> `RECORD_assembler(SENSOR)` -> `HARDWARE::assembleSensorRecord()` -> `AWS_sendHeartbeat()` | Unlike error/ota/log topics, heartbeat does not read queued log file; it sends freshly assembled snapshot data. |

## Publish Conditions (Confirmed)

- Published from telemetry scheduler `HEARTBEAT` slot.
- Preconditions in `TELEMETRY_scheduler(bool sendOnline)`:
  - Returns early if a button is currently pressed.
  - Returns early if `gSYSTEM_WIFI == 0`.
  - Returns early if `wifi.isConnected()` is false.
- Heartbeat send additionally requires:
  - `sendOnline` to be true.
  - `gSYSTEM_drawer != 2` (drawer 2 does not publish heartbeat in this path).
- Timing is interval-based:
  - `HEARTBEAT_INTERVAL_MS = 1000` ms.

## Related Functions and File Locations

- `AWS::AWS_sendHeartbeat(String dataString, const char* timestamp)` in [AWS.cpp](AWS.cpp)
  - Builds heartbeat JSON (`mac`, `type`, `timestamp`, `events`) and publishes to topic selected by mode.

- `TELEMETRY_scheduler(bool sendOnline)` in [main.ino](main.ino)
  - Heartbeat case drives timestamp update and heartbeat send call.

- `RECORD_assembler(int type)` in [main.ino](main.ino)
  - For `SENSOR`/`HEARTBEAT` source data, calls hardware snapshot assembler.

- `HARDWARE::assembleSensorRecord()` in [HARDWARE.cpp](HARDWARE.cpp)
  - Generates the sensor/state string used as heartbeat `events` field.

- Topic definitions in [config.h](config.h)
  - `AWS_HEARTBEAT = fc75/tx/heartbeat`
  - `DEV_HEARTBEAT = fc75/dev/heartbeat`

## Additional Notes

- Mode switch logic is in `AWS_sendHeartbeat()`: publishes to `DEV_HEARTBEAT` when `FUNCTIONMODE == DEV`, otherwise to `AWS_HEARTBEAT`.
- This report is for production topic `fc75/tx/heartbeat`; development topic behavior is included only where needed to explain code paths.
