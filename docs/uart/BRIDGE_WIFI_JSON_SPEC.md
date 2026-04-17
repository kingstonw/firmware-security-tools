# FC75 Bridge — wifi.json Forward Design (ESP-IDF)

> **Scope**: Minimal extension to the existing bridge protocol that lets Drawer 1 push
> its `wifi.json` to Drawer 2 over the STM32 relay after BLE provisioning completes.
> Read `BLE_PROVISIONING_BRIDGE_SPEC.md` (§3–§5) for the underlying frame format.

---

## 1. Why This Is Needed

After BLE provisioning the mobile app provisions each drawer independently.
If for any reason Drawer 2 must share the exact same Wi-Fi credentials as Drawer 1
without a second BLE session, Drawer 1 can forward the assembled `wifi.json` payload
through the STM32 bridge immediately after its own provisioning completes.

---

## 2. New Command Constant

```c
// Add to the bridge command table (next slot after BRIDGE_PASSKEY = 0xE9)
#define BRIDGE_WIFI_JSON  0xEA   // Drawer 1 → Drawer 2: forward wifi.json payload
```

---

## 3. Wire Frame

Uses the existing **command + data** payload layout (§4.2 of the bridge spec):

```
Full bridge frame:
  [0xDD][0xDA][0xFF][0xFF][0xFF][LEN_H][LEN_L]
  [sender_id][0xEA][wifi_json_bytes...][XOR]

Payload breakdown:
  payload[0]          = sender_id        (uint8_t, value 1)
  payload[1]          = 0xEA             (BRIDGE_WIFI_JSON)
  payload[2 … 2+N-1]  = raw JSON string  (UTF-8, NOT null-terminated)

  N = length of the JSON string
  Total payloadLen = 2 + N
```

### 3.1 Size constraint

```
BRIDGE_MAX_PAYLOAD   = 120 bytes  (hard limit from STM32 spec)
sender_id + cmd      =   2 bytes  (overhead)
Available for JSON   = 118 bytes  (maximum)
```

Typical `wifi.json`:
```json
{"ssid":"MyNetwork","password":"MyPassword123"}
```
That is ~48 bytes — well within the limit.

**Worst case** (32-char SSID + 63-char WPA2 password):
```json
{"ssid":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","password":"BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"}
```
That is ~113 bytes — still within 118 bytes.

> If `len(wifi_json) > 118` at runtime, **abort and log a warning**. Do not send a partial
> JSON — an incomplete JSON written to SPIFFS will be rejected by `checkProvisionState()`.
> In practice this limit is never hit by valid Wi-Fi credentials.

---

## 4. Sequence Diagram

```
Drawer 1 (ESP-IDF)                 STM32              Drawer 2 (ESP-IDF)
──────────────────                 ─────              ──────────────────
BLE provisioning complete
→ wifi.json written locally
→ read wifi.json from NVS/SPIFFS
→ build bridge frame
  [DD DA FF FF FF LEN_H LEN_L
   01 EA {json...} XOR]
                                   ← forward as-is →
                                                        bridge_poll() extracts frame
                                                        cmd = 0xEA
                                                        json = payload[2..len-1]
                                                        validate JSON (has "ssid" key)
                                                        write to /wifi.json (AES-encrypted)
                                                        log: "wifi.json received from drawer 1"
```

---

## 5. Trigger Point (Drawer 1)

Send `BRIDGE_WIFI_JSON` **once**, immediately after writing `wifi.json` locally.
The natural trigger is when BLE provisioning finishes (equivalent of `GOTO_PROVISIONING_COMPLETEDSETUP`
in the Arduino firmware).

```c
// Called on Drawer 1 only, after local wifi.json is confirmed written
void bridge_forward_wifi_json(uart_port_t port, uint8_t my_drawer_id,
                              const char *wifi_json, size_t json_len)
{
    if (my_drawer_id != 1) return;  // only Drawer 1 sends

    if (json_len == 0 || json_len > BRIDGE_MAX_PAYLOAD - 2) {
        ESP_LOGW("BRIDGE", "wifi.json too large (%u bytes) to forward", json_len);
        return;
    }

    bool ok = bridge_send_cmd_data(port, my_drawer_id,
                                   BRIDGE_WIFI_JSON,
                                   (const uint8_t *)wifi_json, json_len);

    if (ok) {
        ESP_LOGI("BRIDGE", "wifi.json forwarded to drawer 2 (%u bytes)", json_len);
    } else {
        ESP_LOGE("BRIDGE", "bridge_send_cmd_data failed for BRIDGE_WIFI_JSON");
    }
}
```

**Where to call it** (in your ESP-IDF provisioning completion handler):
```c
// After spiffs_write_wifi_json(wifi_json, json_len) succeeds on Drawer 1:
bridge_forward_wifi_json(UART_NUM_2, my_drawer_id, wifi_json, json_len);
```

---

## 6. Receiver (Drawer 2)

Add one case to `bridge_commands_dispatch()` (or the equivalent switch in your ESP-IDF
bridge task):

```c
case BRIDGE_WIFI_JSON:
{
    // payload layout: [sender_id][0xEA][json_bytes...]
    // len = total payload bytes including sender_id and cmd
    if (len < 3) {
        ESP_LOGW("BRIDGE", "BRIDGE_WIFI_JSON: payload too short (%u)", len);
        break;
    }

    const char *json  = (const char *)&payload[2];
    size_t      json_len = len - 2;

    // Minimal JSON validation: must contain "ssid" key
    // (avoids writing corrupt data to SPIFFS)
    if (strnstr(json, "\"ssid\"", json_len) == NULL) {
        ESP_LOGW("BRIDGE", "BRIDGE_WIFI_JSON: payload missing ssid key, discarding");
        break;
    }

    esp_err_t err = spiffs_write_wifi_json(json, json_len);  // AES-encrypt + write /wifi.json
    if (err == ESP_OK) {
        ESP_LOGI("BRIDGE", "wifi.json received and written from drawer 1");
    } else {
        ESP_LOGE("BRIDGE", "wifi.json write failed: %s", esp_err_to_name(err));
    }
    break;
}
```

> **`spiffs_write_wifi_json`** is your ESP-IDF equivalent of the Arduino
> `SPIFF_Manager::writeBLEpayload(data, config::PATHS::WIFI)`.
> It must AES-128 encrypt the data before writing to match how Drawer 1 stores it.

---

## 7. SPIFFS Write Function (ESP-IDF skeleton)

```c
// Write wifi credentials JSON to SPIFFS, AES-128 encrypted.
// Key: "3A7F2B6D91C84E1A" (AES_KEY from config.h, 16 bytes)
esp_err_t spiffs_write_wifi_json(const char *json, size_t json_len)
{
    // 1. Pad to AES block size (16 bytes)
    size_t padded_len = ((json_len + 15) / 16) * 16;
    uint8_t plaintext[256] = {0};
    if (padded_len > sizeof(plaintext)) return ESP_ERR_INVALID_SIZE;
    memcpy(plaintext, json, json_len);
    // PKCS#7 or zero-padding — match the AES_helper.cpp mode used by Arduino firmware

    // 2. Encrypt with mbedTLS AES-128
    uint8_t ciphertext[256];
    mbedtls_aes_context aes;
    mbedtls_aes_init(&aes);
    mbedtls_aes_setkey_enc(&aes, (const uint8_t *)"3A7F2B6D91C84E1A", 128);
    for (size_t i = 0; i < padded_len; i += 16) {
        mbedtls_aes_crypt_ecb(&aes, MBEDTLS_AES_ENCRYPT,
                               plaintext + i, ciphertext + i);
    }
    mbedtls_aes_free(&aes);

    // 3. Write to SPIFFS
    FILE *f = fopen("/spiffs/wifi.json", "wb");
    if (!f) return ESP_FAIL;
    fwrite(ciphertext, 1, padded_len, f);
    fclose(f);
    return ESP_OK;
}
```

> **Important**: The AES mode (ECB vs CBC) and padding scheme must match `AES_helper.cpp`
> exactly, or Drawer 2 will fail to decrypt. Verify against the Arduino firmware before
> finalising. The key `"3A7F2B6D91C84E1A"` is 16 ASCII bytes = AES-128.

---

## 8. Integration Checklist

| Step | Owner | Notes |
|---|---|---|
| Add `#define BRIDGE_WIFI_JSON 0xEA` | ESP-IDF project | `bridge_protocol.h` |
| Call `bridge_forward_wifi_json()` after provisioning | Drawer 1 firmware | After local SPIFFS write confirmed |
| Add `BRIDGE_WIFI_JSON` case to `bridge_commands_dispatch()` | Drawer 2 firmware | Validate JSON before writing |
| Implement `spiffs_write_wifi_json()` with correct AES mode | Both | Must match `AES_helper.cpp` |
| No STM32 changes needed | STM32 | Transparent relay, frame already supported |

---

## 9. What This Does NOT Cover

| Item | Status |
|---|---|
| `aws_config.json` | Not in scope — small enough to fit in one frame but not implemented here |
| `cert.pem`, `priv.key`, `ca.pem` | Requires multi-frame chunking (files > 1 KB) |
| ACK / retry | Not implemented — if Drawer 2 misses the frame, it must be re-provisioned via BLE |
| Encryption of the JSON in-transit over bridge | Not implemented — the bridge frame is plaintext; the STM32 relay is trusted |

---

*Based on FC75 Arduino firmware v1.0.60 — bridge frame protocol §3–§5 of `BLE_PROVISIONING_BRIDGE_SPEC.md`*
