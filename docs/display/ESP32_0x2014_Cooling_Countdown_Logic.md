# ESP32 Handling of STM32 State `0x2014` (Cooling Countdown)

## Goal of this document
This document explains the **actual implemented logic** in this project for showing cooling countdown on the UI when ESP32 receives STM32 page/state `0x2014`.

It is intended as a transfer document for implementing the same behavior in another ESP-IDF project.

---

## 1) What `0x2014` means in this codebase

`0x2014` is the STM32 display page code mapped as **Progress3 / Cooling**.

### Source definitions
- `config.h`:
  - `config::TX_CMD::Progress3_State = 0x2014` (around line 410)
- `HARDWARE.h`:
  - `DisplayCommand::TX_CMD_Progress3_State = 0x2014` (around line 67)

---

## 2) End-to-end flow (from STM frame to on-screen countdown)

## A. STM frame is parsed and cooling seconds are extracted

### Parsing function
- `HARDWARE::processSerialFramesNonBlocking()` in `HARDWARE.cpp`

### Relevant decoded fields
From validated frame bytes:
- UI page IDs:
  - `drawer1_uipageid = frameBuf[73..74]`
  - `drawer2_uipageid = frameBuf[75..76]`
- Cooling countdown (seconds):
  - `drawer1_CoolingCYCLE = frameBuf[90..91]` (LE)
  - `drawer2_CoolingCYCLE = frameBuf[92..93]` (LE)

Code (exact logic):
```cpp
drawer1_uipageid   = (uint16_t)frameBuf[73] | ((uint16_t)frameBuf[74] << 8);
drawer2_uipageid   = (uint16_t)frameBuf[75] | ((uint16_t)frameBuf[76] << 8);

drawer1_CoolingCYCLE   = (uint16_t)frameBuf[90] | ((uint16_t)frameBuf[91] << 8);
drawer2_CoolingCYCLE   = (uint16_t)frameBuf[92] | ((uint16_t)frameBuf[93] << 8);
```

Then current drawer aliases are selected:
```cpp
if (gSYSTEM_drawer == 2){
  my_TotalTimeForCycle = drawer2_TotalTimeForCycle;
  my_CoolingCYCLE = drawer2_CoolingCYCLE;
  my_uipageid = drawer2_uipageid;
}else{
  my_TotalTimeForCycle = drawer1_TotalTimeForCycle;
  my_CoolingCYCLE = drawer1_CoolingCYCLE;
  my_uipageid = drawer1_uipageid;
}
```

---

## B. Main loop drives state-change routing

In `main.ino::loop()`:
- `myhardware.loop()` calls `processSerialFramesNonBlocking()` continuously.
- `checkDrawerUIPageIds()` compares previous/current page and triggers screen routing.

Trigger to STM alert pipeline:
```cpp
if ((!myhardware.STM_isIdle() && gDeviceStatus != UNDER_STM32_CONTROL) || stateChanged) {
    gOVERRIDEcommands = GOTO_STM32_ALERT;
}
```

---

## C. When page is `0x2014`, Cooling screen is loaded

In `main.ino`, handler `case GOTO_STM32_ALERT`:
```cpp
case config::TX_CMD::Progress3_State:
    arg1 = mydisplay.secondsToHHMMSS(myhardware.my_CoolingCYCLE, false);
    mydisplay.load_screen(25, myui, arg1, emptyS, emptyS);
    break;
```

Then common tail of this handler sets runtime mode:
```cpp
gDeviceStatus = UNDER_STM32_CONTROL;
```

---

## D. Under STM32 control, countdown text is refreshed continuously

In `main.ino`, `case UNDER_STM32_CONTROL`:
```cpp
} else if (myhardware.my_uipageid == config::TX_CMD::Progress3_State) {
  mydisplay.SPRITE_updateText("counter", mydisplay.secondsToHHMMSS(myhardware.my_CoolingCYCLE, false));
  mydisplay.setTimerRingBlinking(4, config::COLORS::GREEN, config::COLORS::GREEN, config::COLORS::BLUE1, config::COLORS::GREEN);
}
```

So once the cooling screen exists, only sprite text `counter` is updated each loop based on latest `my_CoolingCYCLE`.

---

## E. Cooling screen composition (`screenId=25`)

In `SCREEN.cpp`, `load_screen(25, ...)` creates:
- timer ring (`timer_ring`)
- cooling icon (`/assets/cooling.raw`)
- status text from language key `"004"` (default value: `"Cooling"`)
- counter text sprite ID: `"counter"` initialized from `pVar1`

Key snippet:
```cpp
Asset textSprite2 = { "counter", ..., ASSET_TEXT, pVar1, ... };
SPRITE_create(textSprite2);
```

Language default source:
- `config.cpp`: `"004": "Cooling"`

---

## F. Countdown formatting function

`SCREEN::secondsToHHMMSS(unsigned long secs, bool isMinutes)` in `SCREEN.cpp`:
- For cooling path it is called with `isMinutes=false`
- Formatting behavior:
  - if `hours == 0` -> `MM:SS`
  - else -> `H:MM:SS` (or `HH:MM:SS` depending hours digits)

Relevant code:
```cpp
if (hours == 0) {
    snprintf(buf, sizeof(buf), "%02lu:%02lu", minutes, seconds);
} else {
    snprintf(buf, sizeof(buf), "%lu:%02lu:%02lu", hours, minutes, seconds);
}
```

---

## 3) Important behavior characteristics (for re-implementation)

- Countdown source is **STM frame data** (`frameBuf[90..93]`), not ESP local timer math.
- ESP32 does **not** decrement cooling time locally in this path.
- UI updates depend on receiving valid frames regularly.
- Drawer selection matters (`gSYSTEM_drawer` decides whether drawer1 or drawer2 cooling value is shown).
- UI transition into cooling happens when page ID becomes `0x2014`.
- Ongoing text refresh happens only while page remains `0x2014` in `UNDER_STM32_CONTROL`.

---

## 4) Minimal implementation contract for another ESP-IDF project

Implement these elements:

1. Parse incoming STM status frame, extract:
   - `page_id` (equivalent to `drawerX_uipageid`)
   - `cooling_seconds` (equivalent to `drawerX_CoolingCYCLE`)
2. If `page_id == 0x2014`:
   - Enter/ensure cooling UI screen is active.
   - Initialize counter text from current `cooling_seconds`.
3. In periodic UI update loop:
   - If current page still `0x2014`, refresh counter text using `MM:SS` / `H:MM:SS` formatting from latest parsed value.
4. If page changes away from `0x2014`, exit cooling screen according to your state mapping.

---

## 5) Reference pseudocode (ESP-IDF friendly)

```c
// called when a validated STM frame arrives
void on_stm_frame(const Frame* f) {
    uint16_t page = select_drawer_page(f, active_drawer);
    uint16_t cooling_sec = select_drawer_cooling_seconds(f, active_drawer);

    model.page_id = page;
    model.cooling_sec = cooling_sec;

    if (model.page_id == 0x2014) {
        if (ui.current_screen != SCREEN_COOLING) {
            ui_load_cooling_screen(format_hhmmss_seconds(model.cooling_sec));
        }
    }
}

// called every UI tick
void ui_tick(void) {
    if (ui.current_screen == SCREEN_COOLING && model.page_id == 0x2014) {
        ui_update_text("counter", format_hhmmss_seconds(model.cooling_sec));
        ui_set_timer_ring_stage(4);
    }
}
```

---

## 6) Edge cases to preserve

- If STM frames stop/invalid -> countdown may freeze at last value (same as this code’s behavior).
- Ensure endian correctness for 16-bit cooling seconds (`little-endian`).
- If your project supports two drawers, mirror the drawer aliasing logic before rendering.
- Keep state transition and UI rendering decoupled:
  - one place decides screen transitions
  - another place does continuous text refresh

---

## 7) Quick code index (where to look in this repo)

- State constants:
  - `config.h` (`TX_CMD::Progress3_State`)
  - `HARDWARE.h` (`DisplayCommand::TX_CMD_Progress3_State`)
- Frame parsing + cooling extraction:
  - `HARDWARE.cpp` (`processSerialFramesNonBlocking`)
- Routing to cooling screen:
  - `main.ino` (`GOTO_STM32_ALERT`, `Progress3_State -> load_screen(25)`)
- Runtime countdown refresh:
  - `main.ino` (`UNDER_STM32_CONTROL`, `SPRITE_updateText("counter", ...)`)
- Cooling screen UI assets:
  - `SCREEN.cpp` (`case 25`)
- Time formatting:
  - `SCREEN.cpp` (`secondsToHHMMSS`)
- Cooling text localization default:
  - `config.cpp` (`"004": "Cooling"`)

---

## 8) What is NOT inferred

- This document does not assume STM32-side logic for decrement policy.
- This document does not infer hidden protocol fields not parsed in this repo.
- All conclusions are from current project code only.

