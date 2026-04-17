# STM32 States `0x2011/0x2012/0x2013` Runtime Timer Logic (ESP32)

## Purpose
This document traces the full logic for runtime timer display when ESP32 receives STM32 running states:
- `0x2011` (`Running_State`)
- `0x2012` (`Progress1_State`)
- `0x2013` (`Progress2_State`)

The goal is to port the same behavior to another ESP-IDF project and display the correct running time.

---

## 1) State definitions

File: `config.h`

```cpp
static constexpr uint16_t Running_State   = 0x2011;
static constexpr uint16_t Progress1_State = 0x2012;
static constexpr uint16_t Progress2_State = 0x2013;
```

These are STM32 page/status IDs used by ESP32 UI routing.

---

## 2) Where runtime time value comes from (raw frame source)

## STM frame parsing
File: `HARDWARE.cpp`
Function: `HARDWARE::processSerialFramesNonBlocking()`

Relevant fields decoded from frame:

```cpp
// state/page ids from STM
drawer1_uipageid = (uint16_t)frameBuf[73] | ((uint16_t)frameBuf[74] << 8);
drawer2_uipageid = (uint16_t)frameBuf[75] | ((uint16_t)frameBuf[76] << 8);

// another timer field (decoded but not used for runtime display path below)
drawer1_CYCLETIME = (uint16_t)frameBuf[77] | ((uint16_t)frameBuf[78] << 8); // minutes
drawer2_CYCLETIME = (uint16_t)frameBuf[79] | ((uint16_t)frameBuf[80] << 8); // minutes

// runtime total time field actually used by UI
drawer1_TotalTimeForCycle = (uint16_t)frameBuf[98]  | ((uint16_t)frameBuf[99]  << 8);
drawer2_TotalTimeForCycle = (uint16_t)frameBuf[100] | ((uint16_t)frameBuf[101] << 8);
```

### Current-drawer aliasing
Still in same function:

```cpp
if (gSYSTEM_drawer == 2){
  my_TotalTimeForCycle = drawer2_TotalTimeForCycle;
  my_uipageid = drawer2_uipageid;
}else{
  my_TotalTimeForCycle = drawer1_TotalTimeForCycle;
  my_uipageid = drawer1_uipageid;
}
```

So for `0x2011/12/13`, displayed runtime timer source is:
- `my_TotalTimeForCycle`
- which comes from frame bytes `98..101` (drawer-selected)

---

## 3) How state transition reaches runtime screen

File: `main.ino`
Function: `checkDrawerUIPageIds()`

When STM is active or page changed:

```cpp
if ((!myhardware.STM_isIdle() && gDeviceStatus != UNDER_STM32_CONTROL) || stateChanged) {
    gOVERRIDEcommands = GOTO_STM32_ALERT;
}
```

Then `PROCESS_GOTOScreenCalls()` handles `GOTO_STM32_ALERT`:

```cpp
case config::TX_CMD::Running_State:
    arg1 = mydisplay.secondsToHHMMSS(myhardware.my_TotalTimeForCycle, true);
    mydisplay.load_screen(7, myui, arg1, emptyS, emptyS);
    break;

case config::TX_CMD::Progress1_State:
case config::TX_CMD::Progress2_State:
    arg1 = mydisplay.secondsToHHMMSS(myhardware.my_TotalTimeForCycle, true);
    mydisplay.load_screen(7, myui, arg1, emptyS, emptyS);
    break;
```

This means all three states (`0x2011/12/13`) enter the same runtime UI template: `screen 7`.

---

## 4) How runtime timer is continuously refreshed

File: `main.ino`
State handler: `case UNDER_STM32_CONTROL`

```cpp
if (myhardware.my_uipageid == config::TX_CMD::Running_State) {
  mydisplay.SPRITE_updateText("counter", mydisplay.secondsToHHMMSS(myhardware.my_TotalTimeForCycle, true));
  mydisplay.setTimerRingBlinking(1, ...);
} else if (myhardware.my_uipageid == config::TX_CMD::Progress1_State) {
  mydisplay.SPRITE_updateText("counter", mydisplay.secondsToHHMMSS(myhardware.my_TotalTimeForCycle, true));
  mydisplay.setTimerRingBlinking(2, ...);
} else if (myhardware.my_uipageid == config::TX_CMD::Progress2_State) {
  mydisplay.SPRITE_updateText("counter", mydisplay.secondsToHHMMSS(myhardware.my_TotalTimeForCycle, true));
  mydisplay.setTimerRingBlinking(3, ...);
}
```

So while state remains `0x2011/12/13`, text sprite `counter` is updated from the latest parsed `my_TotalTimeForCycle` value each loop.

---

## 5) Screen template where timer is rendered

File: `SCREEN.cpp`
Function: `SCREEN::load_screen(...)`
Branch: `case 7`

```cpp
Asset textSprite2 = { "counter", ..., ASSET_TEXT, pVar1, ... };
SPRITE_create(textSprite2);
```

`pVar1` is the preformatted timer string from `secondsToHHMMSS(...)`.

---

## 6) Time formatting rules (critical for ESP-IDF parity)

File: `SCREEN.cpp`
Function: `SCREEN::secondsToHHMMSS(unsigned long secs, bool isMinutes)`

For these runtime states, call uses `isMinutes = true`.

`isMinutes=true` formatting:

```cpp
if (days == 0) {
    // HH:MM
    snprintf(buf, sizeof(buf), "%02lu:%02lu", hours, minutes);
} else {
    // D:HH:MM (days capped to 99)
    if (days > 99) days = 99;
    snprintf(buf, sizeof(buf), "%lu:%02lu:%02lu", days, hours, minutes);
}
```

### Important
- Input value is treated as **minutes**, not seconds.
- Output is `HH:MM` for <24h total.
- Output becomes `D:HH:MM` for >=24h total minutes.

---

## 7) Which timer field is actually used vs not used

- Used for `0x2011/12/13` display: `my_TotalTimeForCycle` (from `drawerX_TotalTimeForCycle` -> frame `98..101`)
- Not used in this display path: `drawerX_CYCLETIME` (frame `77..80`), though it is decoded and logged.

If your ESP-IDF project currently reads `77..80` for running timer, it will not match this firmware behavior.

---

## 8) Full data-flow summary (one line)

STM frame bytes `98..101` -> `drawerX_TotalTimeForCycle` -> `my_TotalTimeForCycle` (by `gSYSTEM_drawer`) -> `secondsToHHMMSS(..., true)` -> `screen 7` sprite `counter` (`load_screen` init + `SPRITE_updateText` live refresh).

---

## 9) ESP-IDF port contract (recommended)

1. Parse state/page IDs from frame bytes `73..76`.
2. Parse total runtime minutes from frame bytes `98..101` (little-endian, per drawer).
3. Select active drawer value into `my_total_time_for_cycle`.
4. If page is `0x2011/12/13`, show runtime screen and timer text.
5. Format timer as minutes-based:
   - `<24h` => `HH:MM`
   - `>=24h` => `D:HH:MM`
6. Refresh timer text every UI tick while page remains in these states.

---

## 10) Reference pseudocode

```c
void on_stm_frame(const Frame* f) {
    uint16_t page_d1 = le16(f->buf[73],  f->buf[74]);
    uint16_t page_d2 = le16(f->buf[75],  f->buf[76]);

    uint16_t total_min_d1 = le16(f->buf[98],  f->buf[99]);
    uint16_t total_min_d2 = le16(f->buf[100], f->buf[101]);

    if (active_drawer == 2) {
        model.page = page_d2;
        model.total_minutes = total_min_d2;
    } else {
        model.page = page_d1;
        model.total_minutes = total_min_d1;
    }
}

void ui_tick(void) {
    if (model.page == 0x2011 || model.page == 0x2012 || model.page == 0x2013) {
        if (ui.current_screen != SCREEN_RUNNING) {
            ui_load_running_screen(format_minutes(model.total_minutes)); // HH:MM or D:HH:MM
        }
        ui_update_text("counter", format_minutes(model.total_minutes));
    }
}
```

---

## 11) Quick file index

- State constants: `config.h`
- Frame parsing + aliasing: `HARDWARE.cpp`
- State routing to runtime screen: `main.ino` (`GOTO_STM32_ALERT`)
- Live runtime timer updates: `main.ino` (`UNDER_STM32_CONTROL`)
- Runtime screen UI element (`counter`): `SCREEN.cpp` (`case 7`)
- Time formatter: `SCREEN.cpp` (`secondsToHHMMSS`)

