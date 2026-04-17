# FC75 BLE Provisioning – Technical Reference

> **Firmware:** v1.0.63 · **Platform:** LilyGo T-Display S3 (ESP32-S3) · **BLE Stack:** NimBLE-Arduino  
> **Author:** The B Team · **Date:** April 2026

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [GATT Service & Characteristics](#3-gatt-service--characteristics)
4. [BLE Security Mechanisms](#4-ble-security-mechanisms)
5. [Chunked Data Transfer Protocol](#5-chunked-data-transfer-protocol-bofeof)
6. [Credential Files & Encrypted Storage](#6-credential-files--encrypted-storage)
7. [Provisioning State Machine](#7-provisioning-state-machine)
8. [Drawer 1 vs Drawer 2 – Differences](#8-drawer-1-vs-drawer-2--differences)
9. [Inter-Drawer Bridge Protocol](#9-inter-drawer-bridge-protocol)
10. [Q&A: Three Key Questions](#10-qa-three-key-questions)
11. [Session Timeouts & Safety Limits](#11-session-timeouts--safety-limits)
12. [Data Flow Diagram](#12-data-flow-diagram)
13. [Key Source Files Reference](#13-key-source-files-reference)

---

## 1. Overview

The FC75 is a two-drawer food-cycling appliance. Each drawer contains an independent ESP32-S3 module (LilyGo T-Display S3) that must be **provisioned** before it can connect to Wi-Fi and AWS IoT Core. Provisioning is performed via BLE using a companion mobile app.

Provisioning delivers **five credential files** per device:

| File | Content |
|------|---------|
| `/wifi.json` | Wi-Fi SSID, password, optional enterprise username |
| `/aws_config.json` | AWS endpoint, Thing Name, S3 bucket, language |
| `/cert.pem` | AWS IoT device certificate (PEM) |
| `/priv.key` | AWS IoT private key (PEM) |
| `/ca.pem` | AWS Root CA certificate (PEM) |

All files are encrypted at rest with **AES-128-GCM** using a device-unique key stored in ESP32 NVS (Non-Volatile Storage).

---

## 2. Architecture

```
┌──────────────────────────────────────────────────────┐
│                  Mobile App (BLE Central)            │
└───────────────────────┬──────────────────────────────┘
                        │  Authenticated BLE (passkey-protected)
          ┌─────────────┼──────────────┐
          │             │              │
          ▼             ▼              ▼
   ┌─────────────┐             ┌─────────────┐
   │  Drawer 1   │ ◄──Bridge──►│  Drawer 2   │
   │  ESP32-S3   │  (via STM32)│  ESP32-S3   │
   └─────────────┘             └─────────────┘
          │                          │
          ▼                          ▼
   SPIFFS (AES-GCM)          SPIFFS (AES-GCM)
   /wifi.json                /wifi.json
   /aws_config.json          /aws_config.json
   /cert.pem                 /cert.pem
   /priv.key                 /priv.key
   /ca.pem                   /ca.pem
```

### Key Design Decisions

- **Singleton BLE class**: `BLE::instance()` ensures only one NimBLE server per device at all times.
- **Both drawers run independent BLE servers**: The mobile app connects to each drawer separately and sends credentials directly to each.
- **Passkey shared over bridge**: Drawer 1 generates the 6-digit passkey and sends it to Drawer 2 via the STM32 UART bridge (`BRIDGE_PASSKEY`), so both drawers display the same passkey.
- **Deferred writes via queue**: Received payloads are pushed into `bleWriteQueue` and written to SPIFFS one-per-loop, never blocking the BLE event thread.

---

## 3. GATT Service & Characteristics

### Service UUID

```
f920c71f-0619-4efe-a77f-c209cd1a38bb
```

### Characteristics

| Name | UUID | Properties | Purpose |
|------|------|-----------|---------|
| `CHARACTERISTIC_WIFI` | `6f4c480e-93c1-4a6d-bca8-3ac1a6a7d443` | WRITE + WRITE_ENC | Wi-Fi credentials (JSON) |
| `CHARACTERISTIC_AWS_CONFIG` | `14dd1c82-15dd-4215-87ce-956fbb5e67e5` | WRITE + WRITE_ENC | AWS endpoint/Thing/bucket |
| `CHARACTERISTIC_CERT` | `547e55cc-f38c-488a-9e95-588188d69935` | WRITE + WRITE_ENC | Device certificate (PEM) |
| `CHARACTERISTIC_KEY` | `9076c747-07f3-444b-b119-288799fc30b6` | WRITE + WRITE_ENC | Private key (PEM) |
| `CHARACTERISTIC_CA` | `ded6967f-df95-48fc-863d-d4821fadf662` | WRITE + WRITE_ENC | Root CA cert (PEM) |
| `CHARACTERISTIC_MAC` | `2c9b3c4a-5e2f-4c9a-9a2d-9f2e8d6a41c7` | WRITE + READ + ENC | MAC address query |

> **All characteristics require an authenticated, encrypted connection** (`WRITE_ENC` / `READ_ENC`). Writes before pairing is complete are rejected by the NimBLE stack.

### MTU

```cpp
NimBLEDevice::setMTU(512);  // Maximum supported by ESP32
```

### Device Advertising Name

The advertising name is dynamically generated at runtime:

```
FC75<drawer_number>-<last4_of_MAC>
// e.g., "FC751-C3A1"  (Drawer 1)
//       "FC752-C3A1"  (Drawer 2)
```

---

## 4. BLE Security Mechanisms

### 4.1 Pairing & Encryption

```cpp
NimBLEDevice::setSecurityAuth(true, true, true);
//                            bonding  MITM  SecureConnections
NimBLEDevice::setSecurityIOCap(BLE_HS_IO_DISPLAY_ONLY);
NimBLEDevice::setSecurityPasskey(gBLE_PASSKEY);
NimBLEDevice::setSecurityInitKey(BLE_SM_PAIR_KEY_DIST_ENC | BLE_SM_PAIR_KEY_DIST_ID);
NimBLEDevice::setSecurityRespKey(BLE_SM_PAIR_KEY_DIST_ENC | BLE_SM_PAIR_KEY_DIST_ID);
```

| Security Parameter | Value | Meaning |
|---|---|---|
| Bonding | `true` | Keys are stored after pairing |
| MITM Protection | `true` | Man-in-the-middle protection enforced |
| Secure Connections | `true` | LE Secure Connections (ECDH) used |
| IO Capability | `DISPLAY_ONLY` | Device shows passkey; user must enter it on phone |
| Key Distribution | ENC + ID | Both encryption and identity keys exchanged |

### 4.2 Passkey Generation

Drawer 1 generates a cryptographically random 6-digit passkey using `esp_random()`:

```cpp
// In CONNECT_connectBLE() — Drawer 1 only
gBLE_PASSKEY = (esp_random() % 900000) + 100000;  // always 6 digits (100000–999999)
```

This passkey is:
1. Set in the NimBLE stack (`NimBLEDevice::setSecurityPasskey(gBLE_PASSKEY)`)
2. Transmitted to Drawer 2 via the STM32 bridge (`BRIDGE_PASSKEY`)
3. Displayed on the FC75 screen for the user to enter in the mobile app

### 4.3 Authentication Enforcement

The `onAuthenticationComplete` callback enforces encryption before any writes are permitted:

```cpp
void ServerCallbacks::onAuthenticationComplete(NimBLEConnInfo& connInfo) {
    if (!connInfo.isEncrypted()) {
        BLE::instance().recordFailedAttempt();
        NimBLEDevice::getServer()->disconnect(connInfo.getConnHandle());
        return;
    }
    // Auth success — client may now write
}
```

### 4.4 Failed Passkey Lockout (Exponential Backoff)

```
Attempt 1 fail → 5-second advertising pause
Attempt 2 fail → 10-second advertising pause
Attempt 3 fail → BLE permanently locked (state: BLE_LOCKED)
                  Device must be restarted to recover
```

Code path:
```cpp
void BLE::recordFailedAttempt() {
    failedPasskeyAttempts++;
    unsigned long delays[] = { 5000, 10000 };
    if (failedPasskeyAttempts >= 3) {
        NimBLEDevice::stopAdvertising();
        backoffUntil = ULONG_MAX;           // permanent lock
        gOVERRIDEcommands = GOTO_BLE_LOCKED;
    } else {
        backoffUntil = millis() + delays[failedPasskeyAttempts - 1];
        NimBLEDevice::stopAdvertising();
    }
}
```

### 4.5 Numeric Comparison Rejection

If a central device with `DISPLAY_YESNO` IO capability initiates numeric comparison instead of passkey entry, the firmware explicitly **rejects** it to prevent unauthenticated pairing:

```cpp
void ServerCallbacks::onConfirmPassKey(NimBLEConnInfo& connInfo, uint32_t pass_key) {
    NimBLEDevice::injectConfirmPasskey(connInfo, false);  // Always reject
}
```

### 4.6 Credential Encryption at Rest

After BLE provisioning, all five credential files are encrypted using **AES-128-GCM** (mbedTLS, hardware-accelerated) with a **device-unique key** derived from the MAC address and a GUID via HKDF, stored in NVS:

```
Encryption format (Base64 stored to SPIFFS):
  [12-byte random IV] + [ciphertext] + [16-byte GCM auth tag]
```

The GCM tag provides **tamper detection**: any modification to the encrypted file on SPIFFS is caught at decryption time.

> **Legacy migration:** Devices originally provisioned with AES-128-ECB (hardcoded key) are automatically migrated to AES-128-GCM + NVS key on first boot. CBC is an intermediate migration state for dev boards.

---

## 5. Chunked Data Transfer Protocol (BOF/EOF)

BLE MTU is 512 bytes, but PEM certificates can exceed 1 KB. Large payloads are split into chunks by the mobile app and reassembled by `assembleBLEBuffer()`.

### Protocol Markers

| Marker | Value | Action |
|--------|-------|--------|
| **BOF** (Begin Of File) | `24e5c9e1-0d89-4ae4-9bf1-3e77b309c2a8` (GUID) | Clear buffer, open session |
| **EOF** (End Of File) | `"EOF"` | Close session, return assembled payload |
| **FINISHED** | `"FINISHED"` | End all provisioning, stop BLE, restart device |
| **Data chunk** | any other string | Appended to session buffer |

> The BOF marker is a **GUID**, not a simple keyword. This makes it resistant to accidental triggering and provides a first layer of protocol identification security.

### Transfer Flow

```
Mobile App                           ESP32 (BLE Server)
    │                                       │
    │──[Write BOF to characteristic]────────►│  Buffer cleared, session opened
    │                                       │  bleSessionTimeout = now + 10s
    │──[Write chunk 1]──────────────────────►│  chunk appended to bleBuffer
    │──[Write chunk 2]──────────────────────►│  chunk appended, timeout reset
    │   ...                                 │
    │──[Write EOF]──────────────────────────►│  assembled = bleBuffer; buffer cleared
    │                                       │  handleProvisioningWrite() queued
    │──[Write BOF on next characteristic]───►│  New session for next file
    │   ...                                 │
    │──[Write FINISHED]─────────────────────►│  stopBLEbroadcast()
    │                                       │  gOVERRIDEcommands = GOTO_PROVISIONING_COMPLETEDSETUP
```

### Buffer Safety Limits

```cpp
static constexpr size_t TRANSMISSIONLIMIT = 10000;  // 10 KB hard limit per payload
```

If any single assembled payload exceeds 10,000 bytes, the session is aborted and BLE is cancelled.

### Deferred Write Queue

Received payloads are not written to SPIFFS immediately (to avoid blocking the BLE callback thread). Instead:

1. `handleProvisioningWrite()` pushes `{ data, path }` onto `bleWriteQueue`
2. In `BLE::loop()`, one task is dequeued and written per iteration:
   ```cpp
   if (!bleWriteQueue.empty() && spiff) {
       BLEWriteTask task = bleWriteQueue.front();
       bleWriteQueue.erase(bleWriteQueue.begin());
       spiff->writeBLEpayload(task.data, task.path.c_str());
   }
   ```
3. `SPIFF_Manager::writeBLEpayload()` encrypts and saves the file to SPIFFS.

---

## 6. Credential Files & Encrypted Storage

### File Paths (SPIFFS)

```
/wifi.json        ← {"ssid":"...","password":"...","username":"..."}
/aws_config.json  ← {"endpoint":"...","clientId":"...","bucket":"...","lang":"..."}
/cert.pem         ← -----BEGIN CERTIFICATE----- ...
/priv.key         ← -----BEGIN RSA PRIVATE KEY----- ...
/ca.pem           ← -----BEGIN CERTIFICATE----- ...
```

### Provisioning Validation

`SPIFF_Manager::checkProvisionState()` is called at boot and after provisioning. It verifies:
- All five files exist in SPIFFS
- Each file is non-empty and successfully decryptable
- Returns `false` if any file is missing or corrupt → device enters BLE provisioning mode

### Encryption Key Lifecycle

```
First boot (no NVS key):
  1. generateKey() → derive 16-byte key via HKDF(MAC + GUID) → store in NVS
  2. Transition any existing ECB files → re-encrypt with new GCM key

Normal boot (NVS key exists):
  1. getEncryptionKey() → load from NVS
  2. decryptGCM() on credential files as needed
```

---

## 7. Provisioning State Machine

### Device States Involved

```
UNLINKED
  └─► WELCOME_WAIT           (first boot welcome screen)
        └─► SKIP_CHECKUPLOAD_CHECK
              └─► UNPROVISIONED        (no credentials, ready to BLE)
                    └─► BLEBROADCASTING    (advertising active)
                          └─► PROVISIONING     (BOF received — data flowing)
                                └─► PROVISIONING_COMPLETEDSETUP
                                      └─► TESTWIFI → UPDATEMANAGER → ONLINE
```

### State Transition Commands (GOTO_Command)

| Command | Effect |
|---------|--------|
| `GOTO_PROVISIONSTATE_NOT` | Generate passkey → send to Drawer 2 → start BLE advertising |
| `GOTO_BLE_START` | Start BLE broadcast (called from button or bridge) |
| `GOTO_PROVISIONING_START` | Switch to PROVISIONING state, disconnect Wi-Fi |
| `GOTO_PROVISIONING_COMPLETEDSETUP` | Mark provisioned in SPIFFS, stop BLE, load settings, test Wi-Fi |
| `GOTO_UI_CANCELBLE` | Stop BLE, return to idle or unprovisioned |
| `GOTO_BLE_LOCKED` | Lock BLE after 3 failed passkey attempts |

### BLE Lifecycle Functions

```cpp
CONNECT_connectBLE(true)   // Generate passkey, broadcast passkey to Drawer 2, start BLE
CONNECT_connectBLE(false)  // Stop BLE broadcasting, tear down NimBLE stack
```

---

## 8. Drawer 1 vs Drawer 2 – Differences

The **drawer number** (`gSYSTEM_drawer`) is assigned by the STM32 co-processor via UART frames (`device_id` byte). Both drawers run identical firmware; behavior diverges based on this variable alone.

### Comparison Table

| Feature | Drawer 1 | Drawer 2 |
|---------|----------|----------|
| **Passkey generation** | ✅ Generates `gBLE_PASSKEY` via `esp_random()` | ❌ Receives passkey from Drawer 1 via `BRIDGE_PASSKEY` |
| **BLE start trigger** | Starts BLE immediately on `GOTO_PROVISIONSTATE_NOT` | Waits for `BRIDGE_PASSKEY` bridge message, then starts BLE |
| **Heartbeat** | Initiates heartbeat to Drawer 2 (every 20s unlinked / 60s linked) | Responds to heartbeat with `BRIDGE_CONFIRM` |
| **AWS telemetry** | Sends heartbeat to AWS (`if (gSYSTEM_drawer != 2)`) | Does NOT send AWS heartbeat |
| **Bridge PROVISIONSTART** | Sends `BRIDGE_PROVISIONSTART` to notify Drawer 2 | Shows "Drawer 1 provisioning" UI screen |
| **Bridge PROVISIONEND** | Sends `BRIDGE_PROVISIONEND` to notify Drawer 2 | Shows BLE waiting screen |
| **Display screen (provisioning)** | Active provisioning progress screen | Shows "PROVISIONING CONTINUING" (screen 33) |
| **WAITING_FOR_BLE timeout** | Returns to previous flow | **Self-generates passkey** and starts BLE independently |
| **Passkey display** | Shown on local display (from `gBLE_PASSKEY`) | Shown on local display (same value received from Drawer 1) |
| **BLE server name** | `FC751-XXXX` | `FC752-XXXX` |

### Drawer 2 Fallback

If Drawer 2 does not receive a passkey from Drawer 1 within **5 seconds** (`WAITING_FOR_BLE` state), it self-generates a passkey and starts BLE independently:

```cpp
case WAITING_FOR_BLE: {
    if (millis() - gWaitingForBLEStart >= 5000) {
        if (gSYSTEM_drawer == 2) {
            gBLE_PASSKEY = (esp_random() % 900000) + 100000;
            gOVERRIDEcommands = GOTO_BLE_START;
        }
    }
    break;
}
```

> ⚠️ In this fallback scenario, Drawer 1 and Drawer 2 will display **different passkeys**. The mobile app must connect to each drawer separately with the passkey shown on each respective display.

---

## 9. Inter-Drawer Bridge Protocol

Drawers communicate via a custom binary protocol over UART, routed through the STM32 co-processor as a transparent passthrough.

### Frame Format

```
[0xDD][0xDA][0xFF][0xFF][0xFF][LEN_H][LEN_L][SENDER_ID][CMD][DATA...][XOR_CHECKSUM]
 └──────────── 5-byte header ─────────────┘ └── 2-byte length ──┘ └── payload ──┘
```

| Field | Size | Description |
|-------|------|-------------|
| Header | 5 bytes | `0xDD 0xDA 0xFF 0xFF 0xFF` |
| Length | 2 bytes | Big-endian payload length |
| Sender ID | 1 byte | Drawer number (1 or 2) |
| CMD | 1 byte | Command byte (see table below) |
| DATA | 0–118 bytes | Optional command payload |
| XOR Checksum | 1 byte | XOR of all payload bytes |

### Bridge Command Codes

| Command | Hex | Direction | Purpose |
|---------|-----|-----------|---------|
| `BRIDGE_STARTBLE` | `0xE1` | 1→2 / 2→1 | Start BLE on both devices |
| `BRIDGE_STOPBLE` | `0xE2` | 1→2 / 2→1 | Stop BLE on both devices |
| `BRIDGE_FACTORYRESET` | `0xE3` | 1→2 | Factory reset the other drawer |
| `BRIDGE_WELCOMECONTINUE` | `0xE4` | 1↔2 | User confirmed welcome screen |
| `BRIDGE_SKIPPROVISIONING` | `0xE5` | 1↔2 | Skip provisioning flow |
| `BRIDGE_PROVISIONSTART` | `0xE6` | 1→2 | Notify Drawer 2 provisioning started |
| `BRIDGE_PROVISIONEND` | `0xE7` | 1→2 | Notify Drawer 2 provisioning complete |
| `BRIDGE_HEARTBEAT` | `0xE8` | 1→2 | Periodic liveness ping |
| `BRIDGE_PASSKEY` | `0xE9` | 1→2 | Send 4-byte BLE passkey to Drawer 2 |
| `BRIDGE_CONFIRM` | `0xEA` | 2→1 | Heartbeat acknowledgment |

### Passkey Transmission (BRIDGE_PASSKEY)

```cpp
// Drawer 1: encode and send
uint8_t pkData[4] = {
    (pk >> 24) & 0xFF,
    (pk >> 16) & 0xFF,
    (pk >>  8) & 0xFF,
     pk        & 0xFF
};
myhardware.sendBridgeCmd(config::TX_CMD::BRIDGE_PASSKEY, pkData, 4);

// Drawer 2: decode on receipt
gBLE_PASSKEY = ((uint32_t)buf[2] << 24)
             | ((uint32_t)buf[3] << 16)
             | ((uint32_t)buf[4] <<  8)
             |  (uint32_t)buf[5];
gOVERRIDEcommands = GOTO_BLE_START;  // Drawer 2 now starts BLE
```

### Provisioning Bridge Message Contract (Authoritative)

Use this table as the source of truth when implementing the `esp-idf` port.

| Bridge Message | Drawer 1: Exact Send Trigger | Drawer 2: Required Action On Receive |
|---|---|---|
| `BRIDGE_PASSKEY` (`0xE9`) | During BLE start path in `CONNECT_connectBLE(true)`: Drawer 1 generates `gBLE_PASSKEY`, sets `gTriggerCMD = "BRIDGE_PASSKEY|<hex>"`, then `TRIGGERS_process()` sends `myhardware.sendBridgeCmd(BRIDGE_PASSKEY, pkData, 4)`. | Parse 4-byte passkey into `gBLE_PASSKEY`, then set `gOVERRIDEcommands = GOTO_BLE_START` to start local BLE advertising with that passkey. |
| `BRIDGE_PROVISIONSTART` (`0xE6`) | On first provisioning packet marker `BOF` in `CharacteristicCallbacks::onWrite()` (`BLE.cpp`): set `gTriggerCMD = "BRIDGE_PROVISIONSTART"`, then `TRIGGERS_process()` sends bridge command (Drawer 1 only). | Do not start provisioning writes automatically. Update UI state only: `mydisplay.load_screen(33, ...)` ("provisioning continuing / waiting for drawer 1"). |
| `BRIDGE_PROVISIONEND` (`0xE7`) | On `FINISHED` marker in `CharacteristicCallbacks::onWrite()` (`BLE.cpp`): set `gTriggerCMD = "BRIDGE_PROVISIONEND"`, then `TRIGGERS_process()` sends bridge command (Drawer 1 only). | UI/state handoff only: `mydisplay.load_screen(8, ...)` (BLE waiting screen). Drawer 2 still requires its own mobile-app BLE write sequence for the 5 files. |

> Terminology note: if app docs mention `BRIDGE_PROVISIONED`, this firmware symbol is `BRIDGE_PROVISIONEND` (`0xE7`).

---

## 10. Q&A: Three Key Questions

### Q1: What is the difference between Drawer 1 and Drawer 2?

**Summary:** Both drawers run the **exact same firmware binary**. The only difference is the value of `gSYSTEM_drawer` (set by the STM32), which controls a small set of divergent behaviors:

1. **Passkey Generation:** Only **Drawer 1** generates the BLE passkey. It then sends the passkey to Drawer 2 via the `BRIDGE_PASSKEY` bridge command so both displays show the same number.

2. **BLE Start Sequencing:** Drawer 1 starts BLE immediately when provisioning is triggered. Drawer 2 waits up to 5 seconds for the passkey from Drawer 1 before starting BLE (with a self-generate fallback).

3. **AWS Telemetry:** Only **Drawer 1** sends heartbeat telemetry to AWS IoT. Drawer 2 operates silently from the cloud's perspective (the STM32 sensor frame covers both drawers).

4. **Bridge Event Handling:** Drawer 1 sends `BRIDGE_PROVISIONSTART` and `BRIDGE_PROVISIONEND` notifications to Drawer 2. Drawer 2 only displays status UI screens in response.

5. **Heartbeat Initiation:** Drawer 1 initiates the periodic heartbeat; Drawer 2 only responds.

---

### Q2: After Drawer 1 receives data from the mobile app, does it need to send it to Drawer 2 via STM32/bridge?

**The credential payloads are never forwarded. Each drawer has its own independent BLE server and receives its credentials directly from the mobile app.** However, three pieces of provisioning-related data *do* cross the STM32 bridge — and the timing is important:

#### Exact Bridge Message Timeline

```
Phase 0 – BLE Start (CONNECT_connectBLE called)
────────────────────────────────────────────────
  Drawer 1 generates passkey → gTriggerCMD = "BRIDGE_PASSKEY|<hex>"
  TRIGGERS_process() → myhardware.sendBridgeCmd(BRIDGE_PASSKEY, pkData, 4)
  Drawer 2 receives BRIDGE_PASSKEY → sets gBLE_PASSKEY → starts its own BLE (GOTO_BLE_START)

  ↑ The passkey is sent BEFORE any BLE provisioning happens.
    Both drawers now advertise simultaneously with the same passkey.

Phase 1 – Provisioning Begins on Drawer 1 (mobile app sends first BOF)
────────────────────────────────────────────────────────────────────────
  BLE.cpp onWrite(): gTriggerCMD = "BRIDGE_PROVISIONSTART"
  TRIGGERS_process(): if (gSYSTEM_drawer == 1)
      → myhardware.sendBridgeCmd(BRIDGE_PROVISIONSTART)
  Drawer 2 receives → shows "Drawer 1 Provisioning" UI screen

Phase 2 – Provisioning Complete on Drawer 1 (mobile app sends FINISHED)
────────────────────────────────────────────────────────────────────────
  BLE.cpp onWrite(): gTriggerCMD = "BRIDGE_PROVISIONEND"
  TRIGGERS_process(): if (gSYSTEM_drawer == 1)
      → myhardware.sendBridgeCmd(BRIDGE_PROVISIONEND)
  Drawer 2 receives → shows BLE waiting screen (ready for its own provisioning)
```

#### Summary: What Crosses the Bridge

| Data | Direction | When (exactly) |
|------|-----------|----------------|
| BLE passkey (4 bytes) | Drawer 1 → Drawer 2 | **At BLE advertising start** — before any mobile connection |
| `BRIDGE_PROVISIONSTART` | Drawer 1 → Drawer 2 | When **first BOF** is received from the mobile app |
| `BRIDGE_PROVISIONEND` | Drawer 1 → Drawer 2 | When **FINISHED** is received from the mobile app |
| `BRIDGE_STARTBLE` / `BRIDGE_STOPBLE` | 1↔2 | BLE lifecycle control |

#### What Never Crosses the Bridge

The actual credential payloads — Wi-Fi JSON, AWS config, PEM certificate, private key, Root CA — are **never relayed through the STM32 bridge**. After Drawer 1 is provisioned, the mobile app must independently connect to Drawer 2's BLE server and send the credentials directly to it.

The mobile app flow is:
1. Connect to **Drawer 1** (`FC751-XXXX`) → enter passkey → send all 5 credential files → send FINISHED
2. Connect to **Drawer 2** (`FC752-XXXX`) → enter same passkey → send all 5 credential files → send FINISHED

---

### Q3: What are the BLE security mechanisms?

The provisioning system implements a **multi-layer security model**:

#### Layer 1 – BLE Transport Security (Pairing)
| Mechanism | Detail |
|-----------|--------|
| **Secure Connections** | LE Secure Connections with ECDH key exchange |
| **MITM Protection** | Enabled — passkey entry required |
| **IO Capability** | `DISPLAY_ONLY` — device shows passkey, user must type it |
| **Encrypted Link** | All characteristic writes require `WRITE_ENC` |
| **Auth Enforcement** | `onAuthenticationComplete` disconnects any unencrypted client |

#### Layer 2 – Passkey Authentication
| Mechanism | Detail |
|-----------|--------|
| **Random passkey** | `esp_random()` → 100000–999999 (6 digits), unique per session |
| **NimBLE enforcement** | `setSecurityPasskey()` + `setSecurityAuth()` |
| **Failed attempt lockout** | Exponential backoff (5s, 10s) then permanent `BLE_LOCKED` state after 3 failures |
| **Numeric comparison rejected** | `onConfirmPassKey` always calls `injectConfirmPasskey(false)` |

#### Layer 3 – Protocol-Level Security
| Mechanism | Detail |
|-----------|--------|
| **BOF GUID** | Session start marker is a UUID GUID, not a dictionary word |
| **Buffer limit** | 10,000 bytes max per payload — prevents memory exhaustion attacks |
| **Session timeout** | 10-second inactivity timeout (BOF→EOF), session aborted if stalled |
| **Broadcast timer** | BLE advertising auto-stops after 5 minutes (provisioned devices) |
| **Out-of-session drops** | Data received outside BOF…EOF window is silently ignored |

#### Layer 4 – Storage Security
| Mechanism | Detail |
|-----------|--------|
| **AES-128-GCM** | Hardware-accelerated via mbedTLS on ESP32-S3 |
| **Random IV** | Fresh 12-byte IV generated per encryption (never reused) |
| **Auth tag** | 16-byte GCM tag detects any tampering with SPIFFS files |
| **NVS key** | Device-unique key derived from MAC + GUID via HKDF, stored in NVS |
| **Legacy migration** | Automatic re-encryption of ECB → GCM on first boot |

#### Layer 5 – Network Time Integrity
- Time is synced via HTTPS to an **AWS Lambda endpoint** (not plaintext NTP), satisfying TUV EN 18031 Finding #1.
- The Lambda URL is validated using the provisioned CA certificate.

---

## 11. Session Timeouts & Safety Limits

| Timeout | Value | Trigger | Action |
|---------|-------|---------|--------|
| BLE Broadcast Duration | **5 minutes** | No client connected (provisioned device) | `cancelBLE()` — stop advertising |
| Provisioning Session | **10 seconds** | Inactivity after any packet received | `cancelBLE()` — abort provisioning |
| BOF Session Stall | **10 seconds** | No chunk received after BOF | `cancelBLE()` — clear buffer |
| WAITING_FOR_BLE | **5 seconds** | Drawer 2 waiting for passkey from Drawer 1 | Drawer 2 self-generates passkey |
| BLE Backoff (1st fail) | **5 seconds** | Failed passkey attempt #1 | Stop advertising briefly |
| BLE Backoff (2nd fail) | **10 seconds** | Failed passkey attempt #2 | Stop advertising briefly |
| BLE Locked | **permanent** | Failed passkey attempt #3 | Advertising stopped; restart required |
| Buffer Overflow Limit | **10,000 bytes** | Single assembled payload exceeds limit | Session aborted |
| BLE Backoff Recovery | Per `backoffUntil` | Checked in `BLE::loop()` | Resume advertising after expiry |

> **Unprovisioned devices** keep BLE advertising active indefinitely (`broadcastTimer` is not enforced). This allows initial provisioning to complete even without a time constraint.

---

## 12. Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                       PROVISIONING FLOW                         │
└─────────────────────────────────────────────────────────────────┘

Boot (no credentials)
        │
        ▼
UNLINKED ──heartbeat──► Drawer 2 confirms ──► WELCOME_WAIT
        │
        ▼ (after welcome screen)
SKIP_CHECKUPLOAD_CHECK
        │
        ▼
GOTO_PROVISIONSTATE_NOT
        │
        ├─ Drawer 1: gBLE_PASSKEY = esp_random()
        ├─ Drawer 1: gTriggerCMD = "BRIDGE_PASSKEY|<hex>"
        │            (passkey sent to Drawer 2 via STM32 bridge)
        └─ Both: StartBLEbroadcast() → NimBLE server up
                          │
                          ▼
                  UNPROVISIONED / BLEBROADCASTING
                    (advertising: FC751-XXXX / FC752-XXXX)
                          │
                  Mobile App connects + enters passkey
                          │
                  NimBLE pairing (ECDH + passkey verification)
                          │
                          ▼
                  Encrypted BLE link established
                          │
            ┌─────────────┴───────────────┐
            │  for each of 5 credentials: │
            │                             │
            │  Write BOF ──────────────► assembleBLEBuffer("BOF")
            │  Write chunk 1 ──────────► buffer += chunk
            │  Write chunk 2 ──────────► buffer += chunk
            │  Write EOF ───────────────► assembled = buffer
            │                             handleProvisioningWrite()
            │                             → bleWriteQueue.push_back()
            └─────────────────────────────┘
                          │
            Write "FINISHED"
                          │
                          ▼
            stopBLEbroadcast()
            GOTO_PROVISIONING_COMPLETEDSETUP
                          │
                          ▼
            spiff.writeBLEpayload() × 5  (from queue, in BLE::loop())
            Each file: AES-128-GCM encrypt → SPIFFS write
                          │
                          ▼
            SETTINGS_load() → WIFI_connect() → AWS_connect()
                          │
                          ▼
                        ONLINE
```

---

## 13. Key Source Files Reference

| File | Responsibility |
|------|---------------|
| `BLE.cpp` / `BLE.h` | NimBLE server, GATT characteristics, security callbacks, BOF/EOF protocol, write queue |
| `config.h` | All UUIDs, BOF GUID, timeout constants, bridge command codes |
| `main.ino` | State machine, `CONNECT_connectBLE()`, `processBridgeCommands()`, `PROCESS_GOTOScreenCalls()` |
| `HARDWARE.cpp` / `HARDWARE.h` | STM32 UART framing, bridge frame encode/decode, `sendBridgeCmd()`, `hasBridgeFrame()` |
| `SPIFF_Manager.cpp` / `SPIFF_manager.h` | Encrypted SPIFFS file I/O, `writeBLEpayload()`, `checkProvisionState()`, NVS key management |
| `AES_helper.cpp` / `AES_helper.h` | AES-128-GCM encrypt/decrypt via mbedTLS, legacy ECB/CBC migration paths |

---

*Generated from firmware source analysis — FC75 v1.0.63*

