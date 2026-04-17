# ESP32 Drawer Open / Drawer Pause UI State Mapping

## Scope

This document defines the UI and state-machine behavior for:

- `0x2015` — `Drawer_Open_State`
- `0x2016` — `Drawer_Pause_State`

It is derived exclusively from the current Arduino firmware source code and project documents.  
No behavior is invented or assumed. Where information is not found, it is explicitly marked.

---

## 1. Purpose

The STM32 co-processor broadcasts one of these two page IDs to indicate that the physical drawer of the FoodCycler FC75 is open or that a running cycle has been paused because the drawer was opened. The ESP32 must display the correct UI screen, apply runtime animations, configure button behavior, and correctly return to idle or resume the previous state when the drawer is closed.

---

## 2. Source of Truth

Document priority (highest to lowest):

1. `docs/AI_Guidelines.md`
2. `docs/Claude.md`
3. `docs/ai_prompts/base.md`
4. `docs/ai_prompts/analysis.md`
5. `docs/ai_prompts/verification.md`
6. Arduino firmware source files:
   - `config.h` — command code definitions
   - `HARDWARE.h` / `HARDWARE.cpp` — frame parser, `isDrawerOpen()`, `STM_isIdle()`, `checkStateTransitionsForDrawer()`
   - `main.ino` — state machine (`checkDrawerUIPageIds()`, `PROCESS_GOTOScreenCalls()`, `UNDER_STM32_CONTROL`)
   - `SCREEN.cpp` — `load_screen()` cases 24 and 27, `setButtonConfigurationByID()` case 17, `SPRITE_toggleSprites()`, `SPRITE_makeBlink()`
   - `UI.cpp` — `executeAction()` for actions 110, 111

Rule applied: Do not guess missing logic. Explicitly mark unknowns.

---

## 3. STM32 Message Mapping

### 3.1 Definitions

Defined in `config.h` (`config::TX_CMD`):

| Constant                       | Value    | Role             |
|--------------------------------|----------|------------------|
| `config::TX_CMD::Drawer_Open_State`  | `0x2015` | Drawer is open   |
| `config::TX_CMD::Drawer_Pause_State` | `0x2016` | Cycle paused, drawer open |

Mirrored in `HARDWARE.h` (`DisplayCommand` enum):

| Enum entry                              | Value    |
|-----------------------------------------|----------|
| `DisplayCommand::TX_CMD_Drawer_Open_State`  | `0x2015` |
| `DisplayCommand::TX_CMD_Drawer_Pause_State` | `0x2016` |

These values are received in the UART frame from STM32, parsed as `my_uipageid` (for the active drawer) by `processSerialFramesNonBlocking()` in `HARDWARE.cpp`.

### 3.2 How Page ID Is Extracted

Source: `HARDWARE.cpp`, frame parser (`processSerialFramesNonBlocking()`):

- `drawer1_uipageid` = `frameBuf[73] | (frameBuf[74] << 8)`
- `drawer2_uipageid` = `frameBuf[75] | (frameBuf[76] << 8)`
- `my_uipageid` is then assigned based on `gSYSTEM_drawer`:
  - If drawer == 2: `my_uipageid = drawer2_uipageid`
  - If drawer == 1: `my_uipageid = drawer1_uipageid`

---

## 4. Arduino Behavior

### 4.1 Entry Point — `checkDrawerUIPageIds()`

Source: `main.ino`, function `checkDrawerUIPageIds()`

Called every loop iteration. Compares `my_uipageid` (current) against `my_Lastuipageid` (previous):

```cpp
bool stateChanged = false;
if (prev_page != now_page) stateChanged = true;

if (myhardware.checkStateTransitionsForDrawer(gSYSTEM_drawer)) buzzThisCycle = true;

// STM alert or page-change => immediate STM alert flow
if ((!myhardware.STM_isIdle() && gDeviceStatus != UNDER_STM32_CONTROL) || stateChanged) {
    gOVERRIDEcommands = GOTO_STM32_ALERT;
}
```

Result: Any change in `my_uipageid` sets `gOVERRIDEcommands = GOTO_STM32_ALERT`.

### 4.2 Buzzer on Entry

Source: `HARDWARE.cpp`, `checkStateTransitionsForDrawer()`:

```cpp
// Buzz once for entering Drawer Open, Drawer Pause, or any error code
if ((now == DisplayCommand::TX_CMD_Drawer_Open_State ||
     now == DisplayCommand::TX_CMD_Drawer_Pause_State ||
     (curr_cmd >= 0x2030 && curr_cmd <= 0x2049)) && (prev_cmd != curr_cmd)) {
    my_Lastuipageid = curr_cmd;
    return true;  // triggers myui.trigger_buzz() in main.ino
}
```

Result: Buzzer fires **once** when the page ID first changes to `0x2015` or `0x2016`.

### 4.3 Screen Load for `0x2015` — Drawer Open

Source: `main.ino`, `PROCESS_GOTOScreenCalls()`, `GOTO_STM32_ALERT` branch:

```cpp
case config::TX_CMD::Drawer_Open_State:
    if (myhardware.isAnyBucketTempAbove56(gSYSTEM_drawer)) {
        mydisplay.load_screen(27, myui,
            mydisplay.langMap["025"],   // "CAUTION HOT!"
            mydisplay.langMap["020"],   // "DRAWER OPEN"
            emptyS);
    } else {
        mydisplay.load_screen(27, myui,
            mydisplay.langMap["020"],   // "DRAWER OPEN"
            emptyS,
            emptyS);
    }
    break;
```

Both paths use **screen 27**. Arguments differ depending on temperature:

| Condition        | pVar1 (large text)             | pVar2 (small text)             |
|------------------|-------------------------------|-------------------------------|
| Temperature ≤ 56°C | `langMap["020"]` = "DRAWER OPEN" | _(empty)_                  |
| Temperature > 56°C | `langMap["025"]` = "CAUTION HOT!" | `langMap["020"]` = "DRAWER OPEN" |

### 4.4 Screen Load for `0x2016` — Drawer Pause

Source: `main.ino`, `PROCESS_GOTOScreenCalls()`, `GOTO_STM32_ALERT` branch:

```cpp
case config::TX_CMD::Drawer_Pause_State:
    if (myhardware.isAnyBucketTempAbove56(gSYSTEM_drawer)) {
        mydisplay.load_screen(27, myui,
            mydisplay.langMap["025"],   // "CAUTION HOT!"
            mydisplay.langMap["002"],   // "PAUSED"
            emptyS);
    } else {
        mydisplay.load_screen(24, myui,
            mydisplay.langMap["020"],   // "DRAWER OPEN"
            mydisplay.langMap["002"],   // "PAUSED"
            emptyS);
    }
    break;
```

| Condition        | Screen | pVar1 (large text)              | pVar2 (medium text)            |
|------------------|--------|---------------------------------|-------------------------------|
| Temperature ≤ 56°C | 24   | `langMap["020"]` = "DRAWER OPEN" | `langMap["002"]` = "PAUSED" |
| Temperature > 56°C | 27   | `langMap["025"]` = "CAUTION HOT!" | `langMap["002"]` = "PAUSED" |

The screen changes depending on temperature: **screen 24** (no icon) when cool, **screen 27** (with WARNING icon) when hot.

---

## 5. Screen Definitions

### 5.1 Screen 27 — Drawer Open (with Icon)

Source: `SCREEN.cpp`, `load_screen()`, case 27:

```cpp
case 27: {
    myui.setLedDefaults(BLINK, BLINK);
    setButtonConfigurationByID(myui, 17);

    Asset iconSprite = { "alert_icon", 127, LINE7Y, 67, 67, ...,
                         ASSET_ICON, "/assets/WARNING.raw", ... };
    SPRITE_create(iconSprite);

    Asset textSprite  = { "error1", 0, LINE8Y, 320, FONT4H, ...,
                          ASSET_TEXT, pVar1, ..., FONT4, ... };
    SPRITE_create(textSprite);

    Asset textSprite1 = { "error2", 0, LINE9Y, 320, FONT2H, ...,
                          ASSET_TEXT, pVar2, ..., FONT2, ... };
    SPRITE_create(textSprite1);
}
```

| Element        | Sprite ID    | Asset type   | Content                           |
|----------------|-------------|--------------|-----------------------------------|
| Icon           | `alert_icon` | ASSET_ICON   | `/assets/WARNING.raw`             |
| Primary text   | `error1`     | ASSET_TEXT   | pVar1 (large font FONT4)          |
| Secondary text | `error2`     | ASSET_TEXT   | pVar2 (medium font FONT2)         |
| LED 1          | —            | —            | BLINK                             |
| LED 2          | —            | —            | BLINK                             |
| Buttons        | —            | —            | Profile 17 (see §6)               |

Used for: `0x2015` (both temp paths) and `0x2016` (hot path only).

### 5.2 Screen 24 — Drawer Pause (no Icon)

Source: `SCREEN.cpp`, `load_screen()`, case 24:

```cpp
case 24: {
    myui.setLedDefaults(OFF, OFF);
    setButtonConfigurationByID(myui, 17);

    Asset textSprite  = { "error1",  0, LINE8Y, 320, FONT4H, ...,
                          ASSET_TEXT, pVar1, ..., FONT4, ... };
    SPRITE_create(textSprite);

    Asset textSprite1 = { "counter", 0, LINE9Y, 320, FONT2H, ...,
                          ASSET_TEXT, pVar2, ..., FONT2, ... };
    SPRITE_create(textSprite1);
}
```

| Element        | Sprite ID  | Asset type  | Content                            |
|----------------|-----------|-------------|-------------------------------------|
| Icon           | _(none)_  | —           | No icon in this screen              |
| Primary text   | `error1`   | ASSET_TEXT  | pVar1 = "DRAWER OPEN" (large FONT4) |
| Secondary text | `counter`  | ASSET_TEXT  | pVar2 = "PAUSED" (medium FONT2)     |
| LED 1          | —          | —           | OFF                                 |
| LED 2          | —          | —           | OFF                                 |
| Buttons        | —          | —           | Profile 17 (see §6)                 |

Used for: `0x2016` (non-hot path only).

---

## 6. Button Configuration for Both States

Both screen 24 and screen 27 use `setButtonConfigurationByID(myui, 17)`.

Source: `SCREEN.cpp`, `setButtonConfigurationByID()`, case 17:

```cpp
case 17: {
    int actions[BUTTON_DETECTION_COUNT] = {
    //   click  short  long  vlong  ext
        0,     0,     0,    0,     0,   // BTN1
        0,   110,   111,    0,     0,   // BTN2
        0,     0,     0,    0,     0    // BOTH
    };
    configButtons(myui, actions);
}
```

| Button event   | Action ID | Behavior                                      |
|----------------|-----------|-----------------------------------------------|
| BTN2 short     | 110       | Send `STM32_BTN2CLICK` (0x04) to STM32        |
| BTN2 long      | 111       | Send `STM32_TEST_WTR_PUMP` (0x05) to STM32    |
| All others     | 0         | Disabled — no action                          |

Source for action behavior: `UI.cpp`, `executeAction()`:

```cpp
case 110:
    myhardware.sendButtonEvent(gSYSTEM_drawer, config::TX_CMD::STM32_BTN2CLICK);
    break;
case 111:
    myhardware.sendButtonEvent(gSYSTEM_drawer, config::TX_CMD::STM32_TEST_WTR_PUMP);
    break;
```

**Confirmed:** No button action to manually close the drawer screen or return to idle is mapped for either `0x2015` or `0x2016`. The ESP32 relies entirely on the next STM32 page broadcast to exit these screens.

---

## 7. Runtime Updates in `UNDER_STM32_CONTROL`

After a screen is loaded, `gDeviceStatus = UNDER_STM32_CONTROL`. Each loop iteration runs the `UNDER_STM32_CONTROL` block in `main.ino`, which updates dynamic elements.

Source: `main.ino`, case `UNDER_STM32_CONTROL`:

### 7.1 `0x2016` — Drawer Pause, temperature ≤ 56°C

```cpp
} else if (myhardware.my_uipageid == config::TX_CMD::Drawer_Pause_State) {
    mydisplay.SPRITE_makeBlink("counter", 1);
}
```

- `SPRITE_makeBlink("counter", 1)` makes the `counter` sprite (which shows "PAUSED") alternate between `TFT_WHITE` and `TFT_LIGHTGREY` every 1 second.
- This creates a visible blinking "PAUSED" text effect on screen 24.

### 7.2 `0x2015` — Drawer Open, temperature > 56°C  
### and `0x2016` — Drawer Pause, temperature > 56°C (shared path)

```cpp
} else if (myhardware.my_uipageid == config::TX_CMD::Drawer_Pause_State
           && myhardware.isAnyBucketTempAbove56(gSYSTEM_drawer)) {
    mydisplay.SPRITE_toggleSprites("alert_icon", "alert_text",
        "/assets/POWER.raw", "/assets/WARNING.raw", "020", "020", 2);
} else if (myhardware.my_uipageid == config::TX_CMD::Drawer_Open_State
           && myhardware.isAnyBucketTempAbove56(gSYSTEM_drawer)) {
    mydisplay.SPRITE_toggleSprites("alert_icon", "alert_text",
        "/assets/POWER.raw", "/assets/WARNING.raw", "020", "020", 2);
}
```

`SPRITE_toggleSprites` with a 2-second period:

| Toggle target  | Sprite ID    | Phase A          | Phase B           |
|----------------|-------------|-----------------|-------------------|
| Icon           | `alert_icon` | `/assets/POWER.raw` | `/assets/WARNING.raw` |
| Text (no-op)   | `alert_text` | _(not found in screen 27)_ | _(not found)_ |

**Note:** `alert_text` is not a sprite created by `load_screen(27, ...)` (screen 27 creates `error1` and `error2`, not `alert_text`). The `SPRITE_find("alert_text")` call in `SPRITE_toggleSprites` returns -1. The text toggle is a silent no-op. Only `alert_icon` alternates between POWER.raw and WARNING.raw icons.

### 7.3 `0x2015` — Drawer Open, temperature ≤ 56°C

No runtime update block is present for this state and temperature condition in `UNDER_STM32_CONTROL`. Screen 27 is displayed statically with "DRAWER OPEN" text and WARNING.raw icon.

---

## 8. Header Icon

Source: `main.ino`, `loop()`:

```cpp
mydisplay.SPRITE_updateHeader(
    gSYSTEM_WIFI, gSYSTEM_AWS,
    myble.pServer != nullptr,
    myhardware.isDrawerOpen(),
    myhardware.isAnyBucketTempAbove56(gSYSTEM_drawer)
);
```

Source: `HARDWARE.cpp`, `isDrawerOpen()`:

```cpp
bool HARDWARE::isDrawerOpen() {
    return (my_uipageid == static_cast<uint16_t>(DisplayCommand::TX_CMD_Drawer_Open_State) ||
            my_uipageid == static_cast<uint16_t>(DisplayCommand::TX_CMD_Drawer_Pause_State));
}
```

**Confirmed:** The drawer-open header icon (`ICON_DRAWER`, rendered in orange) is displayed for **both** `0x2015` and `0x2016`. It is cleared when the page transitions away from either of these two values.

---

## 9. State-Machine Transitions

### 9.1 On Entry (`0x2015` or `0x2016` received)

```
STM32 broadcasts new page ID
    → processSerialFramesNonBlocking() parses my_uipageid
    → checkDrawerUIPageIds() detects stateChanged = true
    → gOVERRIDEcommands = GOTO_STM32_ALERT
    → checkStateTransitionsForDrawer() returns true → trigger_buzz()
    → PROCESS_GOTOScreenCalls() handles GOTO_STM32_ALERT
        → load_screen(27) or load_screen(24) (temperature-dependent)
        → gOVERRIDEcommands = GOTO_NONE
        → gDeviceStatus = UNDER_STM32_CONTROL
```

### 9.2 While Active (every loop iteration in `UNDER_STM32_CONTROL`)

```
UNDER_STM32_CONTROL:
    → TELEMETRY_scheduler(1)
    → handleTimeSyncNonBlocking()
    → TRIGGERS_process()
    → runtime display updates (blinking / icon toggle — see §7)
    → wifi.tick() + CONNECTION_test(1) (on 10s timer)
```

### 9.3 State Diagram

```
              STM32 sends 0x2015 / 0x2016
                          │
                          ▼
                  checkDrawerUIPageIds()
                          │
                  stateChanged = true
                          │
                          ▼
              gOVERRIDEcommands = GOTO_STM32_ALERT
                          │
              PROCESS_GOTOScreenCalls()
                          │
             ┌────────────┴────────────┐
             │                         │
         NOT hot                     IS hot
             │                         │
          0x2015 → load_screen(27)   Both → load_screen(27)
          0x2016 → load_screen(24)   (with CAUTION HOT! text)
             │                         │
             └────────────┬────────────┘
                          │
                 gDeviceStatus = UNDER_STM32_CONTROL
                          │
              (loop until STM32 sends new page)
                          │
             ┌────────────┴────────────────┐
             │                              │
    STM goes idle                 STM sends new page ID
    (Standby / offline)           (any other page)
             │                              │
   directOnlineForSkipProvisioning()    GOTO_STM32_ALERT
             │                          (new state)
   GOTO_UI_IDLE → load_screen(4)
```

---

## 10. Drawer Close Handling

### 10.1 Confirmed Mechanism

When the STM32 sends a different page ID after the drawer is closed, `checkDrawerUIPageIds()` detects a state change and sets `gOVERRIDEcommands = GOTO_STM32_ALERT`. The new STM32 state is then processed exactly as any other state transition.

If the STM32 transitions to `Standby` (`0x2010`), `STM_isIdle()` returns `true`:

```cpp
// HARDWARE.cpp, STM_isIdle():
return d1 == static_cast<uint16_t>(DisplayCommand::TX_CMD_Standby);
```

This triggers:

```cpp
// main.ino, checkDrawerUIPageIds():
else if (myhardware.STM_isIdle() && gDeviceStatus == UNDER_STM32_CONTROL) {
    if (gOVERRIDEcommands == GOTO_NONE) directOnlineForSkipProvisioning();
}

// directOnlineForSkipProvisioning():
if (gSYSTEM_PROVISIONED) {
    gOVERRIDEcommands = GOTO_UI_IDLE;  // → load_screen(4) "READY"
}
```

### 10.2 Explicit Allowed Transition — Drawer Pause to Standby

Source: `HARDWARE.cpp`, `checkStateTransitionsForDrawer()`:

```cpp
if (prev == DisplayCommand::TX_CMD_Drawer_Pause_State &&
    now == DisplayCommand::TX_CMD_Standby) {
    my_Lastuipageid = curr_cmd;
    return true;  // triggers buzzer
}
```

**Confirmed:** The transition `0x2016 → Standby` is explicitly handled with a buzzer event.

### 10.3 No Explicit Allowed Transition for Drawer Open to Standby

`0x2015 → Standby` is NOT listed in the explicit transition table in `checkStateTransitionsForDrawer()`. However, the general state-change detection path (`stateChanged = true`) still routes to `GOTO_STM32_ALERT`, and if the new state is Standby, `STM_isIdle()` returns `true`, leading to `GOTO_UI_IDLE`.

No buzzer fires for `0x2015 → Standby` unless the general transition detection fires first (which it does on `stateChanged`).

---

## 11. Expected UI Behavior Table

| State received | Temperature | Screen loaded | pVar1 text      | pVar2 text    | LED behavior    | Runtime animation |
|----------------|-------------|--------------|----------------|--------------|-----------------|------------------|
| `0x2015`       | ≤ 56°C      | 27           | "DRAWER OPEN"  | _(empty)_    | BLINK, BLINK    | None (static)    |
| `0x2015`       | > 56°C      | 27           | "CAUTION HOT!" | "DRAWER OPEN"| BLINK, BLINK    | Icon toggles POWER.raw / WARNING.raw every 2s |
| `0x2016`       | ≤ 56°C      | 24           | "DRAWER OPEN"  | "PAUSED"     | OFF, OFF        | "PAUSED" text blinks (1s period) |
| `0x2016`       | > 56°C      | 27           | "CAUTION HOT!" | "PAUSED"     | BLINK, BLINK    | Icon toggles POWER.raw / WARNING.raw every 2s |

---

## 12. Screen Mapping Summary

| Screen number | Used for                                               |
|---------------|-------------------------------------------------------|
| 27            | `0x2015` (both temp paths), `0x2016` (hot path only) |
| 24            | `0x2016` (non-hot path only)                          |

---

## 13. Error / Unclear Points

### 13.1 `alert_text` Sprite Mismatch — Confirmed Discrepancy

In `UNDER_STM32_CONTROL`, the hot-path runtime handler calls:

```cpp
mydisplay.SPRITE_toggleSprites("alert_icon", "alert_text",
    "/assets/POWER.raw", "/assets/WARNING.raw", "020", "020", 2);
```

However, screen 27 does **not** create a sprite with ID `"alert_text"`. It creates `"error1"` and `"error2"`. The `SPRITE_find("alert_text")` returns -1, and the text-toggle half of this call is a **silent no-op**.

Only the `alert_icon` sprite (which **does** exist in screen 27) toggles between POWER.raw and WARNING.raw.

This is a confirmed discrepancy in the current implementation. Whether this is intentional or a bug is **Needs clarification**.

### 13.2 STM32 State After Drawer Close — Not Found

**What state does the STM32 send after the drawer is closed from `0x2015`?**  
Not found in current implementation. The STM32 source code is not part of this repository.

**What state does the STM32 send after the drawer is closed from `0x2016`?**  
Not found in current implementation. The explicit transition `Drawer_Pause_State → Standby` exists in the ESP32 code (see §10.2), suggesting Standby is an expected post-close state. However, whether the STM32 can also transition `0x2016 → Running_State` (resuming the cycle) is not confirmed from current code.

### 13.3 Cycle Resume Behavior After `0x2016` — Not Found

Whether a cycle that was paused due to the drawer opening (`0x2016`) can automatically resume when the drawer is closed is **not found in current implementation**. This decision is made on the STM32 side. The ESP32 code contains no "resume" intermediate screen or logic path — it simply follows whatever page ID the STM32 next broadcasts.

### 13.4 Intermediate "Resume" Screen — Not Found

No intermediate screen or splash is shown when transitioning from `0x2015` or `0x2016` back to a running state. The transition goes directly to the new STM32-driven state via `GOTO_STM32_ALERT`.

### 13.5 `0x2015` versus `0x2016` Semantic Distinction

Based on the code alone:

- `0x2015` (`Drawer_Open_State`): renders screen 27 (with WARNING icon) in both temperature conditions. No "PAUSED" text shown.
- `0x2016` (`Drawer_Pause_State`): renders screen 24 (no icon, "PAUSED" blinking text) when cool, or screen 27 (hot) with "PAUSED" as pVar2.

The product-level distinction between "the drawer is open" and "a cycle is paused because the drawer opened" is **Needs clarification** from the hardware team or product documentation. The code makes them distinguishable via different screens but does not document the product intent.

---

## 14. Implementation Guidance for ESP-IDF

This section describes where the equivalent logic must exist in the ESP-IDF firmware. **No implementation code is provided here.** This is mapping guidance only.

### 14.1 Command Code Definitions

Define the following constants (equivalent to `config::TX_CMD`):

```
DRAWER_OPEN_STATE  = 0x2015
DRAWER_PAUSE_STATE = 0x2016
```

### 14.2 Frame Parser

The ESP-IDF frame parser (equivalent to `processSerialFramesNonBlocking()` in `HARDWARE.cpp`) must:

- Extract `drawer1_uipageid` from frame bytes 73–74 (little-endian)
- Extract `drawer2_uipageid` from frame bytes 75–76 (little-endian)
- Set `my_uipageid` to the value for the active drawer

### 14.3 State Change Detection

Equivalent to `checkDrawerUIPageIds()` in `main.ino`:

- On any change in `my_uipageid`, trigger the STM32 alert routing for the new page ID.
- Do not interrupt OTA download, asset download, provisioning, or firmware transfer states.
- Buzzer must fire once on first entry into `0x2015` or `0x2016`.

### 14.4 Screen for `0x2015`

When `my_uipageid == DRAWER_OPEN_STATE`:

- Check temperature:
  - If temp > 56°C: show screen equivalent to screen 27 with pVar1="CAUTION HOT!", pVar2="DRAWER OPEN"
  - If temp ≤ 56°C: show screen equivalent to screen 27 with pVar1="DRAWER OPEN", pVar2=""
- Start blinking LEDs (both LED 1 and LED 2).
- Enable buttons: BTN2 short → send `STM32_BTN2CLICK` (0x04); BTN2 long → send `STM32_TEST_WTR_PUMP` (0x05).
- In the render loop: if still in DRAWER_OPEN_STATE and temp > 56°C, alternate icon between POWER.raw and WARNING.raw every 2 seconds.

### 14.5 Screen for `0x2016`

When `my_uipageid == DRAWER_PAUSE_STATE`:

- Check temperature:
  - If temp > 56°C: show screen equivalent to screen 27 with pVar1="CAUTION HOT!", pVar2="PAUSED"
  - If temp ≤ 56°C: show screen equivalent to screen 24 with pVar1="DRAWER OPEN", pVar2="PAUSED"; no icon; LEDs off
- Enable same buttons as `0x2015` (profile 17).
- In the render loop:
  - If temp > 56°C: alternate icon between POWER.raw and WARNING.raw every 2 seconds (same as `0x2015` hot path).
  - If temp ≤ 56°C: blink the "PAUSED" text element at 1-second period.

### 14.6 Header Icon

The drawer-open header icon must be displayed when `my_uipageid` is either `0x2015` or `0x2016`. It must be cleared when the page changes to any other value.

Equivalent to `isDrawerOpen()` in `HARDWARE.cpp`:

```
isDrawerOpen = (my_uipageid == 0x2015 || my_uipageid == 0x2016)
```

### 14.7 Drawer Close / Exit from State

When `my_uipageid` changes away from `0x2015` or `0x2016`:

- Re-run the state-routing logic for the new page ID.
- If the new page ID is `Standby` (`0x2010`) and no other override is pending, navigate to the idle/ready screen.
- Buzzer fires once on entry into Standby from `0x2016` (confirmed explicit transition).
- For `0x2015 → Standby`, buzzer does not fire via the explicit transition table (only via general state-change detection).

### 14.8 Temperature Monitoring

The temperature check used in both `0x2015` and `0x2016` is `isAnyBucketTempAbove56(drawer)`:

```cpp
// HARDWARE.cpp
if (drawer == 1) return (temp_ntc_bucket1 > 580 || temp_rtd_heater1 > 580);
if (drawer == 2) return (temp_ntc_bucket2 > 580 || temp_rtd_heater2 > 580);
```

Temperatures are stored as integer tenths of °C (560 = 56.0°C). The threshold used in the current code is `> 580` (58.0°C), not 56.0°C as stated in the function name. This discrepancy is **Needs clarification**.

### 14.9 State Machine State

After loading the screen for either `0x2015` or `0x2016`, the device state must be set to `UNDER_STM32_CONTROL` (or the ESP-IDF equivalent). This state:

- Continues telemetry scheduling.
- Continues time sync.
- Continues WiFi and AWS connection management.
- Applies runtime display updates (blinking, icon toggle) on every render cycle.

---

## 15. Summary Table (Portable Reference)

| STM state | Meaning             | Screen | Icon           | Text row 1 (large) | Text row 2 (medium) | LED      | Runtime animation          | Exit trigger                          |
|-----------|---------------------|--------|----------------|--------------------|--------------------|----------|---------------------------|---------------------------------------|
| `0x2015`  | Drawer open         | 27     | WARNING.raw    | "DRAWER OPEN"      | _(empty)_          | BLINK×2  | None (static, cool)        | Next STM32 page broadcast             |
| `0x2015`  | Drawer open + hot   | 27     | toggles        | "CAUTION HOT!"     | "DRAWER OPEN"      | BLINK×2  | Icon toggles 2s (hot)      | Next STM32 page broadcast             |
| `0x2016`  | Pause (cool)        | 24     | _(none)_       | "DRAWER OPEN"      | "PAUSED" (blinks)  | OFF×2    | "PAUSED" blinks 1s         | Next STM32 page broadcast             |
| `0x2016`  | Pause + hot         | 27     | toggles        | "CAUTION HOT!"     | "PAUSED"           | BLINK×2  | Icon toggles 2s (hot)      | Next STM32 page broadcast             |

---

## 16. Not Found / Needs Clarification

| Item | Status |
|------|--------|
| STM32 state sent after drawer is closed from `0x2015` | **Not found in current implementation** |
| STM32 state sent after drawer is closed from `0x2016` | **Not found in current implementation** |
| Whether cycle resumes after `0x2016` (STM32 decision) | **Not found in current implementation** |
| Product intent of `alert_text` sprite in the hot-path toggle (silent no-op) | **Needs clarification** |
| Why the temperature threshold is `> 580` (58.0°C) when the function is named `isAnyBucketTempAbove56` | **Needs clarification** |
| Whether `0x2015 → Running_State` transition is possible (drawer closed mid-cycle) | **Not found in current implementation** |
| Whether `0x2016 → Running_State` transition is possible (cycle resumes) | **Not found in current implementation** |
| Intended behavior of BTN1 during `0x2015`/`0x2016` (all BTN1 actions disabled in profile 17) | **Needs clarification** |

