# ESP_CHECKFORUPDATES 命令处理流程分析

## 概述
`ESP_CHECKFORUPDATES` **不仅仅是被动的检查**，而是会**自动触发后续的OTA流程**。

---

## 命令处理链

### 1️⃣ AWS 命令接收（AWS.cpp, Line 318-322）
```cpp
else if (cmd == "ESP_CHECKFORUPDATES") {
    myaws.AWS_sendCommandResponse(cmd.c_str(), "EXECUTED", gTimestamp);
    gOVERRIDEcommands = GOTO_UI_CHECKVERSION;
}
```
**作用**：
- 发送 `EXECUTED` 响应给云端
- 设置 `gOVERRIDEcommands = GOTO_UI_CHECKVERSION`，触发状态转换

---

### 2️⃣ 进入 GOTO_UI_CHECKVERSION 状态（main.ino, Line 1252-1261）
```cpp
case GOTO_UI_CHECKVERSION: {
    Serial.println(F("GOTO_UI_CHECKVERSION"));  // trigger OTA version check
    if (gSYSTEM_BLE) break;
    
    ota.checkVersionTrigger = 1;                // 👈 请求版本检查
    gUpdateManagerState = 2;                    // 👈 设置更新管理器状态为2
    mydisplay.load_screen(6, myui, emptyS, emptyS, emptyS);  // 显示"检查中"界面（Screen 6）
    gDeviceStatus = UPDATEMANAGER;              // 进入更新管理器状态
    gOVERRIDEcommands = GOTO_NONE;
    needRedraw = 1;
}
```

**作用**：
- 激活版本检查（`checkVersionTrigger = 1`）
- 设置 `gUpdateManagerState = 2` 以执行实际的版本检查逻辑
- 显示"正在检查更新"界面（Screen 6）
- 转变设备状态为 `UPDATEMANAGER`

---

### 3️⃣ UPDATEMANAGER 状态处理（main.ino, Line 422-469）
```cpp
case UPDATEMANAGER: {
    if (gSkipVersionCheck) {
        ota.checkVersionTrigger = 0;
        lastOTACheck = millis();
        gSkipVersionCheck = 0;
        gOVERRIDEcommands = GOTO_UI_IDLE;
    }

    if (!wifi.isConnected()) return;
    TELEMETRY_scheduler(1);

    switch(gUpdateManagerState) {
        case 1: {
            // 初始化，等待WiFi连接
            if (!wifi.isConnected()) {
                wifi.tick();
                break;
            }
            gOVERRIDEcommands = GOTO_UI_CHECKVERSION;
            break;
        }

        case 2: {
            // 👈 执行非阻塞版本检查
            wifi.tick();
            ota.checkVersionNonBlocking(spiff.getCA(), &spiff, gSYSTEM_LANG);
            break;
        }

        case 3: {
            // 检查是否有资产需要下载
            wifi.tick();
            
            if (spiff.SPIFF_getTotalRecords(config::PATHS::ASSETQUEUE) > 0) {
                gOVERRIDEcommands = GOTO_ASSETS_DOWNLOAD;
            } else {
                gOVERRIDEcommands = GOTO_UI_IDLE;  // 一切已是最新，返回待机
            }
            break;
        }
    }
}
```

**流程**：
- 当 `gUpdateManagerState == 2` 时，调用 `ota.checkVersionNonBlocking()` 进行版本检查

---

### 4️⃣ 版本检查核心逻辑（OTA.cpp, Line 115-348）

#### 4.1 版本检查状态机
```
VC_IDLE 
  → VC_WAITING_HEADER（读取HTTP头）
  → VC_WAITING_BODY（读取version.json）
  → 解析并做决策
```

#### 4.2 从远程获取 version.json
- 连接到版本文件服务器（DEV 或 PROD）
- 请求获取 `version.json`
- 读取HTTP头和响应体

#### 4.3 **关键决策点：版本比较与自动转换**

获取远程版本后，`checkVersionNonBlocking()` 会**自动进行判断**并**立即转换设备状态**：

```cpp
// 提取版本信息
String deviceKey = getDeviceKey();
remoteVersion = doc["fc75"]["devices"][deviceKey]["version"] | "";
stm32Version = doc["fc75"]["devices"]["stm32"]["version"] | "";
assetsListCSV = doc["fc75"]["devices"][deviceKey]["assets"] | "";

// 并行比较版本
bool needESP32Update = compareVersions(String(config::DEVICE::VERSION), remoteVersion);
bool needSTM32Update = compareVersions(String(gSYSTEM_STM32_FIRMWARE), stm32Version) && (gSYSTEM_drawer == 1);
bool assetsInQueue = (spiff->SPIFF_getTotalRecords(config::PATHS::ASSETQUEUE) > 0);
```

---

### 5️⃣ **自动触发的 OTA 路径**

根据版本检查结果，系统会**自动转入相应的流程**（无需用户操作）：

#### ✅ 场景A：有资产在队列中
```cpp
if (assetsInQueue) {
    gOVERRIDEcommands = GOTO_ASSETS_DOWNLOAD;  // 🔴 自动进入资产下载流程
```
→ 进入资产下载，下载资产文件

---

#### ✅ 场景B：首次配网后（工厂配置）
```cpp
else if (wasProvisioned) {
    copyFullAssetListToTask(spiff);            // 将完整资产列表加入队列
    if (needSTM32Update) {
        spiff->SPIFF_addRecord(..., stm32Path);  // 如果STM32有更新，加入队列
    }
    gOVERRIDEcommands = GOTO_ASSETS_DOWNLOAD;  // 🔴 自动进入资产下载
```
→ 下载全部资产 + STM32固件（如需）

---

#### ✅ 场景C：重新配网后
```cpp
else if (wasReprovision) {
    copyFullAssetListToTask(spiff);
    if (needSTM32Update) {
        spiff->SPIFF_addRecord(..., stm32Path);
    }
    gOVERRIDEcommands = GOTO_ASSETS_DOWNLOAD;  // 🔴 自动进入资产下载
```
→ 同场景B

---

#### ✅ 场景D：需要强制资产下载
```cpp
else if (gSYSTEM_FORCEASSETDOWNLOAD) {
    copyFullAssetListToTask(spiff);
    if (needSTM32Update) {
        spiff->SPIFF_addRecord(..., stm32Path);
    }
    gOVERRIDEcommands = GOTO_ASSETS_DOWNLOAD;  // 🔴 自动进入资产下载
```

---

#### ✅ 场景E：需要 ESP32 固件更新
```cpp
else if (needESP32Update) {
    Serial.println(F("[OTA] I NEED ESP32 FIRMWARE"));
    gOVERRIDEcommands = GOTO_FIRMWARE_UPDATECONFIRM;  // 🔴 自动进入固件更新确认
```
→ 显示 "更新固件?" 确认屏幕（Screen 19），用户可选择确认或取消
→ 确认后自动下载 + 刷写 + 重启

---

#### ✅ 场景F：需要 STM32 固件更新
```cpp
else if (needSTM32Update) {
    Serial.println(F("[OTA] I NEED STM32 FIRMWARE"));
    if (spiff->SPIFF_recordExists(..., stm32Path) != 1) {
        spiff->SPIFF_addRecord(..., stm32Path);
        gOVERRIDEcommands = GOTO_ASSETS_DOWNLOAD;  // 🔴 自动进入资产下载（download STM32）
    } else {
        gUpdateManagerState = 3;
        gOVERRIDEcommands = GOTO_UPDATEMANAGER;
    }
```
→ 将STM32固件加入资产下载队列

---

#### ✅ 场景G：一切已是最新版本
```cpp
else {
    Serial.println(F("[OTA] EVERYTHING IS UP TO DATE"));
    gOVERRIDEcommands = GOTO_UPDATEMANAGER;  // 返回更新管理器 state 3
    gUpdateManagerState = 3;                 // 最后进入 GOTO_UI_IDLE
```
→ 返回待机状态

---

## 完整流程图

```
[AWS Command Received]
  ESP_CHECKFORUPDATES
       ↓
[AWS.cpp Line 320]
  gOVERRIDEcommands = GOTO_UI_CHECKVERSION
       ↓
[main.ino Line 1252]
  Show "Checking..." Screen (Screen 6)
  gDeviceStatus = UPDATEMANAGER
  gUpdateManagerState = 2
       ↓
[main.ino Line 450]
  UPDATEMANAGER case → call checkVersionNonBlocking()
       ↓
[OTA.cpp Line 115]
  ├─→ Connect to version server (443)
  ├─→ Fetch version.json
  ├─→ Parse JSON & extract versions
  └─→ Compare local vs remote
       ↓
[OTA.cpp Line 267-337]
  ┌─────────────────────────────────────────┐
  │ Decision Making (NO USER INTERACTION)   │
  └─────────────────────────────────────────┘
       ↓
    ┌──┬──┬──┬──┬──┬──┐
    ↓  ↓  ↓  ↓  ↓  ↓
   A  B  C  D  E  F  G
   │  │  │  │  │  │  │
   ↓  ↓  ↓  ↓  ↓  ↓  ↓
  AssetDL (← unified path)
  ┌─────────────────────────────┐
  │ GOTO_ASSETS_DOWNLOAD        │
  │ (font, layout, icon, STM32) │
  └─────────────────────────────┘
       ↓
   FW Confirm? (only if ESP32 update needed)
   ┌─────────────────────────────┐
   │ GOTO_FIRMWARE_UPDATECONFIRM │
   │ Screen 19: "Update Now?"    │
   └─────────────────────────────┘
       ↓ (User confirms)
  ┌─────────────────────────────┐
  │ GOTO_FIRMWARE_DOWNLOAD      │
  │ (Download ESP32 firmware)   │
  └─────────────────────────────┘
       ↓
  ┌─────────────────────────────┐
  │ FIRMWAREDOWNLOADING         │
  │ (Flash & verify)            │
  └─────────────────────────────┘
       ↓ (Success)
       ESP.restart()
       ↓ (Resume ONLINE & check for next task)
```

---

## 关键特性

| 特性 | 说明 |
|-----|------|
| **检查方式** | 非阻塞（`checkVersionNonBlocking()`），在主循环中持续运行 |
| **自动化** | 版本检查完成后，**自动决策并转移状态**，无需等待用户操作 |
| **ESP32固件更新** | 会显示确认屏幕（Screen 19），给用户最后确认的机会 |
| **资产下载** | 包括字体、布局、图标、STM32固件，全部统一到资产队列 |
| **STM32固件** | 作为资产下载的一部分，自动转移到资产管理器 |
| **优先级** | 资产队列 > 首配 > 重配 > ESP32固件 > STM32固件 > 全部最新 |
| **返回** | 所有流程完成后，最终返回 `GOTO_UI_IDLE` |

---

## 总结

### ❌ 错误理解
"ESP_CHECKFORUPDATES 仅仅检查是否有更新，然后等待用户确认"

### ✅ 正确理解
"ESP_CHECKFORUPDATES 是**全自动的版本检查与OTA触发流程**：
1. **检查**：获取远程 version.json
2. **比较**：与本地版本并行比较
3. **决策**：根据对比结果自动选择合适的OTA路径
4. **执行**：自动进入资产下载、固件下载或返回待机
5. **确认**：仅在用户需要最后决策时（ESP32固件）显示确认屏幕"

---

## 实现细节参考

| 源文件 | 行号 | 功能 |
|-------|------|------|
| AWS.cpp | 318-322 | 命令处理入口 |
| main.ino | 1252-1261 | GOTO_UI_CHECKVERSION 状态 |
| main.ino | 422-469 | UPDATEMANAGER 状态机 |
| OTA.cpp | 115-348 | checkVersionNonBlocking() 核心逻辑 |
| OTA.h | 22-31 | 使用文档示例 |
| OTA.h | 143 | checkVersionTrigger 标志定义 |
| config.h | 177 | GOTO_UI_CHECKVERSION 枚举定义 |
