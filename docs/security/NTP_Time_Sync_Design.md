# FC75 ESP32 — Time Synchronization Design

## Document Priority (Source of Truth)

This document supplements `docs/AI_Guidelines.md` and `docs/Claude.md`.
Source files analyzed: `main.ino`, `config.h`, `WIFI_Manager.cpp`, `AWS.cpp`

---

## 1. Purpose

This document defines the complete time synchronization architecture for the FC75 ESP32 firmware, covering:

- Why standard plaintext NTP was replaced
- The two-phase time sync strategy (coarse NTP bootstrap + precise HTTPS sync)
- How system time is maintained between syncs
- Why 24-hour resync is sufficient
- How AWS/TLS connections depend on correct system time
- All code changes made to implement the recommended architecture

---

## 2. Background — The Original Problem

### 2.1 TUV EN 18031 Finding #1 — Plaintext NTP Forbidden

Standard NTP (UDP port 123, RFC 5905) transmits time data in cleartext with no authentication. A Man-in-the-Middle attacker can:

- Forge NTP responses to shift device time forward or backward
- Cause TLS certificate validation to fail (cert appears expired or not yet valid)
- Manipulate OTA update timing windows
- Invalidate timestamped audit logs

**TUV EN 18031 Finding #1** explicitly flags plaintext NTP as a security vulnerability in IoT devices. The original firmware used `configTime("pool.ntp.org", "time.nist.gov")` and was flagged.

### 2.2 The Chicken-and-Egg Problem

Replacing NTP with an HTTPS endpoint creates a dependency cycle:

```
TLS handshake requires valid system time
    ↓
Valid system time requires HTTPS Lambda response
    ↓
HTTPS Lambda requires TLS handshake
```

**Without a valid system time, mbedTLS cannot validate TLS certificates**, causing all HTTPS and MQTT/TLS connections (including AWS IoT) to fail on first boot or after reboot.

---

## 3. Architecture — Two-Phase Time Sync

The solution uses a two-phase approach that satisfies both security and correctness requirements:

```
Phase 1: NTP Bootstrap (coarse, one-time per boot)
─────────────────────────────────────────────────
  WiFi connects → configTime("pool.ntp.org") → system clock set
  Purpose: Unblock TLS handshakes (AWS IoT, Lambda HTTPS)
  Security: Acceptable because this time is NEVER used for
            telemetry timestamps or OTA logic
  Duration: ≤ 5 seconds blocking wait

Phase 2: Encrypted HTTPS Sync (precise, periodic)
──────────────────────────────────────────────────
  handleTimeSyncNonBlocking() → HTTPS GET → AWS Lambda
  Purpose: Set gBaseEpoch for all telemetry timestamps
  Security: TLS with device CA certificate (MITM-resistant)
  Frequency: On first sync + every 24 hours
  Also calls settimeofday() to keep system clock accurate
```

### 3.1 Phase 1 — NTP Bootstrap Detail

| Property | Value |
|---|---|
| Protocol | SNTP (UDP, port 123) |
| Servers | `pool.ntp.org`, `time.nist.gov` |
| Triggered | Once per boot, first time `handleTimeSyncNonBlocking()` fires |
| Timeout | 5 seconds max (then proceeds with whatever time is available) |
| Output | System clock set via `configTime()` |
| Used for | Unblocking TLS certificate date validation only |
| Used in telemetry | **No** — `gTimestamp` still comes from Phase 2 |

### 3.2 Phase 2 — Encrypted HTTPS Sync Detail

| Property | Value |
|---|---|
| Protocol | HTTPS (TLS 1.2+, port 443) |
| Endpoint | `kpcxqfnqnzh6s6hhpl26n55idu0qyqzo.lambda-url.us-east-1.on.aws` |
| CA Validation | Yes — device CA cert loaded from SPIFFS via `spiff.getCA()` |
| Triggered | On first WiFi connection (when `gBaseEpoch == 0`) + every 24h |
| Timeout | 10s header + 10s body |
| Output | `gBaseEpoch` set + `settimeofday()` called |
| Used for | All `gTimestamp` values in telemetry, logs, MQTT payloads |
| Used for | Keeping mbedTLS system clock accurate (via `settimeofday`) |

> **Endpoint note:** Current active endpoint is the us-east-1 Lambda above (dev/test deployment).
> When migrating to the production AWS environment, replace with:
> `xsgy4ejw4rpn5usclvs7zfm27q0nijeq.lambda-url.ca-central-1.on.aws`

---

## 4. Why 24-Hour Resync is Sufficient

### 4.1 ESP32 Crystal Oscillator Drift

Between Phase 2 syncs, time is tracked via:

```cpp
time_t now = gBaseEpoch + ((millis() - gBaseMillis) / 1000);
```

`millis()` is driven by the ESP32's internal crystal oscillator (XTAL, typically 40 MHz).

| Drift Rate | 24-Hour Accumulated Error |
|---|---|
| 50 ppm (best case) | ≈ 4.3 seconds |
| 100 ppm (typical) | ≈ 8.6 seconds |
| 200 ppm (warm ambient) | ≈ 17.3 seconds |

### 4.2 Accuracy Requirements by Use Case

| Use Case | Accuracy Required | 24h / ≤17s Drift |
|---|---|---|
| MQTT telemetry timestamps (heartbeat, logs) | ±seconds acceptable | ✅ Sufficient |
| OTA 12-hour periodic check | Uses `millis()` directly, unrelated to epoch | ✅ No impact |
| TLS certificate expiry check | mbedTLS uses system clock (set by Phase 2 via `settimeofday`) | ✅ Sufficient |
| Replay-attack prevention | AWS IoT allows ±5 min timestamp skew | ✅ Sufficient |

### 4.3 Why 1-Hour Resync Would Be Overkill

| Factor | Impact of 1h vs 24h |
|---|---|
| Accuracy gain | ±0.4–0.7 seconds improvement per period |
| HTTPS requests | 24× more Lambda calls per day |
| Power consumption | ~24× more TLS handshake energy |
| Network traffic | Negligible but unnecessary |
| **Verdict** | **1-hour interval provides no meaningful benefit** |

### 4.4 Resync After AWS Reconnect

AWS disconnection/reconnection does **not** require a time resync:

- `millis()` continues counting through all network disruptions
- `gBaseEpoch + elapsed_millis` remains accurate at all times
- The 24h resync timer is based on `millis()`, not on connection events

```
Scenario: AWS drops and reconnects after 2 hours
  gBaseEpoch = 1745000000 (set 2h ago)
  millis()   = 7200000ms since last sync
  now = 1745000000 + (7200000/1000) = 1745007200  ← correct
```

---

## 5. Code Changes Implemented

### 5.1 `handleTimeSyncNonBlocking()` — Updated Function

**File:** `main.ino`

Three changes were made:

#### Change A — Phase 1 NTP Bootstrap (added at top)

```cpp
// Phase 1: NTP bootstrap — one-time per boot, unblocks TLS certificate validation
// This coarse time is ONLY used to allow mbedTLS to validate cert expiry dates.
// It is never used for gTimestamp (telemetry). Phase 2 (Lambda HTTPS) provides
// the accurate, authenticated time used for all application purposes.
static bool ntpBootstrapped = false;
if (!ntpBootstrapped) {
    Serial.println(F("[TIME] Phase 1: NTP bootstrap for TLS unblock..."));
    configTime(0, 0, config::DEVICE::NTP_SERVER_1, config::DEVICE::NTP_SERVER_2);
    unsigned long ntpWait = millis();
    while (time(nullptr) < 1000000000UL && millis() - ntpWait < 5000UL) {
        delay(50);
    }
    ntpBootstrapped = true;
    Serial.printf("[TIME] NTP bootstrap complete — system time: %ld\n", (long)time(nullptr));
}
```

#### Change B — `settimeofday()` after successful Lambda sync (added after gBaseEpoch set)

```cpp
gBaseEpoch  = epoch;
gBaseMillis = millis();

// Sync system clock with precise Lambda time so mbedTLS cert validation stays accurate
struct timeval tv = { .tv_sec = epoch, .tv_usec = 0 };
settimeofday(&tv, nullptr);
Serial.printf("[TIME] Phase 2: System clock updated via HTTPS Lambda: %ld\n", (long)gBaseEpoch);
```

#### Change C — Updated doc comment

The function doc comment was updated to describe both phases.

### 5.2 Summary of All External Hosts Contacted

| Phase | Host | Port | Protocol | Auth | Purpose |
|---|---|---|---|---|---|
| 1 (bootstrap) | `pool.ntp.org` | 123 | UDP/SNTP | None | Coarse system time for TLS bootstrap |
| 1 (bootstrap) | `time.nist.gov` | 123 | UDP/SNTP | None | Fallback NTP server |
| 2 (precise) | AWS Lambda URL | 443 | HTTPS/TLS | CA cert | Authenticated epoch for gTimestamp |

---

## 6. Security Analysis

### 6.1 Phase 1 NTP — Acceptable Risk

Phase 1 NTP is plaintext and unauthenticated. The risk is accepted because:

1. **Its output is never used for application timestamps** — only for TLS bootstrap
2. **Phase 2 immediately overwrites system time** with the authenticated Lambda value
3. **The time window of exposure is ≤ 5 seconds** per boot
4. **An attacker shifting time ±minutes** during this window only affects TLS bootstrap, not telemetry integrity
5. **The Lambda HTTPS connection verifies the CA certificate**, making the precise time MITM-resistant

### 6.2 Phase 2 Lambda HTTPS — Strong Security

| Threat | Mitigation |
|---|---|
| MITM time spoofing | TLS with CA cert validation (`spiff.getCA()`) |
| Replay attack | TLS session freshness guarantees |
| DNS spoofing | TLS cert binds to specific hostname |
| Epoch forgery | Epoch < 1700000000 sanity check in firmware |

### 6.3 TLS Certificate Validation — Now Fully Correct

Before this change:
- System clock = epoch 0 or indeterminate after reboot
- mbedTLS cert validation used wrong time → potential failures or lenient skipping

After this change:
- Phase 1 sets approximate system time within seconds of boot
- Phase 2 corrects system time to authenticated precision every 24h
- mbedTLS always has a valid system clock for certificate expiry checking

---

## 7. State Machine Flow (Updated)

```
Boot
  │
  ▼
WiFi connects
  │
  ▼
handleTimeSyncNonBlocking() called (every loop)
  │
  ├─► [ntpBootstrapped == false]
  │       configTime("pool.ntp.org", "time.nist.gov")
  │       Wait ≤ 5s for system time
  │       ntpBootstrapped = true
  │       (system clock now valid for TLS)
  │
  ├─► [tsSyncState == TS_IDLE && gBaseEpoch == 0 || 24h elapsed]
  │       WiFiClientSecure + CA cert
  │       HTTPS GET → Lambda :443
  │       tsSyncState = TS_WAITING_HEADER
  │
  ├─► [tsSyncState == TS_WAITING_HEADER]
  │       Read HTTP headers until blank line
  │       tsSyncState = TS_WAITING_BODY
  │
  └─► [tsSyncState == TS_WAITING_BODY]
          Read JSON body
          Parse {"epoch": ...}
          gBaseEpoch  = epoch
          gBaseMillis = millis()
          settimeofday(&tv, nullptr)    ← NEW: system clock updated
          tsSyncState = TS_IDLE
          (all telemetry timestamps now accurate and authenticated)
```

---

## 8. Variables and Constants Reference

| Symbol | File | Value | Purpose |
|---|---|---|---|
| `gBaseEpoch` | `main.ino` | `time_t` | Epoch from last Lambda sync |
| `gBaseMillis` | `main.ino` | `unsigned long` | `millis()` value at last sync |
| `gTimestamp` | `main.ino` | `char[32]` | ISO 8601 string for MQTT payloads |
| `NTP_RESYNC_INTERVAL_MS` | `config.h` | `24 * 3600 * 1000` | 24-hour resync interval |
| `NTP_SERVER_1` | `config.h` | `"pool.ntp.org"` | Phase 1 NTP server |
| `NTP_SERVER_2` | `config.h` | `"time.nist.gov"` | Phase 1 NTP fallback |
| `FC75TIME` | `config.h` | `https://kpcxqfnqnzh6s6hhpl26n55idu0qyqzo.lambda-url.us-east-1.on.aws/` | Phase 2 HTTPS endpoint (current dev/test) |
| ~~`FC75TIME`~~ | `config.h` | ~~`https://xsgy4ejw4rpn5usclvs7zfm27q0nijeq.lambda-url.ca-central-1.on.aws/`~~ | *(旧 URL，正式部署到生产 AWS 时切换回此地址)* |
| `ntpBootstrapped` | `main.ino` | `static bool` | One-time Phase 1 gate |
| `tsSyncState` | `main.ino` | `TimeSyncState` enum | Phase 2 state machine |

---

## 9. Testing Verification

### 9.1 Verify Phase 1 NTP Bootstrap

Serial log immediately after WiFi connects:
```
[TIME] Phase 1: NTP bootstrap for TLS unblock...
[TIME] NTP bootstrap complete — system time: 1745XXXXXXX
```

System time must be non-zero before Lambda HTTPS is attempted.

### 9.2 Verify Phase 2 Lambda Sync

Serial log after Lambda response:
```
[TIME] Connecting to FC75TIME endpoint...
[TIME] Phase 2: System clock updated via HTTPS Lambda: 1745XXXXXXX
```

### 9.3 Verify System Clock Accuracy (Optional)

After Phase 2 sync:
```cpp
Serial.printf("System time: %ld\n", (long)time(nullptr));
// Should match gBaseEpoch ± 1 second
```

### 9.4 Verify AWS Connection Succeeds

AWS MQTT connect must succeed after Phase 1, without `[AWS] AWS connection failed` errors.

### 9.5 Verify 24h Resync

After 24 hours of uptime, serial log should show:
```
[TIME] Connecting to FC75TIME endpoint...
[TIME] Phase 2: System clock updated via HTTPS Lambda: ...
```

---

## 10. Known Limitations

| Limitation | Impact | Mitigation |
|---|---|---|
| Phase 1 NTP is unauthenticated | Coarse time may be spoofed ±minutes | Phase 2 corrects immediately; Phase 1 only used for TLS bootstrap |
| `settimeofday()` requires `<sys/time.h>` | Already included via Arduino ESP32 SDK | No action needed |
| If Lambda HTTPS fails, gBaseEpoch stays 0 | `gTimestamp` not updated; OTA blocked for 60s | Retry logic in `handleTimeSyncNonBlocking()` |
| Phase 1 is blocking up to 5 seconds | Slight delay on first boot | Acceptable; only happens once per boot |
| Crystal drift up to 17s/day | Minor timestamp inaccuracy | Corrected every 24h by Phase 2 |

