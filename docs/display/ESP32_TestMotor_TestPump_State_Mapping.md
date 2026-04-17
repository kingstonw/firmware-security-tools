# ESP32 Test Motor / Test Water Pump State Mapping

## Scope

This document defines the UI and state-machine behavior for:

- `0x2020` — `Manual_Motor_control` (test motor running)
- `0x2021` — `Water_pump_running` (test water pump running)

Derived exclusively from Arduino firmware source code and project guideline documents.  
No behavior is invented or assumed. Unknowns are explicitly marked.

---

## 1. Purpose

The STM32 co-processor broadcasts `0x2020` when a manual motor test is in progress, and `0x2021` when a water pump test is in progress. These are diagnostic/manual-control states, not error conditions. The ESP32 must display the appropriate status screen, configure user interaction, and correctly exit the state when the STM32 broadcasts a new page ID.

This document is the reference for porting this behavior to the ESP-IDF firmware.

---

## 2. Source of Truth

Document priority (highest to lowest):

1. `docs/AI_Guidelines.md`
2. `docs/Claude.md`
3. `docs/ai_prompts/base.md`
4. `docs/ai_prompts/analysis.md`
5. `docs/ai_prompts/verification.md`
6. Arduino firmware source files:
   - `config.h` — `Manual_Motor_control = 0x2020`, `Water_pump_running = 0x2021`
   - `HARDWARE.h` — `DisplayCommand` enum (gap noted below)
   - `HARDWARE.cpp` — `checkStateTransitionsForDrawer()`, `STM_isIdle()`
   - `main.ino` — `checkDrawerUIPageIds()`, `GOTO_STM32_ALERT` switch, `UNDER_STM32_CONTROL`, AWS trigger handlers
   - `SCREEN.cpp` — `load_screen()` cases 11 and 18, `setButtonConfigurationByID()` cases 12 and 14
   - `UI.cpp` — `executeAction()` for actions 110, 111
   - `ASSETS.h` — `ICON_SETTING` PROGMEM pixel array definition

Rule applied: Do not guess missing logic. Explicitly mark unknowns.

---

## 3. Event Overview

### 3.1 Code Definitions — `config.h`

```cpp
static constexpr uint16_t Manual_Motor_control = 0x2020;
static constexpr uint16_t Water_pump_running   = 0x2021;
```

### 3.2 `DisplayCommand` Enum — `HARDWARE.h`

**Confirmed gap:** `0x2020` and `0x2021` are **not defined** in the `DisplayCommand` enum in `HARDWARE.h`. The enum jumps directly from `0x2019` to `0x2030`:

```cpp
enum class DisplayCommand : uint16_t {
    ...
    TX_CMD_Show_Self_Test_Error = 0x2019,
    // 0x2020 and 0x2021 are NOT here
    TX_CMD_MOTOR_ERR            = 0x2030,
    ...
};
```

These two codes are only defined via `config::TX_CMD` constants in `config.h`. This means functions in `HARDWARE.cpp` that work with the `DisplayCommand` typed enum (such as `checkStateTransitionsForDrawer()`) do not explicitly handle `0x2020` or `0x2021`.

### 3.3 How the Page ID Is Received

Source: `HARDWARE.cpp`, `processSerialFramesNonBlocking()`:

```cpp
drawer1_uipageid = (uint16_t)frameBuf[73] | ((uint16_t)frameBuf[74] << 8);
drawer2_uipageid = (uint16_t)frameBuf[75] | ((uint16_t)frameBuf[76] << 8);

if (gSYSTEM_drawer == 2)
    my_uipageid = drawer2_uipageid;
else
    my_uipageid = drawer1_uipageid;
```

The page ID (`0x2020` or `0x2021`) is parsed from the standard 109-byte UART frame, identical to all other STM32 state values.

### 3.4 How These Test Modes Are Triggered

The test modes are initiated by the ESP32 sending button events to the STM32. The STM32 then enters the test mode and broadcasts `0x2020` or `0x2021` back.

**Trigger path 1 — Physical button press (from any screen with config 7, 9, 16, or 17):**

```cpp
// UI.cpp, executeAction():
case 110: myhardware.sendButtonEvent(gSYSTEM_drawer, config::TX_CMD::STM32_BTN2CLICK);        break;  // 0x04 → STM32 starts motor
case 111: myhardware.sendButtonEvent(gSYSTEM_drawer, config::TX_CMD::STM32_TEST_WTR_PUMP);    break;  // 0x05 → STM32 starts pump
```

| Command sent to STM32 | Value  | Expected STM32 response |
|-----------------------|--------|--------------------------|
| `STM32_BTN2CLICK`     | `0x04` | STM32 starts motor → broadcasts `0x2020` |
| `STM32_TEST_WTR_PUMP` | `0x05` | STM32 starts pump → broadcasts `0x2021` |

**Trigger path 2 — AWS remote command:**

Source: `main.ino`, `TRIGGERS_process()`:

```cpp
else if (cmd == "STM_TESTGRINGINMOTOR") {
    myhardware.sendButtonEvent(gSYSTEM_drawer, config::TX_CMD::STM32_BTN2CLICK);   // 0x04
}
else if (cmd == "STM_TESTWATERPUMP") {
    myhardware.sendButtonEvent(gSYSTEM_drawer, config::TX_CMD::STM32_TEST_WTR_PUMP); // 0x05
}
```

Both paths result in the same UART command to STM32. What STM32 does in response to those commands (broadcasting `0x2020` or `0x2021`) is a **STM32-side decision — Not found in current ESP32 implementation**.

---

## 4. Arduino Behavior

### 4.1 State Change Detection — `checkDrawerUIPageIds()`

Source: `main.ino`, `checkDrawerUIPageIds()`:

Called every loop iteration. Applies the standard guard list to suppress alerts during OTA, provisioning, etc.:

```cpp
if (gDeviceStatus == FIRMWARETRANSFERTOSTM || gDeviceStatus == UPDATEMANAGER
 || gDeviceStatus == PROVISIONING         || gDeviceStatus == FIRMWAREDOWNLOADING
 || gDeviceStatus == ASSETDOWNLOADING     || gDeviceStatus == TESTWIFI
 || gDeviceStatus == DECISION_WITH_TIMEOUT|| gDeviceStatus == FIRMWAREDOWNLOADDECISION
 || gDeviceStatus == UNPROVISIONED        || gDeviceStatus == UNPROVISIONEDSTART
 || ota.assetDLState != OTA::DL_IDLE      || gDeviceStatus == BLEBROADCASTING
 || gDeviceStatus == LOADINGSETTINGS) {
    return;
}
```

After guards pass:

```cpp
bool stateChanged = false;
if (prev_page != now_page) stateChanged = true;

if (myhardware.checkStateTransitionsForDrawer(gSYSTEM_drawer)) buzzThisCycle = true;

if ((!myhardware.STM_isIdle() && gDeviceStatus != UNDER_STM32_CONTROL) || stateChanged) {
    gOVERRIDEcommands = GOTO_STM32_ALERT;
}
```

### 4.2 Buzzer — Not Triggered for `0x2020` / `0x2021`

Source: `HARDWARE.cpp`, `checkStateTransitionsForDrawer()`:

```cpp
// Buzzer fires for drawer open, drawer pause, and error range 0x2030-0x2049:
if ((now == DisplayCommand::TX_CMD_Drawer_Open_State ||
     now == DisplayCommand::TX_CMD_Drawer_Pause_State ||
     (curr_cmd >= 0x2030 && curr_cmd <= 0x2049)) && (prev_cmd != curr_cmd)) {
    return true;  // triggers buzz
}
```

`0x2020` and `0x2021` are **not in the buzzer trigger list**. The buzz condition is not satisfied for these two states. `checkStateTransitionsForDrawer()` returns false, and `buzzThisCycle` remains false.

**Confirmed: No buzzer fires when entering `0x2020` or `0x2021`.**

### 4.3 `STM_isIdle()` — Returns False for Both States

Source: `HARDWARE.cpp`:

```cpp
bool HARDWARE::STM_isIdle() {
    return (my_uipageid == static_cast<uint16_t>(DisplayCommand::TX_CMD_Standby));
    // TX_CMD_Standby = 0x2010
}
```

`0x2020` and `0x2021` ≠ `0x2010`, so `STM_isIdle()` returns false during both test states. This means the device does not return to idle automatically — it must wait for the STM32 to broadcast a new page ID.

### 4.4 Screen Routing — `GOTO_STM32_ALERT` Switch

Source: `main.ino`, `PROCESS_GOTOScreenCalls()`, case `GOTO_STM32_ALERT`:

```cpp
case config::TX_CMD::Manual_Motor_control: {
    Serial.println("MANUAL MOTOR CONTROL DETECTED");
    mydisplay.load_screen(11, myui, mydisplay.langMap["016"], emptyS, emptyS);
} break;

case config::TX_CMD::Water_pump_running: {
    mydisplay.load_screen(18, myui, mydisplay.langMap["067"], emptyS, emptyS);
} break;
```

| Event    | Code     | Screen loaded | pVar1                        | pVar2    | pVar3    |
|----------|----------|---------------|------------------------------|----------|----------|
| `0x2020` | Motor    | **11**        | `langMap["016"]` = `"MOTOR RUNNING"` | `""` (empty) | `""` (empty) |
| `0x2021` | Pump     | **18**        | `langMap["067"]` = `"PUMP RUNNING"`  | `""` (empty) | `""` (empty) |

After the switch:

```cpp
gOVERRIDEcommands = GOTO_NONE;
gDeviceStatus = UNDER_STM32_CONTROL;
needRedraw = 1;
```

---

## 5. Screen / UI Mapping

### 5.1 Screen 11 — Motor Running

Source: `SCREEN.cpp`, `load_screen()`, case 11. Log line: `"[DISPLAY] Motor Running (Stop Button)..."`.

```cpp
case 11: {
    myui.setLedDefaults(ON, ON);
    setButtonConfigurationByID(myui, 12);

    // Y-position logic (pVar2 is empty for 0x2020):
    int iconY  = (pVar2.length() == 0) ? (LINE7Y + 25) : LINE10Y;   // = 35+25 = 60
    int text1Y = (pVar2.length() == 0) ? (LINE7Y + 125) : LINE5Y;   // = 35+125 = 160
    int text2Y = LINE5Y + 25;                                         // = 165 (empty text)

    Asset iconSprite = { "0024", 160-33, 60, 67, 67, ...,
                         ASSET_PROGMEM, "ICON_SETTING", ... };
    SPRITE_create(iconSprite);

    Asset textSprite = { "0025", 0, 160, 320, FONT2H, ...,
                         ASSET_TEXT, pVar1, ..., CENTER, ..., FONT2, ... };
    SPRITE_create(textSprite);

    Asset textSprite2 = { "0035", 0, 165, 320, FONT2H, ...,
                          ASSET_TEXT, pVar2, ..., CENTER, ..., FONT2, ... };
    SPRITE_create(textSprite2);

    Asset button1 = { "0041", 200, 205, 120, 40, ...,
                      ASSET_BUTTON, langMap["065"], ..., LEFT, ..., FONT2, ... };
    SPRITE_create(button1);
}
```

| Element          | Sprite ID | Type          | Content / Value                          |
|------------------|-----------|---------------|------------------------------------------|
| Icon             | `0024`    | ASSET_PROGMEM | `ICON_SETTING` (67×67px, PROGMEM)        |
| Primary text     | `0025`    | ASSET_TEXT    | `"MOTOR RUNNING"` — FONT2, centered      |
| Secondary text   | `0035`    | ASSET_TEXT    | `""` (empty) — FONT2, centered           |
| CANCEL button    | `0041`    | ASSET_BUTTON  | `langMap["065"]` = `"CANCEL"`, 120×40px  |
| LED 1            | —         | —             | ON                                       |
| LED 2            | —         | —             | ON                                       |
| Buttons          | —         | —             | Profile 12 (see §6.1)                    |

**`ICON_SETTING`**: A settings/gear icon compiled into PROGMEM in `ASSETS.h` (67×67 pixels, `ICON_SETTING_W = 67`, `ICON_SETTING_H = 67`). It is rendered by the display engine when `asset.source == "ICON_SETTING"`. It is **not** loaded from SPIFFS.

**Layout when `pVar2` is empty (confirmed case for `0x2020`):**
- Icon: y = 60 (centered horizontally at x = 127)
- "MOTOR RUNNING" text: y = 160 (full-width, centered)
- Empty text2: y = 165 (renders nothing visible)
- "CANCEL" button: x = 200, y = 205, 120×40px, aligned LEFT

### 5.2 Screen 18 — Pump Running

Source: `SCREEN.cpp`, `load_screen()`, case 18. Log line: `"[DISPLAY] Pump Running (Stop Button)..."`.

```cpp
case 18: {
    myui.setLedDefaults(ON, ON);
    setButtonConfigurationByID(myui, 14);

    int iconY  = (pVar2.length() == 0) ? (LINE7Y + 25) : LINE10Y;   // = 60
    int text1Y = (pVar2.length() == 0) ? (LINE7Y + 125) : LINE5Y;   // = 160
    int text2Y = LINE5Y + 25;                                         // = 165

    Asset iconSprite = { "0024", 160-33, 60, 67, 67, ...,
                         ASSET_PROGMEM, "ICON_SETTING", ... };
    SPRITE_create(iconSprite);

    Asset textSprite = { "0025", 0, 160, 320, FONT2H, ...,
                         ASSET_TEXT, pVar1, ..., CENTER, ..., FONT2, ... };
    SPRITE_create(textSprite);

    Asset textSprite2 = { "0035", 0, 165, 320, FONT2H, ...,
                          ASSET_TEXT, pVar2, ..., CENTER, ..., FONT2, ... };
    SPRITE_create(textSprite2);

    // CANCEL button: COMMENTED OUT in source
    // Asset button1 = { "0041", ..., langMap["065"], ... };
    // SPRITE_create(button1);
}
```

| Element        | Sprite ID | Type          | Content / Value                          |
|----------------|-----------|---------------|------------------------------------------|
| Icon           | `0024`    | ASSET_PROGMEM | `ICON_SETTING` (67×67px, PROGMEM)        |
| Primary text   | `0025`    | ASSET_TEXT    | `"PUMP RUNNING"` — FONT2, centered       |
| Secondary text | `0035`    | ASSET_TEXT    | `""` (empty) — FONT2, centered           |
| CANCEL button  | —         | —             | **Not rendered — commented out**         |
| LED 1          | —         | —             | ON                                       |
| LED 2          | —         | —             | ON                                       |
| Buttons        | —         | —             | Profile 14 (see §6.2)                    |

**Layout is identical to screen 11** (same Y positions, same icon, same text position) except:
- The "CANCEL" button sprite is **commented out** and not created.

### 5.3 Comparison — Screen 11 vs Screen 18

| Feature                   | Screen 11 (`0x2020` Motor)     | Screen 18 (`0x2021` Pump)    |
|---------------------------|-------------------------------|------------------------------|
| Log output                | `"[DISPLAY] Motor Running (Stop Button)..."` | `"[DISPLAY] Pump Running (Stop Button)..."` |
| Icon                      | `ICON_SETTING` (PROGMEM)      | `ICON_SETTING` (PROGMEM)     |
| Primary text              | `"MOTOR RUNNING"`             | `"PUMP RUNNING"`             |
| Secondary text            | `""` (empty)                  | `""` (empty)                 |
| CANCEL button rendered    | **Yes** — sprite "0041"       | **No** — commented out       |
| LED 1 / LED 2             | ON / ON                       | ON / ON                      |
| Button config             | 12                            | 14                           |
| Physical buttons active   | BTN2 short only               | None                         |

---

## 6. Button Configurations

### 6.1 Button Config 12 — Motor Running Screen (screen 11)

Source: `SCREEN.cpp`, `setButtonConfigurationByID()`, case 12. Comment: `"Motor Running (Stop Button)"`.

```cpp
case 12: {
    int actions[BUTTON_DETECTION_COUNT] = {
    //   click  short  long  vlong  ext
        0,     0,     0,     0,   0,    // BTN1 — all disabled
        0,   110,     0,     0,   0,    // BTN2 — short only
        0,     0,     0,     0,   0};   // BOTH — all disabled
    configButtons(myui, actions);
} break;
```

| Button event  | Action ID | Behavior                              |
|---------------|-----------|---------------------------------------|
| BTN2 short    | 110       | Send `STM32_BTN2CLICK` (0x04) to STM32 |
| All others    | 0         | Disabled — no action                  |

Source (`UI.cpp`, `executeAction()`):
```cpp
case 110: myhardware.sendButtonEvent(gSYSTEM_drawer, config::TX_CMD::STM32_BTN2CLICK); break;
```

**Confirmed:** While in `0x2020` (Motor Running), the user can press BTN2 short to send `STM32_BTN2CLICK` (0x04) to STM32. Whether this stops or toggles the motor is a **STM32-side decision — Not found in current ESP32 implementation**.

The "CANCEL" button rendered as sprite `"0041"` on screen 11 is of type `ASSET_BUTTON`. Whether this touch-button sprite is connected to a touch input handler is **Not found in current implementation** — no touch event processing for sprites was identified in the code reviewed.

### 6.2 Button Config 14 — Pump Running Screen (screen 18)

Source: `SCREEN.cpp`, `setButtonConfigurationByID()`, case 14. Comment: `"Pump Running (Stop Button)"`.

```cpp
case 14: {
    int actions[BUTTON_DETECTION_COUNT] = {
    //   click  short  long  vlong  ext
        0,     0,     0,     0,   0,    // BTN1 — all disabled
        0,     0,     0,     0,   0,    // BTN2 — all disabled
        0,     0,     0,     0,   0};   // BOTH — all disabled
    configButtons(myui, actions);
} break;
```

**All physical buttons are disabled.** No user action can be taken via physical buttons while screen 18 is displayed. The pump cannot be stopped by the user through the physical interface in the current implementation.

---

## 7. Runtime Update Behavior in `UNDER_STM32_CONTROL`

After either screen is loaded, `gDeviceStatus = UNDER_STM32_CONTROL`. The `UNDER_STM32_CONTROL` block runs every loop iteration.

### 7.1 No Specific Runtime Update for `0x2020` or `0x2021`

Source: `main.ino`, case `UNDER_STM32_CONTROL` (full runtime update block reviewed):

```cpp
if      (my_uipageid == Running_State)      { SPRITE_updateText("counter", ...); ... }
else if (my_uipageid == Progress1_State)    { SPRITE_updateText("counter", ...); ... }
else if (my_uipageid == Progress2_State)    { SPRITE_updateText("counter", ...); ... }
else if (my_uipageid == Progress3_State)    { SPRITE_updateText("counter", ...); ... }
else if (my_uipageid == Drawer_Pause_State && isAnyBucketTempAbove56()) { SPRITE_toggleSprites(...); }
else if (my_uipageid == Drawer_Pause_State) { SPRITE_makeBlink("counter", 1); }
else if (my_uipageid == Self_test_State)    { SPRITE_updateText("counter", ...); ... }
else if (my_uipageid == Drawer_Open_State && isAnyBucketTempAbove56()) { SPRITE_toggleSprites(...); }
else if (my_uipageid == MOTORJAM_ERR)       { SPRITE_toggleSprites(...); }
// ← 0x2020 and 0x2021 are NOT handled here
```

**Confirmed: Neither `0x2020` nor `0x2021` has any runtime update block.** Both screens are displayed **statically** — no animation, no text update, no progress indicator. The display is unchanged from the moment `load_screen()` is called until the state changes.

### 7.2 Shared Operations (all states in `UNDER_STM32_CONTROL`)

The following run every loop iteration regardless:

```cpp
TELEMETRY_scheduler(1);       // AWS telemetry on schedule
handleTimeSyncNonBlocking();  // NTP sync
TRIGGERS_process();           // AWS remote commands

if (delayedExecutionTimer) {  // every 10 seconds
    wifi.tick();
    CONNECTION_test(1);
}
```

---

## 8. Exit / Completion Behavior

### 8.1 Confirmed Exit Mechanism

Both `0x2020` and `0x2021` are exited when the STM32 broadcasts a new page ID. The `checkDrawerUIPageIds()` function detects the change (`stateChanged = true`) and routes to `GOTO_STM32_ALERT` for the new state.

**If STM32 transitions to Standby (`0x2010`) after test ends:**

```cpp
// HARDWARE.cpp:
bool HARDWARE::STM_isIdle() {
    return (my_uipageid == static_cast<uint16_t>(DisplayCommand::TX_CMD_Standby));
}

// main.ino:
else if (myhardware.STM_isIdle() && gDeviceStatus == UNDER_STM32_CONTROL) {
    if (gOVERRIDEcommands == GOTO_NONE) directOnlineForSkipProvisioning();
}

// directOnlineForSkipProvisioning():
gOVERRIDEcommands = GOTO_UI_IDLE;  // → load_screen(4) "READY"
```

**If STM32 transitions to a running state (`0x2011`–`0x2014`) after test ends:**

The running screen is loaded directly via `GOTO_STM32_ALERT`.

### 8.2 User-Initiated Stop — Motor Only (`0x2020`)

While in `0x2020`, BTN2 short (action 110) sends `STM32_BTN2CLICK` (0x04) to STM32. This is the same command that initially started the motor. Whether the STM32 treats a second `0x04` as a "stop" command, a toggle, or ignores it is **Not found in current ESP32 implementation**. The ESP32 sends the event and waits for the STM32 to broadcast a new page ID.

### 8.3 No User-Initiated Stop — Pump (`0x2021`)

While in `0x2021`, all physical buttons are disabled (config 14). The CANCEL button sprite is commented out. There is **no mechanism in the current implementation** for the user to stop the pump via the ESP32 UI. The pump runs until the STM32 decides to end the test and broadcasts a new page ID.

### 8.4 No `checkStateTransitionsForDrawer()` Explicit Handling

The transition out of `0x2020` or `0x2021` to Standby is **not** listed as an explicit transition in `checkStateTransitionsForDrawer()`. The general `stateChanged = true` path handles it. No buzzer fires on exit from these states.

---

## 9. State-Machine Flow

### 9.1 On Entry

```
STM32 broadcasts 0x2020 or 0x2021
    → processSerialFramesNonBlocking() parses my_uipageid
    → checkDrawerUIPageIds():
        [guard check — suppressed if OTA, provisioning, etc.]
        → stateChanged = true (new page ID)
        → checkStateTransitionsForDrawer() → returns false (no buzz)
        → STM_isIdle() = false
        → !STM_isIdle() && gDeviceStatus != UNDER_STM32_CONTROL → true (on first entry)
        → gOVERRIDEcommands = GOTO_STM32_ALERT

    → PROCESS_GOTOScreenCalls():
        → 0x2020: load_screen(11, langMap["016"], "", "")   "MOTOR RUNNING"
        → 0x2021: load_screen(18, langMap["067"], "", "")   "PUMP RUNNING"
        → gOVERRIDEcommands = GOTO_NONE
        → gDeviceStatus = UNDER_STM32_CONTROL
```

### 9.2 While Active

```
UNDER_STM32_CONTROL (every loop tick):
    → TELEMETRY_scheduler(1)
    → handleTimeSyncNonBlocking()
    → TRIGGERS_process()
    → [NO display update for 0x2020 or 0x2021 — screen is static]
    → every 10s: wifi.tick(), CONNECTION_test(1)
```

### 9.3 State Diagram

```
User presses BTN2 short / AWS STM_TESTGRINGINMOTOR
    → sendButtonEvent(STM32_BTN2CLICK 0x04)     ───────────► STM32 starts motor
                                                             │
User presses BTN2 long / AWS STM_TESTWATERPUMP              │
    → sendButtonEvent(STM32_TEST_WTR_PUMP 0x05) ───────────► STM32 starts pump
                                                             │
                                                             ▼
                                           STM32 broadcasts 0x2020 or 0x2021
                                                             │
                                                             ▼
                                                checkDrawerUIPageIds()
                                                   stateChanged = true
                                                   (no buzzer)
                                                             │
                                                             ▼
                                             gOVERRIDEcommands = GOTO_STM32_ALERT
                                                             │
                                               ┌────────────┴────────────┐
                                               │                         │
                                           0x2020                    0x2021
                                               │                         │
                                      load_screen(11)           load_screen(18)
                                      "MOTOR RUNNING"           "PUMP RUNNING"
                                      ICON_SETTING              ICON_SETTING
                                      CANCEL button             No button
                                      LED ON/ON                 LED ON/ON
                                      BTN2 short active         All buttons disabled
                                               │                         │
                                               └────────────┬────────────┘
                                                            │
                                              gDeviceStatus = UNDER_STM32_CONTROL
                                              (static display, telemetry continues)
                                                            │
                                   ┌────────────────────────┴────────────────────────┐
                                   │ (0x2020 only)                                   │
                             BTN2 short:                             STM32 broadcasts new page ID
                             STM32_BTN2CLICK (0x04)                         │
                             [STM32 decides next state]                      ▼
                                                                   stateChanged = true
                                                                   → GOTO_STM32_ALERT
                                                                   [new state processed]
                                                                            │
                                                                  if new state == Standby:
                                                                  → GOTO_UI_IDLE
                                                                  → load_screen(4) "READY"
```

---

## 10. Key Differences Between `0x2020` and `0x2021`

| Aspect                     | `0x2020` — Motor Running         | `0x2021` — Pump Running          |
|----------------------------|----------------------------------|----------------------------------|
| Screen number              | 11                               | 18                               |
| Primary text               | `"MOTOR RUNNING"`                | `"PUMP RUNNING"`                 |
| Icon                       | `ICON_SETTING` (PROGMEM)         | `ICON_SETTING` (PROGMEM)         |
| CANCEL button              | Rendered (sprite `"0041"`)       | Not rendered (commented out)     |
| Physical button config     | Config 12 (BTN2 short active)    | Config 14 (all disabled)         |
| User can interact          | Yes — BTN2 short sends `0x04`    | No — no physical button active   |
| Runtime animation          | None (static)                    | None (static)                    |
| Buzzer on entry            | No                               | No                               |
| LEDs on entry              | ON, ON                           | ON, ON                           |
| In `DisplayCommand` enum   | No                               | No                               |
| Explicit buzzer trigger    | No                               | No                               |

---

## 11. Differences Between Arduino and ESP-IDF Implementation

| Item | Arduino behavior | ESP-IDF status |
|------|-----------------|----------------|
| `0x2020` / `0x2021` defined in `config.h` | Yes | **Needs verification** |
| `0x2020` / `0x2021` in `DisplayCommand` enum | **No — gap in HARDWARE.h** | Match Arduino: do not include in the enum equivalent |
| Buzzer on entry | No | Confirmed — no buzzer needed |
| Screen 11 (motor running) | Yes — ICON_SETTING + "MOTOR RUNNING" + CANCEL button | **Needs implementation** |
| Screen 18 (pump running) | Yes — ICON_SETTING + "PUMP RUNNING" + no button | **Needs implementation** |
| ICON_SETTING asset | PROGMEM pixel array (not SPIFFS file) | **Needs implementation** — asset must be embedded in firmware, not loaded from flash file |
| BTN2 short → STM32_BTN2CLICK (`0x2020` only) | Yes | **Needs implementation** |
| All buttons disabled (`0x2021`) | Yes | **Needs implementation** |
| CANCEL button as touch input | Unknown in Arduino — behavior unclear | **Needs clarification** |
| Static display (no animation) | Yes — confirmed | **Confirmed simple** — load once and hold |
| LEDs ON during both states | Yes | **Needs implementation** |
| Exit via STM32 page change | Yes | **Needs implementation** |
| Return to idle when STM32 → Standby | Yes | **Needs implementation** |
| AWS remote trigger (`STM_TESTGRINGINMOTOR`, `STM_TESTWATERPUMP`) | Yes | **Needs verification** |
| Telemetry continues during test | Yes | **Confirmed requirement** |

---

## 12. Error / Unclear Points

### 12.1 `ICON_SETTING` — PROGMEM Not SPIFFS

`ICON_SETTING` is defined in `ASSETS.h` as a statically allocated PROGMEM pixel array:

```cpp
#define ICON_SETTING_W  67
#define ICON_SETTING_H  67
static const uint16_t ICON_SETTING[ICON_SETTING_W * ICON_SETTING_H] PROGMEM = { ... };
```

It is **not** a `.raw` file loaded from SPIFFS. The display engine detects it by name:

```cpp
else if (asset.source == "ICON_SETTING") { iconData = ICON_SETTING; ... }
```

For the ESP-IDF port: this icon must be embedded as a compiled-in resource (LittleFS image embedded at build time, or equivalent LVGL image descriptor), not downloaded as an asset file.

### 12.2 CANCEL Button on Screen 11 — Touch Behavior Unclear

Screen 11 renders a `"CANCEL"` button sprite (`"0041"`, `ASSET_BUTTON`) at x=200, y=205. However:
- No touch event handler for this sprite was found in the reviewed code paths.
- The `setButtonConfigurationByID(myui, 12)` only configures **physical** button actions.
- Whether the `ASSET_BUTTON` sprite is connected to touch input handling is **Not found in current implementation**.

For the ESP-IDF LVGL port: this button should be implemented as a functional LVGL button widget with a defined click callback, even if the Arduino version did not have touch handling clearly implemented.

### 12.3 `0x2020` / `0x2021` Not in `DisplayCommand` Enum

`HARDWARE.h`'s `DisplayCommand` enum does not include entries for `0x2020` or `0x2021`. This is a confirmed gap. The `checkStateTransitionsForDrawer()` function in `HARDWARE.cpp` uses this typed enum for comparisons and does not have cases for these two values. All handling for `0x2020` and `0x2021` is done via `config::TX_CMD` constants in `main.ino`.

For ESP-IDF: define these codes only in the equivalent of `config.h` (the command constants file), not necessarily in the hardware state enum if maintaining parity.

### 12.4 Pump Stopping — No User Mechanism

For `0x2021` (pump running), all physical buttons are disabled and the CANCEL button sprite is commented out. There is **no confirmed mechanism** in the current implementation for the user to stop the pump via the ESP32 display UI. The pump stops only when:
1. The STM32 internally decides to stop and broadcasts a new page ID.
2. An AWS remote command triggers a different STM32 action.

Whether this is intentional product behavior or a known limitation is **Needs clarification**.

### 12.5 What STM32 Sends After Motor/Pump Test Ends

What page ID the STM32 broadcasts after completing a motor or pump test is **Not found in current ESP32 implementation**. Possible values (Standby, Running_State, etc.) are unknown from the ESP32 source alone.

### 12.6 What STM32 Does With `STM32_BTN2CLICK` (0x04) During `0x2020`

On the motor running screen, BTN2 short sends `0x04` (the same command that started the motor). Whether the STM32 uses this as a stop command, a toggle, or for another purpose is **Not found in current ESP32 implementation**.

### 12.7 Display in `UNDER_STM32_CONTROL` When State Doesn't Change

If the STM32 continues to broadcast `0x2020` or `0x2021` (repeated frames with same page ID), `stateChanged` remains false and `gOVERRIDEcommands` stays `GOTO_NONE`. The screen remains unchanged indefinitely. There is no timeout or watchdog for these test states in the current implementation.

---

## 13. Implementation Guidance for ESP-IDF

This section provides mapping guidance only. **No implementation code is provided.**

### 13.1 Event Code Constants

Define the following constants:

```
MANUAL_MOTOR_CONTROL = 0x2020
WATER_PUMP_RUNNING   = 0x2021
```

These should be in the equivalent of `config.h`, not in any hardware state enum that mirrors `DisplayCommand`.

### 13.2 State Entry Routing

When `my_uipageid` changes to `0x2020` or `0x2021`:

- Apply the same guard list as all other STM32 states (do not interrupt OTA, provisioning, etc.)
- No buzzer on entry — confirmed.
- Load the appropriate screen (see §13.3 and §13.4).
- Set device state to `UNDER_STM32_CONTROL` equivalent.

### 13.3 Screen for `0x2020` (Motor Running)

Build a view containing:
- `ICON_SETTING` icon (67×67px, embedded resource), centered, upper area (y ≈ 60)
- Text: `"MOTOR RUNNING"` (key `"016"`), medium font, centered, lower area (y ≈ 160)
- CANCEL button (120×40px, text `"CANCEL"` key `"065"`), right-aligned at bottom (x=200, y=205)
- LEDs: both ON
- Buttons:
  - BTN2 short → send `STM32_BTN2CLICK` (0x04) to STM32
  - CANCEL button (touch) → behavior **Needs clarification** — suggested: send `STM32_BTN2CLICK` (0x04), matching BTN2 short
  - All other buttons: disabled

### 13.4 Screen for `0x2021` (Pump Running)

Build a view containing:
- `ICON_SETTING` icon (67×67px, embedded resource), centered, upper area (y ≈ 60)
- Text: `"PUMP RUNNING"` (key `"067"`), medium font, centered, lower area (y ≈ 160)
- No CANCEL button — confirmed intentional in Arduino (button is commented out)
- LEDs: both ON
- Buttons: **all disabled** — no physical button or touch action

### 13.5 No Runtime Animation

Neither state requires any render-loop update. Load the screen once when the state is entered. No timers, animations, or dynamic updates are needed until the state changes.

### 13.6 `ICON_SETTING` Asset

The `ICON_SETTING` image must be available as a compiled-in resource in the ESP-IDF firmware. It must not be loaded from LittleFS/SPIFFS at runtime — it is a static firmware asset.

In LVGL terms: define it as a `lv_img_dsc_t` descriptor with the pixel data embedded in the binary.

### 13.7 Exit from Test State

When `my_uipageid` changes away from `0x2020` or `0x2021`:

- Stop all display operations for the current test screen.
- Route the new page ID through the standard state-routing logic.
- If new page ID is `Standby` (`0x2010`): return to idle/ready screen.
- No buzzer fires on exit.

### 13.8 Verification Test Steps

**To trigger motor running (`0x2020`):**
1. While on the idle/ready screen, press BTN2 short → `STM32_BTN2CLICK` (0x04) is sent.
2. Inject UART frame with `my_uipageid = 0x2020`.
3. Expected: screen shows `ICON_SETTING`, text `"MOTOR RUNNING"`, CANCEL button visible.
4. Expected: LEDs are ON.
5. Expected: no buzzer fires.
6. Expected: BTN2 short sends `0x04` via UART.
7. Inject frame with `my_uipageid = 0x2010` (Standby): device returns to READY screen.

**To trigger pump running (`0x2021`):**
1. Press BTN2 long → `STM32_TEST_WTR_PUMP` (0x05) is sent.
2. Inject UART frame with `my_uipageid = 0x2021`.
3. Expected: screen shows `ICON_SETTING`, text `"PUMP RUNNING"`, no CANCEL button.
4. Expected: LEDs are ON.
5. Expected: no buzzer fires.
6. Expected: all physical buttons are disabled — no UART output on any button press.
7. Inject frame with `my_uipageid = 0x2010` (Standby): device returns to READY screen.

---

## 14. Not Found / Needs Clarification

| Item | Status |
|------|--------|
| What STM32 broadcasts after the motor test ends | **Not found in current implementation** |
| What STM32 broadcasts after the pump test ends | **Not found in current implementation** |
| Whether `STM32_BTN2CLICK` (0x04) stops the motor or acts as a toggle during `0x2020` | **Not found in current implementation** |
| Whether the CANCEL button sprite on screen 11 is connected to touch input handling | **Not found in current implementation** |
| Whether the absence of a stop button for `0x2021` is intentional product design | **Needs clarification** |
| What action (if any) the CANCEL button on screen 11 should trigger | **Needs clarification** |
| Whether `0x2020` and `0x2021` should be absent from the `DisplayCommand` enum in the ESP-IDF port as they are in Arduino | **Needs clarification** |
| Whether these test states are accessible from any screen other than READY (e.g., from error screens) | **Needs clarification** — BTN2 long (action 111) is available on error screen configs 7 and 9, which could trigger pump test from an error screen |

