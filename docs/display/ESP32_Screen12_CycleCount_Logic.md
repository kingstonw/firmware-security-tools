# Screen 12 "XX CYCLES COMPLETED" 值来源与持久化逻辑

## 目的
这份文档描述本项目里 `screen 12` 上 `XX CYCLES COMPLETED` 的完整数据链路，便于在另一个 ESP-IDF 项目里复刻同样行为。

---

## 1) 先给结论

`XX` 来自 **持久化计数器**，不是临时 UI 文本。

- 计数变量：
  - 抽屉1：`myhardware.cycleCount`
  - 抽屉2：`myhardware.cycleCount2`
- 持久化位置：`/systemDetails.txt`（SPIFFS）
- 写入时机：周期结束（Running -> Standby）或启动补偿时会触发 `incrementCycle()`，并写回 SPIFFS。
- 读取时机：`setup()` 早期通过 `spiff.loadSystemDetails(...)` 读回 RAM。

所以你的问题“是不是上次处理完成后写入 flash”：**是的（SPIFFS 文件持久化）**。

---

## 2) Screen 12 文本是怎么拼出来的

## UI模板位置
- 文件：`SCREEN.cpp`
- 函数：`SCREEN::load_screen(...)`
- 分支：`case 12`

关键代码：
```cpp
Asset textSprite2 = { "0036", ..., ASSET_TEXT,
    pVar1 + " " + langMap["060"], ...};
```

其中：
- `pVar1` = 传入的数字字符串（即 `XX`）
- `langMap["060"]` = `"CYCLES COMPLETED"`

语言键定义：
- 文件：`config.h`
- 值：`"060": "CYCLES COMPLETED"`

---

## 3) `pVar1`（XX）在 setup 时从哪里来

在 `main.ino::setup()`：

1. 先读系统持久化字段到内存（包含 cycle 计数）
```cpp
spiff.loadSystemDetails(...,
  &myhardware.cycleCount,
  &myhardware.cycleStarted,
  &myhardware.cycleCount2,
  &myhardware.cycleStarted2,
  ...);
```

2. 再加载 `screen 12`，按当前抽屉传入计数值
```cpp
if(gSYSTEM_drawer==1){
  mydisplay.load_screen(12, myui, String(myhardware.cycleCount), "", "");
}else{
  mydisplay.load_screen(12, myui, String(myhardware.cycleCount2), "", "");
}
```

也就是说，`screen 12` 显示的是 **启动时从 SPIFFS 读出的计数**。

---

## 4) 计数器何时增加（核心业务逻辑）

文件：`HARDWARE.cpp`

## 4.1 周期开始标记
函数：`HARDWARE::processAllCycleInformation()`

- 当 UI 页变成 `Running_State` 且尚未标记开始时：
  - `cycleStarted = true`（或 `cycleStarted2 = true`）
  - 同步持久化 `CYCLE_STARTED`（或 `CYCLE_STARTED_2`）为 `1`

## 4.2 周期完成 + 计数递增
同函数里：
- 当 UI 页回到 `Standby` 且 `cycleStarted == true` 时，调用 `incrementCycle(1/2)`。

函数：`HARDWARE::incrementCycle(int pDrawer)`

抽屉1逻辑：
```cpp
cycleStarted = false;
spiff.setSystemDetailByField(SPIFF_Manager::CYCLE_STARTED, "0");
cycleCount++;
spiff.setSystemDetailByField(SPIFF_Manager::CYCLE_COUNT, String(cycleCount));
```

抽屉2逻辑：
```cpp
cycleStarted2 = false;
spiff.setSystemDetailByField(SPIFF_Manager::CYCLE_STARTED_2, "0");
cycleCount2++;
spiff.setSystemDetailByField(SPIFF_Manager::CYCLE_COUNT_2, String(cycleCount2));
```

这一步就是“完成后写入 flash(SPIFFS)”的关键路径。

---

## 5) 异常重启补偿（防止漏记）

文件：`HARDWARE.cpp`
函数：`checkCyclesOnStartup()`

```cpp
if (cycleStarted) incrementCycle(1);
if (cycleStarted2) incrementCycle(2);
```

含义：
- 若上次运行中已标记“周期开始”但未正常走到 Standby（例如断电重启），开机会补一次计数并清掉 started 标记。

在 `setup()` 中调用位置：
- `main.ino` 里在 logo 显示后执行 `myhardware.checkCyclesOnStartup();`

---

## 6) 持久化格式与字段映射

文件：`SPIFF_Manager.cpp`

- 系统信息文件：`/systemDetails.txt`
- CSV 字段（与 cycle 相关）
  - 字段11：`cycleCount`（drawer1）
  - 字段12：`cycleStarted`（drawer1）
  - 字段13：`cycleCount2`（drawer2）
  - 字段14：`cycleStarted2`（drawer2）

读：`loadSystemDetails(...)`
写：`setSystemDetailByField(...)` -> `updateSystemDetails(...)`

因此计数值是跨重启持久的。

---

## 7) 时序注意点（实现到新项目时建议保留）

当前代码的启动顺序是：
1. 先 `loadSystemDetails()`
2. 立即显示 `screen 12`（用当前已读计数）
3. 然后才 `checkCyclesOnStartup()` 做异常补偿

这意味着：
- 若发生“上次未完成但需要补计数”的情况，`screen 12` 可能先显示旧值，再在后台被补写新值。
- 当前代码没有在 `checkCyclesOnStartup()` 后再次刷新 `screen 12` 文本。

如果你在 ESP-IDF 项目中想更一致，建议：
- 要么把 `checkCyclesOnStartup()` 放到显示 `screen 12` 之前；
- 要么补偿后主动刷新一次 logo 计数文本。

---

## 8) 给 ESP-IDF 的最小复刻规范

1. 维护 4 个持久字段：
   - `cycle_count_1`, `cycle_started_1`, `cycle_count_2`, `cycle_started_2`
2. 收到状态流时：
   - 进入 `RUNNING` 且 started=0 -> started=1 并持久化
   - 回到 `STANDBY` 且 started=1 -> `count++`, `started=0` 并持久化
3. 启动时：
   - 读取持久字段
   - 若 `started==1`，执行一次补偿递增并写回
4. `screen 12` 文本：
   - 选择当前抽屉 count 值，拼接 `"<count> CYCLES COMPLETED"`

---

## 9) 代码索引（快速定位）

- Screen 12 显示：`SCREEN.cpp` -> `load_screen()` -> `case 12`
- 文案键：`config.h` -> `"060": "CYCLES COMPLETED"`
- 启动读计数并传给 screen 12：`main.ino` -> `setup()`
- 周期状态处理：`HARDWARE.cpp` -> `processAllCycleInformation()`
- 计数递增并持久化：`HARDWARE.cpp` -> `incrementCycle()`
- 启动补偿：`HARDWARE.cpp` -> `checkCyclesOnStartup()`
- SPIFFS 读写系统字段：`SPIFF_Manager.cpp` -> `loadSystemDetails()`, `setSystemDetailByField()`, `updateSystemDetails()`

---

## 10) 非启用路径说明

`main.ino` 中有一段注释掉的 `incrementCycleCounter()` 示例代码（已停用）。
实际生效逻辑以 `HARDWARE.cpp` 的 `processAllCycleInformation()/incrementCycle()` 为准。

