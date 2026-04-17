# FC75 BLE Provisioning Bridge — Full Protocol Specification

> **Target audience**: ESP-IDF engineers porting the FC75 provisioning subsystem.
> This document is derived entirely from the production Arduino firmware (v1.0.60)
> and can be used directly to generate real ESP-IDF code.

---

## Table of Contents

1. [System Architecture](#1-system-architecture)
2. [Physical Layer — UART](#2-physical-layer--uart)
3. [Bridge Frame Protocol](#3-bridge-frame-protocol)
4. [Bridge Payload Layout](#4-bridge-payload-layout)
5. [Bridge Command Reference](#5-bridge-command-reference)
6. [PASSKEY Frame — Deep Dive](#6-passkey-frame--deep-dive)
7. [Echo Filter](#7-echo-filter)
8. [BLE GATT Service](#8-ble-gatt-service)
9. [BLE Chunked Transfer Protocol (BOF / EOF / FINISHED)](#9-ble-chunked-transfer-protocol-bof--eof--finished)
10. [Provisioned Files — Format](#10-provisioned-files--format)
11. [AES Encryption at Rest](#11-aes-encryption-at-rest)
12. [Security Model](#12-security-model)
13. [Full State Machine — Drawer 1 (Top)](#13-full-state-machine--drawer-1-top)
14. [Full State Machine — Drawer 2 (Bottom)](#14-full-state-machine--drawer-2-bottom)
15. [STM32 Role — Transparent Relay](#15-stm32-role--transparent-relay)
16. [Architecture Note — Credential Flow](#16-architecture-note--credential-flow)
17. [ESP-IDF Port Checklist](#17-esp-idf-port-checklist)
18. [Constant Reference](#18-constant-reference)

---

## 1. System Architecture

```
┌────────────────────────────────────────────────────────────┐
│           Mobile App (iOS / Android)                       │
│  Connects via BLE to EACH drawer independently             │
└──────────────┬────────────────────────┬────────────────────┘
               │ BLE (NimBLE)           │ BLE (NimBLE)
               ▼                        ▼
┌──────────────────────┐    ┌──────────────────────┐
│  ESP32 — DRAWER 1    │    │  ESP32 — DRAWER 2    │
│  (deviceid / top)    │    │  (deviceid / bottom) │
│                      │    │                      │
│  • Full BLE GATT     │    │  • Full BLE GATT     │
│  • Writes creds to   │    │  • Writes creds to   │
│    own SPIFFS        │    │    own SPIFFS        │
│  • Connects to AWS   │    │  • Follows drawer 1  │
│  • Primary device    │    │    UI via bridge      │
└──────────┬───────────┘    └──────────┬───────────┘
           │ UART2 (GPIO17/18)         │ UART2 (GPIO17/18)
           │ 115200 8N1                │ 115200 8N1
           └────────────┬─────────────┘
                        │
              ┌─────────▼─────────┐
              │      STM32        │
              │  Hardware control │
              │                   │
              │  Bridge relay:    │
              │  receives frames  │
              │  from one ESP32,  │
              │  forwards to the  │
              │  other. NO store. │
              └───────────────────┘
```

**Key facts:**

| Item | Value |
|---|---|
| Primary BLE device | Drawer 1 (`gSYSTEM_drawer == 1`) |
| Drawer ID encoding | `1` = top, `2` = bottom |
| Drawer ID source | STM32 broadcasts device ID over UART on startup |
| AWS connected | Drawer 1 primarily; drawer 2 may also connect with the same creds |
| Bridge direction | Bidirectional ESP32↔STM32↔ESP32 |
| STM32 stores bridge data | **No** — purely transparent relay |

---

## 2. Physical Layer — UART

Both ESP32 drawers communicate with the STM32 over **UART2**.

**ESP32 side** (each drawer → STM32):

| Parameter | Value |
|---|---|
| ESP-IDF UART port | `UART_NUM_2` |
| RX pin (ESP32) | `GPIO 18` |
| TX pin (ESP32) | `GPIO 17` |
| Baud rate | `115200` |
| Frame format | `8N1` (8 data bits, no parity, 1 stop bit) |
| Buffer | Firmware uses a `std::vector<uint8_t>` ring buffer internally |

**STM32 side** (per the STM32 firmware author's spec):

| STM32 UART | Connected to | Direction |
|---|---|---|
| `UART1` | Top Drawer / ESP32-1 (Drawer 1) | Bridge ↔ |
| `UART6` | Bottom Drawer / ESP32-2 (Drawer 2) | Bridge ↔ |

```c
// ESP-IDF initialization equivalent
uart_config_t uart_cfg = {
    .baud_rate  = 115200,
    .data_bits  = UART_DATA_8_BITS,
    .parity     = UART_PARITY_DISABLE,
    .stop_bits  = UART_STOP_BITS_1,
    .flow_ctrl  = UART_HW_FLOWCTRL_DISABLE,
};
uart_param_config(UART_NUM_2, &uart_cfg);
uart_set_pin(UART_NUM_2, 17, 18, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
uart_driver_install(UART_NUM_2, 256, 256, 10, NULL, 0);
```

> **Note**: The same UART carries both regular STM32 telemetry frames (109-byte `0x8F..0x8E`
> format) and bridge frames (`0xDD 0xDA` header). The firmware distinguishes them by header
> byte scanning.

---

## 3. Bridge Frame Protocol

Every ESP32→ESP32 message is wrapped in a bridge frame. This frame is written to the UART
and the STM32 passes it through unchanged to the other drawer's UART RX.

### 3.1 Frame Layout

```
Byte offset  STM32 notation  Field           Size    Notes
──────────────────────────────────────────────────────────────────
0            [0]             HEADER_0        1       0xDD  (fixed sync)
1            [1]             HEADER_1        1       0xDA  (fixed sync)
2            [2]             RESERVED        1       0xFF
3            [3]             RESERVED        1       0xFF
4            [4]             RESERVED        1       0xFF
──────────────────────────── "meta" header boundary (5 bytes)
5            [5]             LEN_H           1       payload length, big-endian MSB
6            [6]             LEN_L           1       payload length, big-endian LSB
──────────────────────────── "meta" boundary ends (7 bytes total = BRIDGE_META_LEN)
7 … 7+N-1   [7+]            PAYLOAD         N       1 ≤ N ≤ 120 bytes
7+N          [n-1]           XOR_CHECKSUM    1       see §3.3 — XOR of ALL bytes 0 through n-2
──────────────────────────────────────────────────────────────────
Total max frame size: 128 bytes  (= BRIDGE_MAX_FRAME = STM32 RX_DATA_MAX)
```

> **STM32 spec alignment**: The STM32 author uses `[0]`–`[n-1]` absolute byte notation where
> `n = BRIDGE_META_LEN(7) + payload_len(N) + 1(checksum)`. The mapping is exact.

### 3.2 Constants

```c
#define BRIDGE_HEADER_0    0xDD
#define BRIDGE_HEADER_1    0xDA
#define BRIDGE_RESERVED    0xFF
#define BRIDGE_HEADER_LEN  5        // 0xDD 0xDA 0xFF 0xFF 0xFF
#define BRIDGE_META_LEN    7        // header(5) + length(2)
#define BRIDGE_MAX_PAYLOAD 120
#define BRIDGE_MAX_FRAME   128      // BRIDGE_META_LEN(7) + max_payload(120) + checksum(1)
```

### 3.3 Checksum Algorithm

> **Critical scope clarification**: The STM32 spec describes this as "XOR checksum of all
> data bytes (excluding checksum itself)". The word "data" here means **all pre-checksum
> bytes in the frame** — i.e., header bytes + length bytes + payload bytes (offsets 0 through
> `n-2`). It does **not** mean only the payload. The ESP32 firmware and STM32 firmware
> are in agreement on this; both XOR the full frame content before the checksum byte.

```c
uint8_t xor_val = 0;
for (size_t i = 0; i < frameLen - 1; i++) {
    xor_val ^= frame[i];  // XOR: header[0..4] + LEN[5..6] + payload[7..7+N-1]
}
frame[frameLen - 1] = xor_val;   // last byte = checksum
```

On receive, recalculate and compare:
```c
uint8_t calc = 0;
for (size_t i = 0; i < frameLen - 1; i++) calc ^= buf[i];
if (calc != buf[frameLen - 1])  // checksum mismatch → discard
```

Verification example (from STM32 spec):
```
Frame: DD DA FF FF FF 00 05 48 45 4C 4C 4F [CHKSUM]
XOR:   DD ^ DA ^ FF ^ FF ^ FF ^ 00 ^ 05 ^ 48 ^ 45 ^ 4C ^ 4C ^ 4F  =  CHKSUM
       (all 12 bytes before the checksum byte, NOT just "HELLO")
```

### 3.4 Frame Construction (ESP-IDF reference implementation)

```c
bool send_bridge_frame(uart_port_t port, const uint8_t *payload, size_t payload_len) {
    if (payload_len == 0 || payload_len > BRIDGE_MAX_PAYLOAD) return false;

    uint8_t frame[BRIDGE_MAX_FRAME];
    size_t frame_len = BRIDGE_META_LEN + payload_len + 1;  // +1 for XOR

    frame[0] = BRIDGE_HEADER_0;
    frame[1] = BRIDGE_HEADER_1;
    frame[2] = BRIDGE_RESERVED;
    frame[3] = BRIDGE_RESERVED;
    frame[4] = BRIDGE_RESERVED;
    frame[5] = (uint8_t)(payload_len >> 8);    // LEN_H
    frame[6] = (uint8_t)(payload_len & 0xFF);  // LEN_L

    memcpy(&frame[BRIDGE_META_LEN], payload, payload_len);

    uint8_t xor_val = 0;
    for (size_t i = 0; i < frame_len - 1; i++) xor_val ^= frame[i];
    frame[frame_len - 1] = xor_val;

    return uart_write_bytes(port, (const char *)frame, frame_len) == (int)frame_len;
}
```

### 3.5 Frame Extraction (ESP-IDF reference implementation)

```c
// Returns true if a valid non-echo frame was extracted from `ring_buf`.
// On success: out_payload filled, *out_len set, sender_id returned via *out_sender.
bool try_extract_bridge_frame(uint8_t *ring_buf, size_t *ring_len,
                              uint8_t *out_payload, size_t *out_len,
                              uint8_t *out_sender, uint8_t my_drawer_id)
{
    size_t sz = *ring_len;
    if (sz < BRIDGE_META_LEN + 1) return false;

    for (size_t i = 0; i + BRIDGE_META_LEN <= sz; i++) {
        if (ring_buf[i]   != BRIDGE_HEADER_0 ||
            ring_buf[i+1] != BRIDGE_HEADER_1 ||
            ring_buf[i+2] != BRIDGE_RESERVED  ||
            ring_buf[i+3] != BRIDGE_RESERVED  ||
            ring_buf[i+4] != BRIDGE_RESERVED) continue;

        // discard garbage before header
        if (i > 0) {
            memmove(ring_buf, ring_buf + i, sz - i);
            *ring_len = sz - i;
            return try_extract_bridge_frame(ring_buf, ring_len,
                                            out_payload, out_len, out_sender, my_drawer_id);
        }

        uint16_t payload_len = ((uint16_t)ring_buf[5] << 8) | ring_buf[6];
        if (payload_len == 0 || payload_len > BRIDGE_MAX_PAYLOAD) {
            memmove(ring_buf, ring_buf + BRIDGE_HEADER_LEN, sz - BRIDGE_HEADER_LEN);
            *ring_len = sz - BRIDGE_HEADER_LEN;
            return false;
        }

        size_t frame_len = BRIDGE_META_LEN + payload_len + 1;
        if (sz < frame_len) return false;  // partial frame, wait for more bytes

        // validate XOR checksum
        uint8_t xor_val = 0;
        for (size_t j = 0; j < frame_len - 1; j++) xor_val ^= ring_buf[j];
        if (xor_val != ring_buf[frame_len - 1]) {
            memmove(ring_buf, ring_buf + BRIDGE_HEADER_LEN, sz - BRIDGE_HEADER_LEN);
            *ring_len = sz - BRIDGE_HEADER_LEN;
            return false;
        }

        // echo filter: payload[0] is sender drawer ID
        uint8_t sender_id = ring_buf[BRIDGE_META_LEN];
        if (sender_id == my_drawer_id) {  // discard echoes of our own frames
            memmove(ring_buf, ring_buf + frame_len, sz - frame_len);
            *ring_len = sz - frame_len;
            return false;
        }

        // valid frame — copy payload
        memcpy(out_payload, &ring_buf[BRIDGE_META_LEN], payload_len);
        *out_len    = payload_len;
        *out_sender = sender_id;

        memmove(ring_buf, ring_buf + frame_len, sz - frame_len);
        *ring_len = sz - frame_len;
        return true;
    }
    return false;
}
```

---

## 4. Bridge Payload Layout

Every payload byte `[0]` is always the **sender drawer ID** (1 or 2).
The byte layout depends on which helper was used to send.

### 4.1 Single command byte — `sendBridgeCmd(uint8_t cmd)`

```
payload[0] = sender_id   (uint8_t, value 1 or 2)
payload[1] = cmd         (uint8_t, see §5)

payloadLen = 2
```

### 4.2 Command + data — `sendBridgeCmd(uint8_t cmd, const uint8_t* data, size_t dataLen)`

```
payload[0]           = sender_id
payload[1]           = cmd
payload[2 … 2+N-1]   = data[0 … N-1]

payloadLen = 2 + dataLen  (dataLen ≤ 118, i.e. BRIDGE_MAX_PAYLOAD - 2)
```

### 4.3 Raw ASCII string — `sendBridgeCommand(const char* str)`

```
payload[0]           = sender_id
payload[1 … 1+len-1] = ASCII bytes of str (NOT null-terminated in the frame)

payloadLen = 1 + strlen(str)
```

Used by the `BRIDGE_SEND` trigger for arbitrary ASCII commands (e.g. `"BEEP_ACK"`).

---

## 5. Bridge Command Reference

All ESP32↔ESP32 bridge commands are single bytes in `payload[1]`.

| Constant | Hex | `payload` structure | Who sends | Receiver action |
|---|---|---|---|---|
| `BRIDGE_STARTBLE` | `0xE1` | `[sender][0xE1]` | Either drawer (UI or AWS cmd) | `GOTO_BLE_START` (start local BLE broadcast + passkey display) |
| `BRIDGE_STOPBLE` | `0xE2` | `[sender][0xE2]` | Either drawer (BLE cancel or timeout) | `GOTO_UI_CANCELBLE` (stop local BLE, return to idle) |
| `BRIDGE_FACTORYRESET` | `0xE3` | `[sender][0xE3]` | Either drawer (UI) | `GOTO_PROVISIONING_FACTORYRESET` (wipe settings, reboot) |
| `BRIDGE_WELCOMECONTINUE` | `0xE4` | `[sender][0xE4]` | Either drawer (UI welcome confirmed) | `GOTO_SKIP_CHECKUPLOAD_CHECK` (advance past welcome screen) |
| `BRIDGE_SKIPPROVISIONING` | `0xE5` | `[sender][0xE5]` | Either drawer (UI skip) | `GOTO_PROVISIONING_SKIP` (skip BLE provisioning) |
| `BRIDGE_PROVISIONSTART` | `0xE6` | `[sender][0xE6]` | **Drawer 1 only** (BLE BOF received) | `load_screen(33)` — "other drawer provisioning in progress" UI |
| `BRIDGE_PROVISIONEND` | `0xE7` | `[sender][0xE7]` | **Drawer 1 only** (BLE FINISHED received) | `load_screen(8)` — return to BLE waiting screen |
| `BRIDGE_HEARTBEAT` | `0xE8` | `[sender][0xE8]` | Either drawer (periodic) | (logged, no action yet) |
| `BRIDGE_PASSKEY` | `0xE9` | `[sender][0xE9][B3][B2][B1][B0]` | **Drawer 1 only** (on BLE start) | Store passkey in `gBLE_PASSKEY`, display on screen |

> **Guard**: `BRIDGE_PROVISIONSTART` and `BRIDGE_PROVISIONEND` are only **sent** when
> `gSYSTEM_drawer == 1`. The receiver checks `gSYSTEM_drawer == 2` before acting.

---

## 6. PASSKEY Frame — Deep Dive

The 6-digit numeric BLE passkey is shared between the two drawers so both displays show the
same passcode during the BLE pairing step.

### 6.1 Passkey generation (Drawer 1, once per BLE session)

```c
// In BLE::StartBLEbroadcast() or at GOTO_BLE_START / GOTO_PROVISIONSTATE_NOT
extern uint32_t gBLE_PASSKEY;
if (gBLE_PASSKEY == 0) {
    gBLE_PASSKEY = (esp_random() % 900000) + 100000;  // range [100000, 999999]
}
```

### 6.2 Sending (Drawer 1 → STM32 → Drawer 2)

Done via `TRIGGERS_process()` whenever Drawer 1 enters a BLE state:

```c
// Triggered from GOTO_BLE_START and GOTO_PROVISIONSTATE_NOT:
if (gSYSTEM_drawer == 1 && gBLE_PASSKEY != 0) {
    char hexBuf[24];
    snprintf(hexBuf, sizeof(hexBuf), "BRIDGE_PASSKEY|%06lX", (unsigned long)gBLE_PASSKEY);
    gTriggerCMD = hexBuf;   // e.g. "BRIDGE_PASSKEY|01E240"
}

// In TRIGGERS_process() handler for "BRIDGE_PASSKEY":
uint32_t pk = strtoul(tokens[1].c_str(), nullptr, 16);  // parse hex string
uint8_t pkData[4];
pkData[0] = (pk >> 24) & 0xFF;   // big-endian
pkData[1] = (pk >> 16) & 0xFF;
pkData[2] = (pk >>  8) & 0xFF;
pkData[3] =  pk        & 0xFF;
myhardware.sendBridgeCmd(config::TX_CMD::BRIDGE_PASSKEY, pkData, 4);
```

Resulting bridge payload:
```
[sender_id=1] [0xE9] [pk_B3] [pk_B2] [pk_B1] [pk_B0]
total payload = 6 bytes
```

### 6.3 Receiving (Drawer 2, in `processBridgeCommands()`)

```c
case config::TX_CMD::BRIDGE_PASSKEY:
{
    uint8_t buf[BRIDGE_MAX_PAYLOAD];
    size_t len = myhardware.getBridgePayload(buf, sizeof(buf));
    if (len >= 6) {  // sender(1) + cmd(1) + data(4)
        gBLE_PASSKEY = ((uint32_t)buf[2] << 24)
                     | ((uint32_t)buf[3] << 16)
                     | ((uint32_t)buf[4] <<  8)
                     |  (uint32_t)buf[5];
        // gBLE_PASSKEY is now shown on Drawer 2's display
    }
    break;
}
```

### 6.4 Passkey use in NimBLE pairing (Drawer 1)

```c
// BLE::ServerCallbacks::onPassKeyDisplay() — called by NimBLE when peer requests passkey
uint32_t ServerCallbacks::onPassKeyDisplay() {
    return gBLE_PASSKEY;   // display this to the user as the pin
}

// BLE::ServerCallbacks::onConfirmPassKey() — called when user enters passkey on app
void ServerCallbacks::onConfirmPassKey(NimBLEConnInfo& connInfo, uint32_t pass_key) {
    NimBLEDevice::injectConfirmPasskey(connInfo, true);  // accept passkey unconditionally
}

// BLE::ServerCallbacks::onAuthenticationComplete()
void ServerCallbacks::onAuthenticationComplete(NimBLEConnInfo& connInfo) {
    if (!connInfo.isEncrypted()) {
        NimBLEDevice::getServer()->disconnect(connInfo.getConnHandle()); // reject unencrypted
    }
}
```

---

## 7. Echo Filter

Since both ESP32 drawers share the same shared UART bus through STM32, a frame sent by
Drawer 1 may be echoed back. The firmware discards any frame whose `payload[0]` (sender ID)
equals the current device's own drawer number.

```c
uint8_t senderId = buf[BRIDGE_META_LEN];   // payload[0]
if (senderId == (uint8_t)gSYSTEM_drawer) {
    // discard echo — this came from ourselves
    buf.erase(buf.begin(), buf.begin() + frameLen);
    return false;
}
```

---

## 8. BLE GATT Service

### 8.1 Service UUID

```
f920c71f-0619-4efe-a77f-c209cd1a38bb
```

### 8.2 Characteristics

| Characteristic | UUID | Properties | Destination SPIFFS path |
|---|---|---|---|
| `CHARACTERISTIC_WIFI` | `6f4c480e-93c1-4a6d-bca8-3ac1a6a7d443` | WRITE | `/wifi.json` |
| `CHARACTERISTIC_AWS_CONFIG` | `14dd1c82-15dd-4215-87ce-956fbb5e67e5` | WRITE | `/aws_config.json` |
| `CHARACTERISTIC_CERT` | `547e55cc-f38c-488a-9e95-588188d69935` | WRITE | `/cert.pem` |
| `CHARACTERISTIC_KEY` | `9076c747-07f3-444b-b119-288799fc30b6` | WRITE | `/priv.key` |
| `CHARACTERISTIC_CA` | `ded6967f-df95-48fc-863d-d4821fadf662` | WRITE | `/ca.pem` |
| `CHARACTERISTIC_MAC` | `2c9b3c4a-5e2f-4c9a-9a2d-9f2e8d6a41c7` | WRITE + READ | (utility) |

All provisioning characteristics are **write-only**. The MAC characteristic is a utility
helper: write `"GETMAC"` to it and the firmware sets the characteristic value to the
device's Wi-Fi MAC string (`"XX:XX:XX:XX:XX:XX"`), which the app can then read back.

### 8.3 BLE Server Setup

```c
NimBLEDevice::init("FC75-Server");    // temporary name; overwritten before advertising
NimBLEDevice::setMTU(512);            // 512-byte MTU (maximum ESP32 NimBLE)

// Dynamic device name: "FC75<drawer>-<last4MACnoColons>"
// Example: "FC751-C3A1"
String deviceName = "FC75" + String(gSYSTEM_drawer) + "-" + macSuffix;
NimBLEDevice::getAdvertising()->setName(deviceName.c_str());
```

### 8.4 BLE Broadcast Duration

```c
// 5 minutes from the moment broadcasting starts
static constexpr unsigned long BLE_BROADCAST_DURATION_MS = 5UL * 60UL * 1000UL;

// Timer is reset to +5 min each time a BLE client connects
void BLE::resetBLEtimer() {
    broadcastTimer = millis() + BLE_BROADCAST_DURATION_MS;
}
```

---

## 9. BLE Chunked Transfer Protocol (BOF / EOF / FINISHED)

BLE MTU is 512 bytes but provisioning files (PEM certs, JSON) can be several kilobytes.
The firmware implements a simple session protocol on top of raw BLE characteristic writes.

### 9.1 Protocol Markers

| Marker | Wire value | Purpose |
|---|---|---|
| BOF | `"24e5c9e1-0d89-4ae4-9bf1-3e77b309c2a8"` (GUID string) | Begin of file — clears buffer, starts session |
| EOF | `"EOF"` | End of file — assembles and returns buffer |
| FINISHED | `"FINISHED"` | End of entire provisioning session |

> The BOF string is a GUID (not the literal text "BOF") for security obfuscation.

### 9.2 Per-File Transfer Sequence (repeated for each credential)

```
Mobile App                                  ESP32 (Drawer 1)
────────────────────────────────────────────────────────────
write CHARACTERISTIC_X ← "24e5c9e1-..."   [BOF] → buffer cleared, session opened
                                            → sets gOVERRIDEcommands = GOTO_PROVISIONING_START
                                            → sets gTriggerCMD = "BRIDGE_PROVISIONSTART"
                                              (only on first file / at session start)

write CHARACTERISTIC_X ← chunk_1           buffer += chunk_1
write CHARACTERISTIC_X ← chunk_2           buffer += chunk_2
       …
write CHARACTERISTIC_X ← chunk_N           buffer += chunk_N

write CHARACTERISTIC_X ← "EOF"            [EOF] → assembled = buffer
                                            → handleProvisioningWrite(assembled, path)
                                              (queued to bleWriteQueue for async SPIFFS write)
                                            → provisioningCurrentFile++
```

### 9.3 Session End

```
Mobile App                                  ESP32 (Drawer 1)
────────────────────────────────────────────────────────────
write ANY_CHARACTERISTIC ← "FINISHED"      → stopBLEbroadcast()     (tears down NimBLE stack)
                                            → gTriggerCMD = "BRIDGE_PROVISIONEND"
                                            → gOVERRIDEcommands = GOTO_PROVISIONING_COMPLETEDSETUP
```

### 9.4 Buffer Limits and Timeouts

| Parameter | Value |
|---|---|
| `TRANSMISSIONLIMIT` | 10 000 bytes — session aborted if buffer exceeds this |
| `bleSessionTimeout` | 10 000 ms — reset on every chunk; abort if no chunk arrives within 10 s after BOF |
| `provisioningSessionTimeout` | 10 000 ms — per-provisioning-session watchdog; abort if overall session stalls 10 s |

On any timeout or limit violation:
```c
bufferingInProgress = false;
bleBuffer.clear();
gTriggerCMD = "BRIDGE_STOPBLE";
gOVERRIDEcommands = GOTO_UI_CANCELBLE;
```

### 9.5 Deferred Queue Write

`handleProvisioningWrite()` does **not** write to SPIFFS immediately. It pushes to a
`std::vector<BLEWriteTask>` queue. The main loop drains **one task per iteration**:

```c
if (!bleWriteQueue.empty() && spiff) {
    BLEWriteTask task = bleWriteQueue.front();
    bleWriteQueue.erase(bleWriteQueue.begin());
    spiff->writeBLEpayload(task.data, task.path.c_str());
}
```

This prevents blocking the BLE stack during large SPIFFS writes.

### 9.6 Progress Counter

```c
int provisioningTotalFiles = 5;   // always 5 (wifi, aws_config, cert, key, ca)
int provisioningCurrentFile = 0;  // incremented after each EOF write
// Reset to 0 at the start of BLE::begin() (every new BLE session)
```

The display reads `provisioningCurrentFile` and `provisioningTotalFiles` to show a progress bar.

### 9.7 `onWrite` Dispatch (ESP-IDF reference implementation)

```c
// Called for each characteristic write event (all 5 provisioning characteristics share one handler)
void on_write(const char *uuid, const uint8_t *data, size_t len) {
    // Convert raw bytes to string
    char str[len + 1];
    memcpy(str, data, len);
    str[len] = '\0';

    // MAC characteristic: utility path, not part of provisioning
    if (strcmp(uuid, CHARACTERISTIC_MAC) == 0) {
        if (strcmp(str, "GETMAC") == 0) {
            // set characteristic value to MAC string
        }
        return;
    }

    if (strcmp(str, BLEFINISHED) == 0) {            // "FINISHED"
        trigger_bridge_provisionend();               // → BRIDGE_PROVISIONEND
        finalize_provisioning();                     // → GOTO_PROVISIONING_COMPLETEDSETUP
        ble_stop_broadcast();

    } else if (strcmp(str, BLEBOF) == 0) {          // GUID
        override_goto(GOTO_PROVISIONING_START);
        trigger_bridge_provisionstart();             // → BRIDGE_PROVISIONSTART
        ble_assemble_buffer(BLEBOF);                 // clears buffer, opens session

    } else if (strcmp(str, BLEEOF) == 0) {          // "EOF"
        char *assembled = ble_assemble_buffer(BLEEOF); // drains buffer

        // Dispatch by UUID to the correct SPIFFS path
        const char *path = get_path_for_uuid(uuid); // see table §8.2
        if (path) queue_spiffs_write(assembled, path);

        provisioning_current_file++;

    } else {                                         // data chunk
        ble_assemble_buffer(str);                    // append to buffer
    }
}
```

---

## 10. Provisioned Files — Format

All five files are AES-encrypted before storage (see §11).
Their plaintext content is:

### 10.1 `/wifi.json`

```json
{
  "ssid": "MyWiFiNetwork",
  "password": "MyWiFiPassword",
  "mac": "AA:BB:CC:DD:EE:FF"
}
```

Fields `ssid` and `password` are mandatory for `checkProvisionState()` to pass.
`mac` is optional.

### 10.2 `/aws_config.json`

```json
{
  "endpoint": "xxxxxxxxxxxxxx.iot.ca-central-1.amazonaws.com",
  "thingname": "FC751-C3A1",
  "clientId":  "FC751-C3A1",
  "assets":    "fc75assets",
  "language":  "EN_Lang"
}
```

Fields `endpoint`, `thingname`, and `clientId` are mandatory.
`assets` and `language` are optional but used for OTA/asset download and UI language.

### 10.3 `/cert.pem`

Standard AWS IoT device certificate in PEM format:
```
-----BEGIN CERTIFICATE-----
MIIDWTCCAkGgAwIBAgIUQH7PBSL...
-----END CERTIFICATE-----
```

### 10.4 `/priv.key`

AWS IoT device private key in PEM format:
```
-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA...
-----END RSA PRIVATE KEY-----
```

### 10.5 `/ca.pem`

Amazon Root CA1 in PEM format:
```
-----BEGIN CERTIFICATE-----
MIIDQTCCAimgAwIBAgITBmyfz5m...
-----END CERTIFICATE-----
```

The firmware trims everything before `-----BEGIN` and after `-----END CERTIFICATE-----`
when loading the CA cert.

---

## 11. AES Encryption at Rest

All provisioning files are stored AES-encrypted in SPIFFS via `SPIFF_Manager::saveEncrypted()`
and loaded via `SPIFF_Manager::readDecrypted()`.

```c
// config.h
static constexpr const char* AES_KEY = "3A7F2B6D91C84E1A";  // 16-byte key (AES-128)
```

The raw key is a 16-character ASCII string used directly as the AES key bytes.
Implementation uses mbedTLS AES-ECB (or equivalent Arduino AES helper in `AES_helper.cpp`).

> **ESP-IDF port note**: Use `mbedtls_aes_context` with `mbedtls_aes_setkey_enc/dec` and
> `mbedtls_aes_crypt_ecb` (or CBC, check `AES_helper.cpp` for the exact mode).

---

## 12. Security Model

| Mechanism | Detail |
|---|---|
| BLE passkey | 6-digit numeric [100000–999999], randomly generated via `esp_random()` |
| BLE pairing mode | NimBLE passkey display/confirm — encryption **required** before any write is accepted |
| BOF as GUID | BOF marker is a UUID string (not guessable) to prevent accidental session starts |
| Buffer limit | 10 000 bytes max per file transfer — protects RAM |
| Unencrypted disconnect | If `connInfo.isEncrypted()` is false after auth, firmware disconnects the client |
| SPIFFS encryption | AES-128 at rest; plaintext never persisted |

---

## 13. Full State Machine — Drawer 1 (Top)

```
Power-on → checkProvisionState()
│
├─ provisioned = false ────────────────────────────────────────────────────┐
│                                                                          │
│  GOTO_PROVISIONSTATE_NOT                                                 │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ 1. load_screen(1)  [not-provisioned prompt]                       │   │
│  │ 2. CONNECT_connectWIFI(0)  [disconnect wifi]                      │   │
│  │ 3. myble.StartBLEbroadcast()                                      │   │
│  │    → esp_random() → gBLE_PASSKEY = [100000..999999]               │   │
│  │    → BLE::begin()  (setup NimBLE, advertise "FC751-XXXX")         │   │
│  │    → broadcastTimer = now + 5 min                                 │   │
│  │ 4. if drawer1 && passkey!=0: gTriggerCMD = "BRIDGE_PASSKEY|XXXXXX"│   │
│  │    → TRIGGERS_process() → sendBridgeCmd(0xE9, [B3,B2,B1,B0], 4) │   │
│  │ 5. gDeviceStatus = UNPROVISIONED                                  │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  Mobile App scans BLE → finds "FC751-XXXX" → connects                   │
│  → ServerCallbacks::onConnect() → resetBLEtimer() (extend to +5 min)    │
│  → ServerCallbacks::onPassKeyDisplay() → returns gBLE_PASSKEY            │
│  → User inputs passkey in app                                            │
│  → ServerCallbacks::onConfirmPassKey() → NimBLEDevice::injectConfirmPasskey(true)
│  → ServerCallbacks::onAuthenticationComplete() → verify encrypted        │
│                                                                          │
│  For each of 5 files (wifi, aws_config, cert, key, ca):                  │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ App writes BOF to CHARACTERISTIC_X                               │    │
│  │ → gOVERRIDEcommands = GOTO_PROVISIONING_START                    │    │
│  │ → gTriggerCMD = "BRIDGE_PROVISIONSTART"                          │    │
│  │ → TRIGGERS_process() → sendBridgeCmd(0xE6)  [drawer1 only]      │    │
│  │ → assembleBLEBuffer(BOF)  → buffer cleared, session open         │    │
│  │                                                                  │    │
│  │ App writes chunk_1 … chunk_N to CHARACTERISTIC_X                 │    │
│  │ → assembleBLEBuffer(chunk)  → buffer += chunk                    │    │
│  │                                                                  │    │
│  │ App writes EOF to CHARACTERISTIC_X                               │    │
│  │ → assembled = assembleBLEBuffer(EOF)  → returns full buffer      │    │
│  │ → handleProvisioningWrite(assembled, path)  → bleWriteQueue push │    │
│  │ → provisioningCurrentFile++                                      │    │
│  │ → main loop drains queue → spiff.writeBLEpayload(data, path)     │    │
│  │   (AES-encrypts and writes to SPIFFS)                            │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  App writes FINISHED to ANY characteristic                               │
│  → gTriggerCMD = "BRIDGE_PROVISIONEND"                                   │
│  → gOVERRIDEcommands = GOTO_PROVISIONING_COMPLETEDSETUP                  │
│  → stopBLEbroadcast()  (NimBLE deinit)                                   │
│                                                                          │
│  GOTO_PROVISIONING_COMPLETEDSETUP                                        │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ 1. load_screen(16)  [provisioning completed screen]              │   │
│  │ 2. spiff.setSystemDetailByField(PROVISIONED, "1")                │   │
│  │ 3. Load language from aws_config.json → gSYSTEM_LANG             │   │
│  │ 4. gSYSTEM_PROVISIONED = true                                    │   │
│  │ 5. CONNECT_connectBLE(0)  [stop BLE]                             │   │
│  │ 6. SETTINGS_load()  [reload all settings from SPIFFS]            │   │
│  │ 7. gAlertNextCommand = GOTO_TESTWIFI                             │   │
│  │ 8. gOVERRIDEcommands = GOTO_ALERT_DISPLAY → then GOTO_TESTWIFI  │   │
│  │    → WIFI_connect()  [connect with new credentials]              │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────┘
```

### 13.1 Drawer ID discovery at boot

```c
// main.ino loop — when STM32 broadcasts device_id:
if (myhardware.device_id >= 1 && myhardware.device_id <= 2
    && gSYSTEM_drawer != myhardware.device_id) {
    gSYSTEM_drawer = myhardware.device_id;
    spiff.setSystemDetailByField(SPIFF_Manager::DRAWER, String(gSYSTEM_drawer));
}
```

The STM32 assigns drawer IDs (1 or 2). The ESP32 reads this from the regular 109-byte
telemetry frame and persists to SPIFFS.

---

## 14. Full State Machine — Drawer 2 (Bottom)

Drawer 2 runs the **identical firmware** but takes a passive role during provisioning.
It receives bridge commands from the STM32 and mirrors screen state.

```
Power-on
│
├─ Drawer 2 is unprovisioned:
│  → goes to UNPROVISIONED state → starts own BLE broadcast (same flow as Drawer 1)
│  → Mobile app connects and provisions Drawer 2 independently via BLE
│  (same BLE GATT service, same characteristics, same BOF/EOF/FINISHED protocol)
│
└─ Bridge events received from Drawer 1 during Drawer 1's provisioning session:

   Receive BRIDGE_PASSKEY (0xE9):
   → gBLE_PASSKEY = reconstructed from 4 data bytes
   → shown on Drawer 2 display so user sees same passcode

   Receive BRIDGE_STARTBLE (0xE1):
   → if NOT in a running/active job state:
   →   gOVERRIDEcommands = GOTO_BLE_START
   →   starts own BLE broadcast
   →   extends own passkey display

   Receive BRIDGE_PROVISIONSTART (0xE6):
   → if gSYSTEM_drawer == 2:
   →   load_screen(33)  ["other drawer provisioning in progress"]

   Receive BRIDGE_PROVISIONEND (0xE7):
   → if gSYSTEM_drawer == 2:
   →   load_screen(8)   [return to BLE waiting screen]

   Receive BRIDGE_STOPBLE (0xE2):
   → gOVERRIDEcommands = GOTO_UI_CANCELBLE
   → stops own BLE, returns to idle

   Receive BRIDGE_FACTORYRESET (0xE3):
   → gOVERRIDEcommands = GOTO_PROVISIONING_FACTORYRESET
   → wipes provisioning files, reboots

   Receive BRIDGE_WELCOMECONTINUE (0xE4):
   → if gDeviceStatus == WELCOME_WAIT:
   →   gOVERRIDEcommands = GOTO_SKIP_CHECKUPLOAD_CHECK

   Receive BRIDGE_SKIPPROVISIONING (0xE5):
   → gOVERRIDEcommands = GOTO_PROVISIONING_SKIP
   → sets SKIP_PROVISIONING=1 in SPIFFS
   → gDeviceStatus = NO_INTERNET  (operates without credentials)
```

---

## 15. STM32 Role — Transparent Relay

The STM32 does **not parse or store** bridge frames. It detects the `0xDD 0xDA` header
prefix and forwards the entire frame byte-for-byte to the other UART port — **including
the original header and checksum, untouched**.

**STM32 UART port assignments** (confirmed by STM32 firmware author):

| STM32 port | Connected to | Notes |
|---|---|---|
| `UART1` | Drawer 1 ESP32 (Top) | ESP32 uses UART2 / GPIO17-18 |
| `UART6` | Drawer 2 ESP32 (Bottom) | ESP32 uses UART2 / GPIO17-18 |

From the perspective of both ESP32 drawers, the bridge is a **transparent bidirectional
UART pipe**. The only STM32 action is forwarding.

STM32 implementation pseudocode:
```c
// STM32 main loop — both UART channels
uint8_t b;
if (uart1_available()) {                         // Drawer 1 (Top) sending
    b = uart1_read();
    if (in_bridge_frame || b == 0xDD)
        forward_bridge_byte(UART6, b);           // forward to Drawer 2 (Bottom)
    else
        handle_normal_stm32_protocol(b);         // 0x8F..0x8E sensor/control frames
}
if (uart6_available()) {                         // Drawer 2 (Bottom) sending
    b = uart6_read();
    if (in_bridge_frame || b == 0xDD)
        forward_bridge_byte(UART1, b);           // forward to Drawer 1 (Top)
    else
        handle_normal_stm32_protocol(b);
}
```

---

## 16. Architecture Note — Credential Flow

> **Important**: Based on the production firmware source code, provisioning credential data
> (WiFi SSID/password, AWS certs, private key) is **NOT** relayed via the bridge protocol.

The actual credential flow is:

```
Mobile App ──[BLE]──→ Drawer 1 GATT → SPIFFS (Drawer 1's own flash)
Mobile App ──[BLE]──→ Drawer 2 GATT → SPIFFS (Drawer 2's own flash)
```

Each drawer must be independently provisioned by the mobile app.
The bridge protocol handles only:

1. **Passkey sync** (`BRIDGE_PASSKEY`) — so both drawers display the same 6-digit pin
2. **BLE session sync** (`BRIDGE_STARTBLE` / `BRIDGE_STOPBLE`) — coordinated start/stop
3. **UI state notification** (`BRIDGE_PROVISIONSTART` / `BRIDGE_PROVISIONEND`) — screen changes
4. **Navigation commands** (`BRIDGE_WELCOMECONTINUE`, `BRIDGE_SKIPPROVISIONING`, `BRIDGE_FACTORYRESET`)

If your design requires Drawer 1 to relay credential data to Drawer 2 via bridge, the
bridge frame protocol (§3) supports payloads up to 120 bytes. For files larger than
118 bytes (120 − 2 for sender_id + cmd), you would need to implement fragmentation:
split the file into 116-byte chunks, add a sequence number byte, and reassemble on the
receiving side.

---

## 17. ESP-IDF Port Checklist

| Task | Details |
|---|---|
| UART driver | `uart_driver_install(UART_NUM_2, …)`, GPIO17=TX, GPIO18=RX, 115200 8N1 |
| Bridge RX task | FreeRTOS task reading UART into ring buffer, calling `try_extract_bridge_frame()` |
| Bridge TX | `send_bridge_frame()` from §3.4; protect with mutex if called from multiple tasks |
| NimBLE init | `nimble_port_init()`, `ble_hs_cfg.reset_cb/sync_cb`, set MTU to 512 |
| GATT service | Register 6 characteristics (§8.2); write handler triggers BOF/EOF/FINISHED protocol |
| Passkey pairing | `ble_sm_pair_params` with `BLE_SM_IO_CAP_DISP_ONLY`, confirm via `ble_sm_inject_io()` |
| SPIFFS | `esp_vfs_spiffs_register()`, file paths in §10, AES-128 via mbedTLS (key = `"3A7F2B6D91C84E1A"`) |
| Drawer ID | Read from STM32 telemetry frame (regular 109-byte 0x8F/0x8E protocol), persist to NVS |
| `gBLE_PASSKEY` | `esp_random()` per session in range [100000, 999999] |
| BLE timeout | 5-minute software timer; reset on each client connect |
| Session timeout | 10-second watchdog per chunk — abort on stall |
| Buffer limit | Abort if assembled > 10 000 bytes |
| Deferred queue | Process one SPIFFS write per main-loop yield (not inside BLE event handler) |
| Bridge echo filter | Discard frames where `payload[0] == own_drawer_id` |
| Bridge XOR checksum | XOR of all bytes except the checksum byte itself (see §3.3) |

---

## 18. Constant Reference

### BLE constants

| Name | Value |
|---|---|
| `BLE_BROADCAST_DURATION_MS` | `300 000` (5 min) |
| `TRANSMISSIONLIMIT` | `10 000` bytes |
| `BLEBOF` | `"24e5c9e1-0d89-4ae4-9bf1-3e77b309c2a8"` |
| `BLEEOF` | `"EOF"` |
| `BLEFINISHED` | `"FINISHED"` |
| MTU | `512` bytes |
| Passkey range | `[100000, 999999]` |

### Bridge frame constants

| Name | Value |
|---|---|
| `BRIDGE_HEADER_0` | `0xDD` |
| `BRIDGE_HEADER_1` | `0xDA` |
| `BRIDGE_RESERVED` | `0xFF` |
| `BRIDGE_HEADER_LEN` | `5` |
| `BRIDGE_META_LEN` | `7` |
| `BRIDGE_MAX_PAYLOAD` | `120` |
| `BRIDGE_MAX_FRAME` | `128` |

### Bridge command bytes

| Name | Hex |
|---|---|
| `BRIDGE_STARTBLE` | `0xE1` |
| `BRIDGE_STOPBLE` | `0xE2` |
| `BRIDGE_FACTORYRESET` | `0xE3` |
| `BRIDGE_WELCOMECONTINUE` | `0xE4` |
| `BRIDGE_SKIPPROVISIONING` | `0xE5` |
| `BRIDGE_PROVISIONSTART` | `0xE6` |
| `BRIDGE_PROVISIONEND` | `0xE7` |
| `BRIDGE_HEARTBEAT` | `0xE8` |
| `BRIDGE_PASSKEY` | `0xE9` |

### UART / SPIFFS paths

| Name | Value |
|---|---|
| UART port | `UART_NUM_2` |
| RX pin | `GPIO 18` |
| TX pin | `GPIO 17` |
| Baud | `115200` |
| AES-128 key | `"3A7F2B6D91C84E1A"` |
| `/wifi.json` | WiFi SSID + password |
| `/aws_config.json` | AWS endpoint + thingname + clientId |
| `/cert.pem` | Device certificate PEM |
| `/priv.key` | Private key PEM |
| `/ca.pem` | Root CA certificate PEM |

---

*Document generated from FC75 firmware v1.0.60 (2026-02-06)*
