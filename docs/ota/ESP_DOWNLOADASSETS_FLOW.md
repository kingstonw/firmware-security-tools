# ESP_DOWNLOADASSETS 命令详细流程分析

## 概述

`ESP_DOWNLOADASSETS` 是一个**强制重新下载所有资产的命令** — 它：
- ❌ **不需要 version.json**
- ❌ **不进行版本比对**
- ✅ **直接强制重新下载 ASSETS_FULL.txt 中列出的所有资产**

---

## 流程详解

### 1️⃣ AWS 命令接收（AWS.cpp, Line 322-323）

```cpp
else if (cmd == "ESP_DOWNLOADASSETS") {
    gTriggerCMD = "ESP_DOWNLOADASSETS";  // 👈 设置触发器
    // ❌ 立即返回（无 AWS_sendCommandResponse）
}
```

**特点**：
- 不发送 `EXECUTED` 响应（可能是未完善的命令）
- 仅设置触发器字符串

---

### 2️⃣ main.ino 触发处理（Line 1112-1116）

```cpp
if (cmd == "ESP_DOWNLOADASSETS") {
    myaws.AWS_sendCommandResponse(cmd.c_str(), "EXECUTED", gTimestamp);  // 发送响应
    gSkip_Provisioning = 0;                                              // 清除跳过配网标志
    ota.copyFullAssetListToTask(&spiff);                                 // 👈 关键：读取 ASSETS_FULL 并复制到队列
    gOVERRIDEcommands = GOTO_ASSETS_DOWNLOAD;                          // 立即转移到资产下载
}
```

**关键步骤**：
1. ✅ 发送 `EXECUTED` 响应
2. 清除 `gSkip_Provisioning` 标志
3. 调用 `copyFullAssetListToTask()` 
4. 立即转移到 `GOTO_ASSETS_DOWNLOAD` 状态

---

### 3️⃣ copyFullAssetListToTask() 实现（OTA.cpp, Line 647-683）

```cpp
void OTA::copyFullAssetListToTask(SPIFF_Manager* spiff) {
    // 1️⃣ 清空下载队列
    spiff->SPIFF_initRecord(config::PATHS::ASSETQUEUE);
    
    // 2️⃣ 读取 ASSETS_FULL.txt 的总记录数
    int totalRecords = spiff->SPIFF_getTotalRecords(config::PATHS::ASSETFULL);
    
    // 3️⃣ 检查是否有资产
    if (totalRecords <= 0) {
        Serial.println(F("[OTA] No records in /ASSETS_full.txt. Nothing to copy to queue."));
        return;  // 👈 无资产，直接返回
    }
    
    // 4️⃣ 分配内存并读取所有记录
    String* records = new (std::nothrow) String[totalRecords];
    if (!records) {
        Serial.println(F("[OTA] Memory allocation failed..."));
        return;
    }
    
    // 5️⃣ 从 ASSETS_FULL.txt 读取所有资产
    size_t numRead = spiff->SPIFF_readRecords(
        config::PATHS::ASSETFULL,   // 👈 读取源文件
        records, 
        totalRecords
    );
    
    // 6️⃣ 逐条解析并添加到下载队列
    for (size_t i = 0; i < numRead; ++i) {
        String line = records[i];
        line.trim();
        
        // 跳过空行
        if (line.length() == 0) continue;
        
        // 格式：timestamp|filename
        int sep = line.indexOf('|');
        if (sep == -1) {
            Serial.printf("[OTA] Malformed line at record %u, skipping.\n", i);
            continue;  // 跳过格式错误的行
        }
        
        // 提取文件名（| 后面）
        String asset = line.substring(sep + 1);  // 👈 提取资产名
        asset.trim();
        
        if (asset.length() > 0) {
            // 👈 添加到下载队列
            bool ok = spiff->SPIFF_addRecord(
                config::PATHS::ASSETQUEUE,  // 下载队列
                asset.c_str(),              // 文件名
                "0",                        // 初始重试计数
                200                         // 日志轮转限制
            );
            if (!ok) {
                Serial.printf("[OTA] Failed to add asset '%s' to queue.\n", asset.c_str());
            }
        }
    }
    
    delete[] records;  // 释放内存
}
```

**流程总结**：
```
ASSETS_FULL.txt 结构
┌─────────────────────────────────────┐
│ 0|button1.raw                       │
│ 0|POWER.raw                         │
│ 0|DONE.raw                          │
│ 0|WARNING.raw                       │
│ 0|EN_Lang.json                      │
└─────────────────────────────────────┘
         ↓ (copyFullAssetListToTask)
ASSETQUEUE.txt
┌─────────────────────────────────────┐
│ 0|button1.raw                       │
│ 0|POWER.raw                         │
│ 0|DONE.raw                          │
│ 0|WARNING.raw                       │
│ 0|EN_Lang.json                      │
└─────────────────────────────────────┘
         ↓ (GOTO_ASSETS_DOWNLOAD)
开始下载每个资产
```

---

### 4️⃣ 资产下载执行（main.ino, Line 1325-1330）

```cpp
case GOTO_ASSETS_DOWNLOAD: {
    Serial.println(F("GOTO_ASSETS_DOWNLOAD"));
    mydisplay.load_screen(10, myui, emptyS, emptyS, emptyS);  // 显示下载屏幕
    gOVERRIDEcommands = GOTO_NONE;
    mydisplay.SPRITE_renderDirty();
    
    // 获取当前队列中的资产数
    gAssetsInQueue = spiff.SPIFF_getTotalRecords(config::PATHS::ASSETQUEUE);
    needRedraw = 1;
}
```

然后在主循环中（Line 565）：

```cpp
case ASSETDOWNLOADING:
    // ...
    ota.downloadAssetsFromS3_LOOP(&spiff, myaws.getBucket());  // ✅ 执行实际下载
    break;
```

---

## 🔑 关键特性分析

### ES_DOWNLOADASSETS vs ESP_CHECKFORUPDATES

| 特性 | ESP_CHECKFORUPDATES | ESP_DOWNLOADASSETS |
|------|------|------|
| **需要 version.json** | ✅ 必需 | ❌ 不需 |
| **版本比对** | ✅ 自动比对 ESP32 + STM32 + Assets | ❌ 无版本检查 |
| **如何获取资产列表** | version.json 中的 `assets` 字段 | ASSETS_FULL.txt（本地） |
| **资产列表更新时机** | 每次 CHECKFORUPDATES 时更新 | 无（永不更新） |
| **行为** | 智能决策（按需下载） | 强制重新下载全部 |
| **何时使用** | 定期自动检查 | 资产损坏/恢复 |

---

## 🔄 ASSETS_FULL.txt 如何创建和维护

### 来源：version.json（通过 ESP_CHECKFORUPDATES）

```json
{
  "fc75": {
    "devices": {
      "primary": {
        "assets": "button1.raw,POWER.raw,DONE.raw,WARNING.raw,PAUSE.raw,infinity.raw,cooling.raw"
      }
    }
  }
}
```

### 创建流程（OTA.cpp, Line 245）

```cpp
// ESP_CHECKFORUPDATES 中的 checkVersionNonBlocking()

// 👇 第1步：提取 version.json 中的资产列表
String assetsListCSV = doc["fc75"]["devices"][deviceKey]["assets"] | "";
// 结果：assetsListCSV = "button1.raw,POWER.raw,DONE.raw,...,EN_Lang.json"

// 👇 第2步：添加语言文件
String safeLangFile = langFile + ".json";  // 如 "EN_Lang.json"
if (assetsListCSV.length() > 0 && !assetsListCSV.endsWith(",")) {
    assetsListCSV += ",";
}
assetsListCSV += safeLangFile;

// 👇 第3步：写入 ASSETS_FULL.txt
writeAssetsFullFile(spiff, assetsListCSV);  // 👈 关键函数
```

### writeAssetsFullFile() 实现（OTA.cpp, Line 600-630）

```cpp
void OTA::writeAssetsFullFile(SPIFF_Manager* spiff, const String& assetsCSV) {
    // 1️⃣ 清空或创建 ASSETS_FULL.txt
    spiff->SPIFF_initRecord(config::PATHS::ASSETFULL);
    
    // 2️⃣ 按 CSV 格式解析资产名（用逗号分隔）
    int start = 0, end = 0;
    
    while ((end = assetsCSV.indexOf(',', start)) != -1) {
        String asset = assetsCSV.substring(start, end);  // 提取单个资产名
        asset.trim();                                     // 去除空格
        
        if (asset.length() > 0) {
            // 👇 将每个资产添加到 ASSETS_FULL.txt
            spiff->SPIFF_addRecord(
                config::PATHS::ASSETFULL,   // 目标文件
                asset.c_str(),              // 资产名
                "0",                        // 伪时间戳
                200                         // 日志轮转限制
            );
        }
        start = end + 1;
    }
    
    // 3️⃣ 处理最后一个资产（最后一个逗号之后）
    String asset = assetsCSV.substring(start);
    asset.trim();
    
    if (asset.length() > 0) {
        spiff->SPIFF_addRecord(config::PATHS::ASSETFULL, asset.c_str(), "0", 200);
    }
}
```

---

## 📊 SPIFF 文件结构

### ASSETS_FULL.txt（永久存储资产列表）
```
位置：/ASSETS_full.txt
用途：存储云端资产列表（version.json 驱动）
创建：ESP_CHECKFORUPDATES 完成时
更新：每次 CHECKFORUPDATES 会重写
格式：每行一条：时间戳|资产名
┌──────────────────────────────────────┐
│ 0|button1.raw                        │
│ 0|POWER.raw                          │
│ 0|DONE.raw                           │
│ 0|WARNING.raw                        │
│ 0|PAUSE.raw                          │
│ 0|infinity.raw                       │
│ 0|cooling.raw                        │
│ 0|EN_Lang.json                       │
└──────────────────────────────────────┘
```

### ASSETQUEUE.txt（临时下载队列）
```
位置：/ASSETS_queue.txt
用途：存储待下载的资产（临时工作队列）
创建：copyFullAssetListToTask() 或 SPIFF_addRecord() 时
清空：下载完成后清空
格式：每行一条：重试计数|资产名
┌──────────────────────────────────────┐
│ 0|button1.raw                        │
│ 0|POWER.raw                          │
│ 0|DONE.raw                           │
│ 0|WARNING.raw                        │
│ 0|PAUSE.raw                          │
│ 0|infinity.raw                       │
│ 0|cooling.raw                        │
│ 0|EN_Lang.json                       │
└──────────────────────────────────────┘
```

---

## 🚀 完整流程时序图

```
时间轴：
T0  ┌─ ESP_DOWNLOADASSETS 命令到达
    │
T1  └─→ copyFullAssetListToTask() 
        ├─ 读取 ASSETS_FULL.txt (5KB, ~8 资产)
        ├─ 逐条添加到 ASSETQUEUE
        └─ 耗时：~10-50ms
            │
T2          └─→ GOTO_ASSETS_DOWNLOAD 状态转移
                ├─ 显示下载屏幕
                └─ 进入主下载循环
                    │
T3              └─→ downloadAssetsFromS3_LOOP() 循环
                    ├─ 从队列读取第1个资产：button1.raw
                    ├─ 连接 S3，下载 button1.raw
                    ├─ 验证大小和完整性
                    ├─ 保存到 /assets/button1.raw
                    ├─ 从队列删除 button1.raw
                    │
                    ├─ [重复] 下载 POWER.raw
                    ├─ [重复] 下载 DONE.raw
                    ├─ [重复] 下载 EN_Lang.json
                    │
T4              └─→ 所有资产下载完毕
                    ├─ 清空 ASSETQUEUE
                    └─ 返回 GOTO_UI_IDLE （待机）
```

---

## ⚠️ 重要注意

### 1. 版本判断：没有！

```
❌ 错误：ESP_DOWNLOADASSETS 会比对资产版本并决定是否下载
✅ 正确：ESP_DOWNLOADASSETS 直接强制下载 ASSETS_FULL.txt 中列出的全部资产
```

### 2. ASSETS_FULL.txt 的来源

```
ES_DOWNLOADASSETS 不能自己决定资产是什么：
  ❌ 它无法连接到 version.json
  ❌ 它无法查询云端
  ✅ 它只读取本地 ASSETS_FULL.txt

ASSETS_FULL.txt 必须由 ESP_CHECKFORUPDATES 创建：
  ✅ ESP_CHECKFORUPDATES 获取 version.json
  ✅ 解析资产列表
  ✅ 写入 ASSETS_FULL.txt
  ✅ ESP_DOWNLOADASSETS 才能使用
```

### 3. 如果 ASSETS_FULL.txt 不存在会怎样？

```cpp
int totalRecords = spiff->SPIFF_getTotalRecords(config::PATHS::ASSETFULL);

if (totalRecords <= 0) {
    Serial.println(F("[OTA] No records in /ASSETS_full.txt. Nothing to copy to queue."));
    return;  // 👈 无声地返回，无资产被下载
}
```

**结果**：
- ❌ 没有错误提示
- ❌ 无资产被下载
- ⚠️ 用户感觉命令"失效"

---

## 📋 使用场景

### ✅ 何时使用 ESP_DOWNLOADASSETS

1. **资产文件损坏**
   - 显示错误的字体、布局或图标
   - 解决方案：`ESP_DOWNLOADASSETS` 重新下载全部

2. **已知资产有更新（且 ASSETS_FULL.txt 已是最新）**
   - 上一次 ESP_CHECKFORUPDATES 已更新了 ASSETS_FULL.txt
   - 现在想强制重新下载所有资产
   - 解决方案：`ESP_DOWNLOADASSETS`

3. **调试或测试**
   - 验证所有资产是否都能正确下载
   - 快速验证资产列表

### ❌ 何时** 不应该** 使用 ESP_DOWNLOADASSETS

```
❌ 想检查是否有新资产
   → 应该用 ESP_CHECKFORUPDATES

❌ 不知道当前有哪些资产
   → 应该先用 ESP_CHECKFORUPDATES (自动更新 ASSETS_FULL)
   → 再用 ESP_DOWNLOADASSETS

❌ 只想下载单个资产
   → 应该用 STM_FORCEFIRMWAREINSTALL 的逻辑
   → (目前没有"单个资产"命令)
```

---

## 🎯 总结

| 方面 | 说明 |
|------|------|
| **是否需要 version.json** | ❌ 完全不需要 |
| **版本判断** | ❌ 无（直接强制） |
| **资产列表来源** | ASSETS_FULL.txt（本地） |
| **如何保持ASSETS_FULL 最新** | 定期运行 ESP_CHECKFORUPDATES |
| **下载内容** | ASSETS_FULL.txt 列出的全部资产 |
| **行为** | 无脑强制下载（不管是否已有） |
| **适合场景** | 资产恢复、故障排除 |
| **推荐频率** | 很少使用（仅在必要时） |
