id="77321"}
# CLAUDE.md – ESP32 Firmware Rules

## Core Rule
- DO NOT GUESS.
- Use only logic found in code or documents.
- If missing → say "Not found in current implementation".

---

## Architecture
- ESP32 handles UI (LVGL), BLE provisioning, OTA, UART to STM32
- STM32 handles control logic

---

## UI (LVGL)
- DO NOT create/delete screens repeatedly
- Use pre-created screens or containers
- Reuse UI components (header icons, status views)
- UI must be state-driven

---

## Memory
- Avoid malloc/free in runtime loops
- Prefer static allocation
- Reuse objects
- Use ring buffers

---

## FreeRTOS
- DO NOT update LVGL outside UI task
- DO NOT update from ISR
- Use queues or events

---

## OTA
- MUST be based on version.json
- DO NOT assume version logic
- DO NOT invent targeting rules

---

## BLE Provisioning
- MUST follow BLE_PROVISIONING.md
- DO NOT reorder steps
- DO NOT invent bridge messages

---

## STM32 Communication
- DO NOT change protocol
- DO NOT invent commands

---

## Code Changes
- Keep minimal
- Do not redesign system
- Show exact file + function changes

---

## When Unclear
- Say:
  - "Not found in current code"
  - "Needs claication"
  