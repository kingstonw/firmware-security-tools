# ESP32 Warning / Error State Mapping — `0x2030` to `0x2049`

## Scope

This document defines the UI and state-machine behavior for all STM32 error codes in the range:

- `0x2030` — `MOTOR_ERR`
- `0x2031` — `MOTORJAM_ERR`
- `0x2032` — `HEATER_ERR`
- `0x2033` — `OVERHEAT_ERR`
- `0x2034` — `CMP_ERR`
- `0x2035` — `HEATPUMP_ERR`
- `0x2036` — `BB1_sensor_ERR`
- `0x2037` — `BB2_sensor_ERR`
- `0x2038` — `Heater1_sensor_ERR`
- `0x2039` — `Heater2_sensor_ERR`
- `0x2040` — `CMP_sensor_ERR`
- `0x2041` — `EVP_sensor_ERR`
- `0x2042` — `C2Fan_sensor_1_ERR`
- `0x2043` — `Damper_ERR`
- `0x2044` — `PAFan_ERR`
- `0x2045` — `Water_Pump_ERR`
- `0x2046` — `Filter_Fan_ERR`
- `0x2047` — `C2Fan_sensor_2_ERR`
- `0x2048` — `C2Fan_sensor_3_ERR`
- `0x2049` — `C2Fan_sensor_4_ERR`

Derived exclusively from Arduino firmware source code and project guideline documents.  
No behavior is invented or assumed. Unknowns are explicitly marked.

---

## 1. Purpose

The STM32 co-processor broadcasts one of these error page IDs when a hardware fault is detected. The ESP32 must display the correct UI screen, configure buttons for user interaction, apply runtime animations (where applicable), and correctly exit the error state when the condition is cleared or the user triggers a reboot.

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
   - `config.h` — error code constant definitions and language map
   - `HARDWARE.h` — `DisplayCommand` enum, `ERROR_BASE`/`ERROR_MAX`, `error_seen[]`
   - `HARDWARE.cpp` — `checkStateTransitionsForDrawer()`, frame parser
   - `main.ino` — `checkDrawerUIPageIds()`, `GOTO_STM32_ALERT` switch, `UNDER_STM32_CONTROL`
   - `SCREEN.cpp` — `load_screen()` cases 30 and 32, `setButtonConfigurationByID()` cases 7 and 9, `SPRITE_toggleSprites()`
   - `UI.cpp` — `executeAction()` for actions 108, 109, 110, 111

Rule applied: Do not guess missing logic. Explicitly mark unknowns.

---

## 3. STM32 Error Code Range Overview

### 3.1 Definitions — `config.h` and `HARDWARE.h`

All error codes are defined twice: once in `config::TX_CMD` (config.h) and once in `DisplayCommand` enum (HARDWARE.h).

| Code     | `config::TX_CMD` constant      | `DisplayCommand` enum entry        | Meaning                   |
|----------|--------------------------------|------------------------------------|---------------------------|
| `0x2030` | `MOTOR_ERR`                    | `TX_CMD_MOTOR_ERR`                 | Motor failure             |
| `0x2031` | `MOTORJAM_ERR`                 | `TX_CMD_MOTORJAM_ERR`              | Motor jam / bucket jam    |
| `0x2032` | `HEATER_ERR`                   | `TX_CMD_HEATER_ERR`                | Heater failure            |
| `0x2033` | `OVERHEAT_ERR`                 | `TX_CMD_OVERHEAT_ERR`              | Device overheating        |
| `0x2034` | `CMP_ERR`                      | `TX_CMD_CMP_ERR`                   | Compressor failure        |
| `0x2035` | `HEATPUMP_ERR`                 | `TX_CMD_HEATPUMP_ERR`              | Heat pump failure         |
| `0x2036` | `BB1_sensor_ERR`               | `TX_CMD_BB1_sensor_ERR`            | Bucket Bay 1 sensor fault |
| `0x2037` | `BB2_sensor_ERR`               | `TX_CMD_BB2_sensor_ERR`            | Bucket Bay 2 sensor fault |
| `0x2038` | `Heater1_sensor_ERR`           | `TX_CMD_Heater1_sensor_ERR`        | Heater 1 sensor fault     |
| `0x2039` | `Heater2_sensor_ERR`           | `TX_CMD_Heater2_sensor_ERR`        | Heater 2 sensor fault     |
| `0x2040` | `CMP_sensor_ERR`               | `TX_CMD_CMP_sensor_ERR`            | Compressor sensor fault   |
| `0x2041` | `EVP_sensor_ERR`               | `TX_CMD_EVP_sensor_ERR`            | Evaporator sensor fault   |
| `0x2042` | `C2Fan_sensor_1_ERR`           | `TX_CMD_C2Fan_sensor_1_ERR`        | C2 Fan sensor 1 fault     |
| `0x2043` | `Damper_ERR`                   | `TX_CMD_Damper_ERR`                | Damper failure            |
| `0x2044` | `PAFan_ERR`                    | `TX_CMD_PAFan_ERR`                 | PA Fan failure            |
| `0x2045` | `Water_Pump_ERR`               | `TX_CMD_Water_Pump_ERR`            | Water pump failure        |
| `0x2046` | `Filter_Fan_ERR`               | `TX_CMD_Filter_Fan_ERR`            | Filter fan failure        |
| `0x2047` | `C2Fan_sensor_2_ERR`           | `TX_CMD_C2Fan_sensor_2_ERR`        | C2 Fan sensor 2 fault     |
| `0x2048` | `C2Fan_sensor_3_ERR`           | `TX_CMD_C2Fan_sensor_3_ERR`        | C2 Fan sensor 3 fault     |
| `0x2049` | `C2Fan_sensor_4_ERR`           | `TX_CMD_C2Fan_sensor_4_ERR`        | C2 Fan sensor 4 fault     |

### 3.2 Error Tracking Array

Defined in `HARDWARE.h`:

```cpp
static constexpr int ERROR_BASE = 0x2030;
static constexpr int ERROR_MAX  = 0x2049;
bool error_seen[(ERROR_MAX - ERROR_BASE) + 1] = { false };
```

**Status:** `error_seen[]` is declared but **never written to or read from** in any `.cpp` file found in the current implementation. It is effectively dead code.

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

Frame bytes 73–76 carry the active page ID for each drawer (little-endian 16-bit). `my_uipageid` reflects the currently selected drawer.

---

## 4. Arduino Behavior

### 4.1 Entry Point — `checkDrawerUIPageIds()`

Source: `main.ino`, `checkDrawerUIPageIds()`

Called every loop iteration. Guards are applied first to prevent error alerts from interrupting critical operations:

```cpp
// States that block error alerts:
if (gDeviceStatus == FIRMWARETRANSFERTOSTM
 || gDeviceStatus == UPDATEMANAGER
 || gDeviceStatus == LOADINGSETTINGS
 || gDeviceStatus == PROVISIONING
 || gDeviceStatus == FIRMWAREDOWNLOADING
 || gDeviceStatus == ASSETDOWNLOADING
 || gDeviceStatus == TESTWIFI
 || gDeviceStatus == DECISION_WITH_TIMEOUT
 || gDeviceStatus == FIRMWAREDOWNLOADDECISION
 || gDeviceStatus == UNPROVISIONED
 || gDeviceStatus == UNPROVISIONEDSTART
 || ota.assetDLState != OTA::DL_IDLE
 || gDeviceStatus == BLEBROADCASTING) {
    return;  // error alert suppressed
}
```

After guards pass, state-change detection runs:

```cpp
bool stateChanged = false;
if (prev_page != now_page) stateChanged = true;

if (myhardware.checkStateTransitionsForDrawer(gSYSTEM_drawer)) buzzThisCycle = true;

if (buzzThisCycle) myui.trigger_buzz();

if ((!myhardware.STM_isIdle() && gDeviceStatus != UNDER_STM32_CONTROL) || stateChanged) {
    gOVERRIDEcommands = GOTO_STM32_ALERT;
}
```

**Additional guard for self-test error state:**

```cpp
if (prev_page == config::TX_CMD::Show_Self_Test_Error_State) {
    return;  // while showing self-test errors, ALL STM32 state changes are ignored
}
```

### 4.2 Buzzer on Error Entry

Source: `HARDWARE.cpp`, `checkStateTransitionsForDrawer()`:

```cpp
if ((curr_cmd >= 0x2030 && curr_cmd <= 0x2049) && (prev_cmd != curr_cmd)) {
    my_Lastuipageid = curr_cmd;
    return true;  // triggers myui.trigger_buzz() in main.ino
}
```

**Confirmed:** Buzzer fires **once** when any code in `0x2030–0x2049` is received for the first time. It does not fire again if the same code continues to be reported.

### 4.3 Screen Routing — `GOTO_STM32_ALERT` Switch

Source: `main.ino`, `PROCESS_GOTOScreenCalls()`, case `GOTO_STM32_ALERT`:

The switch on `myhardware.my_uipageid` uses the following cases for error codes:

#### Case Group A — `0x2030` (MOTOR_ERR) — Explicit, no drawer filter

```cpp
case config::TX_CMD::MOTOR_ERR: {
    snprintf(buf, sizeof(buf), "%02X", (uint8_t)(myhardware.my_uipageid & 0xFF));
    arg1 = buf;  // "30"
    mydisplay.load_screen(30, myui, arg1, emptyS, emptyS);
} break;
```

→ Loads **screen 30** with `pVar1 = "30"`.

#### Case Group B — `0x2031` (MOTORJAM_ERR) — Explicit, no drawer filter

```cpp
case config::TX_CMD::MOTORJAM_ERR: {
    snprintf(buf, sizeof(buf), "%02X", (uint8_t)(myhardware.my_uipageid & 0xFF));
    arg1 = buf;  // "31"
    mydisplay.load_screen(32, myui, arg1, emptyS, emptyS);
} break;
```

→ Loads **screen 32** with `pVar1 = "31"`. Note: screen 32 uses hardcoded langMap text — `pVar1` is passed but **not displayed** by screen 32.

#### Case Group C — `0x2036`, `0x2038` — Explicit, **drawer 1 only**

```cpp
case config::TX_CMD::BB1_sensor_ERR:
case config::TX_CMD::Heater1_sensor_ERR:
    if (gSYSTEM_drawer == 1) {
        snprintf(buf, sizeof(buf), "%02X", (uint8_t)(myhardware.my_uipageid & 0xFF));
        arg1 = buf;  // "36" or "38"
        mydisplay.load_screen(30, myui, arg1, emptyS, emptyS);
    }
    break;
```

→ If `gSYSTEM_drawer == 1`: loads **screen 30** with `pVar1 = "36"` or `"38"`.  
→ If `gSYSTEM_drawer == 2`: **no screen is loaded** — confirmed intentional. `0x2036` and `0x2038` are drawer 1 sensor errors; drawer 2's ESP32 does not display them. The device still transitions to `UNDER_STM32_CONTROL`, but the displayed content remains unchanged.

#### Case Group D — `0x2037`, `0x2039` — Explicit, **drawer 2 only**

```cpp
case config::TX_CMD::BB2_sensor_ERR:
case config::TX_CMD::Heater2_sensor_ERR:
    if (gSYSTEM_drawer == 2) {
        snprintf(buf, sizeof(buf), "%02X", (uint8_t)(myhardware.my_uipageid & 0xFF));
        arg1 = buf;  // "37" or "39"
        mydisplay.load_screen(30, myui, arg1, emptyS, emptyS);
    }
    break;
```

→ If `gSYSTEM_drawer == 2`: loads **screen 30** with `pVar1 = "37"` or `"39"`.  
→ If `gSYSTEM_drawer == 1`: **no screen is loaded** — confirmed intentional. `0x2037` and `0x2039` are drawer 2 sensor errors; drawer 1's ESP32 does not display them. The device still transitions to `UNDER_STM32_CONTROL`, but the displayed content remains unchanged.

#### Case Group E — All remaining codes (`0x2032–0x2049`, excluding explicitly handled codes) — Default case

```cpp
default: {
    uint16_t page = myhardware.my_uipageid;
    if (page >= 0x2032 && page <= 0x2059) {
        snprintf(buf, sizeof(buf), "%02X", (uint8_t)(page & 0xFF));
        arg1 = buf;
        mydisplay.load_screen(30, myui, arg1, emptyS, emptyS);
    }
} break;
```

→ Loads **screen 30** with `pVar1` = low byte hex of the page ID.

Codes that reach this default case: `0x2032`, `0x2033`, `0x2034`, `0x2035`, `0x2040`, `0x2041`, `0x2042`, `0x2043`, `0x2044`, `0x2045`, `0x2046`, `0x2047`, `0x2048`, `0x2049`.

#### After the switch (all error codes):

```cpp
gOVERRIDEcommands = GOTO_NONE;
gDeviceStatus = UNDER_STM32_CONTROL;
needRedraw = 1;
```

This always executes regardless of whether a screen was loaded.

### 4.4 Error Code Displayed on Screen

For all cases where screen 30 is loaded, `pVar1` contains the **lower byte of the page ID formatted as a 2-digit uppercase hexadecimal string**:

```cpp
snprintf(buf, sizeof(buf), "%02X", (uint8_t)(myhardware.my_uipageid & 0xFF));
```

| Page ID  | `pVar1` displayed on screen |
|----------|-----------------------------|
| `0x2030` | `"30"`                      |
| `0x2032` | `"32"`                      |
| `0x2033` | `"33"`                      |
| `0x2034` | `"34"`                      |
| `0x2035` | `"35"`                      |
| `0x2036` | `"36"`                      |
| `0x2037` | `"37"`                      |
| `0x2038` | `"38"`                      |
| `0x2039` | `"39"`                      |
| `0x2040` | `"40"`                      |
| `0x2041` | `"41"`                      |
| `0x2042` | `"42"`                      |
| `0x2043` | `"43"`                      |
| `0x2044` | `"44"`                      |
| `0x2045` | `"45"`                      |
| `0x2046` | `"46"`                      |
| `0x2047` | `"47"`                      |
| `0x2048` | `"48"`                      |
| `0x2049` | `"49"`                      |

For `0x2031` (MOTORJAM_ERR), screen 32 is loaded. `pVar1 = "31"` is passed to `load_screen()` but is **not rendered** — screen 32 uses hardcoded language map strings.

---

## 5. Screen Definitions

### 5.1 Screen 30 — Generic Error (used for most codes)

Source: `SCREEN.cpp`, `load_screen()`, case 30. Log line: `"[DISPLAY] ERROR 2033 - 2059"`.

```cpp
case 30: {
    myui.setLedDefaults(OFF, OFF);
    setButtonConfigurationByID(myui, 9);

    Asset iconSprite = { "alert_icon", 160-33, LINE7Y+25, 67, 67, ...,
                         ASSET_ICON, "/assets/WARNING.raw", ... };
    SPRITE_create(iconSprite);

    Asset textSprite = { "error1", 0, LINE7Y+135, 320, FONT4H, ...,
                         ASSET_TEXT, pVar1, ..., CENTER, ..., FONT4, ... };
    SPRITE_create(textSprite);
} break;
```

| Element      | Sprite ID    | Type       | Content                                         |
|--------------|-------------|------------|-------------------------------------------------|
| Icon         | `alert_icon` | ASSET_ICON | `/assets/WARNING.raw` (centered, 67×67px)       |
| Error code   | `error1`     | ASSET_TEXT | `pVar1` — error code hex (e.g. `"33"`) — FONT4, centered |
| LED 1        | —            | —          | OFF                                             |
| LED 2        | —            | —          | OFF                                             |
| Buttons      | —            | —          | Profile 9 (see §6.1)                            |

**No pVar2 or pVar3 used.** Only the error code hex is shown below the WARNING icon.

### 5.2 Screen 32 — Motor Jam / Bucket Jam (used for `0x2031` only)

Source: `SCREEN.cpp`, `load_screen()`, case 32. Log line: `"[DISPLAY] BUCKET JAM"`.

```cpp
case 32: {
    myui.setLedDefaults(OFF, OFF);
    setButtonConfigurationByID(myui, 7);

    Asset iconSprite = { "alert_icon", 160-33, LINE7Y, 67, 67, ...,
                         ASSET_ICON, "/assets/WARNING.raw", ... };
    SPRITE_create(iconSprite);

    Asset textSprite = { "error1", 0, LINE8Y, 320, FONT4H, ...,
                         ASSET_TEXT, langMap["025"], ..., CENTER, ..., FONT4, ... };
    SPRITE_create(textSprite);

    Asset textSprite1 = { "error2", 0, LINE9Y, 320, FONT2H, ...,
                          ASSET_TEXT, langMap["006"], ..., CENTER, ..., FONT2, ... };
    SPRITE_create(textSprite1);
} break;
```

| Element        | Sprite ID    | Type       | Content                                         |
|----------------|-------------|------------|-------------------------------------------------|
| Icon           | `alert_icon` | ASSET_ICON | `/assets/WARNING.raw` (67×67px)                 |
| Primary text   | `error1`     | ASSET_TEXT | `langMap["025"]` = `"CAUTION HOT!"` — FONT4, centered |
| Secondary text | `error2`     | ASSET_TEXT | `langMap["006"]` = `"DEVICE JAMMED"` — FONT2, centered |
| LED 1          | —            | —          | OFF                                             |
| LED 2          | —            | —          | OFF                                             |
| Buttons        | —            | —          | Profile 7 (see §6.2)                            |

**Important:** `pVar1` (`"31"`) is passed by `main.ino` when calling `load_screen(32, ...)` but screen 32 does **not** use `pVar1`. All text is hardcoded from `langMap`.

---

## 6. Button Configurations

### 6.1 Button Config 9 — Generic Error Screens (screen 30)

Source: `SCREEN.cpp`, `setButtonConfigurationByID()`, case 9. Comment: `"ERROR screens (2033-2059)"`.

```cpp
case 9: {
    int actions[BUTTON_DETECTION_COUNT] = {
    //   click  short  long  vlong  ext
        0,     0,     0,   109,   0,    // BTN1
        0,   110,   111,     0,   0,    // BTN2
        0,     0,     0,     0,   0};   // BOTH
    configButtons(myui, actions);
} break;
```

| Button event      | Action ID | Behavior                                          |
|-------------------|-----------|---------------------------------------------------|
| BTN1 verylong     | 109       | Send `STM32_REBOOT` (0x03) to STM32               |
| BTN2 short        | 110       | Send `STM32_BTN2CLICK` (0x04) to STM32            |
| BTN2 long         | 111       | Send `STM32_TEST_WTR_PUMP` (0x05) to STM32        |
| All others        | 0         | Disabled — no action                              |

Source (`UI.cpp`, `executeAction()`):
```cpp
case 109: myhardware.sendButtonEvent(gSYSTEM_drawer, config::TX_CMD::STM32_REBOOT);       break;
case 110: myhardware.sendButtonEvent(gSYSTEM_drawer, config::TX_CMD::STM32_BTN2CLICK);    break;
case 111: myhardware.sendButtonEvent(gSYSTEM_drawer, config::TX_CMD::STM32_TEST_WTR_PUMP); break;
```

**Confirmed:** On generic error screens, the only user-initiated action is to send `STM32_REBOOT` (very long press of BTN1). The ESP32 does not autonomously navigate away from the error screen — it waits for the STM32 to broadcast a new page ID.

### 6.2 Button Config 7 — Motor Jam Screen (screen 32)

Source: `SCREEN.cpp`, `setButtonConfigurationByID()`, case 7. Comment: `"BUCKET JAM"`.

```cpp
case 7: {
    int actions[BUTTON_DETECTION_COUNT] = {
    //   click  short  long  vlong  ext
        0,   108,     0,   109,   0,    // BTN1
        0,   110,   111,     0,   0,    // BTN2
        0,     0,     0,     0,   0};   // BOTH
    configButtons(myui, actions);
} break;
```

| Button event      | Action ID | Behavior                                          |
|-------------------|-----------|---------------------------------------------------|
| BTN1 short        | 108       | Send `STM32_BTN1CLICK` (0x01) to STM32            |
| BTN1 verylong     | 109       | Send `STM32_REBOOT` (0x03) to STM32               |
| BTN2 short        | 110       | Send `STM32_BTN2CLICK` (0x04) to STM32            |
| BTN2 long         | 111       | Send `STM32_TEST_WTR_PUMP` (0x05) to STM32        |
| All others        | 0         | Disabled — no action                              |

The additional BTN1 short (action 108, `STM32_BTN1CLICK` 0x01) is available on the MOTORJAM screen. The product-level meaning of this button press during a jam (e.g., "attempt to clear jam") is a **STM32-side decision — Not found in current ESP32 implementation**.

---

## 7. Runtime Updates in `UNDER_STM32_CONTROL`

After a screen is loaded for any error state, `gDeviceStatus = UNDER_STM32_CONTROL`. The `UNDER_STM32_CONTROL` block in `main.ino` is executed every loop iteration.

### 7.1 `0x2031` (MOTORJAM_ERR) — Animated

Source: `main.ino`, case `UNDER_STM32_CONTROL`:

```cpp
} else if (myhardware.my_uipageid == config::TX_CMD::MOTORJAM_ERR) {
    mydisplay.SPRITE_toggleSprites("alert_icon", "error2",
        "/assets/POWER.raw", "/assets/WARNING.raw", "006", "023", 2);
}
```

`SPRITE_toggleSprites` signature:
```cpp
void SCREEN::SPRITE_toggleSprites(
    const String& imgSpriteId, const String& textSpriteId,
    const String& imgNameA, const String& imgNameB,
    const String& langMapA, const String& langMapB,
    uint32_t periodSeconds)
```

The `langMapA` and `langMapB` parameters are used as **language map keys**:

```cpp
String key = phaseA ? langMapA : langMapB;
SPRITE_updateText(textSpriteId, langMap[key]);
```

Result for `0x2031` at 2-second period:

| Phase   | `alert_icon`          | `error2` text                      |
|---------|-----------------------|------------------------------------|
| Phase A | `/assets/POWER.raw`   | `langMap["006"]` = `"DEVICE JAMMED"` |
| Phase B | `/assets/WARNING.raw` | `langMap["023"]` = `"BLOCKAGE"`    |

Both `alert_icon` and `error2` are sprites created by screen 32 — both toggles are **active** (not a no-op).

### 7.2 All Other Error Codes (`0x2030`, `0x2032`–`0x2049`) — Static

No specific runtime update block exists in `UNDER_STM32_CONTROL` for these codes. Screen 30 is displayed statically (WARNING icon + error code hex text). There is no blinking, toggling, or timed animation.

### 7.3 `UNDER_STM32_CONTROL` Shared Operations (all error states)

Regardless of which error is active, the following run every loop iteration:

```cpp
TELEMETRY_scheduler(1);       // AWS telemetry on schedule
handleTimeSyncNonBlocking();  // periodic NTP sync
TRIGGERS_process();           // AWS remote command processing

if (delayedExecutionTimer) {  // every 10 seconds
    wifi.tick();
    CONNECTION_test(1);
}
```

---

## 8. Code-by-Code Mapping Table

| Code     | Name               | Explicit case? | Drawer filter | Screen | pVar1 shown | LED     | Runtime animation        | Recovery                              |
|----------|--------------------|---------------|---------------|--------|-------------|---------|--------------------------|---------------------------------------|
| `0x2030` | MOTOR_ERR          | Yes           | None          | 30     | `"30"`      | OFF/OFF | None (static)            | STM32 page change or BTN1 very long reboot |
| `0x2031` | MOTORJAM_ERR       | Yes           | None          | 32     | Not shown   | OFF/OFF | Icon + text alternate 2s | STM32 page change or BTN1 short (0x01) or BTN1 very long reboot |
| `0x2032` | HEATER_ERR         | No (default)  | None          | 30     | `"32"`      | OFF/OFF | None (static)            | STM32 page change or BTN1 very long reboot |
| `0x2033` | OVERHEAT_ERR       | No (default)  | None          | 30     | `"33"`      | OFF/OFF | None (static)            | STM32 page change or BTN1 very long reboot |
| `0x2034` | CMP_ERR            | No (default)  | None          | 30     | `"34"`      | OFF/OFF | None (static)            | STM32 page change or BTN1 very long reboot |
| `0x2035` | HEATPUMP_ERR       | No (default)  | None          | 30     | `"35"`      | OFF/OFF | None (static)            | STM32 page change or BTN1 very long reboot |
| `0x2036` | BB1_sensor_ERR     | Yes           | Drawer 1 only | 30     | `"36"`      | OFF/OFF | None (static)            | STM32 page change or BTN1 very long reboot |
| `0x2037` | BB2_sensor_ERR     | Yes           | Drawer 2 only | 30     | `"37"`      | OFF/OFF | None (static)            | STM32 page change or BTN1 very long reboot |
| `0x2038` | Heater1_sensor_ERR | Yes           | Drawer 1 only | 30     | `"38"`      | OFF/OFF | None (static)            | STM32 page change or BTN1 very long reboot |
| `0x2039` | Heater2_sensor_ERR | Yes           | Drawer 2 only | 30     | `"39"`      | OFF/OFF | None (static)            | STM32 page change or BTN1 very long reboot |
| `0x2040` | CMP_sensor_ERR     | No (default)  | None          | 30     | `"40"`      | OFF/OFF | None (static)            | STM32 page change or BTN1 very long reboot |
| `0x2041` | EVP_sensor_ERR     | No (default)  | None          | 30     | `"41"`      | OFF/OFF | None (static)            | STM32 page change or BTN1 very long reboot |
| `0x2042` | C2Fan_sensor_1_ERR | No (default)  | None          | 30     | `"42"`      | OFF/OFF | None (static)            | STM32 page change or BTN1 very long reboot |
| `0x2043` | Damper_ERR         | No (default)  | None          | 30     | `"43"`      | OFF/OFF | None (static)            | STM32 page change or BTN1 very long reboot |
| `0x2044` | PAFan_ERR          | No (default)  | None          | 30     | `"44"`      | OFF/OFF | None (static)            | STM32 page change or BTN1 very long reboot |
| `0x2045` | Water_Pump_ERR     | No (default)  | None          | 30     | `"45"`      | OFF/OFF | None (static)            | STM32 page change or BTN1 very long reboot |
| `0x2046` | Filter_Fan_ERR     | No (default)  | None          | 30     | `"46"`      | OFF/OFF | None (static)            | STM32 page change or BTN1 very long reboot |
| `0x2047` | C2Fan_sensor_2_ERR | No (default)  | None          | 30     | `"47"`      | OFF/OFF | None (static)            | STM32 page change or BTN1 very long reboot |
| `0x2048` | C2Fan_sensor_3_ERR | No (default)  | None          | 30     | `"48"`      | OFF/OFF | None (static)            | STM32 page change or BTN1 very long reboot |
| `0x2049` | C2Fan_sensor_4_ERR | No (default)  | None          | 30     | `"49"`      | OFF/OFF | None (static)            | STM32 page change or BTN1 very long reboot |

---

## 9. Screen Mapping Summary

| Screen | Used for                                               | Icon          | Text 1 (FONT4)           | Text 2 (FONT2)          |
|--------|-------------------------------------------------------|---------------|--------------------------|-------------------------|
| 30     | `0x2030`, `0x2032`–`0x2049` (all except `0x2031`)    | WARNING.raw   | Error code hex (e.g. `"33"`) | _(none)_            |
| 32     | `0x2031` (MOTORJAM_ERR) only                          | WARNING.raw   | `"CAUTION HOT!"`         | `"DEVICE JAMMED"` / `"BLOCKAGE"` (animated) |

---

## 10. State-Machine Transitions

### 10.1 On Entry (any error code 0x2030–0x2049 received)

```
STM32 broadcasts error page ID (0x2030–0x2049)
    → processSerialFramesNonBlocking() parses my_uipageid
    → checkDrawerUIPageIds():
        [guard check — if critical operation in progress: return, error suppressed]
        → stateChanged = true (new page ID differs from last)
        → checkStateTransitionsForDrawer() detects 0x2030–0x2049 range → returns true
        → myui.trigger_buzz()
        → gOVERRIDEcommands = GOTO_STM32_ALERT

    → PROCESS_GOTOScreenCalls() handles GOTO_STM32_ALERT:
        → switch(my_uipageid):
            0x2030 → load_screen(30, arg="30")
            0x2031 → load_screen(32, arg="31")
            0x2036/0x2038 + drawer==1 → load_screen(30, arg="36"/"38")
            0x2037/0x2039 + drawer==2 → load_screen(30, arg="37"/"39")
            0x2036/0x2038 + drawer==2 → [no screen loaded]
            0x2037/0x2039 + drawer==1 → [no screen loaded]
            default (0x2032–0x2049 excl. above) → load_screen(30, arg=hex)

        → gOVERRIDEcommands = GOTO_NONE
        → gDeviceStatus = UNDER_STM32_CONTROL
```

### 10.2 While Error is Active (every loop iteration)

```
UNDER_STM32_CONTROL:
    → TELEMETRY_scheduler(1)     — AWS telemetry
    → handleTimeSyncNonBlocking() — NTP sync
    → TRIGGERS_process()         — remote command processing
    → runtime UI update:
        if my_uipageid == MOTORJAM_ERR:
            SPRITE_toggleSprites (icon + text, 2s period)
        else (all other error codes):
            [no update — screen is static]
    → on 10s timer:
        wifi.tick()
        CONNECTION_test(1)
```

### 10.3 State Diagram

```
STM32 sends 0x2030–0x2049
            │
            ▼
  checkDrawerUIPageIds()
     [guard check]
            │
  stateChanged = true
     buzz once
            │
            ▼
  gOVERRIDEcommands = GOTO_STM32_ALERT
            │
  PROCESS_GOTOScreenCalls()
            │
  ┌─────────┴──────────────────────────────────┐
  │                                             │
0x2031                               0x2030, 0x2032–0x2049
  │                                             │
load_screen(32)                       load_screen(30)
"CAUTION HOT!"                        error_code_hex text
"DEVICE JAMMED"                       WARNING icon
  │                                             │
  └──────────────┬──────────────────────────────┘
                 │
    gDeviceStatus = UNDER_STM32_CONTROL
                 │
   (loop each tick — telemetry, wifi, display)
                 │
    ┌────────────┴───────────────────────────┐
    │                                        │
 STM32 sends                          User: BTN1 very long
 new page ID                          → STM32_REBOOT (0x03)
    │                                 [STM32 decides next state]
    ▼
 stateChanged = true
 gOVERRIDEcommands = GOTO_STM32_ALERT
 [process new state]
    │
 if new state == Standby (0x2010):
    STM_isIdle() → true
    directOnlineForSkipProvisioning()
    → GOTO_UI_IDLE → load_screen(4) "READY"
```

---

## 11. Recovery / Clear-Condition Behavior

### 11.1 Confirmed Recovery Mechanism

Error screens in the Arduino implementation are **fully persistent**. They do not auto-dismiss. The device remains in `UNDER_STM32_CONTROL` displaying the error screen until one of these events occurs:

**Event 1 — STM32 broadcasts a new page ID:**
- `checkDrawerUIPageIds()` detects `stateChanged = true`
- `gOVERRIDEcommands = GOTO_STM32_ALERT` is set
- The new page ID is processed via `PROCESS_GOTOScreenCalls()`
- If the new state is `Standby` (`0x2010`): `STM_isIdle()` → `true` → `directOnlineForSkipProvisioning()` → `GOTO_UI_IDLE` → `load_screen(4)` ("READY" screen)
- If the new state is another running state (`0x2011`–`0x2014`): the running screen is displayed

**Event 2 — User presses BTN1 very long (action 109):**
- `myhardware.sendButtonEvent(gSYSTEM_drawer, config::TX_CMD::STM32_REBOOT)` — sends `0x03` to STM32
- What happens next is a **STM32-side decision — Not found in current ESP32 implementation**
- The ESP32 continues to wait for the next page ID broadcast from STM32

**Event 3 — User presses BTN1 short on MOTORJAM screen (action 108, screen 32 only):**
- `myhardware.sendButtonEvent(gSYSTEM_drawer, config::TX_CMD::STM32_BTN1CLICK)` — sends `0x01` to STM32
- What happens next is a **STM32-side decision — Not found in current ESP32 implementation**
- Likely intended as "attempt to clear jam" — but not confirmed in ESP32 code

### 11.2 No Auto-Dismiss

Confirmed: There is **no `ALERT_DISPLAY` timeout** used for any error state in `0x2030–0x2049`. The error screens are loaded directly into `UNDER_STM32_CONTROL`, not via the `ALERT_DISPLAY` timed state. The `ALERT_DISPLAY` mechanism is used elsewhere (e.g., self-test OK, provisioning complete) but **not** for hardware error codes.

### 11.3 Error Does Not Block Telemetry

During error display, `TELEMETRY_scheduler(1)` continues to run. WiFi connectivity and AWS telemetry are maintained during error states.

---

## 12. AWS Error Logging for STM32 Error Codes

### 12.1 Log Table

Source: `config.cpp`, `config::LOGGER::LOG_TABLE[]`:

The log table contains entries `0x01`–`0x37`. It does **not** contain entries for any STM32 error codes (`0x2030`–`0x2049`). If a STM32 error code is passed to `Logger::log()`, it would match the fallback `unknown` entry `{0xFF, "[UNKNOWN MESSAGE]"}`.

### 12.2 Error Logging Call Site

No call to `Logger::log(LOGGER_ERROR, ...)` was found in `main.ino` or `HARDWARE.cpp` for any code in `0x2030–0x2049`. STM32 hardware errors are **not written to `error.log`** in the current implementation.

### 12.3 `error_seen[]` Array

`HARDWARE.h` declares:
```cpp
bool error_seen[(ERROR_MAX - ERROR_BASE) + 1] = { false };
```
This is never read or written in any `.cpp` file in the current implementation. It is **dead code**.

**Status:** AWS error telemetry for STM32 error codes is **Not found in current implementation**.

---

## 13. Self-Test Relationship

The self-test byte mapping (from `HARDWARE.cpp` frame parser comments) describes which bits in `selftest_b0`, `selftest_b1`, `selftest_b2` map to which error codes. This mapping is used by `formatAndShowSelfTestErrors()` → `load_screen(29)` to display accumulated test results — it is a **separate flow** from the live error state handling documented here.

The self-test lookup table in `SCREEN.cpp` is:
```cpp
static const char* const errorCodeLookup[] = {
    "45","32T","32B","30T","30B","43T","43B","38",
    "36","39","37","40","42","48","47","49","41","46","44T","44B","35"
};
```

These codes correspond to the same `0x2030–0x2049` range but displayed as self-test results, not as live state errors. The two flows (live error vs. self-test) are independent.

---

## 14. Differences Between Arduino and Current ESP-IDF Implementation

This section documents what the Arduino code does and flags whether an equivalent implementation is expected in the ESP-IDF port.

| Item | Arduino behavior | ESP-IDF status |
|------|-----------------|----------------|
| Error code range `0x2030–0x2049` defined | Yes — `config.h` and `HARDWARE.h` | **Needs verification** — are these defined in ESP-IDF? |
| Buzzer on error entry | Yes — fires once on page change | **Needs implementation** — equivalent buzz trigger required |
| Screen 30 (generic error) | Yes — WARNING icon + error hex text | **Needs implementation** — screen layout to be created |
| Screen 32 (MOTORJAM) | Yes — WARNING icon + CAUTION HOT + DEVICE JAMMED | **Needs implementation** — screen layout with animation |
| MOTORJAM runtime animation | Yes — icon + text alternates at 2s period | **Needs implementation** — render-loop toggle logic |
| Generic error static display | Yes — no animation | **Confirmed simple** — load once and hold |
| BTN1 verylong → STM32_REBOOT | Yes — sends 0x03 to STM32 | **Needs implementation** |
| BTN1 short → STM32_BTN1CLICK (MOTORJAM only) | Yes — sends 0x01 to STM32 | **Needs implementation** |
| Drawer-filtered display for `0x2036`–`0x2039` | Yes — only active drawer's sensor errors shown | **Needs implementation** — drawer filter check required |
| AWS error logging for STM32 errors | **Not found in current implementation** | No action needed (parity: also not implemented) |
| `error_seen[]` array tracking | Declared but never used | No action needed (parity: dead code) |
| Guard against interrupting OTA/provisioning | Yes — comprehensive guard list | **Needs implementation** — equivalent guard required |
| Auto-dismiss timeout | Not used for errors | **Confirmed** — no auto-dismiss for error states |

---

## 15. Error / Unclear Points

### 15.1 Drawer-Filtered Errors — No Screen on Wrong Drawer — **Confirmed Intentional**

`0x2036` (BB1_sensor_ERR) and `0x2038` (Heater1_sensor_ERR) are sensor errors that belong exclusively to **drawer 1**.  
`0x2037` (BB2_sensor_ERR) and `0x2039` (Heater2_sensor_ERR) are sensor errors that belong exclusively to **drawer 2**.

**This is confirmed intentional design:** each drawer's ESP32 only shows UI for its own sensor errors. If a drawer 1 sensor error code (`0x2036`, `0x2038`) arrives while `gSYSTEM_drawer == 2`, the case block executes with no `load_screen()` call — the active drawer's display intentionally does not respond to the other drawer's error. The device still transitions to `UNDER_STM32_CONTROL`, but the display retains its current content.

This means:

| Code     | Belongs to | `gSYSTEM_drawer == 1` result | `gSYSTEM_drawer == 2` result |
|----------|-----------|------------------------------|------------------------------|
| `0x2036` | Drawer 1  | Screen 30 shown (`"36"`)     | No screen loaded — intentional |
| `0x2038` | Drawer 1  | Screen 30 shown (`"38"`)     | No screen loaded — intentional |
| `0x2037` | Drawer 2  | No screen loaded — intentional | Screen 30 shown (`"37"`) |
| `0x2039` | Drawer 2  | No screen loaded — intentional | Screen 30 shown (`"39"`) |

For the ESP-IDF port: implement the same drawer ownership check. Do not show a sensor error screen if the received error code belongs to the other drawer.

### 15.2 MOTORJAM Screen Text — `pVar1` Not Used

`main.ino` formats the error code (`"31"`) into `arg1` and passes it as `pVar1` to `load_screen(32, ...)`. However, screen 32 uses hardcoded `langMap["025"]` and `langMap["006"]` — it never references `pVar1`. The formatted error code `"31"` is passed but discarded.

Whether this is intentional (the screen intentionally shows CAUTION HOT + DEVICE JAMMED regardless of which specific jam code was received) is **Needs clarification**.

### 15.3 Screen 30 Label Mismatch

The `Serial.println(F("[DISPLAY] ERROR 2033 - 2059"))` log line in screen 30 says `"2033 - 2059"`, but screen 30 is also used for `0x2030` (MOTOR_ERR) which has an explicit case. The label appears to be a documentation artifact from an earlier implementation where `0x2030` and `0x2031` may have also fallen to the default case.

### 15.4 Recovery After Reboot Command

When the user holds BTN1 very long (action 109), `sendButtonEvent(STM32_REBOOT, 0x03)` is sent to STM32. What the STM32 does with this (reset, retry, clear error, send Standby) is **Not found in current implementation**. The ESP32 simply waits for the next page ID from STM32.

### 15.5 `0x2031` Recovery via BTN1 Short

On screen 32 (MOTORJAM), BTN1 short sends `STM32_BTN1CLICK` (0x01). The product-level meaning — whether this is "attempt to clear jam", "confirm user has removed object", or something else — is a **STM32-side decision — Not found in current ESP32 implementation**.

### 15.6 No "Error Cleared" Intermediate Screen

When an error clears and STM32 sends a new page ID (e.g., Standby), the ESP32 immediately transitions to the new state with no intermediate "error cleared" or "error resolved" screen. The transition is direct.

### 15.7 Behavior When Error Persists Indefinitely

If the STM32 continues to send the same error code (e.g., repeated `0x2033` frames), `stateChanged` remains false and `gOVERRIDEcommands` remains `GOTO_NONE`. The device stays in `UNDER_STM32_CONTROL` indefinitely with the static error screen displayed. There is no timeout or escalation mechanism in the current implementation.

### 15.8 AWS Remote Reboot During Error State

While `UNDER_STM32_CONTROL`, `TRIGGERS_process()` runs every loop. This means AWS remote commands (e.g., `STM_REBOOT`) continue to be processed during error states. However, whether this is the intended behavior for all error scenarios is **Needs clarification**.

---

## 16. Implementation Guidance for ESP-IDF

This section provides guidance for implementing equivalent behavior in ESP-IDF. **No implementation code is provided.** This is mapping guidance only.

### 16.1 Error Code Constants

Define constants for all 20 error codes (equivalent to `config::TX_CMD` in `config.h`):

```
MOTOR_ERR           = 0x2030
MOTORJAM_ERR        = 0x2031
HEATER_ERR          = 0x2032
OVERHEAT_ERR        = 0x2033
CMP_ERR             = 0x2034
HEATPUMP_ERR        = 0x2035
BB1_SENSOR_ERR      = 0x2036
BB2_SENSOR_ERR      = 0x2037
HEATER1_SENSOR_ERR  = 0x2038
HEATER2_SENSOR_ERR  = 0x2039
CMP_SENSOR_ERR      = 0x2040
EVP_SENSOR_ERR      = 0x2041
C2FAN_SENSOR_1_ERR  = 0x2042
DAMPER_ERR          = 0x2043
PAFAN_ERR           = 0x2044
WATER_PUMP_ERR      = 0x2045
FILTER_FAN_ERR      = 0x2046
C2FAN_SENSOR_2_ERR  = 0x2047
C2FAN_SENSOR_3_ERR  = 0x2048
C2FAN_SENSOR_4_ERR  = 0x2049
```

### 16.2 State Change Detection and Guard

Equivalent to `checkDrawerUIPageIds()` in `main.ino`:

- On change in `my_uipageid` to any value in `0x2030–0x2049`, trigger the STM32 alert routing.
- Apply the same guard list: do not interrupt OTA, asset download, provisioning, firmware transfer, WiFi test, decision timeout, unprovisioned state, or BLE broadcasting.
- Buzzer must fire **once** on first entry (page change only — not every frame).

### 16.3 Screen Loading Logic

When `my_uipageid` is in `0x2030–0x2049`, use this routing:

```
error_hex = sprintf("%02X", my_uipageid & 0xFF)

if my_uipageid == 0x2031:
    load screen equivalent to screen 32 (MOTORJAM layout)
    [pVar1 passed but not used; all text is hardcoded]

elif my_uipageid == 0x2036 or 0x2038:
    if active_drawer == 1:
        load screen equivalent to screen 30, error_code = error_hex
    else:
        [do not load new screen — retain current display]

elif my_uipageid == 0x2037 or 0x2039:
    if active_drawer == 2:
        load screen equivalent to screen 30, error_code = error_hex
    else:
        [do not load new screen — retain current display]

else (0x2030, 0x2032–0x2049 remaining):
    load screen equivalent to screen 30, error_code = error_hex

After all cases:
    set device state to UNDER_STM32_CONTROL
```

### 16.4 Screen 30 Equivalent (Generic Error)

Build a view containing:
- WARNING.raw icon, centered, upper area
- Error code hex text, large font, centered, below the icon
- LEDs: both OFF
- Buttons:
  - BTN1 verylong → send `STM32_REBOOT` (0x03) to STM32
  - BTN2 short → send `STM32_BTN2CLICK` (0x04) to STM32
  - BTN2 long → send `STM32_TEST_WTR_PUMP` (0x05) to STM32
  - All other buttons: disabled

### 16.5 Screen 32 Equivalent (Motor Jam)

Build a view containing:
- WARNING.raw icon, centered, upper area
- Large text row: `"CAUTION HOT!"` (or equivalent translated string for key `"025"`)
- Medium text row: `"DEVICE JAMMED"` (key `"006"`)
- LEDs: both OFF
- Buttons:
  - BTN1 short → send `STM32_BTN1CLICK` (0x01) to STM32
  - BTN1 verylong → send `STM32_REBOOT` (0x03) to STM32
  - BTN2 short → send `STM32_BTN2CLICK` (0x04) to STM32
  - BTN2 long → send `STM32_TEST_WTR_PUMP` (0x05) to STM32
  - All other buttons: disabled

### 16.6 MOTORJAM Runtime Animation (render loop)

When `my_uipageid == 0x2031`, on every render cycle:

- Calculate `phase = (millis() / 2000) % 2`
- If phase == 0 (Phase A):
  - Icon: display `POWER.raw`
  - Medium text row: display `langMap["006"]` = `"DEVICE JAMMED"`
- If phase == 1 (Phase B):
  - Icon: display `WARNING.raw`
  - Medium text row: display `langMap["023"]` = `"BLOCKAGE"`

In LVGL: update the image source and label text in-place on each render pass. Do not recreate widgets.

### 16.7 Recovery

When `my_uipageid` changes away from any error code:

- Stop any active animations.
- Process the new page ID using the normal state-routing logic.
- If the new page ID is `Standby` (`0x2010`):
  - Return to idle/ready screen.
- If the new page ID is a running state (`0x2011`–`0x2014`):
  - Show the appropriate running screen.

### 16.8 Buzzer

Fire a single buzzer event the first time an error code is received (on `my_uipageid` change). Do not fire again if the same error code continues to arrive in subsequent frames.

### 16.9 Telemetry During Error States

Continue all background operations during error display:
- Scheduled AWS telemetry publishing
- WiFi connectivity management
- Remote command (trigger) processing

---

## 17. Verification Guidance

### 17.1 Expected Log Sequence (from Arduino implementation)

When an error is received, the following Serial output appears:

```
GOTO_STM32_ALERT              ← state machine entering error routing
[DISPLAY] ERROR 2033 - 2059  ← screen 30 loaded (for most errors)
[DISPLAY] BUCKET JAM          ← screen 32 loaded (for 0x2031 only)
```

For the ESP-IDF implementation, equivalent log tags should be added.

### 17.2 Manual Test Steps

**To trigger a generic error screen (e.g., `0x2033`):**
1. Inject UART frame with `my_uipageid` = `0x2033` at frame bytes 73–74.
2. Expected: device transitions to error screen showing WARNING icon and text `"33"`.
3. Expected: buzzer fires once.
4. Expected: device enters equivalent of `UNDER_STM32_CONTROL`.
5. Expected: screen remains static (no animation).
6. BTN1 verylong: `STM32_REBOOT` (0x03) is sent via UART.
7. Inject new frame with `my_uipageid` = `0x2010` (Standby): device should return to idle/ready screen.

**To trigger MOTORJAM (`0x2031`):**
1. Inject UART frame with `my_uipageid` = `0x2031`.
2. Expected: device shows screen with WARNING icon, `"CAUTION HOT!"`, `"DEVICE JAMMED"`.
3. Expected: buzzer fires once.
4. Expected: icon alternates between POWER.raw and WARNING.raw every 2 seconds.
5. Expected: medium text alternates between `"DEVICE JAMMED"` and `"BLOCKAGE"` every 2 seconds.
6. BTN1 short: `STM32_BTN1CLICK` (0x01) is sent.
7. BTN1 verylong: `STM32_REBOOT` (0x03) is sent.

**To test drawer-filtered errors (`0x2036`):**
1. Set `active_drawer = 1`. Inject `my_uipageid = 0x2036`.
2. Expected: screen 30 shown with text `"36"`.
3. Set `active_drawer = 2`. Inject `my_uipageid = 0x2036`.
4. Expected: no new screen loaded; display unchanged; device enters UNDER_STM32_CONTROL.

### 17.3 Test Injection (Without Full STM32)

The Arduino implementation uses `myhardware.my_uipageid` as the sole decision variable. In the ESP-IDF port, the equivalent variable can be set directly in a test mode to simulate any error code without requiring actual UART frames from STM32.

```
// Pseudo-test hook:
set_test_uipageid(0x2033);  // simulate OVERHEAT_ERR
```

This allows full error screen verification independently of hardware.

---

## 18. Not Found / Needs Clarification

| Item | Status |
|------|--------|
| What STM32 does with `STM32_REBOOT` (0x03) during an error | **Not found in current implementation** |
| What STM32 does with `STM32_BTN1CLICK` (0x01) during MOTORJAM | **Not found in current implementation** |
| `0x2036`/`0x2038` on drawer 2 (or `0x2037`/`0x2039` on drawer 1) retaining current display | **Confirmed intentional — each drawer only responds to its own sensor errors; cross-drawer codes are silently ignored at display level** |
| Why `pVar1` (error hex) is passed to `load_screen(32, ...)` but not rendered by screen 32 | **Needs clarification** |
| Whether STM32 can clear an error and resume a running cycle, or always returns to Standby | **Not found in current implementation** |
| What the STM32 sends after an error condition is physically resolved | **Not found in current implementation** |
| Whether any escalation path exists if an error persists for an extended period | **Not found in current implementation** |
| Whether `error_seen[]` array was ever intended to be used (it is currently dead code) | **Needs clarification** |
| Whether AWS should receive a notification when a STM32 error code is entered | **Not found in current implementation** |
| Whether the `"CAUTION HOT!"` text on screen 32 (MOTORJAM) is intentional or a copy-paste artifact from drawer-open hot-path screens | **Needs clarification** |

