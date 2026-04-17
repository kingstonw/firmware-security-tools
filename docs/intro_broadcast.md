# FCS Intra-Device MQTT Message Specification

## 1. Overview

This document defines the MQTT topic and payload format used for **intra-device communication**
between multiple ESP32 devices connected to the same STM32 controller.

Typical use cases:
- ESP32 ↔ ESP32 coordination
- Role-based command dispatch
- Stress testing / diagnostics
- Screen, OTA, network state synchronization

This design uses **broadcast topics + payload-level filtering**.

---

## 2. MQTT Topic Definition

### Topic Pattern
### Topic Parameters

| Field      | Type   | Description |
|------------|--------|-------------|
| deviceID   | string | logical device ID |

### Example
devices/FC75-00000148/intro/broadcast

All ESP32 devices belonging to the same STM32 **must subscribe** to this topic.

---

## 3. Payload Format (JSON)

### Base Payload Schema

```json
{
  "from": "esp32-d1",
  "fromDeviceId": 1,
  "target": "esp32-d2",
  "type": "STRESS_TESTING",
  "ts": 1733828392
}

esp32-d2(which is bottom drawer and g_deviceid=2) should  parse the payload messgae and if type is "STRESS_TESTING", set g_stress_testing =true. This global flag will tell screen task to display "Stree Testing" label correctly.

