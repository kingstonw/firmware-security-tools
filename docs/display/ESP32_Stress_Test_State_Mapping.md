# ESP32 Stress Test State Mapping

## Scope

This document defines the complete behavior of the **Stress Test** feature in the Arduino firmware, including:

- How the user triggers stress test
- Which screens and button configurations expose this action
- What UART command is sent to STM32
- What the ESP32 displays before, during, and after the trigger
- What STM32 response (if any) is expected
- How the state machine behaves for this feature

Derived exclusively from Arduino firmware source code and project guideline documents.  
No behavior is invented or assumed. Unknowns are explicitly marked.

---

## 1. Purpose

The stress test is a hardware diagnostic command sent from the ESP32 to the STM32 co-processor. It is intended for factory or field testing to exercise the hardware under load. The ESP32 sends a single UART command (`STM32_STRESSTEST`, value `0x0A`) to the STM32. The Arduino firmware does **not** show a dedicated stress test UI screen, does **not** change device state, and does **not** route any STM32 response page ID specifically for "stress test mode."

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
   - `config.h` — `STM32_STRESSTEST = 0x0A` definition
   - `HARDWARE.cpp` — `sendButtonEvent()` UART frame builder
   - `SCREEN.cpp` — button configurations 16 (Drawer 1 READY) and 6 (Drawer 2 READY)
   - `UI.cpp` — `executeAction()` case 117
   - `main.ino` — state machine and AWS trigger handlers
   - `AWS.cpp` — remote command list (stress test **not** present)

Rule applied: Do not guess missing logic. Explicitly mark unknowns.

---

## 3. Stress Test Overview

### 3.1 Command Definition

Source: `config.h`, `config::TX_CMD`:

```cpp
// button event codes sent to STM32
static constexpr uint16_t STM32_STRESSTEST = 0x0A;
```

`STM32_STRESSTEST` is categorized under **button event codes sent to STM32** — meaning it is a command sent *to* STM32, not a page ID received *from* STM32.

### 3.2 Summary of Behavior

| Property | Value |
|----------|-------|
| Command value | `0x0A` |
| Direction | ESP32 → STM32 (outbound only) |
| Trigger method | Physical button combination only (see §5) |
| AWS remote trigger | **Not implemented** — no `STM_STRESSTEST` command in `AWS.cpp` |
| Dedicated UI screen | **None** — READY screen remains displayed |
| State machine change | **None** — device stays in current state |
| Expected STM32 response page | **Not found in current implementation** |
| Buzzer on trigger | **Not confirmed** — no buzzer code found in the trigger path |
| Drawer restriction | Drawer 1 only triggers stress test; Drawer 2 triggers Factory Reset Confirmation instead |

---

## 4. Trigger Path From User Input

### 4.1 Physical Button Combination

Stress test is triggered exclusively by a **physical button press**. The combination is:

- **BOTH buttons** (BTN1 + BTN2 held simultaneously)
- **Extended duration press** (the longest hold duration)
- **While on the READY screen** (`screen 4`)
- **Only when `gSYSTEM_drawer == 1`** (Drawer 1)

Source: `SCREEN.cpp`, button configuration 16 (READY, Drawer 1):

```cpp
case 16: {                     // READY (Drawer 1)
    int actions[BUTTON_DETECTION_COUNT] = {
    // click  short  long  vlong  ext
       0,   108,   0,   109,   0,    // BTN1
       0,   110, 111,   102, 120,    // BTN2
       0,     0,   0,   112, 117};   // BOTH → ext = 117 = STRESS TEST
    configButtons(myui, actions);
} break;
```

The trigger column is `ext` (extended hold) for `BOTH`:
- `BOTH extended → action 117`

### 4.2 What Happens for Drawer 2

On the READY screen when `gSYSTEM_drawer == 2`, button configuration 6 is applied instead:

```cpp
case 6: {                      // READY (Drawer 2)
    int actions[BUTTON_DETECTION_COUNT] = {
    // click  short  long  vlong  ext
       0,   108,   0,   109,   0,    // BTN1
       0,   110, 111,   102,   0,    // BTN2
       0,     0,   0,   112, 117};   // BOTH → ext = 117
    configButtons(myui, actions);
} break;
```

Action 117 is also mapped to `BOTH extended` on the Drawer 2 READY screen. However, the behavior inside action 117 branches on `gSYSTEM_drawer`:

- If `gSYSTEM_drawer == 1` → Stress Test (sends `STM32_STRESSTEST 0x0A`)
- If `gSYSTEM_drawer == 2` → Factory Reset Confirmation (loads screen 21)

**Confirmed: Stress test is only triggered for Drawer 1.**

### 4.3 No AWS Remote Trigger

Confirmed by scanning `AWS.cpp` (`aws_defaultRemoteCommandCallback`): there is **no** case for `"STM_STRESSTEST"` or any equivalent string. The complete AWS command list for the firmware does not include a stress test trigger.

The AWS command comment block in `AWS.cpp` lists all verified/active commands. Stress test is absent.

---

## 5. Button / Action Mapping

### 5.1 Action 117 — Drawer-Dependent Behavior

Source: `UI.cpp`, `executeAction()`:

```cpp
case 117: {
    if (gSYSTEM_drawer == 1) {
        Serial.println("ACTION 117, Drawer 1 - Stress Test");
        myhardware.sendButtonEvent(gSYSTEM_drawer, config::TX_CMD::STM32_STRESSTEST);
    } else {
        Serial.println("ACTION 117, Drawer 2 - Factory Reset Confirmation");
        mydisplay.load_screen(21, *this, "", "", "");
    }
} break;
```

| Condition           | Behavior                                          |
|---------------------|---------------------------------------------------|
| `gSYSTEM_drawer == 1` | Sends `STM32_STRESSTEST` (`0x0A`) to STM32 via UART |
| `gSYSTEM_drawer == 2` | Loads screen 21 (Factory Reset Confirmation)      |

### 5.2 Button Config Summary — All Screens with Action 117

From `SCREEN.cpp`, `setButtonConfigurationByID()`:

| Config ID | Screen purpose    | Where action 117 is mapped | Result (drawer 1) | Result (drawer 2) |
|-----------|-------------------|-----------------------------|-------------------|-------------------|
| 16        | READY (Drawer 1)  | BOTH extended               | Stress test       | _(not applicable — drawer 1 screen)_ |
| 6         | READY (Drawer 2)  | BOTH extended               | Stress test       | Factory Reset Confirmation |
| 10        | Provisioning (skip option) | BOTH extended      | Stress test       | Factory Reset Confirmation |

**Button config 10** also maps BOTH extended → 117. This means the BOTH extended combination during provisioning (skip option screen) can also trigger stress test for drawer 1.

Source: `SCREEN.cpp`, button configuration 10:

```cpp
case 10: {                     // Provisioning (skip option)
    int actions[BUTTON_DETECTION_COUNT] = {
    // click  short  long  vlong  ext
       0,     0,     0,   109,   0,    // BTN1
     114,   114,     0,     0,   0,    // BTN2
       0,     0,     0,     0, 117};   // BOTH → ext = 117
    configButtons(myui, actions);
} break;
```

### 5.3 Complete Trigger Path

```
User holds BTN1 + BTN2 (extended duration)
    while on READY screen (screen 4)
    with gSYSTEM_drawer == 1
            │
            ▼
    Action ID 117 fires
            │
    gSYSTEM_drawer == 1 → true
            │
            ▼
    myhardware.sendButtonEvent(1, config::TX_CMD::STM32_STRESSTEST)
    = sendButtonEvent(drawer=1, eventTypeID=0x0A)
            │
            ▼
    11-byte UART frame sent to STM32
```

---

## 6. UART / STM32 Command Mapping

### 6.1 `sendButtonEvent()` Frame Format

Source: `HARDWARE.cpp`, `sendButtonEvent()`:

```cpp
bool HARDWARE::sendButtonEvent(int drawer, uint8_t eventTypeID) {
    uint8_t msg[11];
    msg[0] = 0x8F;                            // SOF byte
    msg[1] = 0x66;                            // protocol marker
    msg[2] = 0x10;                            // protocol marker
    msg[3] = (drawer == 1) ? 0x01 : 0x02;    // drawer ID
    msg[4] = msg_id_high;                     // message ID high byte
    msg[5] = msg_id_low;                      // message ID low byte (auto-increments)
    msg[6] = 0x01;                            // payload length
    msg[7] = eventTypeID;                     // event type = 0x0A for stress test
    msg[8] = 0x01;                            // payload footer
    // XOR checksum of bytes 1-8:
    msg[9] = checksum;
    msg[10] = 0x8E;                           // EOF byte
    UART.write(msg, 11);
    UART.flush();
}
```

### 6.2 Stress Test Frame

For `sendButtonEvent(1, 0x0A)` (drawer 1, stress test):

| Byte | Value | Description |
|------|-------|-------------|
| `[0]` | `0x8F` | Start-of-frame |
| `[1]` | `0x66` | Protocol marker |
| `[2]` | `0x10` | Protocol marker |
| `[3]` | `0x01` | Drawer 1 ID |
| `[4]` | `msg_id_high` | Message ID high (auto-increment) |
| `[5]` | `msg_id_low` | Message ID low (auto-increment) |
| `[6]` | `0x01` | Payload length |
| `[7]` | **`0x0A`** | **`STM32_STRESSTEST` command** |
| `[8]` | `0x01` | Payload footer |
| `[9]` | XOR checksum | Bytes `[1]`–`[8]` XORed |
| `[10]` | `0x8E` | End-of-frame |

Total: 11 bytes, sent via `UART.write()` followed by `UART.flush()`.

### 6.3 No STM32 Response Page ID for Stress Test

Searching the full Arduino codebase: there is **no** `case config::TX_CMD::STRESSTEST` or any equivalent `0x20XX` page ID handling in `GOTO_STM32_ALERT` or `UNDER_STM32_CONTROL` that indicates stress test mode feedback from STM32. The `config::TX_CMD` class defines stress test only as an outbound command (`0x0A`), not as an inbound page ID.

**Confirmed: The ESP32 sends `0x0A` to STM32 and does not process any specific stress test page ID in response. What STM32 does internally during stress test is not found in current ESP32 implementation.**

---

## 7. Arduino Behavior

### 7.1 Before Trigger — READY Screen

The device is on **screen 4** ("READY" screen), `gDeviceStatus = UNDER_STM32_CONTROL` or `ONLINE`:

Source: `SCREEN.cpp`, case 4:

```cpp
case 4: {
    myui.setLedDefaults(OFF, OFF);

    if (gSYSTEM_drawer == 1) {
        setButtonConfigurationByID(myui, 16);  // stress test available via BOTH ext
    } else {
        setButtonConfigurationByID(myui, 6);   // factory reset for drawer 2
    }

    Asset textSprite2 = { "counter", 0, LINE5Y, 320, FONT4H, ...,
                          ASSET_TEXT, langMap["001"], ..., CENTER, ..., FONT4, ... };
    SPRITE_create(textSprite2);
}
```

Screen 4 displays:
- Text: `langMap["001"]` = `"READY"` — large font, centered
- LEDs: both OFF
- Buttons: config 16 (drawer 1) or config 6 (drawer 2)

### 7.2 On Trigger — `sendButtonEvent` Sent, No Screen Change

When action 117 fires for drawer 1:

```cpp
myhardware.sendButtonEvent(gSYSTEM_drawer, config::TX_CMD::STM32_STRESSTEST);
```

- The 11-byte UART frame is written to STM32 immediately.
- **No `gOVERRIDEcommands` is set.**
- **No screen transition occurs.**
- **No `gDeviceStatus` change occurs.**
- The READY screen (screen 4) remains displayed.
- The device stays in whatever state it was in before the trigger.

Serial output (always printed, not behind `gVerbosePrints`):

```
ACTION 117, Drawer 1 - Stress Test
SND: 8F 66 10 01 [id_h] [id_l] 01 0A 01 [cs] 8E
SND: wrote 11
```

### 7.3 After Trigger — No Dedicated State

The Arduino implementation does not have a "stress test in progress" state, screen, or animation. After the UART frame is sent:

- `checkDrawerUIPageIds()` continues to run each loop
- If STM32 broadcasts a new page ID (any value), the state machine responds normally
- If STM32 broadcasts a page ID that indicates an error (`0x2030`–`0x2049`), the error screen is shown
- If STM32 broadcasts Standby (`0x2010`), the device returns to idle

No specific handling for "stress test completed" or "stress test failed" exists in the current implementation.

---

## 8. Screen / UI Mapping

### 8.1 Before Trigger — Screen 4 (READY)

| Element | Value |
|---------|-------|
| Screen number | 4 |
| Log output | `"[DISPLAY] READY screen..."` |
| Text sprite `"counter"` | `langMap["001"]` = `"READY"` (large FONT4, centered) |
| LEDs | OFF, OFF |
| Button config | 16 (drawer 1) / 6 (drawer 2) |
| BOTH extended press | Action 117 → stress test (drawer 1) or factory reset (drawer 2) |

### 8.2 During Stress Test — No UI Change

**Confirmed: There is no dedicated stress test UI screen.** The READY screen remains displayed while the STM32 executes the stress test. The ESP32 does not change any display element on trigger.

### 8.3 After Trigger — Follows STM32 Page ID

If the STM32 broadcasts any page ID in response to the stress test:
- The page ID is parsed via `processSerialFramesNonBlocking()`
- `checkDrawerUIPageIds()` detects `stateChanged = true`
- The appropriate screen is loaded via `GOTO_STM32_ALERT`
- This is the **same path** as any other STM32 state change

What page ID the STM32 broadcasts during or after stress test is **Not found in current implementation**.

---

## 9. State-Machine Behavior

### 9.1 Confirmed State Transitions

```
User: BOTH extended press on READY screen (drawer 1)
            │
            ▼
    executeAction(117)
            │
    sendButtonEvent(1, 0x0A) → UART to STM32
            │
    [NO gOVERRIDEcommands change]
    [NO gDeviceStatus change]
    [READY screen remains displayed]
            │
            ▼
    STM32 receives 0x0A and starts stress test
    [what STM32 does: Not found in current implementation]
            │
            ▼
    If STM32 broadcasts new page ID (any):
        stateChanged = true
        → GOTO_STM32_ALERT
        → route to appropriate screen
            │
    If STM32 broadcasts Standby (0x2010):
        STM_isIdle() → true
        → directOnlineForSkipProvisioning()
        → GOTO_UI_IDLE → load_screen(4) READY
```

### 9.2 State Diagram

```
[READY screen, drawer 1]
        │
[BOTH extended → action 117]
        │
[sendButtonEvent(0x0A)]
        │
        ├──────────────────────────────────────┐
        │                                      │
   [STM32 still on Standby /          [STM32 broadcasts new page]
    no page change]                          │
        │                             stateChanged = true
   [READY screen persists]             GOTO_STM32_ALERT
        │                                      │
        └──────────────────────────────────────┘
                                              │
                                [Normal page routing]
                                [any 0x20XX page ID]
```

---

## 10. Runtime Update Behavior

**Confirmed: No runtime update specific to stress test exists.**

The `UNDER_STM32_CONTROL` block in `main.ino` has no branch for stress test mode. All runtime updates during the READY screen and any subsequent STM32 state use the standard update paths. The stress test command is a one-shot outbound UART write — there is no ongoing UI update associated with it.

---

## 11. Exit / Completion Behavior

### 11.1 Confirmed Exit Path

The stress test has no dedicated exit path in the ESP32. The device transitions away from the READY screen only if:

1. **STM32 broadcasts a new page ID** (any value) after the stress test.
   - Detected by `checkDrawerUIPageIds()` → `stateChanged = true` → `GOTO_STM32_ALERT`
   - If the new page is Standby → returns to READY
   - If the new page is an error → error screen shown
   - If the new page is a running state → running screen shown

2. **Another user action** on the READY screen triggers a different state (e.g., BTN2 short starts the motor).

### 11.2 No Timeout or Completion Indicator

There is **no timeout**, **no completion acknowledgment**, and **no "stress test done" screen** in the current implementation. The ESP32 simply waits for the STM32 to change its page ID.

---

## 12. Differences Between Arduino and Current ESP-IDF Implementation

| Item | Arduino behavior | ESP-IDF status |
|------|-----------------|----------------|
| `STM32_STRESSTEST = 0x0A` defined | Yes — `config.h` | **Needs verification** |
| BOTH extended press on READY screen → action 117 | Yes — button config 16 | **Needs implementation** |
| Action 117 → drawer check → send 0x0A | Yes — drawer 1 only | **Needs implementation** |
| 11-byte UART frame with 0x0A at byte `[7]` | Yes — `sendButtonEvent()` | **Needs implementation** |
| No screen change on trigger | Yes — confirmed fire-and-forget | **Confirmed behavior** |
| No state machine change on trigger | Yes — device stays in current state | **Confirmed behavior** |
| No dedicated stress test UI screen | Yes — READY screen persists | **Confirmed behavior** |
| No STM32 response page ID for stress test | Not found | **No handling needed** |
| No AWS remote trigger for stress test | Not implemented | **No AWS support needed** |
| Provisioning skip screen also has action 117 | Yes — button config 10 | **Needs implementation if provisioning screen is ported** |
| Drawer 2: action 117 → factory reset (not stress test) | Yes | **Needs implementation — check drawer before sending** |
| Buzzer on trigger | Not confirmed | **Not implemented in Arduino — do not add** |

---

## 13. Error / Unclear Points

### 13.1 No STM32 Response — Behavior Unknown

What the STM32 does after receiving `0x0A` (stress test) is **Not found in current ESP32 implementation**. Possible outcomes:
- STM32 may stay silent (no page ID change)
- STM32 may eventually broadcast Standby when done
- STM32 may broadcast an error page if a fault is detected

None of these are handled by specific ESP32 logic — all outcomes fall through the generic `checkDrawerUIPageIds()` path.

### 13.2 Stress Test Available From Provisioning Screen

Button config 10 (provisioning skip screen) also maps BOTH extended → action 117. This means a user performing provisioning who holds both buttons simultaneously for an extended duration could trigger the stress test command to STM32. Whether this is intentional behavior is **Needs clarification**.

### 13.3 No Confirmation Screen Before Stress Test

Unlike factory reset (which shows a confirmation screen 21), stress test has **no confirmation step**. The UART command is sent immediately when the button combination is detected. Whether this is intentional or an oversight is **Needs clarification**.

### 13.4 Drawer 2 Action 117 Mismatch in Comment

The comment in `SCREEN.cpp` for button config 16 says:
```
0, 0, 0, 112, 117};  // BOTH: [click], [short], [long], [STM32 self test], [STRESS TEST]
```

And for config 6 (Drawer 2):
```
0, 0, 0, 112, 117};  // BOTH: [click], [short], [long], [STM32 self test], [factory reset]
```

The comment for config 6 correctly names the Drawer 2 extended press as "factory reset," matching the code in `executeAction(117)`. The comment is accurate.

### 13.5 No Serial Monitor Output from `sendButtonEvent` Unless `gVerbosePrints`

The hex dump of the UART frame in `sendButtonEvent()` is gated behind `if (gVerbosePrints)`. However, the `Serial.print(F("SND: wrote")); Serial.println(n);` line is **not** gated — it always prints. The "ACTION 117, Drawer 1 - Stress Test" message in `executeAction()` is also always printed. These are reliable indicators for debugging.

### 13.6 What Constitutes "Extended" Button Hold Duration

The `BUTTON_DETECTION_COUNT` array has 5 entries per button group: click, short, long, vlong, ext. The actual timing thresholds for each tier are defined elsewhere in the UI/button driver — not found in the files reviewed. What "extended" means in milliseconds is **Needs clarification**.

---

## 14. Implementation Guidance for ESP-IDF

This section provides mapping guidance only. **No implementation code is provided.**

### 14.1 Command Constant

Define the following constant (equivalent to `config::TX_CMD::STM32_STRESSTEST` in `config.h`):

```
STM32_STRESSTEST = 0x0A
```

This is an outbound-only command. It does **not** appear as an inbound STM32 page ID.

### 14.2 UART Frame

Use the existing `sendButtonEvent()` frame format:

- 11 bytes total
- SOF: `0x8F`
- Drawer ID: `0x01` (drawer 1) or `0x02` (drawer 2)
- Command byte at position `[7]`: `0x0A`
- XOR checksum of bytes `[1]`–`[8]`
- EOF: `0x8E`

This is identical to `STM32_BTN2CLICK`, `STM32_SELF_TEST`, and all other outbound button events.

### 14.3 Trigger Condition

Implement the BOTH extended press detection on the READY screen for drawer 1 only:

```
if (drawer == 1 and BOTH_buttons_extended_press):
    send sendButtonEvent(1, 0x0A)
    [no screen change]
    [no state change]

if (drawer == 2 and BOTH_buttons_extended_press):
    [show factory reset confirmation — separate feature, not stress test]
```

### 14.4 No UI Change Required

After sending `0x0A`:
- Do not change the current screen.
- Do not change the device state.
- Do not start any timer or animation.
- Continue processing incoming STM32 page IDs normally.

### 14.5 No AWS Remote Trigger Required

The Arduino implementation has no AWS command for stress test. No equivalent remote command needs to be implemented in the ESP-IDF port for parity.

### 14.6 Verification Test

1. Put the device on the READY screen with `active_drawer = 1`.
2. Simulate BOTH extended press.
3. Expected: UART frame with byte `[7] = 0x0A` is transmitted.
4. Expected: Serial output shows `"ACTION 117, Drawer 1 - Stress Test"` and `"SND: wrote 11"`.
5. Expected: Display remains on READY screen — no visual change.
6. Expected: Device remains in its current state.

To verify drawer 2 does NOT trigger stress test:
1. Set `active_drawer = 2`.
2. Simulate BOTH extended press.
3. Expected: Factory Reset Confirmation screen (screen 21) is shown — NOT stress test.
4. Expected: No UART frame with `0x0A` is sent.

---

## 15. Not Found / Needs Clarification

| Item | Status |
|------|--------|
| What STM32 does after receiving `0x0A` (stress test content/duration/behavior) | **Not found in current implementation** |
| What page ID (if any) the STM32 broadcasts after stress test completes | **Not found in current implementation** |
| Whether stress test from the provisioning screen (button config 10) is intentional | **Needs clarification** |
| Whether the absence of a confirmation screen before stress test is intentional | **Needs clarification** |
| Exact timing threshold for "extended" button hold duration | **Not found in reviewed files** |
| Whether any LED or display feedback should accompany the trigger | **Not found in current implementation** |
| Whether stress test is available from any screen other than READY and provisioning | **Not confirmed for other screens** — only configs 6, 10, 16 include action 117 |

