# OTA 四大命令详细对比分析

## 四大命令概览

| 命令 | 作用 | 需要 version.json | 自动决策 | 范围 |
|------|------|---------|---------|------|
| **ESP_CHECKFORUPDATES** | 智能检查与自动触发 | ✅ 必需 | ✅ 自动 | ESP32 + STM32 + Assets |
| **ESP_DOWNLOADASSETS** | 强制重新下载全部资产 | ❌ 不需 | ❌ 直接 | Assets 只 |
| **STM_INSTALLFIRMWARE** | 启动 STM32 bootloader | ❌ 不需 | ❌ 直接 | STM32 只 |
| **STM_FORCEFIRMWAREINSTALL** | 指定版本的强制安装 | ❌ 不需 | ❌ 直接 | 单个 STM32 文件 |

---

## 1️⃣ ESP_CHECKFORUPDATES - 完整自动版本检查

### AWS.cpp 命令处理（Line 318-320）
```cpp
else if (cmd == "ESP_CHECKFORUPDATES") {
    myaws.AWS_sendCommandResponse(cmd.c_str(), "EXECUTED", gTimestamp);
    gOVERRIDEcommands = GOTO_UI_CHECKVERSION;  // 👈 进入检查界面
}
```

### 处理流程

```
1. 【AWS】接收命令
   ↓
2. 【main.ino】GOTO_UI_CHECKVERSION 状态
   - 显示"检查中..."界面（Screen 6）
   - gDeviceStatus = UPDATEMANAGER
   - gUpdateManagerState = 2
   ↓
3. 【OTA.cpp】checkVersionNonBlocking()
   ├─ 连接服务器：HTTPS → version 服务器 (port 443)
   ├─ 请求：GET /version.json（或 /versionDev.json）
   ├─ 解析：提取 remoteVersion, stm32Version, stm32localVersion
   ├─ 比对：compareVersions(本地, 云端)
   └─ 决策：根据比对结果自动转移状态
      ↓
4. 【自动决策】七种路径之一
   ├─ 资产在队列中 → GOTO_ASSETS_DOWNLOAD
   ├─ 首次配网 → GOTO_ASSETS_DOWNLOAD (完整资产)
   ├─ 重新配网 → GOTO_ASSETS_DOWNLOAD (完整资产)
   ├─ 强制资产下载 → GOTO_ASSETS_DOWNLOAD
   ├─ 需要 ESP32 固件 → GOTO_FIRMWARE_UPDATECONFIRM (需用户确认)
   ├─ 需要 STM32 固件 → GOTO_ASSETS_DOWNLOAD (先下载 STM32)
   └─ 一切最新 → GOTO_UI_IDLE (返回待机)
```

### 关键特性

| 特性 | 说明 |
|------|------|
| **网络需求** | ✅ 必需（获取 version.json） |
| **版本比对** | ✅ ESP32 + STM32 + 资产 |
| **用户交互** | ⚠️ 仅 ESP32 固件时需确认 |
| **自动化程度** | ⭐⭐⭐⭐⭐ 最高（系统完全自动决策） |
| **灵活性** | 云端 version.json 完全掌控 |

### 数据流

```
version.json (云端)
{
  "fc75": {
    "devices": {
      "primary": {"version": "1.0.63"},
      "stm32": {"version": "07.01.44", "localfwversion": "2.16.1.8"}
    }
  }
}
       ↓
   extractVersions()
       ↓
   compareVersions(local, remote)
       ↓
   [自动决策] 触发对应流程
```

---

## 2️⃣ ESP_DOWNLOADASSETS - 强制重新下载所有资产

### AWS.cpp 命令处理（Line 322-323）
```cpp
else if (cmd == "ESP_DOWNLOADASSETS") {
    gTriggerCMD = "ESP_DOWNLOADASSETS";  // 👈 设置触发器
}
```

### main.ino 处理（Line 1112-1116）
```cpp
if (cmd == "ESP_DOWNLOADASSETS") {
    myaws.AWS_sendCommandResponse(cmd.c_str(), "EXECUTED", gTimestamp);
    gSkip_Provisioning = 0;
    ota.copyFullAssetListToTask(&spiff);      // 👈 将完整资产列表加入队列
    gOVERRIDEcommands = GOTO_ASSETS_DOWNLOAD;
}
```

### 处理流程

```
1. 【AWS】接收命令
   ↓
2. 【main.ino】触发处理
   - copyFullAssetListToTask() 读取 ASSETS_FULL.txt
   - 逐条添加到 ASSETQUEUE
   ↓
3. 【立即转移】→ GOTO_ASSETS_DOWNLOAD
   ├─ 显示下载界面
   ├─ 开始下载每个资产文件
   └─ 完成后返回 IDLE
```

### copyFullAssetListToTask() 做了什么？（OTA.cpp, Line 647-683）

```cpp
void OTA::copyFullAssetListToTask(SPIFF_Manager* spiff) {
    // 1. 读取 ASSETS_FULL.txt 中的完整资产列表
    String assetCSV = spiff->SPIFF_readRecord(config::PATHS::ASSETFULL, "");
    
    // 2. 初始化 ASSETQUEUE
    spiff->SPIFF_initRecord(config::PATHS::ASSETQUEUE);
    
    // 3. 逐个切割并添加到下载队列
    while (有资产) {
        String asset = ...提取单个;
        spiff->SPIFF_addRecord(config::PATHS::ASSETQUEUE, asset.c_str(), "0", 200);
    }
}
```

### 关键特性

| 特性 | 说明 |
|------|------|
| **网络需求** | ✅ 必需（下载资产文件） |
| **版本检查** | ❌ 不需（跳过 version.json） |
| **自动化程度** | ⭐⭐⭐⭐ 高（直接下载） |
| **覆盖范围** | Assets 完整列表 |
| **何时使用** | 已知需要重新下载所有资产 |
| **与 CHECKFORUPDATES 的区别** | 不进行版本比对，直接强制 |

### 何时使用

- ✅ 已知资产损坏或丢失
- ✅ 刚刚更新了 version.json 中的资产列表
- ✅ 想要跳过版本检查，直接强制重新下载
- ❌ 不推荐：用 CHECKFORUPDATES 更智能（自动比对版本）

---

## 3️⃣ STM_INSTALLFIRMWARE - 直接启动 STM32 bootloader

### AWS.cpp 命令处理（Line 335-337）
```cpp
else if (cmd == "STM_INSTALLFIRMWARE") {
    myaws.AWS_sendCommandResponse(cmd.c_str(), "EXECUTED", gTimestamp);
    gTriggerCMD = "STM_INSTALLFIRMWARE";
}
```

### main.ino 处理（Line 1123-1128）
```cpp
else if (cmd == "STM_INSTALLFIRMWARE") {
    spiff.setSystemDetailByField(SPIFF_Manager::STARTUP_IN_BOOTLOAD, "1");
    for (int i = 0; i < 4; ++i) {
        myhardware.sendButtonEvent(
            gSYSTEM_drawer, 
            config::TX_CMD::STM32_START_BOOTLOADER  // 👈 启动 bootloader
        );
        delay(1000);
    }
}
```

### 处理流程

```
1. 【AWS】接收命令
   ↓
2. 【main.ino】立即执行
   - 设置标志：STARTUP_IN_BOOTLOAD = 1
   - 发送 4 次 STM32_START_BOOTLOADER 信号（确保收到）
   - 延迟 1000ms × 4 = 4 秒
   ↓
3. 【STM32】响应
   - 进入 bootloader 模式（等待新固件）
   - STM32 开始扫描闪存中的 package.bin
   - 自动安装现有固件
   ↓
4. 【结束】重启后回到 ONLINE
```

### 关键特性

| 特性 | 说明 |
|------|------|
| **网络需求** | ❌ 不需 |
| **版本检查** | ❌ 不需 |
| **下载固件** | ❌ 不需（使用设备上已有的）|
| **自动化程度** | ⭐⭐⭐⭐⭐ 最高（无需用户操作） |
| **前置条件** | ✅ /stm32/package.bin 必须存在 |
| **转移状态** | ❌ 无（直接操作硬件） |
| **何时使用** | STM32 固件已下载，需要安装 |

### 与其他命令的区别

```
┌──────────────────────────────────────────────────────┐
│ STM_INSTALLFIRMWARE vs 其他 STM 命令                 │
├──────────────────────────────────────────────────────┤
│ 命令                    │ 下载 │ 安装 │ 自动 │ 人工 │
├──────────────────────────────────────────────────────┤
│ CHECKFORUPDATES         │ ✅   │ ✅   │ ✅   │ 可能 │
│ STM_INSTALLFIRMWARE     │ ❌   │ ✅   │ ✅   │  -  │
│ STM_FORCEFIRMWAREINSTALL│ ✅   │ ✅   │ ✅   │  -  │
└──────────────────────────────────────────────────────┘
```

### 前置条件检查

```cpp
// 关键前置条件：/stm32/package.bin 必须存在！
if (spiff.fileExists("/stm32/package.bin")) {
    // ✅ STM_INSTALLFIRMWARE 可以执行
} else {
    // ❌ STM_INSTALLFIRMWARE 无效（没有固件可装）
    // 需要先用 STM_FORCEFIRMWAREINSTALL 下载
}
```

---

## 4️⃣ STM_FORCEFIRMWAREINSTALL - 指定版本强制安装

### AWS.cpp 命令处理（Line 379-395）
```cpp
else if (cmd == "STM_FORCEFIRMWAREINSTALL") {
    String value = doc["value"] | "";  // 获取固件文件名，如 "STM02.18.1.8.bin"
    
    String vLower = value;
    vLower.toLowerCase();
    
    // ✅ 必须是 .bin 文件
    if (vLower.endsWith(".bin")) {
        myaws.AWS_sendCommandResponse(cmd.c_str(), "EXECUTED", gTimestamp);
        gTriggerCMD = "STM_FORCEFIRMWAREINSTALL|" + value + "|";  // 编码备用参数
    } else {
        myaws.AWS_sendCommandResponse(cmd.c_str(), "ERROR-wrong file type", gTimestamp);
    }
}
```

### main.ino 处理（Line 1146-1149）
```cpp
else if (cmd == "STM_FORCEFIRMWAREINSTALL") {
    Serial.println("STM_FORCEFIRMWAREINSTALL received");
    // tokens[1] = 文件名，如 "STM02.18.1.8.bin"
    spiff.SPIFF_addRecord(
        config::PATHS::ASSETQUEUE,   // 👈 加入下载队列
        tokens[1].c_str(),           // 👈 指定文件
        "0",                         // 初始计数
        200                          // 优先级
    );
    gOVERRIDEcommands = GOTO_ASSETS_DOWNLOAD;
}
```

### 处理流程

```
1. 【AWS】接收命令并提取参数
   {"command": "STM_FORCEFIRMWAREINSTALL", "value": "STM02.18.1.8.bin"}
   ↓
   检查文件名是否以 .bin 结尾 ✅
   ↓
2. 【main.ino】触发处理
   - tokens[1] = "STM02.18.1.8.bin"
   - SPIFF_addRecord(ASSETQUEUE, "STM02.18.1.8.bin")
   ↓
3. 【立即转移】→ GOTO_ASSETS_DOWNLOAD
   ├─ 从 S3 bucket 下载 "STM02.18.1.8.bin"
   ├─ 保存到 /stm32/package.bin
   └─ 设置标志：UPDATE_STM_FIRMWARE = 1
      ↓
4. 【下载完成】
   - 设置 STARTUP_IN_BOOTLOAD = 1
   - 重启 ESP32 → STM32 进入 bootloader
   - STM32 自动安装 /stm32/package.bin
   ↓
5. 【最终】重启完毕，回到 ONLINE
```

### 命令格式详解

```bash
# ✅ 正确格式
{"command": "STM_FORCEFIRMWAREINSTALL", "value": "STM02.18.1.8.bin"}
{"command": "STM_FORCEFIRMWAREINSTALL", "value": "firmware.bin"}

# ❌ 错误格式
{"command": "STM_FORCEFIRMWAREINSTALL", "value": "firmware"}        # 没有 .bin
{"command": "STM_FORCEFIRMWAREINSTALL", "value": "STM.txt"}         # 结尾不是 .bin
```

### 关键特性

| 特性 | 说明 |
|------|------|
| **网络需求** | ✅ 必需（下载指定固件） |
| **版本检查** | ❌ 不需（跳过 version.json） |
| **灵活性** | ⭐⭐⭐⭐⭐ 最高（云端可指定任意版本） |
| **自动化程度** | ⭐⭐⭐⭐ 高 |
| **何时使用** | 需要安装特定版本的 STM32 固件 |
| **风险** | ⚠️ 可能跳过版本检查，安装不兼容版本 |

### 与 CHECKFORUPDATES 的区别

```
ESP_CHECKFORUPDATES：
  - 获取 version.json
  - 自动比对版本
  - 智能决策（只在必要时更新）
  - 安全性高

STM_FORCEFIRMWAREINSTALL：
  - 跳过 version.json
  - 云端直接指定版本
  - 无条件安装
  - 灵活但可能过时或不兼容
```

---

## 🔄 命令关系图

```
                    ┌──────────────────────────────────┐
                    │  云端决策服务                      │
                    └──────┬───────────────────────────┘
                           │ version.json 或 直接命令
                           ↓
        ┌─────────────────┬─────────────────┬──────────────────┐
        ↓                 ↓                 ↓                  ↓
   ┌─────────────┐  ┌──────────────┐  ┌─────────────┐  ┌──────────────────┐
   │   ESP_      │  │  ESP_DOWN-   │  │  STM_       │  │  STM_FORCE       │
   │ CHECKFROM   │  │  LOADASSETS  │  │INSTALL      │  │FIRMWAREINSTALL   │
   │  UPDATES    │  │              │  │FIRMWARE     │  │                  │
   └─────┬───────┘  └──────┬───────┘  └──────┬──────┘  └────────┬─────────┘
         │                  │                 │                  │
         │ 完整版本检查      │ 跳过版本检查    │ 直接硬件操作     │ 指定特定版本
         │ + 自动决策        │ 强制资产列表    │ （无下载）       │ + 自动下载
         │                  │                 │                  │
         ├─ ESP32           ├─ Assets        ├─ STM32          ├─ STM32
         ├─ STM32           └─ 无版本决策     │                 ├─ 强制覆盖
         └─ Assets                          └─ 前置条件：bin   └─ 自动安装
                                               已存在
```

---

## 📊 对比总表

| 维度 | ESP_CHECKFORUPDATES | ESP_DOWNLOADASSETS | STM_INSTALLFIRMWARE | STM_FORCEFIRMWAREINSTALL |
|------|------|------|------|------|
| **需要 version.json** | ✅ 必需 | ❌ 不需 | ❌ 不需 | ❌ 不需 |
| **获取网络数据** | ✅ (JSON + 固件 + 资产) | ✅ (资产) | ❌ | ✅ (单个固件) |
| **版本比对** | ✅ 自动 | ❌ | ❌ | ❌ |
| **自动决策** | ✅ (7 种路径) | ❌ (固定资产) | ❌ (无状态转移) | ❌ (固定+ STM32) |
| **覆盖范围** | ESP32 + STM32 + Assets | Assets 只 | STM32 只 (硬件操作) | 单个 STM32 固件 |
| **用户交互** | ⚠️ ESP32 需确认 | ❌ 无 | ❌ 无 | ❌ 无 |
| **前置条件** | WiFi + AWS | WiFi | /stm32/package.bin | 无 |
| **灵活性** | 低（云端 JSON 控制） | 中（固定列表） | 低（只启动器）| **高**（指定任意版本） |
| **安全性** | **高** (版本检查) | 中 | 高 (前置检查) | 低 (可能跳过兼容) |
| **典型用途** | 定期自动更新检查 | 资产损坏恢复 | STM32 固件已准备好 | 特定版本修复 / 回滚 |

---

## ⚠️ 关键问题解答

### Q1: 服务器上只指定升级 ESP32，不升级 STM32，是否可行？

**✅ 完全可行**

```json
{
  "fc75": {
    "devices": {
      "primary": {
        "version": "1.0.63"        // ← 新版本
      },
      "stm32": {
        "version": "07.01.32",     // ← 保持不变（与本地相同）
        "localfwversion": "2.16.1.4"
      }
    }
  }
}

// 结果：
// compareVersions(1.0.60, 1.0.63) → true  ✅ 需要 ESP32 更新
// compareVersions(07.01.32, 07.01.32) → false ✅ 不需要 STM32 更新
```

**决策流程**：
```
checkVersionNonBlocking() 检查：
  ├─ needESP32Update = true  (1.0.60 < 1.0.63)
  ├─ needSTM32Update = false (07.01.32 = 07.01.32)
  └─ 结果 → GOTO_FIRMWARE_UPDATECONFIRM
     ↓ (用户确认后)
     GOTO_FIRMWARE_DOWNLOAD
     ↓ (下载并安装 ESP32 固件)
     ESP重启
     ↓ (回到 ONLINE，STM32 无任何改变)
```

---

### Q2: 服务器上只指定升级 STM32，不升级 ESP32，是否可行？

**✅ 完全可行**

```json
{
  "fc75": {
    "devices": {
      "primary": {
        "version": "1.0.60"        // ← 保持不变（与本地相同）
      },
      "stm32": {
        "version": "07.01.44",     // ← 新版本
        "localfwversion": "2.16.1.8"
      }
    }
  }
}

// 结果：
// compareVersions(1.0.60, 1.0.60) → false ✅ 不需要 ESP32 更新
// compareVersions(07.01.32, 07.01.44) → true ✅ 需要 STM32 更新
```

**决策流程**：
```
checkVersionNonBlocking() 检查：
  ├─ needESP32Update = false (1.0.60 = 1.0.60)
  ├─ needSTM32Update = true (07.01.32 < 07.01.44)
  └─ 结果 → spiff->SPIFF_addRecord(ASSETQUEUE, stm32Path)
     ↓
     GOTO_ASSETS_DOWNLOAD
     ↓ (下载 STM32 固件)
     ↓
     设置 STARTUP_IN_BOOTLOAD = 1
     ↓ (ESP 重启)
     STM32 进入 bootloader → 自动安装固件
     ↓ (重启完毕，STM32 更新成功)
```

---

### Q3: 自动检查每次都要 ESP32 + STM32 + Assets，是否效率低下？

**❌ 不会，系统非常智能**

**比对逻辑**：

```cpp
// OTA.cpp Line 232-233
bool needESP32Update = compareVersions(
    String(config::DEVICE::VERSION),    // 本地：1.0.60
    remoteVersion                        // 云端：1.0.63
);  // ✅ 仅检查版本号（字符串比对，极快）

bool needSTM32Update = compareVersions(
    String(gSYSTEM_STM32_FIRMWARE),    // 本地：07.01.32
    stm32Version                        // 云端：07.01.32
);  // ✅ 结果 = false，无需下载
```

**实际流程**：

```
版本检查花费时间：
  ├─ HTTPS 连接：~500ms
  ├─ JSON 下载：~1KB（~100ms）
  ├─ JSON 解析：~50ms
  ├─ compareVersions x3：~5ms
  └─ 总计：~700ms

版本比对后（假设无需更新）：
  ➜ 立即返回 GOTO_UI_IDLE（无任何下载）
  ➜ 用户感受不到延迟
```

**核心机制**：
- ✅ `compareVersions()` 只比对版本字符串（极快）
- ✅ 版本相同 → **跳过下载**
- ✅ 版本不同 → **才会下载**

**效率对比**：

```
╔════════════════════════════════════════════════════════════╗
║ 场景1：10 次检查，只有 1 次有更新                           ║
├────────────────────────────────────────────────────────────┤
║ 9 次：版本检查 (~700ms) → 比对完毕 → 无下载 → 返回       ║
║ 1 次：版本检查 → 下载 → 安装 (可能 5-10 分钟)            ║
║                                                            ║
║ ✅ 总成本 = 版本检查小成本 + 偶发的实际下载               ║
╚════════════════════════════════════════════════════════════╝
```

---

### Q4: 能否跳过 CHECKFORUPDATES，直接用 FORCEFIRMWAREINSTALL？

**✅ 技术可行，❌ 不建议**

**可行性**：

```bash
# 方案1：直接 FORCEFIRMWAREINSTALL
curl -X POST ... -d '{"command": "STM_FORCEFIRMWAREINSTALL", "value": "STM02.18.1.8.bin"}'

# ✅ 设备会：
# 1. 下载指定的 STM02.18.1.8.bin
# 2. 写入 /stm32/package.bin
# 3. 启动 bootloader，安装新固件
# 4. 重启完毕
```

**为什么不推荐**：

| 问题 | 说明 |
|------|------|
| ❌ **无版本检查** | 不知道是否已经是该版本，可能重复下载/安装 |
| ❌ **无 ESP32 检查** | ESP32 可能有更新，被忽略 |
| ❌ **无资产检查** | 资产文件可能遗失，被忽略 |
| ❌ **不灵活** | 云端无法灵活控制（按协议硬编码版本） |
| ⚠️ **可能不兼容** | 跳过版本检查，可能安装不兼容的版本 |

**推荐方案**：

```
方案 A（推荐）：
  1. 云端 version.json：指定新 STM32 版本
  2. 设备：ESP_CHECKFORUPDATES
  3. 系统自动比对、决策、下载、安装
  4. ✅ 智能、安全、完整

方案 B（特殊场景）：
  - 只有 Firmware 需要更新（其他都最新）
  - 云端也可以此前已通过 CHECKFORUPDATES 检查过
  - 再用 FORCEFIRMWAREINSTALL 强制回滚某个版本
```

---

### Q5: 三个组件（ESP32 + STM32 + Assets）能分别更新吗？

**✅ 完全可以**

| 更新组件 | 使用命令 | 说明 |
|---------|--------|------|
| **仅 Assets** | `ESP_DOWNLOADASSETS` | 跳过版本检查，强制重新下载全部资产 |
| **仅 STM32** | `ESP_CHECKFORUPDATES` (version.json 其他部分相同) | 智能检查，仅 STM32 版本更新 |
| **仅 STM32** | `STM_FORCEFIRMWAREINSTALL` | 跳过检查，直接安装指定版本 |
| **仅 ESP32** | `ESP_CHECKFORUPDATES` (STM32 版本相同) | 智能检查，仅 ESP32 版本更新 |
| **仅硬件操作** | `STM_INSTALLFIRMWARE` | 启动 bootloader（前置条件：/stm32/package.bin 存在） |

---

## 📋 决策树：使用哪个命令？

```
┌─ 需要检查全部（ESP32 + STM32 + Assets）？
│  ├─ YES → ESP_CHECKFORUPDATES ✅
│  │        （智能、安全、完整）
│  │
│  └─ 仅更新特定组件？
│
├─ 仅 Assets？
│  └─ ESP_DOWNLOADASSETS ✅
│     （已知需要重新下载）
│
├─ 仅 STM32 且已知固件版本？
│  └─ STM_FORCEFIRMWAREINSTALL ✅
│     （指定特定版本，跳过检查）
│
├─ 仅 STM32 且已在设备上？
│  └─ STM_INSTALLFIRMWARE ✅
│     （启动 bootloader 安装）
│
└─ 定期自动化检查？
   └─ ESP_CHECKFORUPDATES ✅✅✅
      （最推荐）
```

---

## 总结

### ✅ 可行方案

1. **云端仅指定 ESP32 更新** → 可行
   - version.json 保持 STM32 版本不变
   - 系统自动忽略 STM32，只更新 ESP32

2. **云端仅指定 STM32 更新** → 可行
   - version.json 保持 ESP32 版本不变
   - 系统自动忽略 ESP32，只更新 STM32

3. **跳过版本检查，直接指定更新** → 可行但不推荐
   - 用 `STM_FORCEFIRMWAREINSTALL` 等特定命令
   - ⚠️ 灵活但失去智能决策

4. **每次都检查三个组件** → 不低效
   - 版本比对极快（毫秒级）
   - 无变化时无下载成本

### ⭐ 最佳实践

**定期使用 ESP_CHECKFORUPDATES**：
- ✅ 一条命令处理全部更新
- ✅ 智能版本比对决策
- ✅ 安全且完整
- ✅ 云端 version.json 掌控灵活性
