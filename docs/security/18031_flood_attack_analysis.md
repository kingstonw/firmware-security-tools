# EN 18031 泛洪攻击安全整改分析报告

**版本：** v1.0.66  
**日期：** 2026-04-15  
**TUV Finding 参考：** Finding #6（Network Stack / Flood Attack）  
**扫描范围：** `main.ino`, `AWS.cpp`, `AWS.h`, `BLE.cpp`, `BLE.h`, `WIFI_Manager.cpp`, `WIFI_manager.h`, `config.h`, `HARDWARE.cpp/h`

---

## 一、已实施的改动

### 1. WiFi 网络栈级硬化（TUV Finding #6）

**文件：** `main.ino` → `printSystemDiagnostics()`，第 2816–2819 行

```cpp
Serial.println(F(" Network Stack Hardening (TUV Finding #6):"));
Serial.println(F("  WiFi library patched : WiFiGeneric.cpp (dynamic_rx_buf, rx_ba_win)"));
Serial.println(F("  dynamic_rx_buf       : 8  (stock: 32)"));
Serial.println(F("  rx_ba_win            : 6  (stock: 16)"));
```

- **层次：驱动层（底层 ESP-IDF/Arduino WiFi 库修改）**
- ESP32 WiFi 接收缓冲区 `dynamic_rx_buf` 从默认 32 缩减为 8；接收块确认窗口 `rx_ba_win` 从 16 缩减为 6
- 直接缓解 WiFi 层泛洪攻击（大量数据帧淹没接收缓冲区）
- 实际修改在 Arduino 库的 `WiFiGeneric.cpp` 中（不在本仓库代码树），此处为文档记录

---

### 2. Busy 状态控制（拒绝非空闲时执行命令）

**文件：** `AWS.cpp` → `aws_defaultRemoteCommandCallback()`，第 317–322 行

```cpp
if(gDeviceStatus != PROVISIONED && gDeviceStatus != ONLINE) {
    myaws.AWS_sendCommandResponse(cmd.c_str(), "DEVICE BUSY", gTimestamp);
    return;
}
```

- 设备在 OTA、BLE Provisioning、资产下载等关键操作期间，拒绝执行所有 AWS 远程命令
- `ESP_STATUS` 命令同样有非 ONLINE 时响应 `"DEVICE BUSY"` 的检查
- `checkDrawerUIPageIds()` 在多种忙碌状态下屏蔽 STM32 状态变化，防止并发冲突

---

### 3. 命令白名单（隐式白名单）

**文件：** `AWS.cpp` → `aws_defaultRemoteCommandCallback()`，第 253–418 行

- 所有命令经 `toUpperCase()` 规范化后与固定字符串列表逐一匹配
- 未知命令返回 `"NOT RECOGNIZED"` 且不触发任何操作
- `STM_FORCEFIRMWAREINSTALL` 额外校验文件名必须以 `.bin` 结尾

---

### 4. JSON 格式校验

**文件：** `AWS.cpp` → `aws_defaultRemoteCommandCallback()`，第 244–251 行

```cpp
StaticJsonDocument<256> doc;
DeserializationError error = deserializeJson(doc, payload, length);
if (error) { return; }  // 丢弃无效 JSON
```

---

### 5. BLE Payload 大小上限

**文件：** `BLE.cpp` → `assembleBLEBuffer()`，第 479–486 行

```cpp
if (bleBuffer.length() > config::BLE::TRANSMISSIONLIMIT) {  // 10,000 字节
    bufferingInProgress = false;
    bleBuffer.clear();
    gOVERRIDEcommands = GOTO_UI_CANCELBLE;
}
```

---

### 6. MQTT 出包大小校验

**文件：** `AWS.cpp` → `AWS_sendHeartbeat()` / `AWS_sendEvents()` / `AWS_sendCommandResponse()`

```cpp
if (bytesWritten >= sizeof(mqttPayloadBuffer)) {
    Logger::log(LOGGER_ERROR, 0x14, "payload truncated—skipping publish");
    return;
}
```

---

### 7. MQTT 自动重连 + 重订阅

**文件：** `AWS.cpp` → `AWS_manageConnection()`

- 5 秒间隔自动重连（`RECONNECT_INTERVAL_MS = 5000`）
- 重连成功后自动重新订阅 `foodcycle/{mac}/command` Topic

---

### 8. WiFi 自动重连（带指数退避）

**文件：** `WIFI_Manager.cpp` → `tick()`

```cpp
if (reconnectAttempts < 10) { reconnectDelay = 30000; }
else                         { reconnectDelay = 60000; }
```

同时：`WiFi.setAutoReconnect(true)` 启用底层自动重连。

---

### 9. BLE 暴力破解锁定

**文件：** `BLE.cpp` → `recordFailedAttempt()`

- Passkey 失败 1 次：暂停广播 5 秒  
- Passkey 失败 2 次：暂停广播 10 秒  
- Passkey 失败 3 次：永久停止广播（`GOTO_BLE_LOCKED`，需重启恢复）

---

### 10. 队列资源管理

**文件：** `main.ino` → `TELEMETRY_scheduler()`

- 每次 loop 只处理一种遥测类型（轮询公平调度）
- `RECORD_sendAWS()` 每次最多读取 `maxRecords` 条（ERROR: 5条，LOG: 3条）
- Bridge 帧 payload 大小硬限 120 字节（`BRIDGE_MAX_PAYLOAD`）

---

### 11. 加密时间同步（TUV Finding #1）

**文件：** `main.ino` → `handleTimeSyncNonBlocking()`

- 明文 NTP（UDP/123，易被注入伪造）替换为 HTTPS Lambda 加密时间源
- 防止时间篡改影响 TLS 证书验证等安全功能

---

## 二、待实施改动（详细设计）

以下三项当前代码中尚未实现，存在安全缺口，需要补充。

---

### ❌ 缺口 A：MQTT 命令频率限流

#### 问题说明

`aws_defaultRemoteCommandCallback()` 对同一 MQTT Topic 到达的命令**没有频率限制**。  
攻击者若持有合法设备凭证（或凭证泄露），可每秒向 `foodcycle/{mac}/command` 发送大量命令：

- 每条消息都触发 `deserializeJson`（CPU 消耗）
- 每条消息都触发 `AWS_sendCommandResponse`（MQTT 发包，消耗内存 + 网络带宽）
- 大量响应 publish 可能导致 MQTT 发包队列阻塞，进而影响心跳上报

"Busy 状态"只能拒绝命令**执行**，但无法阻止入口处的 CPU / 内存消耗。

#### 实现方案：滑动窗口计数器

在 `AWS.cpp` 中的 `aws_defaultRemoteCommandCallback()` 函数入口处，加入基于 `millis()` 的滑动窗口计数器：

**参数定义（建议加入 `config.h`）：**

```cpp
// config.h → class DEVICE
static constexpr uint8_t  CMD_RATE_LIMIT_MAX      = 5;      // 窗口内最大命令数
static constexpr uint32_t CMD_RATE_LIMIT_WINDOW_MS = 10000; // 滑动窗口长度（10秒）
```

**在 `AWS.cpp` 中的实现：**

```cpp
static void aws_defaultRemoteCommandCallback(char* topic, byte* payload, unsigned int length) {

    // -----------------------------------------------------------------------
    // [SECURITY] Rate limiting: max CMD_RATE_LIMIT_MAX commands per
    // CMD_RATE_LIMIT_WINDOW_MS milliseconds. Protects CPU and MQTT tx queue
    // from high-frequency command floods, even with valid credentials.
    // -----------------------------------------------------------------------
    static uint8_t  cmdCount        = 0;
    static uint32_t cmdWindowStart  = 0;

    uint32_t now = millis();

    // Reset window counter when the window has elapsed
    if (now - cmdWindowStart >= config::DEVICE::CMD_RATE_LIMIT_WINDOW_MS) {
        cmdWindowStart = now;
        cmdCount       = 0;
    }

    cmdCount++;

    if (cmdCount > config::DEVICE::CMD_RATE_LIMIT_MAX) {
        // Drop silently — do NOT send a response (that would compound the load)
        Serial.println(F("[AWS] Command rate limit exceeded — dropping"));
        Logger::log(LOGGER_ERROR, 0x30, "CMD_RATE_LIMIT");
        return;  // <-- 在所有 JSON 解析之前退出，零额外开销
    }
    // -----------------------------------------------------------------------

    Serial.print("[AWS] Received remote command: ");
    for (unsigned int i = 0; i < length; i++) Serial.print((char)payload[i]);
    Serial.println();

    // ... 后续 JSON 解析和命令处理逻辑保持不变 ...
}
```

**效果说明：**

| 场景 | 行为 |
|---|---|
| 正常使用（10秒内 ≤5条命令） | 正常处理 |
| 高频攻击（10秒内第6条起） | 在 JSON 解析之前丢弃，无响应 |
| 攻击停止后 10 秒 | 窗口自动重置，恢复正常 |

**为何选择"静默丢弃"而非发送错误响应：**  
发送错误响应本身也消耗 MQTT 发包资源，在泛洪场景下会加重负担。静默丢弃是对抗泛洪的标准做法（类似 TCP SYN cookie）。

---

### ❌ 缺口 B：MQTT Payload 入口大小前置拦截

#### 问题说明

当前代码：

```cpp
StaticJsonDocument<256> doc;
DeserializationError error = deserializeJson(doc, payload, length);
```

`StaticJsonDocument<256>` 会**截断**超出 256 字节的 payload，但：

1. `deserializeJson` 仍然会读取所有 `length` 字节进行扫描（不提前中止）
2. 若攻击者发送 4096 字节的 payload，`deserializeJson` 会扫描全部字节后才返回错误
3. 在频率限流之外，超大 payload 是另一个独立攻击面（单包 CPU 消耗攻击）

#### 实现方案：入口 length 前置守卫

**参数定义（建议加入 `config.h`）：**

```cpp
// config.h → class DEVICE
static constexpr uint16_t CMD_MAX_PAYLOAD_BYTES = 512; // MQTT 命令 payload 最大字节数
```

**在 `AWS.cpp` 中的修改（在频率限流之后、JSON 解析之前）：**

```cpp
static void aws_defaultRemoteCommandCallback(char* topic, byte* payload, unsigned int length) {

    // [SECURITY] Rate limiting (see above) ...

    // -----------------------------------------------------------------------
    // [SECURITY] Payload size pre-check: reject oversized payloads before
    // any JSON parsing. Prevents CPU exhaustion from large single-packet attacks.
    // A valid command JSON is always well under 512 bytes.
    // -----------------------------------------------------------------------
    if (length == 0 || length > config::DEVICE::CMD_MAX_PAYLOAD_BYTES) {
        Serial.printf("[AWS] Payload size %u rejected (max %u)\n",
                      length, config::DEVICE::CMD_MAX_PAYLOAD_BYTES);
        Logger::log(LOGGER_ERROR, 0x31, "CMD_PAYLOAD_OVERSIZE");
        return;  // 在 deserializeJson 之前退出
    }
    // -----------------------------------------------------------------------

    Serial.print("[AWS] Received remote command: ");
    for (unsigned int i = 0; i < length; i++) Serial.print((char)payload[i]);
    Serial.println();

    StaticJsonDocument<256> doc;
    DeserializationError error = deserializeJson(doc, payload, length);
    if (error) {
        Serial.print("[AWS] JSON parse failed: ");
        Serial.println(error.c_str());
        return;
    }

    // ... 后续命令处理逻辑保持不变 ...
}
```

**效果说明：**

| payload 大小 | 行为 |
|---|---|
| 0 字节 | 立即丢弃，无 JSON 解析 |
| 1–512 字节（正常范围） | 进入 JSON 解析 |
| 513–4096 字节（超大攻击包） | 立即丢弃，CPU 开销接近零 |

**为何上限定为 512 字节：**  
所有合法命令 JSON（如 `{"command":"STM_FORCEFIRMWAREINSTALL","value":"STM02.18.1.8.bin"}`）均远小于 512 字节。512 字节提供了充裕的余量，同时拦截了所有明显异常的超大 payload。

---

### ❌ 缺口 C：应用层流量异常监控

#### 问题说明

WiFi 驱动层缓冲缩减（`dynamic_rx_buf=8`, `rx_ba_win=6`）是被动的硬件层防护：

- 仅在 WiFi 驱动层丢弃超出缓冲的帧，无法感知或记录
- 应用层无法知道"当前是否正在遭受泛洪攻击"
- 没有告警机制，攻击后无法审计

**注：** ESP32 应用层无法直接实现 IP 包过滤（需要 AP/路由器侧或 AWS IoT Policy 限速）。但应用层可以实现**异常感知与日志上报**，以满足 18031 的可观测性要求。

#### 实现方案：应用层 MQTT 接收流量计数器 + 异常告警上报

**设计原则：**  
通过监控 MQTT 回调调用频率和 WiFi RSSI 突变来推断是否处于攻击状态，并向云端上报告警事件。

**参数定义（建议加入 `config.h`）：**

```cpp
// config.h → class DEVICE
static constexpr uint8_t  FLOOD_DETECT_THRESHOLD  = 20;    // 窗口内触发告警的回调次数
static constexpr uint32_t FLOOD_DETECT_WINDOW_MS  = 10000; // 检测窗口（10秒）
static constexpr uint32_t FLOOD_ALERT_COOLDOWN_MS = 60000; // 告警发送冷却（60秒，防重复）
```

**新增函数（建议放在 `AWS.cpp`，在 callback 之前）：**

```cpp
// -----------------------------------------------------------------------
// [SECURITY] Application-layer flood detection monitor.
// Counts MQTT callback invocations per time window. If the count exceeds
// FLOOD_DETECT_THRESHOLD, logs a security event and reports to AWS.
// This provides observability for audit even when driver-layer drops packets.
// -----------------------------------------------------------------------
static void checkFloodCondition() {

    static uint32_t floodWindowStart   = 0;
    static uint16_t floodCallbackCount = 0;
    static uint32_t lastFloodAlert     = 0;

    uint32_t now = millis();

    // Reset window
    if (now - floodWindowStart >= config::DEVICE::FLOOD_DETECT_WINDOW_MS) {
        floodWindowStart   = now;
        floodCallbackCount = 0;
    }

    floodCallbackCount++;

    // Check threshold
    if (floodCallbackCount >= config::DEVICE::FLOOD_DETECT_THRESHOLD) {

        // Cooldown: avoid sending repeated alerts every 10s
        if (now - lastFloodAlert >= config::DEVICE::FLOOD_ALERT_COOLDOWN_MS) {
            lastFloodAlert = now;

            Serial.printf("[SECURITY] Flood condition detected: %u callbacks in %lums window\n",
                          floodCallbackCount, (unsigned long)config::DEVICE::FLOOD_DETECT_WINDOW_MS);

            // Log locally as a security error event
            Logger::log(LOGGER_ERROR, 0x32, "FLOOD_DETECTED");

            // Report to AWS via error telemetry topic (reuses existing telemetry pipeline)
            // The Logger::log above will be picked up by TELEMETRY_scheduler → RECORD_sendAWS
            // on the next ERROR telemetry cycle — no extra MQTT publish needed here.
        }
    }
}
```

**在 `aws_defaultRemoteCommandCallback` 入口处调用：**

```cpp
static void aws_defaultRemoteCommandCallback(char* topic, byte* payload, unsigned int length) {

    // [SECURITY] Step 1: Monitor for flood condition (observability)
    checkFloodCondition();

    // [SECURITY] Step 2: Rate limiting
    // ... (缺口A的实现) ...

    // [SECURITY] Step 3: Payload size pre-check
    // ... (缺口B的实现) ...

    // ... 后续正常处理 ...
}
```

**效果说明：**

| 功能 | 说明 |
|---|---|
| 感知泛洪攻击 | 10秒窗口内回调次数 ≥ 20 次触发告警 |
| 本地日志记录 | `Logger::log(LOGGER_ERROR, 0x32, "FLOOD_DETECTED")` 写入 `/error.log` |
| 云端审计上报 | 由 `TELEMETRY_scheduler` 的 ERROR 类型定时通过 MQTT 上传至 AWS |
| 冷却机制 | 60 秒内不重复告警，防止自身消耗资源 |
| 不干扰正常流程 | 仅监控，不阻断；阻断由缺口A（Rate Limit）负责 |

---

## 三、新增错误码说明

需在 `config.h` → `class LOGGER` 的 `LOG_TABLE` 中添加：

```cpp
{ 0x30, "[AWS] Command rate limit exceeded — dropped" },
{ 0x31, "[AWS] Command payload size rejected (oversized)" },
{ 0x32, "[SECURITY] Flood condition detected on MQTT command topic" },
```

---

## 四、实施步骤汇总

```
Step 1: config.h
  - 添加 CMD_RATE_LIMIT_MAX、CMD_RATE_LIMIT_WINDOW_MS
  - 添加 CMD_MAX_PAYLOAD_BYTES
  - 添加 FLOOD_DETECT_THRESHOLD、FLOOD_DETECT_WINDOW_MS、FLOOD_ALERT_COOLDOWN_MS
  - LOG_TABLE 添加 0x30 / 0x31 / 0x32 错误码

Step 2: AWS.cpp
  - aws_defaultRemoteCommandCallback() 入口处依次添加：
    a. checkFloodCondition() 调用
    b. 滑动窗口计数器（Rate Limit）
    c. length 前置守卫（Payload Size Check）
  - 在 callback 之前添加 checkFloodCondition() 函数定义

Step 3: 回归测试
  - 正常命令（10秒内 ≤5条）：功能无变化
  - 高频命令（>5条/10秒）：第6条起静默丢弃
  - 超大 payload（>512字节）：立即丢弃，不解析
  - 20+ 回调/10秒：/error.log 出现 0x32，下次 ERROR 遥测周期上报云端
```

---

## 五、总结对照表

> Flash Encryption 专项分析详见：[flash_encryption_analysis.md](./flash_encryption_analysis.md)

### 泛洪攻击整改项

| 安全要求 | 实施情况 | 位置 | 覆盖层次 |
|---|---|---|---|
| 命令处理限流 | ✅ 已实施（Busy拒绝）+ **⚠️ 待补充滑动窗口Rate Limit** | `AWS.cpp` | 应用层 |
| Payload 长度校验 | ✅ JSON doc截断 + **⚠️ 待补充入口前置拦截** | `AWS.cpp` | 应用层 |
| JSON 格式校验 | ✅ 已实施 | `AWS.cpp:246` | 应用层 |
| 命令白名单 | ✅ 已实施（隐式 if/else） | `AWS.cpp:253-418` | 应用层 |
| 队列/资源管理 | ✅ 已实施 | `main.ino`, `HARDWARE.cpp` | 应用层 |
| Busy 状态控制 | ✅ 已实施 | `AWS.cpp:319` | 应用层 |
| MQTT 自动重连 | ✅ 已实施 | `AWS.cpp:645` | 应用层 |
| WiFi 自动重连 | ✅ 已实施 | `WIFI_Manager.cpp:263` | 应用层 |
| WiFi 泛洪防护 | ✅ 已实施（驱动层补丁） | `WiFiGeneric.cpp` | 驱动层 |
| 加密时间同步 | ✅ 已实施 | `main.ino:2465` | 应用层 |
| BLE 暴力破解锁定 | ✅ 已实施 | `BLE.cpp:359` | 应用层 |
| 应用层流量异常监控 | **⚠️ 待实施（checkFloodCondition）** | `AWS.cpp` 新增 | 应用层 |


