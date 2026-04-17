---
mode: agent
description: Implement the FC75 ESP32-to-ESP32 bridge protocol for an ESP-IDF project, following the FC75 BLE Provisioning Bridge Specification.
---

# Implement FC75 Bridge Protocol (ESP-IDF)

You are implementing the **FC75 ESP32-to-ESP32 UART bridge protocol** for an ESP-IDF project.
The protocol is fully specified in `BLE_PROVISIONING_BRIDGE_SPEC.md` (attached to this project).
Read that file in full before writing any code.

Follow every step below in order. Do not skip steps. Do not add features not listed here.

---

## Step 1 — Create `bridge_protocol.h`

Create the header `components/bridge/include/bridge_protocol.h`.

Define the following:

```c
// Frame constants (must match BLE_PROVISIONING_BRIDGE_SPEC.md §3.2)
#define BRIDGE_HEADER_0    0xDD
#define BRIDGE_HEADER_1    0xDA
#define BRIDGE_RESERVED    0xFF
#define BRIDGE_HEADER_LEN  5
#define BRIDGE_META_LEN    7
#define BRIDGE_MAX_PAYLOAD 120
#define BRIDGE_MAX_FRAME   128

// Bridge command bytes (§5)
#define BRIDGE_STARTBLE          0xE1
#define BRIDGE_STOPBLE           0xE2
#define BRIDGE_FACTORYRESET      0xE3
#define BRIDGE_WELCOMECONTINUE   0xE4
#define BRIDGE_SKIPPROVISIONING  0xE5
#define BRIDGE_PROVISIONSTART    0xE6
#define BRIDGE_PROVISIONEND      0xE7
#define BRIDGE_HEARTBEAT         0xE8
#define BRIDGE_PASSKEY           0xE9
```

Declare the following public API:

```c
// Initialise the bridge UART (call once at boot)
esp_err_t bridge_init(uart_port_t port, int tx_pin, int rx_pin, int baud);

// Send a single command byte to the other drawer
// payload = [my_drawer_id][cmd]
bool bridge_send_cmd(uart_port_t port, uint8_t my_drawer_id, uint8_t cmd);

// Send a command byte with additional data bytes
// payload = [my_drawer_id][cmd][data...]
bool bridge_send_cmd_data(uart_port_t port, uint8_t my_drawer_id,
                          uint8_t cmd, const uint8_t *data, size_t data_len);

// Non-blocking poll: extract one valid non-echo bridge frame from the UART ring buffer.
// Returns true if a frame was extracted.
// out_payload: buffer of at least BRIDGE_MAX_PAYLOAD bytes
// out_len:     number of payload bytes written
// out_sender:  drawer ID of the sender (payload[0])
// out_cmd:     command byte (payload[1])
bool bridge_poll(uart_port_t port, uint8_t my_drawer_id,
                 uint8_t *out_payload, size_t *out_len,
                 uint8_t *out_sender, uint8_t *out_cmd);
```

---

## Step 2 — Create `bridge_protocol.c`

Create `components/bridge/bridge_protocol.c`.

### 2a — `bridge_init`

```c
esp_err_t bridge_init(uart_port_t port, int tx_pin, int rx_pin, int baud) {
    uart_config_t cfg = {
        .baud_rate  = baud,
        .data_bits  = UART_DATA_8_BITS,
        .parity     = UART_PARITY_DISABLE,
        .stop_bits  = UART_STOP_BITS_1,
        .flow_ctrl  = UART_HW_FLOWCTRL_DISABLE,
    };
    ESP_ERROR_CHECK(uart_param_config(port, &cfg));
    ESP_ERROR_CHECK(uart_set_pin(port, tx_pin, rx_pin,
                                 UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
    return uart_driver_install(port, 256, 256, 0, NULL, 0);
}
```

### 2b — Internal `send_bridge_frame`

Implement the raw frame builder exactly as specified in §3.4:
- Header bytes 0-4: `0xDD 0xDA 0xFF 0xFF 0xFF`
- Bytes 5-6: `payload_len` big-endian
- Bytes 7…7+N-1: payload
- Last byte: XOR checksum of **all preceding bytes** (header + length + payload — see §3.3 scope note)

Reject `payload_len == 0` or `payload_len > BRIDGE_MAX_PAYLOAD`. Return false.

### 2c — `bridge_send_cmd`

Build payload `[my_drawer_id, cmd]` (2 bytes), call `send_bridge_frame`.

### 2d — `bridge_send_cmd_data`

Build payload `[my_drawer_id, cmd, data[0]…data[N-1]]`.
Reject if `data_len > BRIDGE_MAX_PAYLOAD - 2`. Return false.

### 2e — `bridge_poll`

Maintain a **static** internal ring buffer `uint8_t rx_buf[256]` and `size_t rx_len`.

Each call:
1. Read all available bytes from UART into `rx_buf` with `uart_read_bytes(..., 0)` (non-blocking).
2. Scan `rx_buf` for the 5-byte header `DD DA FF FF FF`.
3. Discard garbage bytes before the header (memmove).
4. Read `payload_len = (rx_buf[5] << 8) | rx_buf[6]`.
5. If `payload_len == 0 || payload_len > BRIDGE_MAX_PAYLOAD`: discard header, return false.
6. If `rx_len < BRIDGE_META_LEN + payload_len + 1`: return false (partial frame, wait).
7. Validate XOR checksum — XOR bytes `[0 … frameLen-2]`, compare with `rx_buf[frameLen-1]`.
   On mismatch: discard header bytes, return false.
8. **Echo filter**: `rx_buf[BRIDGE_META_LEN]` is `sender_id`. If `sender_id == my_drawer_id`, discard frame and return false.
9. Copy `payload_len` bytes from `rx_buf[BRIDGE_META_LEN]` into `out_payload`.
10. Set `*out_len = payload_len`, `*out_sender = out_payload[0]`, `*out_cmd = out_payload[1]`.
11. Consume the frame from `rx_buf` (memmove).
12. Return true.

---

## Step 3 — Create `bridge_commands.c` / `bridge_commands.h`

Create a thin dispatch layer that calls application callbacks for each command.

### 3a — Callback typedefs (in `bridge_commands.h`)

```c
typedef void (*bridge_on_startble_fn)(void);
typedef void (*bridge_on_stopble_fn)(void);
typedef void (*bridge_on_factoryreset_fn)(void);
typedef void (*bridge_on_welcomecontinue_fn)(void);
typedef void (*bridge_on_skipprovisioning_fn)(void);
typedef void (*bridge_on_provisionstart_fn)(void);
typedef void (*bridge_on_provisionend_fn)(void);
typedef void (*bridge_on_passkey_fn)(uint32_t passkey);

typedef struct {
    bridge_on_startble_fn        on_startble;
    bridge_on_stopble_fn         on_stopble;
    bridge_on_factoryreset_fn    on_factoryreset;
    bridge_on_welcomecontinue_fn on_welcomecontinue;
    bridge_on_skipprovisioning_fn on_skipprovisioning;
    bridge_on_provisionstart_fn  on_provisionstart;
    bridge_on_provisionend_fn    on_provisionend;
    bridge_on_passkey_fn         on_passkey;
} bridge_callbacks_t;
```

Declare:
```c
void bridge_commands_register(const bridge_callbacks_t *cbs);
void bridge_commands_dispatch(const uint8_t *payload, size_t len, uint8_t cmd);
```

### 3b — `bridge_commands_dispatch` (in `bridge_commands.c`)

Implement a switch on `cmd` matching every command in §5:

- `BRIDGE_STARTBLE`  → call `on_startble()`
- `BRIDGE_STOPBLE`   → call `on_stopble()`
- `BRIDGE_FACTORYRESET` → call `on_factoryreset()`
- `BRIDGE_WELCOMECONTINUE` → call `on_welcomecontinue()`
- `BRIDGE_SKIPPROVISIONING` → call `on_skipprovisioning()`
- `BRIDGE_PROVISIONSTART` → call `on_provisionstart()`
- `BRIDGE_PROVISIONEND` → call `on_provisionend()`
- `BRIDGE_PASSKEY` → decode 4-byte big-endian passkey per §6.3:
  ```c
  // payload = [sender_id][0xE9][B3][B2][B1][B0]
  // len must be >= 6
  uint32_t pk = ((uint32_t)payload[2] << 24)
              | ((uint32_t)payload[3] << 16)
              | ((uint32_t)payload[4] <<  8)
              |  (uint32_t)payload[5];
  if (cbs->on_passkey) cbs->on_passkey(pk);
  ```
- `default` → log unknown command, do nothing

All callbacks must be null-checked before invocation.

---

## Step 4 — Create a FreeRTOS bridge task (`bridge_task.c`)

Create a FreeRTOS task that runs the bridge RX loop:

```c
void bridge_task(void *arg) {
    // arg = pointer to bridge_task_config_t (uart_port, my_drawer_id)
    uint8_t payload[BRIDGE_MAX_PAYLOAD];
    size_t  len;
    uint8_t sender, cmd;

    for (;;) {
        if (bridge_poll(port, my_drawer_id, payload, &len, &sender, &cmd)) {
            bridge_commands_dispatch(payload, len, cmd);
        }
        vTaskDelay(pdMS_TO_TICKS(10));  // 10ms polling interval
    }
}
```

Define `bridge_task_config_t`:
```c
typedef struct {
    uart_port_t port;
    uint8_t     my_drawer_id;
} bridge_task_config_t;
```

Provide a start function:
```c
esp_err_t bridge_task_start(const bridge_task_config_t *cfg);
```
Stack size: `4096`. Priority: `5`. Core: `tskNO_AFFINITY`.

---

## Step 5 — Sending helpers (`bridge_send_helpers.c`)

Implement these convenience functions using `bridge_send_cmd` / `bridge_send_cmd_data`:

```c
// All return bool (true = UART write succeeded)

bool bridge_notify_startble(uart_port_t port, uint8_t my_drawer_id);
bool bridge_notify_stopble(uart_port_t port, uint8_t my_drawer_id);
bool bridge_notify_factoryreset(uart_port_t port, uint8_t my_drawer_id);
bool bridge_notify_welcomecontinue(uart_port_t port, uint8_t my_drawer_id);
bool bridge_notify_skipprovisioning(uart_port_t port, uint8_t my_drawer_id);

// Only called by Drawer 1 (guard: only send when my_drawer_id == 1)
bool bridge_notify_provisionstart(uart_port_t port, uint8_t my_drawer_id);
bool bridge_notify_provisionend(uart_port_t port, uint8_t my_drawer_id);

// Encodes passkey as big-endian 4 bytes (§6.2)
// passkey must be in range [100000, 999999]
// Only send when my_drawer_id == 1
bool bridge_send_passkey(uart_port_t port, uint8_t my_drawer_id, uint32_t passkey);
```

For `bridge_send_passkey`, encode:
```c
uint8_t data[4] = {
    (passkey >> 24) & 0xFF,
    (passkey >> 16) & 0xFF,
    (passkey >>  8) & 0xFF,
     passkey        & 0xFF,
};
return bridge_send_cmd_data(port, my_drawer_id, BRIDGE_PASSKEY, data, 4);
```

---

## Step 6 — `CMakeLists.txt`

Generate `components/bridge/CMakeLists.txt`:

```cmake
idf_component_register(
    SRCS
        "bridge_protocol.c"
        "bridge_commands.c"
        "bridge_task.c"
        "bridge_send_helpers.c"
    INCLUDE_DIRS
        "include"
    REQUIRES
        driver
        freertos
        esp_common
)
```

---

## Constraints

- **No Arduino API**. ESP-IDF only (`uart_*`, `esp_*`, `vTask*`).
- **No dynamic allocation** in the hot path (`bridge_poll`, `bridge_commands_dispatch`). Stack or static buffers only.
- **No third-party libraries** beyond what ESP-IDF provides.
- **Thread safety**: protect `rx_buf` / `rx_len` with a `portMUX_TYPE` spinlock if `bridge_poll` may be called from multiple contexts.
- Every public function must be null-checked against invalid arguments.
- All `ESP_ERROR_CHECK` / `ESP_LOGW` / `ESP_LOGE` tags must use `"BRIDGE"` as the tag string.
- The echo filter (§7) **must** be implemented. A frame whose `payload[0] == my_drawer_id` is silently discarded.
- The XOR checksum covers **all bytes before the checksum byte** — including header and length bytes (§3.3). Do not XOR only the payload.

---

## Expected output file structure

```
components/bridge/
├── CMakeLists.txt
├── include/
│   ├── bridge_protocol.h
│   └── bridge_commands.h
├── bridge_protocol.c
├── bridge_commands.c
├── bridge_task.c
└── bridge_send_helpers.c
```

After generating all files, verify:
1. `bridge_send_passkey` correctly encodes a passkey of `123456` (0x01E240) as `[0x00][0x01][0xE2][0x40]`.
2. A frame of `[DD DA FF FF FF 00 02 01 E1 XOR]` would yield `cmd = BRIDGE_STARTBLE (0xE1)`, `sender = 0x01`.
3. An echo frame (sender == my_drawer_id) is discarded and `bridge_poll` returns false.
