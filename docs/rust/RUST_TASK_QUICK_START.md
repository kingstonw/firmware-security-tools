# Rust Task 快速验证指南

## 目标
快速验证用 Rust 重写一个 task 并嵌入到 ESP-IDF 中的可行性。

## 推荐架构：混合方案 ✅

### C/C++ 负责硬件控制，Rust 负责业务逻辑

**优势**：
- ✅ **不依赖 ESP-IDF HAL 成熟度**：GPIO、UART 等用成熟的 C API
- ✅ **利用 Rust 优势**：业务逻辑的内存安全、类型安全、错误处理
- ✅ **渐进式迁移**：可以逐步将业务逻辑迁移到 Rust
- ✅ **风险最低**：硬件层保持稳定，只改变业务逻辑层

**架构图**：
```
┌─────────────────────────────────────┐
│   ESP-IDF C/C++ (硬件层)            │
│   - GPIO 控制                        │
│   - UART 通信                        │
│   - 定时器                           │
└──────────────┬──────────────────────┘
               │ FFI 接口
┌──────────────▼──────────────────────┐
│   Rust (业务逻辑层)                  │
│   - 状态机                           │
│   - 数据处理                         │
│   - 错误处理                         │
└─────────────────────────────────────┘
```

## 推荐验证方案

### 选择最简单的任务：input_task 的业务逻辑

**理由**：
- ✅ 逻辑相对简单（按钮状态机、事件处理）
- ✅ GPIO 控制继续用 C（成熟稳定）
- ✅ 业务逻辑用 Rust（内存安全）
- ✅ 不涉及复杂的网络/文件操作
- ✅ 即使失败也不会影响核心功能
- ✅ 容易验证（按钮按下有明确反馈）

## 快速开始步骤

### 步骤 1：安装 Rust 和 ESP-IDF Rust 工具链

```bash
# 1. 安装 Rust（如果还没有）
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env

# 2. 安装 ESP-IDF Rust 工具链
cargo install espup
espup install

# 3. 设置环境变量（添加到 ~/.bashrc 或 ~/.zshrc）
source $HOME/.export-esp.sh
```

### 步骤 2：在项目中创建 Rust 模块

```bash
# 在项目根目录创建 Rust crate
cd /Users/kingstonw/FCS_ws/WatusiPanel-V2
cargo new --lib rust_tasks
cd rust_tasks
```

### 步骤 3：配置 Cargo.toml

创建 `rust_tasks/Cargo.toml`：

```toml
[package]
name = "rust_tasks"
version = "0.1.0"
edition = "2021"

[lib]
crate-type = ["staticlib", "cdylib"]

[dependencies]
esp-idf-sys = { version = "0.36", features = ["binstart"] }
esp-idf-hal = "0.40"
esp-idf-svc = "0.48"
freertos-rust = "0.1"
log = "0.4"

[build-dependencies]
esp-idf-sys = { version = "0.36", features = ["native"] }
```

### 步骤 4：创建简单的 Rust Task（最小验证）

创建 `rust_tasks/src/lib.rs`：

```rust
use esp_idf_sys::*;
use log::*;

// C FFI 接口：从 C++ 调用
#[no_mangle]
pub extern "C" fn rust_input_task_start() {
    info!("Rust input_task started!");
    
    // 创建一个简单的循环，模拟按钮检测
    loop {
        unsafe {
            // 简单的延迟（1秒）
            vTaskDelay(pdMS_TO_TICKS(1000));
            
            // 这里可以添加 GPIO 读取逻辑
            info!("Rust task running...");
        }
    }
}
```

### 步骤 5：配置构建系统

在 `main/CMakeLists.txt` 中添加：

```cmake
# 添加 Rust 构建
set(RUST_TASKS_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../rust_tasks")

# 构建 Rust 库
add_custom_command(
    OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/librust_tasks.a
    COMMAND cargo build --release --manifest-path ${RUST_TASKS_DIR}/Cargo.toml
    WORKING_DIRECTORY ${RUST_TASKS_DIR}
    COMMENT "Building Rust tasks library"
)

# 链接 Rust 库
target_link_libraries(${COMPONENT_LIB} 
    PRIVATE 
    ${CMAKE_CURRENT_BINARY_DIR}/librust_tasks.a
)

# 包含 Rust 头文件
target_include_directories(${COMPONENT_LIB} PRIVATE 
    ${CMAKE_CURRENT_SOURCE_DIR}/../rust_tasks/include
)
```

### 步骤 6：创建 C 头文件（供 C++ 调用）

创建 `rust_tasks/include/rust_tasks.h`：

```c
#ifndef RUST_TASKS_H
#define RUST_TASKS_H

#ifdef __cplusplus
extern "C" {
#endif

// 声明 Rust 函数
void rust_input_task_start(void);

#ifdef __cplusplus
}
#endif

#endif // RUST_TASKS_H
```

### 步骤 7：在 C++ 中调用 Rust Task

在 `main/main.cpp` 中：

```cpp
// 添加头文件
extern "C" {
#include "rust_tasks.h"
}

// 在 app_main() 中创建任务
void app_main() {
    // ... 其他初始化 ...
    
    // 测试：创建 Rust task（替代或并行运行）
    xTaskCreate(
        [](void* param) {
            rust_input_task_start();  // 调用 Rust 函数
        },
        "RustInputTask",
        4096,
        nullptr,
        5,
        nullptr
    );
    
    // ... 其他代码 ...
}
```

### 步骤 8：构建和测试

```bash
# 1. 构建 Rust 库
cd rust_tasks
cargo build --release

# 2. 构建 ESP-IDF 项目
cd ..
idf.py build

# 3. 烧录和监控
idf.py flash monitor
```

## 验证清单

- [ ] Rust 工具链安装成功
- [ ] Rust 库可以编译
- [ ] Rust 库可以链接到 ESP-IDF 项目
- [ ] Rust task 可以启动
- [ ] Rust task 可以运行（看到日志输出）
- [ ] Rust 和 C++ 可以通信（通过 FFI）

## 进阶：混合架构实现（推荐）✅

### 方案：C 控制 GPIO，Rust 处理业务逻辑

#### 1. C 层：GPIO 读取（保持原有代码）

在 `main/tasks/input_task.cpp` 中：

```cpp
// C 层只负责硬件读取
extern "C" {
    // Rust 函数声明
    void rust_process_button_state(bool btn1_pressed, bool btn2_pressed, 
                                    uint32_t btn1_duration, uint32_t btn2_duration);
}

void input_task(void *pvParameters) {
    // GPIO 配置（保持原有）
    gpio_set_direction(BUTTON1_PIN, GPIO_MODE_INPUT);
    gpio_set_direction(BUTTON2_PIN, GPIO_MODE_INPUT);
    
    Button button1(BUTTON1_PIN, ...);
    Button button2(BUTTON2_PIN, ...);
    
    while (true) {
        // C 层：硬件读取
        button1.update();
        button2.update();
        
        bool btn1_pressed = button1.isPressed();
        bool btn2_pressed = button2.isPressed();
        uint32_t btn1_duration = button1.getPressDuration();
        uint32_t btn2_duration = button2.getPressDuration();
        
        // 调用 Rust 处理业务逻辑
        rust_process_button_state(btn1_pressed, btn2_pressed, 
                                  btn1_duration, btn2_duration);
        
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}
```

#### 2. Rust 层：业务逻辑处理

在 `rust_tasks/src/lib.rs` 中：

```rust
use esp_idf_sys::*;
use log::*;

// 按钮状态机（Rust 实现）
struct ButtonStateMachine {
    btn1_press_start: Option<u32>,
    btn2_press_start: Option<u32>,
    self_test_active: bool,
}

impl ButtonStateMachine {
    fn new() -> Self {
        Self {
            btn1_press_start: None,
            btn2_press_start: None,
            self_test_active: false,
        }
    }
    
    fn process(&mut self, btn1_pressed: bool, btn2_pressed: bool,
               btn1_duration: u32, btn2_duration: u32) {
        // Rust 实现业务逻辑
        // - 状态机管理
        // - 事件检测
        // - 错误处理
        
        if btn1_pressed && btn2_pressed {
            // 组合按键逻辑
            self.handle_combo();
        } else if btn1_pressed {
            // 按钮1逻辑
            self.handle_button1(btn1_duration);
        } else if btn2_pressed {
            // 按钮2逻辑
            self.handle_button2(btn2_duration);
        }
    }
    
    fn handle_combo(&mut self) {
        // 组合按键处理（Rust 实现）
        info!("Combo button detected");
    }
    
    fn handle_button1(&mut self, duration: u32) {
        // 按钮1处理（Rust 实现）
        if duration > 10000 {
            info!("Button1 long press");
        }
    }
    
    fn handle_button2(&mut self, duration: u32) {
        // 按钮2处理（Rust 实现）
        if duration > 10000 {
            info!("Button2 long press");
        }
    }
}

static mut STATE_MACHINE: Option<ButtonStateMachine> = None;

#[no_mangle]
pub extern "C" fn rust_process_button_state(
    btn1_pressed: bool,
    btn2_pressed: bool,
    btn1_duration: u32,
    btn2_duration: u32,
) {
    unsafe {
        if STATE_MACHINE.is_none() {
            STATE_MACHINE = Some(ButtonStateMachine::new());
        }
        
        if let Some(ref mut sm) = STATE_MACHINE {
            sm.process(btn1_pressed, btn2_pressed, btn1_duration, btn2_duration);
        }
    }
}

// 如果需要调用 C 函数（如发送事件）
extern "C" {
    fn sendEvent2Queue(event: u8);
}

#[no_mangle]
pub extern "C" fn rust_send_event(event: u8) {
    unsafe {
        sendEvent2Queue(event);
    }
}
```

#### 3. C 头文件（可选，用于类型定义）

创建 `rust_tasks/include/rust_tasks.h`：

```c
#ifndef RUST_TASKS_H
#define RUST_TASKS_H

#ifdef __cplusplus
extern "C" {
#endif

// Rust 函数声明
void rust_process_button_state(bool btn1_pressed, bool btn2_pressed,
                                uint32_t btn1_duration, uint32_t btn2_duration);
void rust_send_event(uint8_t event);

#ifdef __cplusplus
}
#endif

#endif // RUST_TASKS_H
```

### 优势对比

| 方面 | 纯 Rust（依赖 HAL） | 混合架构（推荐） |
|------|-------------------|-----------------|
| **GPIO 控制** | ⚠️ 依赖 ESP-IDF HAL | ✅ 使用成熟的 C API |
| **业务逻辑** | ✅ Rust 内存安全 | ✅ Rust 内存安全 |
| **成熟度** | ⚠️ HAL 可能不完整 | ✅ C API 非常成熟 |
| **迁移成本** | ⚠️ 需要重写硬件层 | ✅ 只需迁移业务逻辑 |
| **风险** | ⚠️ 较高 | ✅ 较低 |
| **调试** | ⚠️ Rust 调试工具 | ✅ C 调试工具成熟 |

## 常见问题

### 1. 链接错误

**问题**：`undefined reference to rust_input_task_start`

**解决**：
- 确保 Rust 库已编译
- 检查 CMakeLists.txt 中的链接路径
- 确保函数使用 `#[no_mangle]` 和 `extern "C"`

### 2. 符号冲突

**问题**：Rust 和 C++ 使用相同的符号

**解决**：
- 使用命名空间（Rust 模块）
- 使用不同的函数名

### 3. 内存分配问题

**问题**：Rust 和 C++ 使用不同的堆

**解决**：
- 使用 ESP-IDF 的堆分配器
- 通过 FFI 传递指针，不传递所有权

## 最小验证代码示例

### 最简单的 Rust Task（仅验证可行性）

```rust
// rust_tasks/src/lib.rs
#![no_std]

use esp_idf_sys::*;
use log::*;

#[no_mangle]
pub extern "C" fn rust_test_task() {
    info!("Hello from Rust!");
    
    loop {
        unsafe {
            vTaskDelay(pdMS_TO_TICKS(1000));
            info!("Rust task tick");
        }
    }
}
```

### C++ 调用

```cpp
// main/main.cpp
extern "C" {
    void rust_test_task();
}

void app_main() {
    xTaskCreate(
        [](void*) { rust_test_task(); },
        "RustTest",
        4096,
        nullptr,
        5,
        nullptr
    );
}
```

## 推荐验证顺序（混合架构）

### 阶段 1：最小验证（30 分钟）
1. ✅ 安装工具链
2. ✅ 创建最简单的 Rust 函数（只打印日志）
3. ✅ 从 C++ 调用 Rust 函数
4. ✅ 验证可以编译、链接、运行

### 阶段 2：业务逻辑验证（1-2 小时）
1. ✅ C 层：保持 GPIO 读取（不改动）
2. ✅ Rust 层：实现简单的状态机
3. ✅ 通过 FFI 传递数据（按钮状态）
4. ✅ 验证 Rust 可以处理业务逻辑

### 阶段 3：完整迁移（2-4 小时）
1. ✅ 将 input_task 的业务逻辑迁移到 Rust
2. ✅ C 层只负责硬件读取
3. ✅ Rust 层处理所有状态机和事件
4. ✅ 充分测试

## 混合架构示例：input_task

### 完整实现示例

#### C 层（`main/tasks/input_task.cpp`）

```cpp
extern "C" {
    void rust_process_button_state(bool btn1, bool btn2, uint32_t d1, uint32_t d2);
    void rust_handle_button_event(uint8_t btn_id, uint8_t event_type);
}

void input_task(void *pvParameters) {
    // GPIO 配置（保持原有，不变）
    gpio_set_direction(BUTTON1_PIN, GPIO_MODE_INPUT);
    gpio_set_direction(BUTTON2_PIN, GPIO_MODE_INPUT);
    
    Button button1(BUTTON1_PIN, ...);
    Button button2(BUTTON2_PIN, ...);
    
    while (true) {
        // C 层：硬件读取（保持原有逻辑）
        button1.update();
        button2.update();
        
        // 准备数据
        bool btn1_pressed = button1.isPressed();
        bool btn2_pressed = button2.isPressed();
        uint32_t btn1_duration = button1.getPressDuration();
        uint32_t btn2_duration = button2.getPressDuration();
        
        // 调用 Rust 处理业务逻辑
        rust_process_button_state(btn1_pressed, btn2_pressed,
                                  btn1_duration, btn2_duration);
        
        // 处理按钮事件（如果需要）
        if (button1.released()) {
            uint8_t event_type = button1.getEventType();
            rust_handle_button_event(1, event_type);
        }
        if (button2.released()) {
            uint8_t event_type = button2.getEventType();
            rust_handle_button_event(2, event_type);
        }
        
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}
```

#### Rust 层（`rust_tasks/src/lib.rs`）

```rust
use esp_idf_sys::*;
use log::*;

// 按钮事件类型
#[repr(C)]
pub enum ButtonEvent {
    ShortPress = 1,
    LongPress = 2,
    UltraLongPress = 3,
}

// 状态机（Rust 实现）
struct InputStateMachine {
    // 状态变量
    self_test_active: bool,
    btn1_press_start: Option<u32>,
    btn2_press_start: Option<u32>,
}

impl InputStateMachine {
    fn new() -> Self {
        Self {
            self_test_active: false,
            btn1_press_start: None,
            btn2_press_start: None,
        }
    }
    
    fn process_button_state(&mut self, 
                           btn1_pressed: bool, btn2_pressed: bool,
                           btn1_duration: u32, btn2_duration: u32) {
        // Rust 实现所有业务逻辑
        // - 状态机管理
        // - 事件检测
        // - 错误处理
        
        if btn1_pressed && btn2_pressed {
            self.handle_combo(btn1_duration, btn2_duration);
        } else if btn1_pressed {
            self.handle_button1(btn1_duration);
        } else if btn2_pressed {
            self.handle_button2(btn2_duration);
        }
    }
    
    fn handle_combo(&mut self, d1: u32, d2: u32) {
        // 组合按键逻辑（Rust 实现）
        if d1 > 10000 && d2 > 10000 {
            self.self_test_active = true;
            info!("Self-test activated");
        }
    }
    
    fn handle_button1(&mut self, duration: u32) {
        // 按钮1逻辑（Rust 实现）
        if duration > 10000 {
            info!("Button1 long press");
        }
    }
    
    fn handle_button2(&mut self, duration: u32) {
        // 按钮2逻辑（Rust 实现）
        if duration > 10000 {
            info!("Button2 long press");
        }
    }
}

// C 函数接口
static mut STATE_MACHINE: Option<InputStateMachine> = None;

#[no_mangle]
pub extern "C" fn rust_process_button_state(
    btn1_pressed: bool,
    btn2_pressed: bool,
    btn1_duration: u32,
    btn2_duration: u32,
) {
    unsafe {
        if STATE_MACHINE.is_none() {
            STATE_MACHINE = Some(InputStateMachine::new());
        }
        
        if let Some(ref mut sm) = STATE_MACHINE {
            sm.process_button_state(btn1_pressed, btn2_pressed,
                                    btn1_duration, btn2_duration);
        }
    }
}

// 调用 C 函数（发送事件到队列）
extern "C" {
    fn sendEvent2Queue(event: u8);
}

#[no_mangle]
pub extern "C" fn rust_handle_button_event(btn_id: u8, event_type: u8) {
    unsafe {
        // Rust 处理事件逻辑
        match event_type {
            1 => {
                info!("Button {} short press", btn_id);
                sendEvent2Queue(btn_id + 3); // 调用 C 函数
            }
            2 => {
                info!("Button {} long press", btn_id);
                sendEvent2Queue(btn_id + 3);
            }
            _ => {
                warn!("Unknown event type: {}", event_type);
            }
        }
    }
}
```

### 优势总结

✅ **不依赖 ESP-IDF HAL**：GPIO、UART 等继续用成熟的 C API  
✅ **利用 Rust 优势**：业务逻辑的内存安全、类型安全  
✅ **渐进式迁移**：可以逐步迁移业务逻辑  
✅ **风险最低**：硬件层保持稳定  
✅ **调试方便**：C 层调试工具成熟，Rust 层逻辑清晰

## 快速命令参考

```bash
# 设置环境
source $HOME/.export-esp.sh

# 构建 Rust
cd rust_tasks && cargo build --release

# 构建 ESP-IDF
cd .. && idf.py build

# 烧录
idf.py flash monitor
```

## 预期结果

如果验证成功，你应该看到：
1. Rust 库编译成功
2. ESP-IDF 项目链接成功
3. 设备启动后看到 "Hello from Rust!" 日志
4. 每秒看到 "Rust task tick" 日志

## 下一步

如果基本验证成功：
1. ✅ 评估 Rust 在 ESP-IDF 上的稳定性
2. ✅ 评估开发效率
3. ✅ 决定是否继续用 Rust 重写其他任务

如果验证失败：
1. ⚠️ 记录具体错误
2. ⚠️ 评估是否值得继续
3. ⚠️ 考虑替代方案

## 混合架构的优势总结

### ✅ 为什么选择混合架构？

1. **硬件层稳定**：
   - GPIO、UART、SPI 等用成熟的 C API
   - 不依赖 ESP-IDF HAL 的成熟度
   - 调试工具成熟（GDB、ESP-IDF monitor）

2. **业务逻辑安全**：
   - Rust 的内存安全保证
   - 类型安全减少 bug
   - 强制错误处理

3. **渐进式迁移**：
   - 可以先迁移简单的业务逻辑
   - 逐步增加 Rust 代码比例
   - 风险可控

4. **性能**：
   - C 层直接调用 ESP-IDF API（无开销）
   - Rust 层只处理业务逻辑（性能足够）
   - FFI 调用开销可忽略（不是热点路径）

### 📊 适用场景

| 任务 | C 层负责 | Rust 层负责 |
|------|---------|------------|
| **input_task** | GPIO 读取、硬件配置 | 状态机、事件处理 |
| **uart_task** | UART 读写、硬件配置 | 数据解析、协议处理 |
| **mqtt_task** | MQTT 客户端（ESP-IDF） | 消息处理、状态管理 |
| **ota_task** | Flash 操作、HTTP 客户端 | 验证逻辑、错误处理 |

## 资源链接

- ESP-IDF Rust 文档：https://esp-rs.github.io/book/
- ESP-IDF Rust 示例：https://github.com/esp-rs/esp-idf-template
- FreeRTOS Rust 绑定：https://github.com/lobaro/FreeRTOS-rust
- Rust FFI 指南：https://doc.rust-lang.org/nomicon/ffi.html

