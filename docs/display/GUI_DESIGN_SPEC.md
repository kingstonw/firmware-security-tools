# GUI Current Design and Implementation Status

---

## 1. Scope

| Field | Value |
|---|---|
| **Source project** | Arduino (this repo — `SCREEN.cpp`, `SCREEN.h`, `UI.cpp`, `UI.h`, `ASSETS.h`, `config.h`, `config.cpp`, `main.ino`) |
| **Target project** | ESP-IDF implementation |
| **Purpose** | Document current GUI exactly as implemented in Arduino source |
| **Rule** | Do not infer missing behavior. Unknown values are explicitly marked. |
| **Display hardware** | LilyGo T-Display S3 — exact variant unknown from source; coordinate evidence (X up to 320, Y up to 245) indicates **320×240** effective resolution in landscape |
| **Display driver** | TFT_eSPI (`tft.init()`, `tft.setRotation(3)` — landscape) |
| **Color depth** | RGB565 (16-bit) |
| **Rendering strategy** | Double-buffered sprite — full-screen `TFT_eSprite` (`backgroundSprite`) composited then pushed via `backgroundSprite->pushSprite(0, 0)` |

> **Note:** `SCREEN.cpp` header comment says "160x128 ST7735 TFT." This contradicts actual Y coordinates used (e.g., `y=230`, `y=245`) and X=320. Header comment is stale/incorrect. Actual dimensions confirmed as ≥320×240 from code behaviour.

---

## 2. Resource Migration Status

### 2.1 PROGMEM Icons (compiled into `ASSETS.h`)

These are RGB565 pixel arrays stored in flash (`PROGMEM`), rendered by `renderPROGMEM()`.

| Icon symbol | Dimensions | Confirmed usage |
|---|---|---|
| `ICON_LOGO` | 212 × 49 | Screen 12 (Boot/Logo screen) |
| `ICON_SETTING` | 67 × 67 | Screens 5, 8, 11, 13, 18, 26 |
| `ICON_QR` | 100 × 100 | Screen 1 (QR code provisioning) |
| `ICON_WIFI` | 33 × 33 | Header — WiFi connected |
| `ICON_NOWIFI` | 25 × 25 | Header — WiFi disconnected |
| `ICON_BLUETOOTH` | 33 × 33 | Header — BLE active |
| `ICON_AWS` | 33 × 33 | Header — AWS connected |
| `ICON_DRAWER` | 33 × 33 | Header — drawer active (tinted `ORANGEBRIGHT`) |
| `ICON_HOT` | 37 × 33 | Header — over-temperature (tinted `ORANGEBRIGHT`) |
| `ICON_STAT1` | 68 × 67 | Progress blocks widget — download step (position 2) |
| `ICON_STAT2` | 68 × 67 | Progress blocks widget — provisioning step (position 0) |
| `ICON_STAT3` | 68 × 67 | Progress blocks widget — configure step (position 3) |
| `ICON_STAT4` | 68 × 67 | Progress blocks widget — search step (position 1) |

**Migration status:** All above confirmed present in `ASSETS.h` with `PROGMEM` keyword. No ESP-IDF port exists yet.

**Not found in PROGMEM / not confirmed:**
- `ICON_WIFI0` — declared in `ASSETS.h` (25×25) but not referenced in any `SCREEN.cpp` renderPROGMEM lookup table.

---

### 2.2 SPIFFS `.raw` Asset Files

Loaded at runtime from SPIFFS as `ASSET_ICON` type (raw RGB565 binary). File path hardcoded in `load_screen()`.

| File path | Used in screen | Context |
|---|---|---|
| `/assets/WARNING.raw` | 22, 27, 29, 30, 32 | Warning / error icon |
| `/assets/DONE.raw` | 16, 28 | Success / complete icon |
| `/assets/PAUSE.raw` | 33 | Waiting for other drawer |
| `/assets/infinity.raw` | 7 | Running timer icon (25×12) |
| `/assets/cooling.raw` | 25 | Cooling timer icon (20×20) |
| `/assets/POWER.raw` | 27 (dynamic) | Alternates with WARNING.raw via `SPRITE_toggleSprites` for hot drawer-open/pause states |

**Migration status:** All 5 files referenced in source. Physical files must exist in SPIFFS on device. No ESP-IDF port exists yet.

**Not confirmed:**
- Exact file dimensions for `WARNING.raw`, `DONE.raw`, `PAUSE.raw` — drawn using asset `w=67, h=67` in all cases.
- Byte order / pixel packing assumed same as ICON assets (RGB565, `swapBytes=true` in `renderIMAGE`).

---

### 2.3 Fonts

All fonts are compiled-in GFX fonts (not VLW). Resolved in `SCREEN::resolveFont()`.

| Font symbol | Config alias | File included |
|---|---|---|
| `Varela_7` | `FONT1` | `<Fonts/Custom/Varela_7.h>` |
| `Roboto_10` | `FONT2` | `<Fonts/Custom/Roboto_10.h>` |
| `FjallaOne_21` | `FONT3`, `FONT4` | `<Fonts/Custom/FjallaOne_21.h>` |

**Current Arduino usage confirmed in `SCREEN.cpp`:**

| Alias | Used for |
|---|---|
| `FONT1` (`Varela_7`) | Small captions, status sub-lines, firmware version string |
| `FONT2` (`Roboto_10`) | Primary text labels, button labels, most UI text |
| `FONT3`/`FONT4` (both → `FjallaOne_21`) | Large counter/timer display (`HH:MM:SS`), ready label |

**Not confirmed:**
- `ArchivoBlack_18` is mentioned in a commented-out line in `resolveFont()` — not loaded, not used.
- VLW font loading infrastructure exists in `SCREEN.h` comments but is **commented out** in the implementation (`validateAvailableFonts` call commented out in `begin()`). VLW fonts are not used in current code.

---

### 2.4 Language / Localization

Loaded via `SCREEN::begin()` → `SPIFF_Manager::loadLanguageMap()` into `langMap` (`std::map<String, String>`).

**Fallback default** (hardcoded in `config.cpp`, keys 001–025):

| Key | English text |
|---|---|
| `"001"` | Ready |
| `"002"` | Paused |
| `"003"` | On |
| `"004"` | Cooling |
| `"005"` | Done |
| `"006"` | Jammed |
| `"007"` | Hold To Clear Jam |
| `"008"` | No Bucket |
| `"009"` | Add Bucket |
| `"010"` | Diagnostic |
| `"011"` | Reset To Factory Settings |
| `"012"` | Options |
| `"013"` | Wireless |
| `"014"` | Hot Surface! |
| `"015"` | Clear Jam, Remove Object |
| `"016"` | Bucket Required, Insert Bucket |
| `"017"` | Cycle Complete |
| `"018"` | Resume Cycle |
| `"019"` | Pause Cycle |
| `"020"` | Drawer Open |
| `"021"` | Error |
| `"022"` | Device Unprovisioned. Please Download The App *(re-used as firmware download progress label)* |
| `"023"` | 14 Lbs CO2e Averted. 8 Lbs Waste Diverted |
| `"024"` | Cycling |
| `"025"` | Hold For 3 Sec After Object Removed |

**Language keys referenced in `SCREEN.cpp` but NOT in default fallback (026+):**

| Key | Used in screen | Text unknown — from SPIFFS lang file only |
|---|---|---|
| `"026"` | Screen 10 (Asset Downloading) progress label | ❓ |
| `"027"` | Screen 9 (Provisioning) progress label | ❓ |
| `"028"` | Screen 8 (Waiting for BLE) main text | ❓ |
| `"029"` | Screen 6 (Check Updates) progress label | ❓ |
| `"032"` | Screen 5 (WiFi Connect) text | ❓ |
| `"033"` | Screen 1 (QR) top text line | ❓ |
| `"037"` | Screen 7 (Running) status sub-label | ❓ |
| `"039"` | Screen 2 (Downloading Firmware) status text | ❓ |
| `"041"` | Screen 13 — Restart instance text | ❓ |
| `"042"` | Screen 17 (Loading Settings) progress label | ❓ |
| `"045"` | YES / confirm button label | ❓ |
| `"046"` | NO / cancel button label | ❓ |
| `"047"` | Screen 5 / Screen 13 (WiFi connecting text) | ❓ |
| `"048"` | Screen 19 title — update available | ❓ |
| `"049"` | Screen 19 body — install update? | ❓ |
| `"050"` | Screen 13 — loading text | ❓ |
| `"051"` | YES button fallback / skip provisioning button | ❓ |
| `"056"` | Screen 20 — unable to connect to WiFi | ❓ |
| `"057"` | Screen 20 — update settings in app? | ❓ |
| `"059"` | Screen 16 (Done) — asset download complete message | ❓ |
| `"060"` | Screen 12 (Logo) device ID suffix label | ❓ |
| `"063"` | Screen 14 (Welcome) main text | ❓ |
| `"064"` | Screen 14 (Welcome) secondary text | ❓ |
| `"065"` | Screen 11 — CANCEL button label | ❓ |
| `"066"` | Screen 14 — CONTINUE button label | ❓ |
| `"067"` | Screen 18 — pump running label | ❓ |
| `"068"` | Screen 21 — factory reset confirmation body | ❓ |
| `"069"` | Screen 16 (provisioning completed) message | ❓ |
| `"071"` | Screen 33 — waiting for Drawer 1 text | ❓ |

---

## 3. Screen / Page Inventory

| ID | Screen Name | Implemented in Arduino | Source | Notes |
|---|---|---|---|---|
| 0 | Sleep | Yes | `SCREEN.cpp` case 0 | No sprites; LED1 BLINK, LED2 OFF; button config 1 |
| 1 | QR Code / Device Unprovisioned | Yes | `SCREEN.cpp` case 1 | QR icon + device ID + passkey (Drawer 1 only) + skip button |
| 2 | Downloading Firmware | Yes | `SCREEN.cpp` case 2 | Progress blocks (step 3) + status text + progress bar |
| 3 | Firmware Download Complete | Yes | `SCREEN.cpp` case 3 | Progress blocks (step 3) + empty status + full progress bar |
| 4 | Ready | Yes | `SCREEN.cpp` case 4 | "READY" center text; buttons differ by drawer ID |
| 5 | WiFi Connect | Yes | `SCREEN.cpp` case 5 | Gear icon + connecting text + status text + progress bar. **Commented out in main.ino; replaced by Screen 13** |
| 6 | Check Updates | Yes | `SCREEN.cpp` case 6 | Progress blocks (step 1) + status text + blue progress bar |
| 7 | Running (cycle timer) | Yes | `SCREEN.cpp` case 7 | Timer ring + infinity icon + "CYCLING" label + counter (HH:MM:SS) |
| 8 | Waiting for BLE | Yes | `SCREEN.cpp` case 8 | Gear icon + waiting text + device ID + passkey (Drawer 1 only) |
| 9 | Provisioning In Progress | Yes | `SCREEN.cpp` case 9 | Progress blocks (step 0) + status text + progress bar; LEDs BLINK |
| 10 | Asset Downloading | Yes | `SCREEN.cpp` case 10 | Progress blocks (step 2) + status text + progress bar |
| 11 | Motor Running (Stop button) | Yes | `SCREEN.cpp` case 11 | Gear icon + pVar1 text + optional pVar2 + CANCEL button |
| 12 | Boot / Logo | Yes | `SCREEN.cpp` case 12 | Logo + device ID line + firmware version string |
| 13 | General Working (no buttons) | Yes | `SCREEN.cpp` case 13 | Gear icon + pVar1 text + optional pVar2; all buttons off |
| 14 | Welcome | Yes | `SCREEN.cpp` case 14 | Two text lines + CONTINUE button |
| 15 | Generic Error | Yes | `SCREEN.cpp` case 15 | WARNING.raw icon + "Error" text; all buttons off |
| 16 | Done (generic complete) | Yes | `SCREEN.cpp` case 16 | DONE.raw icon + pVar1 text + optional pVar2; all buttons off |
| 17 | Loading Settings | Yes | `SCREEN.cpp` case 17 | Progress blocks (step 3) only; all buttons off |
| 18 | Pump Running | Yes | `SCREEN.cpp` case 18 | Same layout as Screen 11 without CANCEL button; button config 14 (no actions) |
| 19 | Firmware Update Prompt | Yes | `SCREEN.cpp` case 19 | "Update Available" + "Install?" + countdown counter + progress bar + YES/LATER buttons |
| 20 | No WiFi / Reprovision Prompt | Yes | `SCREEN.cpp` case 20 | "Unable to connect" + "Update settings?" + counter + progress bar + YES/NO buttons |
| 21 | Factory Reset Confirmation | Yes | `SCREEN.cpp` case 21 | "Reset To Factory Settings" + confirm body + YES/NO buttons |
| 22 | BLE / Provisioning Failed | Yes | `SCREEN.cpp` case 22 | WARNING.raw icon + "PROVISIONING FAILED" text; all buttons off |
| 23 | (commented out) Auto-Update Check prompt | No | Code commented out | Disabled in current build |
| 24 | Drawer Open (no icon) | Yes | `SCREEN.cpp` case 24 | pVar1 large text + pVar2 sub-text; motor/pump buttons enabled |
| 25 | Cooling (cycle timer) | Yes | `SCREEN.cpp` case 25 | Timer ring + cooling.raw icon + "Cooling" label + counter |
| 26 | Self-Test Running | Yes | `SCREEN.cpp` case 26 | Gear icon + "Diagnostic" text + counter text + progress bar |
| 27 | Drawer Open (with WARNING icon) | Yes | `SCREEN.cpp` case 27 | WARNING.raw icon + pVar1 large text + pVar2 sub-text; LEDs BLINK |
| 28 | Self-Test OK | Yes | `SCREEN.cpp` case 28 | DONE.raw icon + success text |
| 29 | Self-Test Errors | Yes | `SCREEN.cpp` case 29 | WARNING.raw icon + 3 error text lines (pVar1/2/3) |
| 30 | STM32 Sensor Error (2033–2059) | Yes | `SCREEN.cpp` case 30 | WARNING.raw icon + pVar1 error code text (large font); buttons config 9 |
| 31 | Updating STM32 Firmware | Yes | `SCREEN.cpp` case 31 | Progress blocks (step 3) + status text + progress bar; LEDs BLINK |
| 32 | Bucket Jam | Yes | `SCREEN.cpp` case 32 | WARNING.raw icon + "Hold For 3 Sec After Object Removed" + "Jammed" text |
| 33 | Drawer 2 Waiting for Drawer 1 | Yes | `SCREEN.cpp` case 33 | PAUSE.raw icon + waiting text; all buttons off; LEDs ON |

---

## 4. Per-Page Detailed Design

### 4.1 Screen 0 — Sleep

#### 4.1.1 Purpose
Confirmed from code: display idle / sleep state. No visual content rendered.

#### 4.1.2 UI Elements
None. No sprites created.

#### 4.1.3 LED / Button State
- LED1: BLINK (2 = `BLINK` constant)
- LED2: OFF
- Button config ID 1 → BTN1 short or BTN2 short → Action 100 (go to IDLE)

#### 4.1.4 Unknown / Not Confirmed
- Whether backlight is turned off in this state — not implemented in `SCREEN.cpp` case 0.

---

### 4.2 Screen 4 — Ready

#### 4.2.1 Purpose
Confirmed: primary standby state when device is provisioned and online.

#### 4.2.2 UI Elements
| Element | ID | Type | Content | Position | Font |
|---|---|---|---|---|---|
| Main label | `"counter"` | `ASSET_TEXT` | `langMap["001"]` → "Ready" | x=0, y=`LINE5Y`(140), w=320 | `FONT4` (`FjallaOne_21`) |

#### 4.2.3 Layout
- Single centered text at y=140 spanning full width.

#### 4.2.4 LED / Button State
- LED1: OFF, LED2: OFF
- **Drawer 1**: Button config ID 16 — BTN1 short=Action 108 (STM32 btn1), BTN1 verylong=Action 109 (reboot), BTN2 short=Action 110 (motor), BTN2 long=Action 111 (pump test), BTN2 verylong=Action 102 (start BLE), BTN2 extended=Action 120 (factory reset confirm), BOTH verylong=Action 112 (self test), BOTH extended=Action 117 (stress test)
- **Drawer 2**: Button config ID 6 — BTN1 short=108, BTN1 verylong=109, BTN2 short=110, BTN2 long=111, BTN2 verylong=102, BOTH verylong=112, BOTH extended=117 (factory reset confirm)

#### 4.2.5 Data Binding
None — text is static from `langMap["001"]`.

---

### 4.3 Screen 1 — QR Code / Device Unprovisioned

#### 4.3.1 Purpose
Confirmed: shown when device has no provisioning credentials. Displays device ID as QR code (static PROGMEM) and short device ID string. Drawer 1 also shows BLE passkey.

#### 4.3.2 UI Elements
| Element | ID | Type | Content | Position | Notes |
|---|---|---|---|---|---|
| QR icon | `"0033"` | `ASSET_PROGMEM` | `ICON_QR` (100×100) | x=110, y=5+8=13 | White, no tint |
| Top text | `"0012"` | `ASSET_TEXT` | `langMap["033"]` | x=0, y=`LINE2Y-30+8`=138 | `FONT1`, center |
| Sub-text | `"0013"` | `ASSET_TEXT` | `langMap["032"]` | x=0, y=`LINE2Y-10+8`=158 | `FONT1`, center |
| Device ID | `"0035"` | `ASSET_TEXT` | `getShortDeviceId()` | x=0, y=`LINE2Y+13+8`=181 | `FONT2`, center, orange text |
| Passkey *(Drawer 1 only)* | `"0036"` | `ASSET_TEXT` | 6-digit passkey string | x=65, y=225 | `FONT2`, left |
| Skip button | `"0041"` | `ASSET_BUTTON` | `langMap["051"]` | x=200, y=205, 120×40 | `FONT2`, center |

#### 4.3.3 Layout
- QR code right-aligned (x=110 in 320px-wide screen → right half).
- Text lines stack center-justified below top area.
- Passkey and skip button at bottom.
- `offset_y = 8` applied to all Y coordinates.

#### 4.3.4 LED / Button State
- All buttons off by default; button config ID 10 also applied:
  - BTN2 click and short → Action 114 (skip provisioning)
  - BOTH extended → Action 117 (factory reset confirm)

#### 4.3.5 Dynamic Behavior
- `gBLE_PASSKEY` generated via `esp_random()` if not already set (Drawer 1 only).
- Passkey regenerated only if zero — not on each screen load.

#### 4.3.6 Unknown / Not Confirmed
- `langMap["033"]` and `langMap["032"]` text not in default fallback (026+).
- Exact size of QR icon (100×100 confirmed in `ASSETS.h`).
- QR code content is static PROGMEM — not dynamically generated from device ID.

---

### 4.4 Screen 8 — Waiting for BLE

#### 4.4.1 Purpose
Confirmed: BLE advertising is active, waiting for mobile app to connect.

#### 4.4.2 UI Elements
| Element | ID | Type | Content | Position |
|---|---|---|---|---|
| Gear icon | `"0021"` | `ASSET_PROGMEM` | `ICON_SETTING` (67×67) | x=`160-33`=127, y=`LINE10Y`=45 |
| Main text | `"0022"` | `ASSET_TEXT` | `langMap["028"]` | x=0, y=`LINE5Y`=140, `FONT2`, center |
| Device ID | `"0035"` | `ASSET_TEXT` | `getShortDeviceId()` | x=0, y=`LINE2Y+21`=181, `FONT2`, center, orange |
| Passkey *(Drawer 1 only)* | `"0036"` | `ASSET_TEXT` | 6-digit passkey | x=0, y=`LINE2Y+50`=210, `FONT2`, center |

#### 4.4.3 LED / Button State
- LED1: OFF, LED2: OFF
- Button config ID 3 → BTN1 short or BTN2 short → Action 101 (exit BLE)

#### 4.4.4 Unknown / Not Confirmed
- `langMap["028"]` text not in default fallback.

---

### 4.5 Screen 9 — Provisioning In Progress

#### 4.5.1 Purpose
Confirmed: shown while BLE provisioning data is being received and written to SPIFFS.

#### 4.5.2 UI Elements
| Element | ID | Type | Content | Position |
|---|---|---|---|---|
| Progress blocks widget | (composite) | 5 sprites (1055, 1051–1054, 1056) | Step 0 (STAT2) highlighted | y=100 for icons, y=85 for label |
| Status text | `"status"` | `ASSET_TEXT` | `" "` (populated dynamically) | x=0, y=`LINE3Y`=216 |
| Progress bar | `"progressbar"` | `ASSET_PROGRESSBAR` | initial=0, max=100 | x=0, y=230, w=330, h=6 |

#### 4.5.3 LED / Button State
- LED1: BLINK, LED2: BLINK
- All buttons off

#### 4.5.4 Dynamic Updates
- `status` text updated via `SPRITE_updateText("status", ...)` during provisioning.
- Progress bar updated via `updateProgressBar("progressbar", 100, current)`.

#### 4.5.5 Progress Blocks Widget Detail
Four 68×67 icons at y=100, x={18, 90, 162, 234}, plus label at y=85 and orange highlight bar (68×4) at y=175 under active step:
- Position 0 → `ICON_STAT2` (provisioning icon highlighted)
- Position 1 → `ICON_STAT4` (search)
- Position 2 → `ICON_STAT1` (download)
- Position 3 → `ICON_STAT3` (configure)

---

### 4.6 Screen 12 — Boot / Logo

#### 4.6.1 Purpose
Confirmed: boot splash screen shown after hardware initialization.

#### 4.6.2 UI Elements
| Element | ID | Type | Content | Position |
|---|---|---|---|---|
| Logo | `"logo"` | `ASSET_PROGMEM` | `ICON_LOGO` (212×49) | x=`160-106`=54, y=`LINE12Y`=85 |
| Device ID line | `"0036"` | `ASSET_TEXT` | `pVar1` + `" "` + `langMap["060"]` | x=0, y=200, `FONT2`, center, electric green |
| Firmware version | `"0035"` | `ASSET_TEXT` | `"FIRMWARE: " + config::DEVICE::VERSION` | x=0, y=225, `FONT1`, center, white |

#### 4.6.3 Data Binding
- `pVar1` = Drawer-specific cycle count: `String(myhardware.cycleCount)` for Drawer 1 or `String(myhardware.cycleCount2)` for Drawer 2. (Confirmed: `main.ino` lines 267/269).
- Firmware version = `"1.0.60"` (from `config::DEVICE::VERSION`).

#### 4.6.4 LED / Button State
- LED1: OFF, LED2: OFF
- All buttons off

---

### 4.7 Screen 14 — Welcome

#### 4.7.1 Purpose
Confirmed: first-run welcome message after provisioning complete. Requires user to press CONTINUE button.

#### 4.7.2 UI Elements
| Element | ID | Type | Content | Position |
|---|---|---|---|---|
| Text line 1 | `"0025"` | `ASSET_TEXT` | `langMap["063"]` | x=0, y=`LINE7Y+70`=105, `FONT2`, center |
| Text line 2 | `"0035"` | `ASSET_TEXT` | `langMap["064"]` | x=0, y=`LINE7Y+100`=135, `FONT2`, center |
| CONTINUE button | `"0041"` | `ASSET_BUTTON` | `langMap["066"]` | x=200, y=205, 120×40, `FONT2`, left-justified in button |

#### 4.7.3 LED / Button State
- LED1: OFF, LED2: OFF
- Button config ID 13 → BTN2 short → Action 118 (welcome acknowledged → sets `gTriggerCMD = "BRIDGE_WELCOMECONTINUE"`, goes to `GOTO_SKIP_CHECKUPLOAD_CHECK`)

#### 4.7.4 Unknown / Not Confirmed
- `langMap["063"]`, `"064"`, `"066"]` text not in default fallback.

---

### 4.8 Screen 7 — Running (Cycle Timer)

#### 4.8.1 Purpose
Confirmed: shown during active food-cycling operation. Displays animated segmented ring and elapsed/remaining time.

#### 4.8.2 UI Elements
| Element | ID | Type | Content | Position |
|---|---|---|---|---|
| Timer ring | `"timer_ring"` | `ASSET_VECTOR` | 4-segment ring, initial color: BLUE | x=69, y=34, 184×184 |
| Timer icon | `"icon"` | `ASSET_ICON` | `/assets/infinity.raw` | x=149, y=69, 25×12 |
| Status label | `"status"` | `ASSET_TEXT` | `langMap["037"]` (???—not in fallback) | x=100, y=`LINE6Y`=164, w=80, `FONT2`, center |
| Counter | `"counter"` | `ASSET_TEXT` | `pVar1` (timer string) | x=0, y=`LINE5Y`=140, w=320, `FONT4`, center |

#### 4.8.3 Timer Ring Detail
- `ASSET_VECTOR` rendered by `renderTIMERBKG()` via `drawSegmentedCircle()`.
- 4 segments, gap degrees: not confirmed from source (function parameters not visible in this excerpt).
- Segments controlled by `setTimerRingBlinking(phase, color0–3)`.
- Phase 0 = all dark grey. Phase 1–4 progressively illuminate segments.
- Segment color mapping: `segmentMap[4] = {3,0,1,2}` (non-sequential order).

#### 4.8.4 Data Binding
- `pVar1` = timer string, e.g. `"00:00:00"` format. Formatted externally and passed at `load_screen` call.
- Timer string updated: `SPRITE_updateText("counter", newTimerString)` called from `main.ino` loop.

#### 4.8.5 LED / Button State
- LED1: ON, LED2: OFF
- Button config ID 2: BTN1 short=Action 108 (STM32 btn1 click), BTN1 verylong=Action 109 (reboot).

#### 4.8.6 Unknown / Not Confirmed
- `langMap["037"]` text = unknown (not in default fallback).
- `drawSegmentedCircle` gap degrees and animation speed.

---

### 4.9 Screen 25 — Cooling

#### 4.9.1 Purpose
Confirmed: shown during cooling phase after food processing.

#### 4.9.2 UI Elements
Same structure as Screen 7 except:
- Timer icon: `/assets/cooling.raw` at x=151, y=67, 20×20
- Status label: `langMap["004"]` → **"Cooling"** (confirmed in default fallback)

#### 4.9.3 LED / Button State
Identical to Screen 7 (LED1 ON, LED2 OFF, button config ID 2).

---

### 4.10 Screen 2 — Downloading Firmware

#### 4.10.1 Purpose
Confirmed: OTA firmware download in progress.

#### 4.10.2 UI Elements
| Element | Notes |
|---|---|
| Progress blocks widget | Step 3 (`ICON_STAT3`) highlighted; label = `langMap["022"]` |
| Status text `"status"` | `langMap["039"]`, center, `FONT1`, y=216 |
| Progress bar `"progressbar"` | x=0, y=230, w=330, h=6, white fill |

#### 4.10.3 LED / Button State
- LED1: BLINK, LED2: BLINK
- All buttons off

---

### 4.11 Screen 10 — Asset Downloading

#### 4.11.1 Purpose
Confirmed: downloading display asset files from S3.

#### 4.11.2 UI Elements
Same structure as Screen 2 except:
- Progress blocks label = `langMap["026"]`
- Step 2 (`ICON_STAT1`) highlighted
- LED1: OFF, LED2: OFF

---

### 4.12 Screen 31 — Updating STM32 Firmware

#### 4.12.1 Purpose
Confirmed: transferring firmware binary to STM32 MCU.

#### 4.12.2 UI Elements
Same structure as Screen 2 except:
- Progress blocks label = `langMap["007"]` → **"Hold To Clear Jam"** *(Note: this key's default-fallback text appears semantically incorrect for this context — likely correct text comes from the SPIFFS lang file)*
- Step 3 (`ICON_STAT3`) highlighted
- LED1: BLINK, LED2: BLINK

---

### 4.13 Screen 6 — Check Updates

#### 4.13.1 Purpose
Confirmed: polling version server to check for available firmware updates.

#### 4.13.2 UI Elements
| Element | Notes |
|---|---|
| Progress blocks widget | Step 1 (`ICON_STAT4`) highlighted; label = `langMap["029"]` |
| Status text `"status"` | `" "`, center, `FONT1` |
| Progress bar | x=0, y=230, w=330, h=6, **BLUE** fill (not white) |

#### 4.13.3 LED / Button State
- LED1: OFF, LED2: OFF
- Button config ID 11 → BTN2 short → Action 115 (skip update check → `GOTO_SKIP_VERSION_CHECK`)

---

### 4.14 Screen 11 — Motor Running (Stop Button)

#### 4.14.1 Purpose
Confirmed: manual motor control state with CANCEL button available.

#### 4.14.2 UI Elements
| Element | ID | Content | Position — notes |
|---|---|---|---|
| Gear icon | `"0024"` | `ICON_SETTING` | y adapts: if `pVar2` empty → `LINE7Y+25`=60; else `LINE10Y`=45 |
| Primary text | `"0025"` | `pVar1` | y adapts same logic |
| Secondary text | `"0035"` | `pVar2` | y=`LINE5Y+25`=165, only shown |
| CANCEL button | `"0041"` | `langMap["065"]` | x=200, y=205, 120×40 |

#### 4.14.3 LED / Button State
- LED1: ON, LED2: ON
- Button config ID 12 → BTN2 short → Action 110 (trigger motor / toggle)

#### 4.14.4 Data Binding
- Called with: `load_screen(11, myui, langMap["016"], emptyS, emptyS)` — pVar1 = `langMap["016"]` = **"Bucket Required, Insert Bucket"** (confirmed).

---

### 4.15 Screen 13 — General Working (No Buttons)

#### 4.15.1 Purpose
Confirmed: reusable generic template for any working/loading state requiring no user interaction.

#### 4.15.2 UI Elements
Same structure as Screen 11 but without the CANCEL button. All buttons off.

#### 4.15.3 Known instance calls from `main.ino`
| Call site | pVar1 content |
|---|---|
| `main.ino:831` | `""` (WiFi update loading) |
| `main.ino:1264` | `langMap["041"]` (restarting screen) |
| `main.ino:1561` | `langMap["050"]` (loading...) |
| `main.ino:1579` | `langMap["047"]` (connecting to services) |
| `main.ino:1693` | `langMap["050"]` (update WiFi, loading) |

---

### 4.16 Screen 19 — Firmware Update Prompt

#### 4.16.1 Purpose
Confirmed: asks user whether to install available firmware update. Has 30-second auto-countdown shown on screen.

#### 4.16.2 UI Elements
| Element | ID | Content | Position |
|---|---|---|---|
| Title | `"0023"` | `langMap["048"]` | x=0, y=`LINE12Y`=85, `FONT2`, center |
| Body | `"0024"` | `langMap["049"]` | x=0, y=110, `FONT2`, center |
| Countdown | `"counter"` | `"30"` (initial, updated externally) | x=0, y=`LINE3Y-45`=171, `FONT2`, center |
| Progress bar | `"progressbar"` | max=100, fill=white | x=0, y=180, w=330, h=6 |
| YES button | `"0041"` | `langMap["045"]` | x=200, y=205, 120×40, left |
| LATER button | `"0042"` | `langMap["051"]` | x=0, y=205, 120×40, right |

#### 4.16.3 LED / Button State
- LED1: OFF, LED2: OFF
- Button config ID 4: BTN1 short=Action 104 (go idle/later), BTN2 short=Action 105 (start firmware download)

#### 4.16.4 Dynamic Updates
- `"counter"` text updated via `SPRITE_updateText("counter", ...)` from `main.ino` loop countdown.
- Progress bar updated accordingly.

---

### 4.17 Screen 20 — No WiFi / Reprovision Prompt

#### 4.17.1 Purpose
Confirmed: shown when WiFi test fails after provisioning. Offers re-provisioning or restart.

#### 4.17.2 UI Elements
Same layout as Screen 19 except:
- Title: `langMap["056"]` ("Unable to connect to WiFi" — text from SPIFFS lang file)
- Body: `langMap["057"]` ("Update Settings In App?" — text from SPIFFS lang file)
- Counter: initial `" "` instead of `"30"`
- Button config ID 5: BTN1 short=Action 107 (restart), BTN2 short=Action 102 (start BLE)

---

### 4.18 Screen 21 — Factory Reset Confirmation

#### 4.18.1 Purpose
Confirmed: two-step factory reset requiring explicit button confirmation.

#### 4.18.2 UI Elements
| Element | ID | Content |
|---|---|---|
| Title | `"0023"` | `langMap["011"]` → **"Reset To Factory Settings"** (confirmed) |
| Body | `"0024"` | `langMap["068"]` (from SPIFFS lang file) |
| YES button | `"0041"` | `langMap["045"]` (from SPIFFS) |
| NO button | `"0042"` | `langMap["046"]` (from SPIFFS) |

#### 4.18.3 LED / Button State
- Button config ID 15: BTN1 short=Action 100 (return to idle), BTN2 short=Action 119 (confirm factory reset → `gTriggerCMD = "BRIDGE_FACTORYRESET"`)

---

### 4.19 Screen 26 — Self-Test Running

#### 4.19.1 Purpose
Confirmed: diagnostic self-test initiated by STM32 command or button combo.

#### 4.19.2 UI Elements
| Element | ID | Content |
|---|---|---|
| Gear icon | `"0030"` | `ICON_SETTING` (67×67) at x=127, y=`LINE10Y`=45 |
| Text | `"0023"` | `langMap["010"]` → **"Diagnostic"** (confirmed) |
| Counter text | `"counter"` | `" "` (updated externally) |
| Progress bar | `"progressbar"` | white, x=0, y=230, w=330, h=6 |

#### 4.19.3 LED / Button State
- LED1: OFF, LED2: OFF
- All buttons off

---

### 4.20 Screen 28 — Self-Test OK

#### 4.20.1 UI Elements
- `DONE.raw` icon at x=127, y=`LINE7Y+25`=60
- Text: `langMap["015"]` → **"Clear Jam, Remove Object"** (confirmed in default fallback — note this key's fallback text may not match intended self-test OK message; correct text from SPIFFS lang file)

#### 4.20.2 Button State
Config ID 8: BTN1 long or verylong → Action 113 (self-test reboot)

---

### 4.21 Screen 29 — Self-Test Errors

#### 4.21.1 UI Elements
- `WARNING.raw` icon at y=`LINE7Y`=35
- Three text lines: `"errors1"`, `"errors2"`, `"errors3"` — pVar1/2/3 formatted by `SCREEN::formatAndShowSelfTestErrors()`

#### 4.21.2 Button State
Config ID 8 (same as Screen 28).

---

### 4.22 Screen 30 — STM32 Sensor Error

#### 4.22.1 Purpose
Confirmed: sensor or hardware error codes 2033–2059 from STM32.

#### 4.22.2 UI Elements
- `WARNING.raw` icon centered at y=`LINE7Y+25`=60
- Error code text `"error1"` in `FONT4` (large) at y=`LINE7Y+135`=170 — pVar1 = formatted error string

#### 4.22.3 Button State
Config ID 9: BTN1 verylong=Action 109 (reboot), BTN2 short=Action 110 (motor), BTN2 long=Action 111 (pump test)

---

### 4.23 Screen 32 — Bucket Jam

#### 4.23.1 Purpose
Confirmed: bucket jam detected by STM32 (`MOTORJAM_ERR = 0x2031`).

#### 4.23.2 UI Elements
- `WARNING.raw` icon at y=`LINE7Y`=35
- `"error1"`: `langMap["025"]` → **"Hold For 3 Sec After Object Removed"** (confirmed)
- `"error2"`: `langMap["006"]` → **"Jammed"** (confirmed)

#### 4.23.3 Button State
Config ID 7: BTN1 short=108, BTN1 verylong=109, BTN2 short=110, BTN2 long=111

---

### 4.24 Screen 33 — Drawer 2 Waiting for Drawer 1 Provisioning

#### 4.24.1 Purpose
Confirmed: Drawer 2 waits idle while Drawer 1 completes BLE provisioning.

#### 4.24.2 UI Elements
- `PAUSE.raw` icon at x=127, y=`LINE7Y+25`=60 (67×67)
- Text `"0023"`: `langMap["071"]` (from SPIFFS lang file)

#### 4.24.3 LED / Button State
- LED1: ON, LED2: ON
- All buttons off

---

### 4.25 Screen 24 — Drawer Open (No Icon)

#### 4.25.1 Purpose
Confirmed from `SCREEN.cpp` case 24 comment and `main.ino` dispatcher: shown when STM32 reports `Drawer_Pause_State` (0x2016) **and** bucket/heater temperature is ≤ 58.0 tenths-°C (i.e. `isAnyBucketTempAbove56()` returns false). Displays drawer-open and paused state text with no warning icon. Motor and pump controls remain available to user.

#### 4.25.2 State Machine Entry
Reached exclusively via `GOTO_STM32_ALERT` → `case config::TX_CMD::Drawer_Pause_State:` in `main.ino`:

```
Drawer_Pause_State + isAnyBucketTempAbove56() == false
    → load_screen(24, myui, langMap["020"], langMap["002"], emptyS)
    → gDeviceStatus = UNDER_STM32_CONTROL
```

Confirmed single call site (`main.ino` line 1415):
```cpp
mydisplay.load_screen(24, myui, mydisplay.langMap["020"], mydisplay.langMap["002"], emptyS);
// comment: DRAWER OPEN | PAUSED
```

#### 4.25.3 UI Elements

| Element | Sprite ID | Type | Content | x | y | Size | Font / Color |
|---|---|---|---|---|---|---|---|
| Large text (pVar1) | `"error1"` | `ASSET_TEXT` | `langMap["020"]` → **"Drawer Open"** | 0 | `LINE8Y`=150 | w=320, h=`FONT4H`=20 | `FONT4` (`FjallaOne_21`), WHITE, CENTER |
| Sub-text (pVar2) | `"counter"` | `ASSET_TEXT` | `langMap["002"]` → **"Paused"** | 0 | `LINE9Y`=178 | w=320, h=`FONT2H`=40 | `FONT2` (`Roboto_10`), WHITE, CENTER |

**No icon** — confirmed from code comment "Drawer Open - NO ICON" and absence of any `ASSET_ICON` / `ASSET_PROGMEM` sprite creation.

**Total content sprites:** 2. Header sprites in addition (up to 6). Well within `MAX_SPRITES = 20`.

#### 4.25.4 pVar Argument Mapping (confirmed)

| pVar | Value passed | langMap key | Default fallback text |
|---|---|---|---|
| `pVar1` | `langMap["020"]` | `"020"` | **"Drawer Open"** (confirmed in `config.cpp`) |
| `pVar2` | `langMap["002"]` | `"002"` | **"Paused"** (confirmed in `config.cpp`) |
| `pVar3` | `emptyS` | — | Not used |

Both strings confirmed in the default fallback (`config.cpp` lines 8, 11).

#### 4.25.5 Layout

```
y=150  [      langMap["020"] — "Drawer Open"  FONT4 FjallaOne_21, centered      ]

y=178  [           langMap["002"] — "Paused"  FONT2 Roboto_10, centered         ]
```

- No icon above text (unlike Screen 27).
- Both texts span full display width (w=320), center-justified.
- `LINE8Y`=150 and `LINE9Y`=178 — gap of 28px between baselines.

#### 4.25.6 LED / Button State
- LED1: OFF (`setLedDefaults(OFF, OFF)`)
- LED2: OFF
- Button config ID 17: BTN2 short → Action 110 (trigger motor / `STM32_BTN2CLICK`), BTN2 long → Action 111 (test water pump / `STM32_TEST_WTR_PUMP`). All other detection slots = 0.

#### 4.25.7 Dynamic Behavior in `UNDER_STM32_CONTROL` Loop
Confirmed from `main.ino` line 696–697:
```cpp
} else if (myhardware.my_uipageid == config::TX_CMD::Drawer_Pause_State) {
    mydisplay.SPRITE_makeBlink("counter", 1);
}
```
- **`"counter"` sprite blinks at 1-second period** (alternates between `TFT_WHITE` and `TFT_LIGHTGREY`).
- `SPRITE_makeBlink()` is called every loop iteration in `UNDER_STM32_CONTROL`; it updates the color only when the phase changes — no redundant redraws.
- This applies when temperature is **not** above threshold (cool drawer-pause). When temperature is above threshold, Screen 27 is shown instead (see §4.26).

#### 4.25.8 Header Updates
- `SPRITE_updateHeader()` is called every loop iteration from `main.ino` line 407–410.
- `drawer` icon: `myhardware.isDrawerOpen()` returns `true` for `Drawer_Pause_State` (confirmed: `HARDWARE.cpp` line 1258–1259) → orange drawer icon shown in header.
- `hot` icon: `isAnyBucketTempAbove56()` returns `false` (that is the condition for this screen) → hot icon NOT shown.

#### 4.25.9 Transition Out
- Screen exits when STM32 sends a new page ID (e.g., `Standby` = cycle complete, `Running_State` = resume).
- `checkStateTransitionsForDrawer()` buzzes once on Drawer_Pause_State → Standby transition (confirmed `HARDWARE.cpp` line 1274).

#### 4.25.10 Unknown / Not Confirmed
| Item | Status |
|---|---|
| `langMap["020"]` from SPIFFS lang file | **Confirmed** — default fallback = "Drawer Open" |
| `langMap["002"]` from SPIFFS lang file | **Confirmed** — default fallback = "Paused" |
| Whether `"counter"` blink color `TFT_LIGHTGREY` is visually distinguishable from `TFT_WHITE` on this display | ❓ Hardware-dependent |
| Any additional text variant for pVar1/pVar2 at this call site | Not applicable — single call site with fixed args |

---

### 4.26 Screen 27 — Drawer Open (With WARNING Icon)

#### 4.26.1 Purpose
Confirmed from `SCREEN.cpp` case 27 comment and `main.ino` dispatcher: shown when STM32 reports **either** `Drawer_Open_State` (0x2015) **or** `Drawer_Pause_State` (0x2016) when bucket/heater temperature **exceeds 58.0 tenths-°C** (`isAnyBucketTempAbove56()` returns true). Adds a WARNING icon and LED blink to reinforce the hot-surface hazard.

#### 4.26.2 State Machine Entry
Three confirmed call sites (`main.ino` lines 1404, 1406, 1413):

| STM32 state | Hot condition | pVar1 | pVar2 | Comment |
|---|---|---|---|---|
| `Drawer_Open_State` | `isAnyBucketTempAbove56() == true` | `langMap["025"]` | `langMap["020"]` | CAUTION HOT \| DRAWER OPEN \| ICON |
| `Drawer_Open_State` | `isAnyBucketTempAbove56() == false` | `langMap["020"]` | `emptyS` | DRAWER OPEN (no hot) — **only shows WARNING icon + text without pVar2** |
| `Drawer_Pause_State` | `isAnyBucketTempAbove56() == true` | `langMap["025"]` | `langMap["002"]` | CAUTION HOT \| PAUSED \| ICON |

> **Note:** Screen 27 is used for `Drawer_Open_State` **regardless** of temperature — the icon is always shown. For `Drawer_Pause_State`, Screen 27 is only used when hot; Screen 24 handles the cool case.

#### 4.26.3 UI Elements

| Element | Sprite ID | Type | Content | x | y | Size | Font / Color |
|---|---|---|---|---|---|---|---|
| WARNING icon | `"alert_icon"` | `ASSET_ICON` | `/assets/WARNING.raw` | 127 | `LINE7Y`=35 | 67×67 | WHITE |
| Large text (pVar1) | `"error1"` | `ASSET_TEXT` | see §4.26.2 table | 0 | `LINE8Y`=150 | w=320, h=`FONT4H`=20 | `FONT4` (`FjallaOne_21`), WHITE, CENTER |
| Sub-text (pVar2) | `"error2"` | `ASSET_TEXT` | see §4.26.2 table (empty if `Drawer_Open_State` + cold) | 0 | `LINE9Y`=178 | w=320, h=`FONT2H`=40 | `FONT2` (`Roboto_10`), WHITE, CENTER |

**Key differences from Screen 24:**
- WARNING icon present (`"alert_icon"` at x=127, y=35).
- Sprite IDs differ: Screen 24 uses `"counter"` for sub-text; Screen 27 uses `"error2"`.
- LEDs BLINK (vs OFF in Screen 24).

#### 4.26.4 pVar Argument Mapping (confirmed)

| Scenario | pVar1 key | pVar1 confirmed text | pVar2 key | pVar2 confirmed text |
|---|---|---|---|---|
| Hot + Drawer Open | `"025"` | **"Hold For 3 Sec After Object Removed"** | `"020"` | **"Drawer Open"** |
| Cold + Drawer Open | `"020"` | **"Drawer Open"** | `emptyS` | *(empty string)* |
| Hot + Paused | `"025"` | **"Hold For 3 Sec After Object Removed"** | `"002"` | **"Paused"** |

All three strings confirmed in default fallback (`config.cpp`).

#### 4.26.5 Layout

```
y=35   [          /assets/WARNING.raw  67×67  x=127           ]

y=150  [             pVar1  FONT4 FjallaOne_21, centered       ]

y=178  [             pVar2  FONT2 Roboto_10, centered          ]
         (empty string if cold Drawer_Open_State)
```

- WARNING icon is centre-of-screen horizontally: x=127 (320÷2 − 67÷2 = 126.5 → 127).
- Text layout identical to Screen 24 but with icon above.

#### 4.26.6 LED / Button State
- LED1: BLINK (`setLedDefaults(BLINK, BLINK)`)
- LED2: BLINK
- Button config ID 17 (same as Screen 24): BTN2 short → Action 110 (motor), BTN2 long → Action 111 (pump test). All other detection slots = 0.

#### 4.26.7 Dynamic Behavior in `UNDER_STM32_CONTROL` Loop

**Drawer_Pause_State + hot** (`main.ino` line 694–695):
```cpp
mydisplay.SPRITE_toggleSprites("alert_icon", "alert_text",
    "/assets/POWER.raw", "/assets/WARNING.raw", "020", "020", 2);
```
- `"alert_icon"` toggles between `/assets/POWER.raw` and `/assets/WARNING.raw` every 2 seconds.
- `"alert_text"` text updates between `langMap["020"]` and `langMap["020"]` every 2 seconds — **both phases use key "020"** so the text itself does not change, only the icon alternates.
- Period = 2 seconds (confirmed: last argument = 2 in `SPRITE_toggleSprites` call).

> **Note:** `"alert_text"` sprite ID is used by `SPRITE_toggleSprites` but **Screen 27's load_screen creates `"error2"` and `"error1"`, not `"alert_text"`**. `SPRITE_find("alert_text")` will return -1 for Screen 27 — only the icon toggle applies. The text toggle silently no-ops. This is confirmed behaviour, not a bug to fix.

**Drawer_Open_State + hot** (`main.ino` line 709–710):
```cpp
mydisplay.SPRITE_toggleSprites("alert_icon", "alert_text",
    "/assets/POWER.raw", "/assets/WARNING.raw", "020", "020", 2);
```
- Identical call — same toggle behaviour as Drawer_Pause_State hot path.

**`/assets/POWER.raw`** — additional SPIFFS asset referenced only in these two live calls. **Not listed in the spec's §2.2 asset table** — must be added.

#### 4.26.8 Header Updates
- `drawer` icon: `isDrawerOpen()` returns `true` for both `Drawer_Open_State` and `Drawer_Pause_State` → orange drawer icon shown in header.
- `hot` icon: `isAnyBucketTempAbove56()` returns `true` in the hot variant call sites → orange hot icon shown in header. In the cold `Drawer_Open_State` call site it returns `false` → hot icon not shown.

#### 4.26.9 Transition Out
- Same as Screen 24: exits when STM32 sends a new page ID.
- `checkStateTransitionsForDrawer()` buzzes on state change to Standby (confirmed).

#### 4.26.10 Unknown / Not Confirmed
| Item | Status |
|---|---|
| `/assets/POWER.raw` file dimensions | ❓ Used in `SPRITE_toggleSprites` as `ASSET_ICON`; no explicit size found — expected 67×67 by analogy with other icon assets but unconfirmed |
| Whether `"alert_text"` sprite being absent causes any log/error output | ❓ `SPRITE_toggleSprites` silently returns if sprite not found (confirmed: `SPRITE_find` returns -1, function checks `imgIdx >= 0`) |
| Sub-text rendered when `pVar2 == emptyS` | Confirmed: `ASSET_TEXT` with `source = ""` renders blank — no visual artifact |

---

### 4.27 Screen 17 — Loading Settings

#### 4.27.1 Purpose
Confirmed from `SCREEN.cpp` case 17 comment and `DeviceStatus` enum (`config.h` line 65): displayed while device settings are being loaded from SPIFFS (WiFi credentials, AWS credentials, language map). Acts as a transient blocking screen — no user interaction is possible while it is shown.

#### 4.27.2 State Machine Entry
- `DeviceStatus::LOADINGSETTINGS` is defined in `config.h` and handled in `main.ino` `case LOADINGSETTINGS:`.
- The `case LOADINGSETTINGS:` handler calls `mydisplay.load_screen(17, myui,"","","")` then `break` — no further action in the case body.
- **No explicit `gDeviceStatus = LOADINGSETTINGS` assignment found anywhere in the reviewed source.** The state exists in the enum and is guarded against STM32 interrupts (`main.ino` line 2160), but no code path in `main.ino` actively sets it.
- `SETTINGS_load()` itself is called from multiple sites (`main.ino` lines 311, 738, 874, 1347, 1516, 1569, 1585) without first setting `gDeviceStatus = LOADINGSETTINGS`. In all confirmed call sites the screen is NOT set to 17 before `SETTINGS_load()` — Screen 13 is used instead.
- **Conclusion: `LOADINGSETTINGS` / Screen 17 is a declared but effectively unreachable state in the current build.** Screen 13 (General Working) is the active substitute for all loading-settings UI instances.

#### 4.27.3 UI Elements

Screen 17 creates **no sprites directly**. All visual content comes exclusively from `SPRITE_drawProgressBlocks(langMap["042"], 3)`.

**`SPRITE_drawProgressBlocks` creates 6 sprites internally (pPos = 3):**

| Sprite ID | Type | Content | x | y | Size | Color / Font | Notes |
|---|---|---|---|---|---|---|---|
| `"1055"` | `ASSET_TEXT` | `langMap["042"]` | 0 | 85 (`LINE12Y`) | w=320, h=`FONT2H`=40 | White, `FONT2` (`Roboto_10`), CENTER | Title label — text unknown (SPIFFS lang file only) |
| `"1051"` | `ASSET_PROGMEM` | `ICON_STAT2` | 18 | 100 | 68×67 | White, no tint | Step 0 icon — provisioning |
| `"1052"` | `ASSET_PROGMEM` | `ICON_STAT4` | 90 | 100 | 68×67 | White, no tint | Step 1 icon — search |
| `"1053"` | `ASSET_PROGMEM` | `ICON_STAT1` | 162 | 100 | 68×67 | White, no tint | Step 2 icon — download |
| `"1054"` | `ASSET_PROGMEM` | `ICON_STAT3` | 234 | 100 | 68×67 | White, no tint | Step 3 icon — configure **(active step)** |
| `"1056"` | `ASSET_BUTTON` | `""` (empty) | 234 | 175 | 68×4 | `ORANGE` fill | Orange highlight bar under active step icon |

**Total sprite count:** 6 content sprites + up to 6 persistent header sprites = 12 maximum. Within `MAX_SPRITES = 20`.

#### 4.27.4 Layout

```
y=85   [       langMap["042"] — centered, FONT2, white       ]

y=100  [STAT2 68x67][STAT4 68x67][STAT1 68x67][STAT3 68x67]
        x=18         x=90         x=162        x=234

y=175                                          [████ 68x4 ORANGE]
                                                x=234  ← step 3 highlight bar
```

- 4 step icons horizontally at fixed x positions: 18, 90, 162, 234 (spacing = 72px, icon width = 68px, gap = 4px).
- Orange highlight bar (68×4) sits at y=175, directly below the step 3 icon (y=100+67+8=175).
- No progress bar — confirmed. Screen 17 is the only progress-blocks screen that **omits** `addProgressBar` and the `"status"` text sprite.
- No `"status"` sprite — confirmed. The `"status"` text asset present in screens 2, 9, 10, 31 is absent here.

#### 4.27.5 Active Step Meaning

Step 3 (rightmost position, `ICON_STAT3`) is the **configure / finalize** step in the progress blocks metaphor:

| Position | Icon | Step meaning |
|---|---|---|
| 0 (x=18) | `ICON_STAT2` | Provisioning / BLE |
| 1 (x=90) | `ICON_STAT4` | Search / check |
| 2 (x=162) | `ICON_STAT1` | Download |
| **3 (x=234)** | **`ICON_STAT3`** | **Configure / apply settings ← active** |

Screen 17 highlights step 3, indicating "configure" phase — consistent with applying loaded settings before going online.

#### 4.27.6 LED / Button State
- LED1: OFF (`ledDefaultState[0] = 0`)
- LED2: OFF (`ledDefaultState[1] = 0`)
- All button detection disabled: `configAllButtonsOff(myui)` — all `detectionEnabled[]` flags set false, all `buttonActionID[]` set to 0.
- No button action is possible while screen 17 is shown.

#### 4.27.7 Dynamic Behavior
- **None confirmed.** No `SPRITE_updateText("status", ...)` call found for screen 17.
- No progress bar to update.
- Screen is static for its entire display duration.
- No timer, countdown, or animation confirmed.

#### 4.27.8 Header State at Entry
- Header icons reflect the last call to `SPRITE_updateHeader()`. Screen 17's `case` block does not call `SPRITE_updateHeader()` — header state at entry is whatever was set by the preceding screen.
- Header sprites are not cleared by `SPRITE_clearAll()` so they persist visually regardless.

#### 4.27.9 `SETTINGS_load()` — What It Does (Called Before/After This Screen)
Confirmed from `main.ino` lines 874–917:
1. `spiff.getWifiCredentials(wifiCreds)` → `wifi.setCredentials(ssid, password)`
2. `spiff.getAWSCredentials(awsCreds)` → `myaws.AWS_initialize(endpoint, clientId, rootCA, cert, key, bucket, language, mac)`
3. `gSYSTEM_LANG = spiff.getSystemDetailAttribute(SPIFF_Manager::LANG)`
4. `spiff.loadLanguageMap("/assets/" + gSYSTEM_LANG + ".json", mydisplay.langMap)` — reloads all language strings including keys 026+

**This is a side effect of `SETTINGS_load()` relevant to Screen 17:** langMap is updated during or immediately after the state in which this screen would appear, meaning `langMap["042"]` label text is loaded from the same SPIFFS operation this screen is meant to represent.

#### 4.27.10 Unknown / Not Confirmed
| Item | Status |
|---|---|
| `langMap["042"]` display text | ❓ Unknown — not in default fallback (`config.cpp` only defines keys 001–025) |
| Whether `gDeviceStatus = LOADINGSETTINGS` is set anywhere | ❓ No assignment found in any reviewed source file |
| Whether Screen 17 is ever actually rendered at runtime | ❓ Not confirmed — `LOADINGSETTINGS` state appears unreachable based on reviewed code |
| Header icon state when screen 17 is entered | ❓ Depends on preceding screen; not deterministic |

---

## 5. Header / Status Bar

Always visible. Never cleared by `SPRITE_clearAll()`. All header sprites use `HEADER` asset type.

| Icon | Sprite ID | Position (x, y) | Size | Condition |
|---|---|---|---|---|
| WiFi connected | `"wifi"` | x=10, y=10 | 33×33 | `wifi=true AND aws=false` |
| WiFi disconnected | `"nowifi"` | x=10, y=10 | 33×33 | `wifi=false AND aws=false` |
| AWS connected | `"aws"` | x=10, y=10 | 33×33 | `aws=true` (overrides WiFi) |
| BLE active | `"ble"` | x=51, y=10 | 33×33 | `ble=true` |
| Drawer active | `"drawer"` | x=`tft.width()-90`, y=10 | 33×33 | `drawer=true`; tinted `ORANGEBRIGHT` (blend=255) |
| Temperature hot | `"temp"` | x=`tft.width()-45`, y=10 | 37×33 | `hot=true`; tinted `ORANGEBRIGHT` (blend=255) |

**Priority rule (confirmed):** `aws` overrides `wifi`; when `aws=true`, `wifi` and `nowifi` sprites are removed. BLE shown **independently alongside** connection icon.

---

## 6. Shared Components

### 6.1 Progress Blocks Widget (`SPRITE_drawProgressBlocks`)
- Used by: screens 9, 2, 3, 10, 31, 6, 17
- 4 fixed icon slots at y=100, x={18, 90, 162, 234}, each 68×67
- Orange highlight bar (68×4) at y=175 beneath active step (`pPos` index 0–3)
- Title label at x=0, y=85 (`LINE12Y`), `FONT2`, center, white

### 6.2 Progress Bar (`ASSET_PROGRESSBAR`)
- Used by: screens 9, 2, 3, 10, 31, 6, 5, 19, 20, 26
- Standard position: x=0, y=230, w=330, h=6
- Exception in decision screens (19, 20): y=180
- Color auto-transitions: >80% → orange, >40% → purple, >20% → blue; initial white
- `"progressbar"` is the conventional sprite ID

### 6.3 Button Pair Pattern (YES / NO / CANCEL)
- Confirmed in screens: 19, 20, 21, 14
- Left button: `"0042"` at x=0, y=205, 120×40, right-justified text
- Right button: `"0041"` at x=200, y=205, 120×40, left-justified text
- Background: `BUTTONBKG` = white; text: `BUTTONTXT` = black; font: `FONT2`

### 6.4 Timer Ring (`ASSET_VECTOR`)
- Used by: screens 7 (Running), 25 (Cooling)
- `"timer_ring"` sprite ID; position x=69, y=34, 184×184
- Drawn by `renderTIMERBKG()` → `drawSegmentedCircle()`
- 4 segments controlled by `setTimerRingBlinking()`
- Default color: `TFT_DARKGREY` (all off = idle), segments activate per phase

### 6.5 `load_alert()` Generic Alert Template
A `screenId`-mapped overlay used for non-switch-case alerts:
- 1 icon (configurable type + source path)
- 2 text lines from `langMap[]` keys
- 1 button config by action ID
- Icon position: x=`LINE7Y`=35, y=64 (likely transposed; exact rendering not further confirmed)

---

## 7. Navigation Flow

```
Boot
 └─ Screen 12 (Logo)
     ├─ [Drawer 1, provisioned]  → Screen 4 (Ready)
     ├─ [Drawer 2, provisioned]  → Screen 4 (Ready)
     └─ [not provisioned]        → Screen 1 (QR Code)

Screen 1 (QR / Unprovisioned)
 ├─ BTN2: skip   → Screen 4 (GOTO_PROVISIONING_SKIP)
 └─ BLE connect  → Screen 9 (Provisioning)
                    → Screen 33 (waiting for Drawer 1, Drawer 2 only)
                    → Screen 8 (back to BLE waiting)

Screen 4 (Ready / Online)
 └─ State machine → Screen 6 (Check Updates)
                     ├─ updates available → Screen 17 (Loading) → Screen 19 (Prompt)
                     │    ├─ YES → Screen 2 (Download FW) → Screen 31 (STM32 FW) → Screen 10 (Assets) → Screen 16 (Done)
                     │    └─ LATER → Screen 4
                     └─ up to date → Screen 4

Screen 4 (Ready / Under STM32 Control)
 ├─ Running       → Screen 7
 ├─ Cooling       → Screen 25
 ├─ Drawer open   → Screen 24 / 27
 ├─ Motor manual  → Screen 11
 ├─ Pump running  → Screen 18
 ├─ Self test     → Screen 26 → Screen 28 (OK) / Screen 29 (Errors)
 ├─ Sensor error  → Screen 30
 └─ Bucket jam    → Screen 32

Screen 20 (No WiFi)
 ├─ YES (re-provision) → Screen 8 (BLE waiting)
 └─ NO (restart)       → GOTO_RESTART

Screen 21 (Factory Reset Confirm)
 ├─ YES → factory reset → Screen 1
 └─ NO  → Screen 4

WELCOME_WAIT state → Screen 14 (Welcome)
 └─ CONTINUE → GOTO_SKIP_CHECKUPLOAD_CHECK
```

**Back navigation:** Confirmed only via explicit button action (Action 100 → `GOTO_UI_IDLE`). No swipe / back gesture exists.

---

## 8. State-Driven UI Behavior

| Application State | Screen ID | Trigger |
|---|---|---|
| `STARTING` | 12 | Boot |
| `UNPROVISIONED` / `UNPROVISIONEDSTART` | 1 or 4 | `checkProvisionState()` result |
| `BLEBROADCASTING` | 8 | BLE start command |
| `PROVISIONING` | 9 | BLE data arriving |
| `FIRMWAREDOWNLOADING` | 2 | OTA download started |
| `FIRMWARETRANSFERTOSTM` | 31 | STM32 flash write |
| `ASSETDOWNLOADING` | 10 | S3 asset download |
| `LOADINGSETTINGS` | 17 | SPIFFS load |
| `TESTWIFI` | 13 | WiFi credential test |
| `ONLINE` | 4 | All connections healthy |
| `FIRMWAREDOWNLOADDECISION` | 19 | Update available |
| `NO_WIFI` | 20 | WiFi test failed |
| `UNDER_STM32_CONTROL` | 7 / 25 / 26 / 11 / 18 / 27 / 24 / 28 / 29 / 30 / 32 | STM32 state codes |
| `WELCOME_WAIT` | 14 | First boot after provisioning |
| `SKIP_CHECKUPLOAD_CHECK` | 13 | Checking skip upload setting |

---

## 9. Button Actions Reference

| Action ID | Behavior | Confirmed source |
|---|---|---|
| 100 | Go to `GOTO_UI_IDLE` | `UI.cpp` |
| 101 | Stop BLE, `GOTO_UI_CANCELBLE`, `gTriggerCMD = "BRIDGE_STOPBLE"` | `UI.cpp` |
| 102 | Start BLE, `GOTO_BLE_START`, `gTriggerCMD = "BRIDGE_STARTBLE"` | `UI.cpp` |
| 103 | Load screen 21, `GOTO_PROVISIONING_FACTORYRESET` | `UI.cpp` |
| 104 | `GOTO_UI_IDLE` | `UI.cpp` |
| 105 | `GOTO_FIRMWARE_DOWNLOAD` | `UI.cpp` |
| 106 | Start BLE (same as 102) | `UI.cpp` |
| 107 | `GOTO_RESTART` | `UI.cpp` |
| 108 | `sendButtonEvent(drawer, STM32_BTN1CLICK)` | `UI.cpp` |
| 109 | `sendButtonEvent(drawer, STM32_REBOOT)` | `UI.cpp` |
| 110 | `sendButtonEvent(drawer, STM32_BTN2CLICK)` | `UI.cpp` |
| 111 | `sendButtonEvent(drawer, STM32_TEST_WTR_PUMP)` | `UI.cpp` |
| 112 | `sendButtonEvent(drawer, STM32_SELF_TEST)` | `UI.cpp` |
| 113 | `sendButtonEvent(drawer, STM32_REBOOT)` + `GOTO_UI_IDLE` | `UI.cpp` |
| 114 | `GOTO_PROVISIONING_SKIP`, `gTriggerCMD = "BRIDGE_SKIPPROVISIONING"` | `UI.cpp` |
| 115 | `GOTO_SKIP_VERSION_CHECK` | `UI.cpp` |
| 117 | Drawer 1: stress test (`STM32_STRESSTEST`); Drawer 2: load screen 21 | `UI.cpp` |
| 118 | Welcome ack → `GOTO_SKIP_CHECKUPLOAD_CHECK`, `gTriggerCMD = "BRIDGE_WELCOMECONTINUE"` | `UI.cpp` |
| 119 | Factory reset confirmed → `GOTO_PROVISIONING_FACTORYRESET`, `gTriggerCMD = "BRIDGE_FACTORYRESET"` | `UI.cpp` |
| 120 | Load screen 21 (factory reset confirm overlay) | `UI.cpp` |

---

## 10. Implementation Notes for Copilot (ESP-IDF Port)

1. **Follow current Arduino behavior exactly.** Do not add screens, pages, or navigation paths not documented here.
2. **Display resolution:** Treat as 320×240 landscape. All Y coordinates are validated against actual spriting code (highest confirmed Y = `230+6=236`).
3. **Double-buffer pattern must be preserved:** Full-screen sprite → fill black → render all visible assets in layer order → push to TFT. This is the only pattern that prevents flicker.
4. **`MAX_SPRITES = 20`** — do not exceed. Allocate slots accordingly. Header icons are persistent and count toward this limit.
5. **All text rendering uses condensed GFX font renderer (`drawCondensedString`).** Full-width charset rendering is not used. Fonts compile to `GFXfont*` struct.
6. **Justification:** `CENTER` calculates `(screen_width/2) - (text_width/2)`; `RIGHT` calculates `screen_width - text_width - 10`. `LEFT` and `FREE` use raw `asset.x`.
7. **PROGMEM icon byte-swap:** Pixels are stored little-endian in PROGMEM arrays. Swap bytes (`px = (px << 8) | (px >> 8)`) before pushing to sprite. Already handled in `pushTintedPROGMEM()`.
8. **`ASSET_ICON` / `ASSET_IMAGE` (SPIFFS `.raw`):** Loaded with `swapBytes=true` in `renderIMAGE()`.
9. **Progress bar:** Do not call `SPRITE_create()` directly — use `addProgressBar()` equivalent. Values must be in 0–100 range.
10. **Header sprites use `HEADER` type** and must not be deleted on screen transitions. Implement persistence by excluding `HEADER` type from the clear-all path.
11. **If behavior is undocumented, leave `// TODO` comments** rather than guessing.
12. **Language keys 026+ must come from SPIFFS lang file.** The fallback default only covers 001–025. At minimum, keys referenced in screens must exist in whichever language file is loaded at boot.
13. **Timer ring animation** (`setTimerRingBlinking`) must be called from the main loop, not from `load_screen`. It modifies existing sprite assets in place.
14. **Button config IDs 1–17 are fully confirmed** in `setButtonConfigurationByID()`. Replicate exact action-to-detection-mode mapping.
15. **`gSYSTEM_drawer` check:** Screens 1, 4, 8 render different content for Drawer 1 vs. Drawer 2. This guard must be preserved.

---

## 11. Open Questions / Missing Information

| # | Question | Evidence |
|---|---|---|
| 1 | Exact text for language keys 026–071 | Not in `config.cpp` default fallback; requires SPIFFS `EN_Lang.json` content |
| 2 | Exact display model / part number | Code says ST7735 160×128 but coordinates contradict this; likely ST7789 320×240 |
| 3 | `ICON_WIFI0` usage | Declared in `ASSETS.h` (25×25) but not referenced in `renderPROGMEM()` lookup — dead code or missing case |
| 4 | `ASSET_TEXTBOX`, `ASSET_ELLIPSE` enum values | Declared in `AssetType` enum but no `renderTextBox()` or `renderEllipse()` found in reviewed code |
| 5 | `drawSegmentedCircle()` gap degrees | Function exists; parameter values confirmed as `segments=4, gapDegrees=?`; gap value not found in current call sites |
| 6 | `load_alert()` icon x/y position | Declared as `x=LINE7Y, y=64` which is likely inverted (35 and 64 — unusual axis swap); not confirmed to be correct |
| 7 | SPIFFS `.raw` file dimensions for WARNING/DONE/PAUSE | All drawn at 67×67 in asset specification but actual file content dimensions unconfirmed |
| 8 | `langMap["015"]` used in Screen 28 (Self Test OK) | Default text "Clear Jam, Remove Object" is semantically wrong for Self Test OK; correct message exists in SPIFFS lang file |
| 9 | Screen 3 (Firmware Download Complete) call site | Not found in `main.ino` grep results — may be triggered indirectly or via button timer |
| 10 | `ALERT_DISPLAY` state / `load_alert()` usage | `DeviceStatus::ALERT_DISPLAY` and `GOTO_ALERT_DISPLAY` exist in state machine but `load_alert()` call sites not identified in `main.ino` excerpt |
| 11 | `Screen 5` (WiFi Connect) — deprecated | Call site commented out in `main.ino`; Screen 13 used instead for TESTWIFI state; Screen 5 may be removed in future |
| 12 | `formatAndShowSelfTestErrors()` output format | Function exists; input = 3 raw bytes from STM32; output format shown as 3 text strings but exact bit-to-error-name mapping not found in reviewed files |
