# ESP32 和 STM32 版本来源及比较机制分析

## 概述

`ESP32` 和 `STM32` 的版本信息：
1. **不是实时从硬件读取**，而是来自编译时配置和云端指定
2. **通过 version.json 驱动版本更新决策**
3. **版本比对使用语义版本控制系统**

---

## 版本信息来源

### 1️⃣ ESP32 版本 - `config::DEVICE::VERSION`

#### 定义位置（config.h, Line 471）
```cpp
static constexpr const char* VERSION = "1.0.60";   // 当前 ESP32 固件版本
```

#### 特点
- **编译时固定**：在编译时在 `config.h` 中硬编码
- **无需读取硬件或文件**：直接使用编译常量
- **何时更新**：只能通过重新编译和刷新固件更新

#### 版本检查时的比对
```cpp
// OTA.cpp Line 232
bool needESP32Update = compareVersions(
    String(config::DEVICE::VERSION),   // 🔴 本地版本（编译时）
    remoteVersion                       // 🔴 云端版本（来自 version.json）
);
```

---

### 2️⃣ STM32 版本 - 双层结构

#### 📦 2A: 初始版本（config.h, Line 472）
```cpp
static constexpr const char* STMVERSION = "07.01.32";  // 默认编译时版本
```

#### 📦 2B: 全局变量版本（main.ino, Line 127）
```cpp
String gSYSTEM_STM32_FIRMWARE = String(config::DEVICE::STMVERSION);
// 初始值 = "07.01.32"
// 可能被更新为 SPIFF 中保存的值
```

#### 📦 2C: 本地化固件版本（main.ino, Line 132）
```cpp
String gSYSTEM_STM_LOCALIZED_FW_VERSION = "";
// 初始为空，启动时从 SPIFF 读取
// 本地化 = 云端指定这个设备应该本地持有的版本
```

---

## 启动时版本初始化流程

### 初始化顺序（main.ino, Line 240-253）

```cpp
spiff.loadSystemDetails(
    &gSYSTEM_drawer,
    &gSYSTEM_STM32_FIRMWARE,           // 👈 从 SPIFF 读取（或使用默认值）
    &gSYSTEM_ESP32_FIRMWARE,
    &gSYSTEM_LANG,
    &gSYSTEM_FORCEASSETDOWNLOAD,
    &gSYSTEM_MAC,
    &gSYSTEM_PROVISIONEDFLAG,
    &gSYSTEM_UPDATE_STM_FIRMWARE,
    &gSYSTEM_STM_LOCALIZED_FW_VERSION, // 👈 从 SPIFF 读取（或使用默认值）
    ...
);
```

### 值来源优先级（SPIFF_Manager.cpp）

#### 场景1：首次启动（SPIFF 中无 system.txt）
```
gSYSTEM_STM32_FIRMWARE = config::DEVICE::STMVERSION ("07.01.32")
gSYSTEM_STM_LOCALIZED_FW_VERSION = config::DEVICE::STMVERSION ("07.01.32")
```

#### 场景2：SPIFF 中已有 system.txt（正常启动）
```
gSYSTEM_STM32_FIRMWARE = system.txt 中的第 1 个字段
gSYSTEM_STM_LOCALIZED_FW_VERSION = system.txt 中的第 9 个字段
```

---

## 版本比对逻辑

### compareVersions() 函数（OTA.cpp, Line 1081-1099）

```cpp
bool OTA::compareVersions(const String& currentVersion, const String& newVersion) {
  int remote[3] = { 0 }, current[3] = { 0 };

  // 解析 "major.minor.patch" 格式
  sscanf(newVersion.c_str(),    "%d.%d.%d", &remote[0], &remote[1], &remote[2]);
  sscanf(currentVersion.c_str(), "%d.%d.%d", &current[0], &current[1], &current[2]);

  // 逐段比对：major → minor → patch
  for (int i = 0; i < 3; i++) {
    if (remote[i] > current[i]) return true;   // ✅ 需要更新
    if (remote[i] < current[i]) return false;  // ❌ 云端版本更旧，不更新
  }
  return false;  // 版本相同，不更新
}
```

#### 比对规则

| 当前版本 | 云端版本 | 结果 | 说明 |
|---------|---------|------|------|
| 1.0.60 | 1.0.63 | ✅ 更新 | minor 增加 |
| 1.0.63 | 1.0.63 | ❌ 不更新 | 完全相同 |
| 1.0.63 | 1.0.60 | ❌ 不更新 | 云端更旧（防止降级） |
| 2.0.0 | 1.9.9 | ❌ 不更新 | 本地 major 更大 |

---

## 版本检查完整流程

### 第1步：获取 version.json（OTA.cpp, Line 115-220）

```
├─ 连接：HTTPS → version 服务器 (port 443)
├─ 请求：GET /version.json (或 /versionDev.json)
└─ 响应：200 OK with JSON body
```

### 第2步：解析和提取版本（OTA.cpp, Line 219-226）

```cpp
String deviceKey = getDeviceKey();  // "primary", "dev", 或 "secondary"

remoteVersion = doc["fc75"]["devices"][deviceKey]["version"] | "";
// ✅ ESP32 远程版本（例：1.0.63）

stm32Version = doc["fc75"]["devices"]["stm32"]["version"] | "";
// ✅ STM32 远程版本（例：07.01.44）

stm32localVersion = doc["fc75"]["devices"]["stm32"]["localfwversion"] | "";
// ✅ STM32 本地化版本（例：2.16.1.8，需要保存在本地）
```

### 第3步：版本比对（OTA.cpp, Line 232-233）

```cpp
bool needESP32Update = compareVersions(
    String(config::DEVICE::VERSION),   // 本地：1.0.60
    remoteVersion                       // 云端：1.0.63
);  // 结果：true（需要更新）

bool needSTM32Update = compareVersions(
    String(gSYSTEM_STM32_FIRMWARE),    // 本地：07.01.32
    stm32Version                        // 云端：07.01.44
) && (gSYSTEM_drawer == 1);            // 仅 Drawer 1 允许更新
// 结果：true（需要更新）
```

### 第4步：保存云端指定的本地版本（OTA.cpp, Line 877-879）

```cpp
// 🔴 关键：将云端指定的"本地化版本"保存到本地
gSYSTEM_STM_LOCALIZED_FW_VERSION = stm32localVersion;  // "2.16.1.8"
s->setSystemDetailByField(
    SPIFF_Manager::STM_LOCAL_FW, 
    String(gSYSTEM_STM_LOCALIZED_FW_VERSION)
);
```

---

## 版本信息的 SPIFF 存储

### system.txt 文件格式（SPIFF_Manager.cpp, Line 617-635）

```
字段0,字段1,字段2,字段3,字段4,字段5,字段6,字段7,字段8
drawer,  stm32,  esp32,  lang,  force,  mac,  prov,  update,  stmLocalFW
 1,    07.01.44, 1.0.63, EN,     0,    30:..., 1,      0,      2.16.1.8
```

#### 字段说明

| 序号 | 字段名 | 来源 | 更新条件 |
|------|-------|------|---------|
| 0 | drawer | 抽屉编号 | 硬件检测 |
| 1 | stm32 | `gSYSTEM_STM32_FIRMWARE` | 版本检查后 |
| 2 | esp32 | `gSYSTEM_ESP32_FIRMWARE` | 首次启动 |
| 3 | lang | `gSYSTEM_LANG` | 手动设置 |
| 4 | force | 强制资产标志 | 手动设置 |
| 5 | mac | 系统MAC地址 | 配网时 |
| 6 | prov | 配网标志 | 配网完成 |
| 7 | update | STM32更新标志 | 版本检查后 |
| **8** | **stmLocalFW** | **gSYSTEM_STM_LOCALIZED_FW_VERSION** | **版本检查后** |

---

## 流程图：version.json 驱动版本更新

```
┌──────────────────────────────────────┐
│          ESP_CHECKFORUPDATES         │
│      或定时检查（每4小时）            │
└──────────────────┬───────────────────┘
                   ↓
        ┌──────────────────────┐
        │ 连接 HTTPS           │
        │ 下载 version.json    │
        └──────────┬───────────┘
                   ↓
        ┌──────────────────────────────────────┐
        │ 解析版本元数据：                       │
        │ • remoteVersion (ESP32)              │
        │ • stm32Version (STM32)               │
        │ • stm32localVersion (本地化版本)     │
        └──────────┬───────────────────────────┘
                   ↓
        ┌──────────────────────────────────────┐
        │ 版本比对                              │
        │ compareVersions(本地, 云端)          │
        └──────┬─────────────────────┬─────────┘
               ↓                     ↓
        ┌─────────────┐      ┌──────────────┐
        │ 需要更新    │      │ 已是最新版本  │
        │ ESP32 or    │      │              │
        │ STM32       │      └──────┬───────┘
        └────┬────────┘             ↓
             ↓              保存 stm32localVersion
        ┌─────────────────────────┐
        │ 触发下载流程            │
        │ • GOTO_FIRMWARE_UPDATE  │
        │ • GOTO_ASSETS_DOWNLOAD  │
        └─────────────────────────┘
```

---

## 关键理解

### ❌ 误区1：版本来自硬件实时查询
```
错：ESP32 向 STM32 查询当前版本 → 串口通信
正：版本来自 SPIFF 和 config.h 的编译常量
```

### ❌ 误区2：gSYSTEM_STM_LOCALIZED_FW_VERSION 是硬件版本
```
错：STM32 的当前硬件版本
正：云端指定"应该在设备上本地化"的版本号
     用于版本检查后的持久化存储
```

### ✅ 理解1：版本号作为状态决策驱动
```
版本检查 → 版本比对 → 自动转移到相应的 OTA 流程
无需用户干预，完全自动化
```

### ✅ 理解2：SPIFF 是版本持久化的关键
```
system.txt (SPIFF)
├─ 保存上次已知的 STM32 版本
├─ 保存上次云端指定的本地版本
└─ 下次启动时直接读取（无需网络）
```

---

## 序列监视器输出示例

### 启动诊断日志（main.ino, Line 2541-2563）

```
============================================================
             FoodCycle FC75 System Diagnostics              
============================================================
 Firmware Version      : 1.0.60                    ✅ ESP32 当前版本
 Build Time            : Dec 28 2024 14:32:15
 Free Heap (RAM)       :   123 KB
 SPIFFS Used           :    845 KB
 SPIFFS Free           :    234 KB
 SPIFFS Total          :   1079 KB
 Provisioning State    : YES
 Drawer Number         : 1
 ...
 STM32 FW Version      : 07.01.32                 👈 本地 STM32 版本
 Asset Queue Size      : 0
 Language              : EN
 MAC Address           : 30:ED:A0:15:6D:A4
 STM32 Needs Update    : NO
 Start in bootload     : NO
```

### 版本检查日志

```
[OTA] Connecting to fc75firmware.s3.ca-central-1.amazonaws.com/... (Attempt 1/5)
[OTA] version.json content:
{
  "fc75": {
    "devices": {
      "primary": {
        "version": "1.0.63"                       👈 云端 ESP32
        "assets": "button1.raw,POWER.raw,...",
        ...
      },
      "stm32": {
        "version": "07.01.44",                    👈 云端 STM32
        "localfwversion": "2.16.1.8",             👈 要本地化的版本
        ...
      }
    }
  }
}

[OTA] I NEED ESP32 FIRMWARE                       ✅ 1.0.60 < 1.0.63
[OTA] I NEED STM32 FIRMWARE                       ✅ 07.01.32 < 07.01.44
```

---

## 实现参考

| 源文件 | 行号 | 功能 |
|-------|------|------|
| config.h | 471 | ESP32 版本定义 |
| config.h | 472 | STM32 初始版本定义 |
| main.ino | 127 | `gSYSTEM_STM32_FIRMWARE` 全局变量 |
| main.ino | 132 | `gSYSTEM_STM_LOCALIZED_FW_VERSION` 全局变量 |
| main.ino | 240-253 | 版本初始化加载 |
| main.ino | 2541-2563 | 诊断日志输出 |
| OTA.cpp | 115-230 | checkVersionNonBlocking() 核心 |
| OTA.cpp | 219-226 | 版本信息提取 |
| OTA.cpp | 232-233 | 版本比对 |
| OTA.cpp | 877-879 | 本地版本保存到 SPIFF |
| OTA.cpp | 1081-1099 | compareVersions() 比对函数 |
| SPIFF_Manager.cpp | 617-635 | system.txt 格式定义 |

---

## 总结

**版本信息流向**：

```
编译时：
  config.h → VERSION               ("1.0.60")
  config.h → STMVERSION            ("07.01.32")
              ↓
首次启动：
  → SPIFF (system.txt) 初始化
             ↓
正常启动：
  SPIFF (system.txt) → gSYSTEM_STM32_FIRMWARE
                    → gSYSTEM_STM_LOCALIZED_FW_VERSION
             ↓
版本检查：
  version.json 云端 → remoteVersion, stm32Version, stm32localVersion
                     ↓ (compareVersions)
                     决策更新 ↓
  存回 SPIFF (system.txt) 更新第 1 和第 9 字段
```

**不会实时查询硬件**，所有版本信息均来自编译配置和云端 version.json 的驱动。
