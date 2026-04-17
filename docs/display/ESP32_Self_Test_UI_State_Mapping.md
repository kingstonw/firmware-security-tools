# ESP32 Self Test UI State Mapping

## Scope
This document defines self test UI mapping using current firmware code and current docs in this repository.

It covers:
1. self test related STM32 messages
2. meaning of `0x2017` and `0x2018`
3. UI behavior per self test state
4. success page behavior
5. failure page behavior
6. error code display rules
7. firmware files/functions that implement this mapping

---

## Document precedence used

The mapping below was prepared with this priority:
1. `docs/AI_Guidelines.md`
2. `docs/Claude.md`
3. `docs/ai_prompts/base.md`
4. `docs/ai_prompts/analysis.md`
5. `docs/ai_prompts/verification.md`
6. Arduino firmware source files (`main.ino`, `SCREEN.cpp`, `HARDWARE.cpp`, `UI.cpp`, `config.h`, `HARDWARE.h`)

Rule applied: do not guess missing logic; explicitly mark unknowns.

---

## 1) Self test related STM32 messages

## 1.1 STM32 -> ESP32 display state messages
Defined in `config.h` (`config::TX_CMD`):
- `Self_test_State` = `0x2017`
- `Show_Self_test_OK_State` = `0x2018`
- `Show_Self_Test_Error_State` = `0x2019`

Also mirrored in `HARDWARE.h` (`DisplayCommand` enum):
- `TX_CMD_Self_test_State      = 0x2017`
- `TX_CMD_Show_Self_test_OK    = 0x2018`
- `TX_CMD_Show_Self_Test_Error = 0x2019`

## 1.2 ESP32 -> STM32 command that starts self test
Defined in `config.h`:
- `STM32_SELF_TEST = 0x0F`

Triggered by UI action path:
- `SCREEN.cpp` -> `setButtonConfigurationByID(16)` maps `BOTH_LONG` to action `112`
- `UI.cpp` action `112` sends `config::TX_CMD::STM32_SELF_TEST`

---

## 2) Meaning of `0x2017` and `0x2018` (from current code)

## `0x2017` (`Self_test_State`)
Observed behavior in `main.ino`:
- entering this state sets `gSelfTestTimer = millis()`
- loads `screen 26` (self-test running UI)
- under `UNDER_STM32_CONTROL`, UI shows a countdown using `SELFTEST_TIMEOUT_MS`

Interpretation from implemented behavior:
- ESP32 treats `0x2017` as self test running/in-progress.

## `0x2018` (`Show_Self_test_OK_State`)
Observed behavior in `main.ino`:
- loads `screen 28` (done icon + text)
- sets timed alert flow:
  - `gAlertNextCommand = GOTO_UI_IDLE`
  - `gAlertStartTime = 0`
  - `gOVERRIDEcommands = GOTO_NONE`
  - `gDeviceStatus = ALERT_DISPLAY`
- `ALERT_DISPLAY` auto-exits after `ALERT_DISPLAY_TIMEOUT_MS` (5s)

Interpretation from implemented behavior:
- ESP32 treats `0x2018` as self test success page.

Exact STM-side criteria for sending `0x2018`: **Not found in current implementation**.

---

## 3) UI screen behavior for each self test state

## 3.1 `0x2017` -> running screen (`screen 26`)
Routing:
- `main.ino` -> `PROCESS_GOTOScreenCalls()` -> `GOTO_STM32_ALERT`
- case `config::TX_CMD::Self_test_State`:
  - `gSelfTestTimer = millis()`
  - `mydisplay.load_screen(26, myui, emptyS, emptyS, emptyS)`

`screen 26` (`SCREEN.cpp`):
- icon: `ICON_SETTING`
- text: `langMap["010"]`
- text sprite: `counter` (blank initially)
- progress bar: `progressbar`
- buttons disabled via `configAllButtonsOff(myui)`

Runtime updates while page remains `0x2017` (`main.ino`, `UNDER_STM32_CONTROL`):
- `timeLeft = SELFTEST_TIMEOUT_MS - (millis() - gSelfTestTimer)` (clamped at 0)
- `secondsLeft = (timeLeft + 999) / 1000`
- `counter` = `secondsToHHMMSS(secondsLeft, false)`
- progress bar updated with `totalSeconds = SELFTEST_TIMEOUT_MS / 1000`

## 3.2 `0x2018` -> success screen (`screen 28`)
Routing:
- `main.ino` -> `GOTO_STM32_ALERT` -> case `Show_Self_test_OK_State`
- `mydisplay.load_screen(28, ...)`
- enter `ALERT_DISPLAY` timed flow

`screen 28` (`SCREEN.cpp`):
- icon: `/assets/DONE.raw`
- text: `langMap["015"]`
- button profile: `setButtonConfigurationByID(myui, 8)`

## 3.3 `0x2019` -> failure screen (`screen 29`)
Routing:
- `main.ino` -> `GOTO_STM32_ALERT` -> case `Show_Self_Test_Error_State`
- calls `formatAndShowSelfTestErrors(...)`
- `mydisplay.load_screen(29, myui, pStr1, pStr2, pStr3)`

`screen 29` (`SCREEN.cpp`):
- icon: `/assets/WARNING.raw`
- three error text rows: `errors1`, `errors2`, `errors3`
- button profile: `setButtonConfigurationByID(myui, 8)`

---

## 4) Success page behavior

Success page is `screen 28` for state `0x2018`.

Behavior chain:
1. Load `screen 28`.
2. Switch to `ALERT_DISPLAY`.
3. After `ALERT_DISPLAY_TIMEOUT_MS` (5s), route to `GOTO_UI_IDLE`.

Additional button behavior on screen profile `8`:
- `UI.cpp` action `113`: sends `STM32_REBOOT`, then sets `GOTO_UI_IDLE`.

Other actions present in profile `8` (`110`, `111`) are mapped in code but their intent for self-test success UX is **Needs clarification**.

---

## 5) Failure page behavior

Failure page is `screen 29` for state `0x2019`.

Behavior chain:
1. Decode self test bits into 1..3 text lines.
2. Load `screen 29` with those lines.
3. No success-style timed auto-exit branch is set in this state handler.
4. `checkDrawerUIPageIds()` guard:
   - if previous page is `Show_Self_Test_Error_State`, function returns early and ignores STM state-change routing.

Observed effect:
- failure page behaves as sticky in current flow.

Exact intended exit policy for failure page: **Needs clarification**.

---

## 6) How error codes are displayed

## 6.1 Raw source bytes
From `HARDWARE.cpp` frame parse:
- `selftest_b0 = frameBuf[82]`
- `selftest_b1 = frameBuf[83]`
- `selftest_b2 = frameBuf[84]`

## 6.2 Decode/display function
`SCREEN.cpp` -> `formatAndShowSelfTestErrors(uint8_t b0, uint8_t b1, uint8_t b2, String& s1, String& s2, String& s3)`

Implemented rules:
- evaluates 21 bit positions (`0..20`)
- lookup list by bit position:
  - `45, 32T, 32B, 30T, 30B, 43T, 43B, 38, 36, 39, 37, 40, 42, 48, 47, 49, 41, 46, 44T, 44B, 35`
- bit meaning:
  - `1 = FAIL` (show)
  - `0 = PASS` (skip)
- line packing:
  - max 8 codes per line
  - max 3 lines
  - overflow appends `+` to last non-empty line
- all-pass case:
  - line1=`OK`, line2=``, line3=``
- empty lines normalized to single-space for layout stability

`screen 29` renders `s1/s2/s3` as three rows.

---

## 7) Firmware files/functions implementing this mapping

## Constants and message IDs
- `config.h` -> `config::TX_CMD`
- `HARDWARE.h` -> `DisplayCommand`

## STM frame parse source
- `HARDWARE.cpp` -> `processSerialFramesNonBlocking()`
  - page IDs
  - `selftest_b0/b1/b2`

## State routing and state-machine behavior
- `main.ino`
  - `checkDrawerUIPageIds()`
  - `PROCESS_GOTOScreenCalls()` (`GOTO_STM32_ALERT` branch)
  - `UNDER_STM32_CONTROL` (countdown/progress updates)
  - `ALERT_DISPLAY` (timed success exit)

## Screen composition and error formatting
- `SCREEN.cpp`
  - `load_screen()` cases `26`, `28`, `29`
  - `formatAndShowSelfTestErrors(...)`
  - `setButtonConfigurationByID(...)` case `8`

## Button action dispatch
- `UI.cpp`
  - action `112` (send `STM32_SELF_TEST`)
  - action `113` (send `STM32_REBOOT`, go idle)

---

## State mapping table (portable)

| STM state | Meaning in ESP32 code | Screen | Timer behavior | Exit behavior |
|---|---|---|---|---|
| `0x2017` | Self test running | `26` | local countdown from `SELFTEST_TIMEOUT_MS` | follows STM state changes |
| `0x2018` | Self test success | `28` | no running countdown | auto to idle via `ALERT_DISPLAY` after 5s |
| `0x2019` | Self test failure | `29` | no running countdown | sticky in current flow; explicit auto-exit not found |

---

## Not found / needs clarification

- STM-side decision criteria for sending `0x2018` vs `0x2019`: **Not found in current implementation**.
- Product-intended auto-exit policy for failure page (`0x2019`): **Needs clarification**.

